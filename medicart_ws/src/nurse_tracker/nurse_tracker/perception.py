"""perception — OAK-D RGB-D + YOLO 기반 추종 대상 추적 + 정면 depth 측정.

검증된 RGB-D 탐지 파이프라인(RGB compressed + Depth compressedDepth를
ApproximateTimeSynchronizer로 동기화, 12B 헤더 스킵 후 PNG 디코딩, bbox 중심 depth
중앙값)을 그대로 재사용해, 회진보조용 '추종 대상' 하나와 '정면 중앙 depth'를 산출한다.

산출물(콜백에서 갱신, mode_manager가 폴링):
  - target: Target | None  — 추종할 대상(거리 m, 방위 rad, track_id)
  - front_depth_m: float   — 정면 중앙 depth 중앙값(m). 무효 시 -1.0 (안전 게이트용)

대상 선택: target_classes에 속하는 박스 중 가장 큰 것. 한번 잡으면 track_id를 락온해
같은 대상을 유지하고, 놓치면(lost_grace 프레임) 락 해제 후 재탐색한다.

방위 부호: bearing = (0.5 - cx/w) * hfov  → 대상이 왼쪽이면 +(control.follow_cmd 규약).
"""

import math
import time
from dataclasses import dataclass

import cv2
import numpy as np
import message_filters
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage

from .yolo_helper import YoloHelper   # ByteTrack 래퍼

_QOS_SENSOR = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE)
# compressed_depth_image_transport ConfigHeader: enum(4)+float(4)+float(4)=12B 후 PNG.
_CDEPTH_HEADER_BYTES = 12


@dataclass
class Target:
    detected: bool
    distance: float      # m
    bearing: float       # rad (+ = 화면 왼쪽)
    track_id: int
    area: float          # bbox 픽셀 면적
    stamp: float         # time.monotonic()


@dataclass
class Detection:
    """프레임 내 개별 탐지(순찰 모드 알림용 — 클래스 무관 전체)."""
    class_name: str
    confidence: float
    distance: float      # m, 무효 시 -1.0
    bearing: float       # rad (+ = 왼쪽)
    track_id: int


class PersonTracker:
    """RGB-D+YOLO로 추종 대상 1개와 정면 depth를 추적한다.

    node: rclpy Node (구독 생성 + 로깅용)
    """

    def __init__(self, node, ns, model_path="ward_model.pt", target_classes=("person",),
                 conf=0.5, hfov_deg=69.0, sync_slop=0.05, depth_radius=4,
                 rgb_topic=None, depth_topic=None):
        self._node = node
        self._log = node.get_logger()
        self._target_classes = set(target_classes)
        self._hfov = math.radians(float(hfov_deg))
        self._depth_r = int(depth_radius)
        self._yolo = YoloHelper(model_path, conf=conf, logger=self._log)

        self.target = None        # type: Target | None
        self.detections = []      # type: list[Detection] — 최근 프레임 전체 탐지
        self.front_depth_m = -1.0
        self._locked_id = -1      # 락온된 track_id
        self._lost_frames = 0
        self._lost_grace = 8      # 이 프레임 수 동안 미검출이면 락 해제

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
        self._log.info(f"[perception] target={self._target_classes} hfov={hfov_deg} (RGB-D 동기화)")

    def _decode_depth(self, depth_msg):
        try:
            png = np.frombuffer(bytes(depth_msg.data)[_CDEPTH_HEADER_BYTES:], np.uint8)
            return cv2.imdecode(png, cv2.IMREAD_UNCHANGED)   # 16UC1, mm
        except Exception as e:
            self._log.warn(f"depth decode: {e}")
            return None

    def _sample_depth(self, depth, cx, cy):
        """(cx,cy) 주변 반경 depth_r 내 유효 depth 중앙값(m). 없으면 -1.0."""
        r = self._depth_r
        h, w = depth.shape[:2]
        x0, y0 = max(0, cx - r), max(0, cy - r)
        x1, y1 = min(w, cx + r), min(h, cy + r)
        patch = depth[y0:y1, x0:x1].flatten().astype(float)
        patch = patch[(patch > 0) & (patch < 65535)]
        if len(patch) == 0:
            return -1.0
        return float(np.median(patch)) / 1000.0

    def _select_box(self, boxes, depth, w):
        """추종 대상 박스 선택. 락온 우선, 없으면 정면최근접(|cx-W/2|·depth 최소)으로 (재)락온.

        반환: 선택 박스 [x1,y1,x2,y2,conf,cls,track_id] 또는 None.
        """
        cands = [b for b in boxes if str(b[5]) in self._target_classes] if self._target_classes else list(boxes)
        if not cands:
            return None
        # 락온 ID가 후보에 있으면 그것을 유지
        if self._locked_id != -1:
            for b in cands:
                if len(b) > 6 and int(b[6]) == self._locked_id:
                    return b
        # (재)락온: 정면최근접 점수(작을수록 1위) — 정면도 + 0.5·근접도
        def _score(b):
            cx = (b[0] + b[2]) / 2.0
            cy = int((b[1] + b[3]) / 2.0)
            d = self._sample_depth(depth, int(cx), cy) if depth is not None else -1.0
            front = abs(cx - w / 2.0) / (w / 2.0)            # 0(정면)~1
            prox = d if d > 0 else 99.0                       # 가까울수록 작음
            return front + 0.5 * prox
        best = min(cands, key=_score)
        if len(best) > 6 and int(best[6]) != -1:
            self._locked_id = int(best[6])
        return best

    def _on_synced(self, rgb_msg, depth_msg):
        try:
            img = cv2.imdecode(np.frombuffer(rgb_msg.data, np.uint8), cv2.IMREAD_COLOR)
        except Exception as e:
            self._log.warn(f"rgb decode: {e}")
            return
        if img is None:
            return
        depth = self._decode_depth(depth_msg)
        h, w = img.shape[:2]

        # 정면 중앙 depth(안전 게이트용) — 항상 갱신
        if depth is not None:
            self.front_depth_m = self._sample_depth(depth, w // 2, h // 2)
        else:
            self.front_depth_m = -1.0

        boxes = self._yolo.detect(img)

        # 전체 탐지 목록 갱신(순찰 알림용 — 클래스 무관)
        dets = []
        for b in boxes:
            bx, by = int((b[0] + b[2]) / 2), int((b[1] + b[3]) / 2)
            bd = self._sample_depth(depth, bx, by) if depth is not None else -1.0
            dets.append(Detection(
                class_name=str(b[5]), confidence=float(b[4]),
                distance=bd, bearing=(0.5 - bx / w) * self._hfov,
                track_id=int(b[6]) if len(b) > 6 else -1))
        self.detections = dets

        box = self._select_box(boxes, depth, w)

        if box is None:
            self._lost_frames += 1
            if self._lost_frames >= self._lost_grace:
                self._locked_id = -1
                self.target = None
            return

        self._lost_frames = 0
        x1, y1, x2, y2 = box[:4]
        cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
        dist = self._sample_depth(depth, cx, cy) if depth is not None else -1.0
        bearing = (0.5 - cx / w) * self._hfov          # +가 왼쪽
        self.target = Target(
            detected=(dist > 0.0),
            distance=dist,
            bearing=bearing,
            track_id=int(box[6]) if len(box) > 6 else -1,
            area=float((x2 - x1) * (y2 - y1)),
            stamp=time.monotonic(),
        )
