"""perception — OAK-D RGB-D + YOLO 기반 추종 대상 추적.

검증된 RGB-D 탐지 파이프라인(RGB compressed + Depth compressedDepth를
ApproximateTimeSynchronizer로 동기화, 12B 헤더 스킵 후 PNG 디코딩)을 그대로
재사용해, 회진보조용 '추종 대상' 하나를 산출한다.

대상 선택·중심오차 산출은 minicar_navigator.oakd_approach_node 알고리즘을 포팅:
  - 대상 선택: target_classes에 속하는 박스 중 confidence 최고값 1개를 매 프레임
    재선정한다(_find_best_target 포팅 — 락온 없음).
  - error_x = (cx - w/2) / (w/2)  → bbox 중심이 화면 오른쪽이면 +(follow_control 규약).

거리 추정은 bbox 기하학적 중심 한 점이 아니라 bbox 영역 내부 depth 중
가장 가까운(값이 작은) 상위 near_percentile 비율의 중앙값을 사용한다 — 대상의
자세가 기울어져 중심점이 빈 공간/배경에 걸리는 경우에도 강건하다.

산출물(콜백에서 갱신, tracker_node가 폴링):
  - target: Target | None  — 추종할 대상(거리 m, 중심오차 error_x, track_id)

디버그 시각화:
  - /nurse_tracker/annotated_image (sensor_msgs/Image, bgr8) — 선택된 박스를
    그린 영상. 구독자가 있을 때만 인코딩·발행한다(rqt_image_view 등으로 확인).
    주의: CompressedImage로 발행하면 image_transport가 토픽명을
    "<base>/<transport>"로 해석해 transport 플러그인 로딩을 시도하다 크래시
    난다(이름에 "compressed"가 없어도 마지막 세그먼트를 transport로 오인함).
    raw Image로 발행하면 image_transport가 "raw" 트랜스포트로 토픽명 그대로
    직접 구독하므로 문제없다.
"""

import time
from dataclasses import dataclass

import cv2
import numpy as np
import message_filters
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage, Image

from .yolo_helper import YoloHelper   # ByteTrack 래퍼(track_id는 상태 보고용으로만 사용)

_QOS_SENSOR = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE)
# compressed_depth_image_transport ConfigHeader: enum(4)+float(4)+float(4)=12B 후 PNG.
_CDEPTH_HEADER_BYTES = 12


@dataclass
class Target:
    detected: bool
    distance: float      # m
    error_x: float       # -1~+1 (+ = 화면 오른쪽), bbox 중심 기준 (oakd_approach_node 규약)
    track_id: int
    stamp: float         # time.monotonic()


class PersonTracker:
    """RGB-D+YOLO로 추종 대상 1개를 추적한다.

    대상 선택은 oakd_approach_node._find_best_target 포팅: target_classes 중
    confidence 최고값 박스 1개를 매 프레임 재선정한다(락온 없음 — 가장 확신도 높은
    탐지를 그대로 따라간다).

    node: rclpy Node (구독 생성 + 로깅용)
    """

    def __init__(self, node, ns, model_path="ward_model.pt", target_classes=("nurse",),
                 conf=0.5, sync_slop=0.05, near_percentile=0.30,
                 rgb_topic=None, depth_topic=None):
        self._node = node
        self._log = node.get_logger()
        self._target_classes = set(target_classes)
        self._near_pct = float(near_percentile)
        self._yolo = YoloHelper(model_path, conf=conf, logger=self._log)

        self.target = None        # type: Target | None
        # 디버그용 — 선택된 박스를 그린 영상(rqt_image_view 등으로 확인). 구독자 없으면 인코딩 생략.
        self._annotated_pub = node.create_publisher(
            Image, "/nurse_tracker/annotated_image", 5)

        p = f"/{ns}"
        rgb_topic = rgb_topic or f"{p}/oakd/rgb/image_raw/compressed"
        depth_topic = depth_topic or f"{p}/oakd/stereo/image_raw/compressedDepth"
        rgb_sub = message_filters.Subscriber(
            node, CompressedImage, rgb_topic, qos_profile=_QOS_SENSOR)
        depth_sub = message_filters.Subscriber(
            node, CompressedImage, depth_topic, qos_profile=_QOS_SENSOR)
        self._sync = message_filters.ApproximateTimeSynchronizer(
            [rgb_sub, depth_sub], queue_size=5, slop=float(sync_slop))
        self._sync.registerCallback(self._on_synced)
        self._log.info(f"[perception] target={self._target_classes} (RGB-D 동기화)")

    def _decode_depth(self, depth_msg):
        try:
            png = np.frombuffer(bytes(depth_msg.data)[_CDEPTH_HEADER_BYTES:], np.uint8)
            return cv2.imdecode(png, cv2.IMREAD_UNCHANGED)   # 16UC1, mm
        except Exception as e:
            self._log.warn(f"depth decode: {e}")
            return None

    def _sample_box_depth(self, depth, x1, y1, x2, y2):
        """bbox 영역 내부 depth 중 가장 가까운(값이 작은) 상위 near_percentile 비율의
        중앙값(m). 없으면 -1.0.

        bbox 기하학적 중심 한 점보다 자세 기울어짐·박스 모서리 배경 혼입에 강건하다 —
        YOLO가 이미 이 영역을 타깃으로 판별했으므로, 그 안에서 가장 가까운 depth
        덩어리는 대개 배경이 아니라 타깃 본체다.
        """
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

    def _publish_annotated(self, img, box, dist=-1.0):
        """선택된 박스를 그린 영상을 발행한다(디버그/시각화용). 구독자 없으면 생략."""
        if self._annotated_pub.get_subscription_count() == 0:
            return
        vis = img.copy()
        if box is not None:
            x1, y1, x2, y2 = (int(v) for v in box[:4])
            label = f"{box[5]} {box[4]:.2f}"
            if dist > 0.0:
                label += f" {dist:.2f}m"
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

    def _select_box(self, boxes):
        """추종 대상 박스 선택 — oakd_approach_node._find_best_target 포팅.

        target_classes에 속한 박스 중 confidence가 가장 높은 1개를 매 프레임
        재선정한다(락온 없음). 반환: [x1,y1,x2,y2,conf,cls,track_id] 또는 None.
        """
        cands = [b for b in boxes if str(b[5]) in self._target_classes] if self._target_classes else list(boxes)
        if not cands:
            return None
        return max(cands, key=lambda b: b[4])

    def _on_synced(self, rgb_msg, depth_msg):
        try:
            img = cv2.imdecode(np.frombuffer(rgb_msg.data, np.uint8), cv2.IMREAD_COLOR)
        except Exception as e:
            self._log.warn(f"rgb decode: {e}")
            return
        if img is None:
            return
        depth = self._decode_depth(depth_msg)
        w = img.shape[1]

        boxes = self._yolo.detect(img)
        box = self._select_box(boxes)

        if box is None:
            self.target = None
            self._publish_annotated(img, None)
            return

        x1, y1, x2, y2 = box[:4]
        cx = int((x1 + x2) / 2)
        dist = self._sample_box_depth(depth, x1, y1, x2, y2) if depth is not None else -1.0
        self._publish_annotated(img, box, dist)
        error_x = (2.0 * cx / w) - 1.0          # -1(왼쪽 끝)~+1(오른쪽 끝), oakd_approach_node 규약
        self.target = Target(
            detected=(dist > 0.0),
            distance=dist,
            error_x=error_x,
            track_id=int(box[6]) if len(box) > 6 else -1,
            stamp=time.monotonic(),
        )
