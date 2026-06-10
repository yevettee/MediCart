"""perception — OAK-D RGB-D + YOLO 기반 추종 대상 추적.

depth → robot frame 좌표 변환 방식:
  1. YOLO bbox 중심 픽셀 (u, v) + depth → 카메라 광학 프레임 3D 좌표
  2. tf2 로 base_link 프레임으로 변환
  3. (x_robot, y_robot): 로봇 기준 전방/좌우 미터 좌표 → follow_control 에 전달

거리 추정은 bbox 영역 내부 depth 중 가까운 상위 near_percentile 비율의 중앙값을
사용한다 — 단일 점보다 자세 기울어짐·배경 혼입에 강건하다.
"""

import math
import time
from dataclasses import dataclass

import cv2
import numpy as np
import message_filters
import rclpy.duration
import rclpy.time
import tf2_ros
import tf2_geometry_msgs          # PointStamped 변환 등록 (import 자체가 side-effect)
from geometry_msgs.msg import PointStamped
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CameraInfo, CompressedImage, Image

from .yolo_helper import YoloHelper

# depth=1: 최신 프레임만 유지, 처리 못한 이전 프레임 즉시 폐기 → stale 방지
_QOS_SENSOR = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE)
_CDEPTH_HEADER_BYTES = 12   # compressed_depth_image_transport ConfigHeader


@dataclass
class Target:
    detected: bool
    distance: float    # m (depth 측정값)
    x_robot: float     # m, base_link 기준 전방(+앞)
    y_robot: float     # m, base_link 기준 좌우(+왼쪽)
    track_id: int
    stamp: float       # time.monotonic()


class PersonTracker:
    """RGB-D + YOLO → base_link 프레임 좌표로 추종 대상 추적."""

    def __init__(self, node, ns, model_path="ward_model.pt", target_classes=("nurse",),
                 conf=0.5, sync_slop=0.05, near_percentile=0.30,
                 infer_hz=10.0, rgb_topic=None, depth_topic=None):
        self._node = node
        self._ns = ns
        self._log = node.get_logger()
        self._target_classes = set(target_classes)
        self._near_pct = float(near_percentile)
        self._yolo = YoloHelper(model_path, conf=conf, logger=self._log)

        self.target = None        # type: Target | None
        self._active = False
        self._infer_interval = 1.0 / max(1.0, float(infer_hz))  # YOLO 추론 최소 간격(s)
        self._last_infer_t = 0.0

        # 카메라 내부 파라미터 (camera_info 수신 후 설정)
        self._fx = self._fy = self._cx = self._cy = None
        self._camera_frame = None

        # TF2
        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, node)

        # 디버그 시각화
        self._annotated_pub = node.create_publisher(
            Image, "/nurse_tracker/annotated_image", 5)

        p = f"/{ns}"
        rgb_topic   = rgb_topic   or f"{p}/oakd/rgb/image_raw/compressed"
        depth_topic = depth_topic or f"{p}/oakd/stereo/image_raw/compressedDepth"
        cam_info_topic = f"{p}/oakd/rgb/camera_info"

        node.create_subscription(CameraInfo, cam_info_topic, self._on_camera_info, _QOS_SENSOR)

        rgb_sub   = message_filters.Subscriber(node, CompressedImage, rgb_topic,   qos_profile=_QOS_SENSOR)
        depth_sub = message_filters.Subscriber(node, CompressedImage, depth_topic, qos_profile=_QOS_SENSOR)
        # queue_size=2: 동기화에 필요한 최소 버퍼만 유지 (30fps 기준 33ms 간격, slop=50ms)
        self._sync = message_filters.ApproximateTimeSynchronizer(
            [rgb_sub, depth_sub], queue_size=2, slop=float(sync_slop))
        self._sync.registerCallback(self._on_synced)
        self._log.info(f"[perception] target={self._target_classes} (depth→robot_frame 모드)")

    # ── 카메라 내부 파라미터 ─────────────────────────────────────────────
    def _on_camera_info(self, msg: CameraInfo):
        if self._fx is not None:
            return
        k = msg.k
        self._fx, self._fy = k[0], k[4]
        self._cx, self._cy = k[2], k[5]
        self._camera_frame = msg.header.frame_id
        self._log.info(
            f"[perception] camera_info 수신: fx={self._fx:.1f} fy={self._fy:.1f} "
            f"cx={self._cx:.1f} cy={self._cy:.1f} frame={self._camera_frame}")

    # ── depth → base_link 좌표 변환 ──────────────────────────────────────
    def _to_robot_frame(self, u: float, v: float, depth_m: float):
        """픽셀 (u, v) + depth → base_link 프레임 (x, y) m.

        TF 실패 시 카메라 광학 프레임 기준 근사값으로 폴백:
          카메라 광학(z=전방, x=우, y=하) → base_link(x=전방, y=좌)
          x_base ≈ z_cam = depth_m
          y_base ≈ -x_cam = -(u - cx) * depth / fx
        """
        if self._fx is None:
            # camera_info 미수신 — 픽셀 기반 근사
            return depth_m, 0.0

        x_cam = (u - self._cx) * depth_m / self._fx
        y_cam = (v - self._cy) * depth_m / self._fy
        z_cam = depth_m

        if self._camera_frame is not None:
            pt = PointStamped()
            pt.header.frame_id = self._camera_frame
            pt.header.stamp    = rclpy.time.Time().to_msg()  # 최신 TF 사용
            pt.point.x, pt.point.y, pt.point.z = float(x_cam), float(y_cam), float(z_cam)
            base_frame = f"{self._ns}/base_link"
            try:
                pt_base = self._tf_buffer.transform(
                    pt, base_frame,
                    timeout=rclpy.duration.Duration(seconds=0.05))
                return pt_base.point.x, pt_base.point.y
            except Exception:
                pass  # TF 미준비 → 폴백

        # 폴백: 카메라 광학 프레임 근사 (수평 장착 가정)
        return z_cam, -x_cam

    # ── depth 처리 ───────────────────────────────────────────────────────
    def _decode_depth(self, depth_msg):
        try:
            png = np.frombuffer(bytes(depth_msg.data)[_CDEPTH_HEADER_BYTES:], np.uint8)
            return cv2.imdecode(png, cv2.IMREAD_UNCHANGED)   # 16UC1, mm
        except Exception as e:
            self._log.warn(f"depth decode: {e}")
            return None

    def _sample_box_depth(self, depth, x1, y1, x2, y2):
        h, w = depth.shape[:2]
        x0, y0 = max(0, int(x1)), max(0, int(y1))
        x1c, y1c = min(w, int(x2)), min(h, int(y2))
        region = depth[y0:y1c, x0:x1c].flatten().astype(float)
        region = region[(region > 0) & (region < 65535)]
        if len(region) == 0:
            return -1.0
        region.sort()
        n = max(1, int(len(region) * self._near_pct))
        return float(np.median(region[:n])) / 1000.0

    # ── 시각화 ──────────────────────────────────────────────────────────
    def _publish_annotated(self, img, box, dist=-1.0, x_r=0.0, y_r=0.0):
        if self._annotated_pub.get_subscription_count() == 0:
            return
        vis = img.copy()
        if box is not None:
            x1, y1, x2, y2 = (int(v) for v in box[:4])
            label = f"{box[5]} {box[4]:.2f}"
            if dist > 0.0:
                label += f" d={dist:.2f}m x={x_r:.2f} y={y_r:.2f}"
            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(vis, label, (x1, max(0, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        msg = Image()
        msg.height, msg.width = vis.shape[:2]
        msg.encoding = "bgr8"
        msg.is_bigendian = 0
        msg.step = vis.shape[1] * 3
        msg.data = vis.tobytes()
        self._annotated_pub.publish(msg)

    # ── 박스 선택 ────────────────────────────────────────────────────────
    def _select_box(self, boxes):
        cands = [b for b in boxes if str(b[5]) in self._target_classes] if self._target_classes else list(boxes)
        if not cands:
            return None
        return max(cands, key=lambda b: b[4])

    # ── active 제어 ──────────────────────────────────────────────────────
    def set_active(self, active: bool):
        self._active = active
        if not active:
            self.target = None

    # ── 메인 콜백 ────────────────────────────────────────────────────────
    def _on_synced(self, rgb_msg, depth_msg):
        if not self._active:
            return
        now = time.monotonic()
        if now - self._last_infer_t < self._infer_interval:
            return  # 이번 프레임 건너뜀 — control_hz에 맞춰 YOLO 추론 횟수 제한
        self._last_infer_t = now
        try:
            img = cv2.imdecode(np.frombuffer(rgb_msg.data, np.uint8), cv2.IMREAD_COLOR)
        except Exception as e:
            self._log.warn(f"rgb decode: {e}")
            return
        if img is None:
            return

        depth = self._decode_depth(depth_msg)
        boxes = self._yolo.detect(img)
        box   = self._select_box(boxes)

        if box is None:
            self.target = None
            self._publish_annotated(img, None)
            return

        x1, y1, x2, y2 = box[:4]
        u_center = (x1 + x2) / 2.0
        v_center = (y1 + y2) / 2.0
        dist = self._sample_box_depth(depth, x1, y1, x2, y2) if depth is not None else -1.0

        if dist > 0.0:
            x_robot, y_robot = self._to_robot_frame(u_center, v_center, dist)
        else:
            x_robot, y_robot = 0.0, 0.0

        self._publish_annotated(img, box, dist, x_robot, y_robot)
        self.target = Target(
            detected=(dist > 0.0),
            distance=dist,
            x_robot=x_robot,
            y_robot=y_robot,
            track_id=int(box[6]) if len(box) > 6 else -1,
            stamp=time.monotonic(),
        )
