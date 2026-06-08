# nurse_tracker (round 모드) 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 또는 executing-plans. 체크박스 추적.

**Goal:** nurse_tracker 를 round(추종) REACTIVE 모드 노드로 구현 — intel1 perception/follow 포팅 + 허브 계약 I/O.

**Architecture:** intel1 `yolo_helper`·`perception(PersonTracker)`·`control.follow_cmd` 를 복사·적응(standalone). 순수 follow 로직은 단위테스트. tracker_node 가 모드 계약(set/cmd_vel/status) + TargetBBox + StartTracking 결선. Nav2 미사용(허브 safety_gate가 벽 정지).

**스펙:** `docs/superpowers/specs/2026-06-07-nurse-tracker-round-design.md`

## 파일 구조
- 생성 `nurse_tracker/nurse_tracker/yolo_helper.py` — intel1 복사(무변경)
- 생성 `nurse_tracker/nurse_tracker/perception.py` — intel1 복사 + 적응(토픽 파라미터·정면최근접 lock·conf 0.5)
- 생성 `nurse_tracker/nurse_tracker/follow_control.py` — intel1 follow_cmd/FollowParams 복사 + FollowFSM(신규·순수)
- 수정 `nurse_tracker/nurse_tracker/tracker_node.py` — 모드 계약 + 오케스트레이션
- 삭제 `yolo_detector.py`·`host_tracker.py`·`spatial_estimator.py`·`spatial_transform.py`(stub)
- 생성 `nurse_tracker/test/test_follow_control.py`
- 확인 `setup.py`(tracker_node 엔트리 기존), `package.xml`(deps 기존: rclpy/sensor_msgs/geometry_msgs/tf2/medi_interfaces)

---

### Task 1: follow_control.py (순수) + 단위테스트  [TDD]

**Files:** Create `follow_control.py`, `test/test_follow_control.py`

- [ ] **Step 1: 실패 테스트** — `test/test_follow_control.py`
```python
"""follow_control 순수 테스트. 실행: cd nurse_tracker && PYTHONPATH=. python3 -m pytest test/test_follow_control.py -q"""
from nurse_tracker.follow_control import FollowParams, follow_cmd, FollowFSM


class T:  # 스텁 target
    def __init__(self, distance, bearing, detected=True, stamp=0.0):
        self.distance = distance; self.bearing = bearing
        self.detected = detected; self.stamp = stamp


def test_follow_cmd_far_forward():
    lin, ang = follow_cmd(2.0, 0.0, FollowParams(desired_distance=0.8))
    assert lin > 0.0 and abs(ang) < 1e-6


def test_follow_cmd_hold_in_deadband():
    lin, _ = follow_cmd(0.85, 0.0, FollowParams(desired_distance=0.8, deadband=0.1))
    assert lin == 0.0


def test_follow_cmd_close_reverse():
    p = FollowParams(desired_distance=0.8, deadband=0.05, allow_reverse=True, max_reverse=0.06)
    lin, _ = follow_cmd(0.5, 0.0, p)
    assert lin < 0.0 and lin >= -0.06


def test_follow_cmd_bearing_turns():
    _, ang = follow_cmd(1.0, 0.5, FollowParams())   # +bearing(왼쪽) → +ang(CCW)
    assert ang > 0.0


def test_fsm_follow_then_lost_then_recover():
    fsm = FollowFSM(FollowParams(desired_distance=0.8), follow_timeout=1.0, lost_timeout=5.0)
    lin, ang, d = fsm.step(T(2.0, 0.0, stamp=10.0), now=10.0)
    assert d == "FOLLOW" and lin > 0.0
    lin, ang, d = fsm.step(None, now=11.5)           # 미검출 → 정지 대기
    assert (lin, ang) == (0.0, 0.0) and d == "LOST_WAIT"
    _, _, d = fsm.step(None, now=16.6)               # 5s 초과 → lost
    assert d == "lost"
    _, _, d = fsm.step(T(1.5, 0.0, stamp=20.0), now=20.0)  # 재등장 → 복귀
    assert d == "FOLLOW"
```

- [ ] **Step 2: 실패 확인** `cd nurse_tracker && PYTHONPATH=. python3 -m pytest test/test_follow_control.py -q` → FAIL(ModuleNotFound)

- [ ] **Step 3: 구현** — `follow_control.py`
```python
"""follow_control — 추종 제어 순수 로직(ROS 무관). intel1 control.follow_cmd 포팅 + 손실 FSM."""
from dataclasses import dataclass


@dataclass
class FollowParams:
    desired_distance: float = 0.8    # 유효 인지 거리(m)
    deadband: float = 0.10
    k_lin: float = 0.6
    k_ang: float = 1.5
    max_lin: float = 0.12
    max_ang: float = 0.6
    allow_reverse: bool = True        # 가까우면 후진(사용자 사양)
    max_reverse: float = 0.06


def follow_cmd(distance, bearing, p: FollowParams):
    """거리(m)·방위(rad, +=왼쪽) → (lin, ang). intel1 규약."""
    err = distance - p.desired_distance
    if abs(err) <= p.deadband:
        lin = 0.0
    elif err > 0:
        lin = min(p.k_lin * err, p.max_lin)
    else:
        lin = max(p.k_lin * err, -p.max_reverse) if p.allow_reverse else 0.0
    ang = max(-p.max_ang, min(p.k_ang * bearing, p.max_ang))
    return lin, ang


class FollowFSM:
    """FOLLOW ↔ LOST_WAIT. 손실 5s 초과 시 detail='lost'(모드 유지=HOLD)."""

    def __init__(self, params: FollowParams = None, follow_timeout=1.0, lost_timeout=5.0):
        self.p = params or FollowParams()
        self.follow_timeout = follow_timeout
        self.lost_timeout = lost_timeout
        self._lost_since = None

    def reset(self):
        self._lost_since = None

    def step(self, target, now):
        """target(거리·방위·detected·stamp) | None, now → (lin, ang, detail)."""
        fresh = (target is not None and getattr(target, "detected", False)
                 and target.distance > 0.0 and (now - target.stamp) <= self.follow_timeout)
        if fresh:
            self._lost_since = None
            lin, ang = follow_cmd(target.distance, target.bearing, self.p)
            return lin, ang, "FOLLOW"
        if self._lost_since is None:
            self._lost_since = now
        detail = "lost" if (now - self._lost_since) > self.lost_timeout else "LOST_WAIT"
        return 0.0, 0.0, detail
```

- [ ] **Step 4: 통과** `PYTHONPATH=. python3 -m pytest test/test_follow_control.py -q` → 5 passed

---

### Task 2: yolo_helper + perception 포팅

**Files:** Create `yolo_helper.py`(복사), `perception.py`(복사+적응)

- [ ] **Step 1: yolo_helper 복사**
`cp /home/rokey/rokey_ws/src/intel1/AMR1/src/ward_robot/ward_robot/yolo_helper.py /home/rokey/MediCart/medicart_ws/src/nurse_tracker/nurse_tracker/yolo_helper.py`

- [ ] **Step 2: perception 복사**
`cp /home/rokey/rokey_ws/src/intel1/AMR1/src/ward_robot/ward_robot/perception.py /home/rokey/MediCart/medicart_ws/src/nurse_tracker/nurse_tracker/perception.py`

- [ ] **Step 3: perception 적응 3가지**
  1. import `from .yolo_helper import YoloHelper` (그대로 — 같은 패키지).
  2. 토픽 파라미터화: 생성자에 `rgb_topic`, `depth_topic` 인자 추가(기본 `f"{p}/oakd/rgb/image_raw/compressed"`, `f"{p}/oakd/stereo/image_raw/compressedDepth"`). message_filters.Subscriber 에 사용.
  3. 초기 lock 을 **정면최근접**으로 — `_select_box` 의 재락온 부분을 max-area 대신 점수화. 박스에 cx·depth 필요하므로 시그니처를 `_select_box(self, boxes, depth, w)` 로 바꾸고 `_on_synced` 호출부 갱신:
```python
    def _select_box(self, boxes, depth, w):
        cands = [b for b in boxes if str(b[5]) in self._target_classes] if self._target_classes else list(boxes)
        if not cands:
            return None
        if self._locked_id != -1:
            for b in cands:
                if len(b) > 6 and int(b[6]) == self._locked_id:
                    return b
        # (재)락온: 정면최근접 — |cx-w/2| 작고 depth 작을수록 우선
        def score(b):
            cx = (b[0] + b[2]) / 2.0
            cy = int((b[1] + b[3]) / 2.0)
            d = self._sample_depth(depth, int(cx), cy) if depth is not None else -1.0
            front = abs(cx - w / 2.0) / (w / 2.0)            # 0(정면)~1
            prox = d if d > 0 else 99.0                       # 가까울수록 작음
            return front + 0.5 * prox                         # 작을수록 1위
        best = min(cands, key=score)
        if len(best) > 6 and int(best[6]) != -1:
            self._locked_id = int(best[6])
        return best
```
   그리고 `_on_synced` 에서 `box = self._select_box(boxes)` → `box = self._select_box(boxes, depth, w)`.
  4. conf 기본값 0.5 로(생성자 기본 `conf=0.5`).

- [ ] **Step 4: 빌드·import**
`cd /home/rokey/MediCart/medicart_ws && colcon build --packages-select nurse_tracker --symlink-install && source install/setup.bash && python3 -c "import nurse_tracker.perception, nurse_tracker.yolo_helper, nurse_tracker.follow_control; print('OK')"`
Expected: OK (ultralytics 없어도 yolo_helper graceful — import 자체는 됨; perception 은 cv2/numpy/message_filters 필요)

---

### Task 3: tracker_node.py (모드 계약 + 오케스트레이션)

**Files:** Modify `tracker_node.py`, 삭제 stub 4개

- [ ] **Step 1: stub 삭제**
`cd /home/rokey/MediCart/medicart_ws/src/nurse_tracker/nurse_tracker && rm -f yolo_detector.py host_tracker.py spatial_estimator.py spatial_transform.py`

- [ ] **Step 2: tracker_node.py 구현**
```python
#!/usr/bin/env python3
"""tracker_node — round(추종) 모드 노드. 허브 계약(set/cmd_vel/status) + perception + follow_control.

active 시 PersonTracker(perception) 의 target 을 FollowFSM 으로 추종 Twist 로 변환해
/{ns}/mode/round/cmd_vel 발행(허브가 safety_gate). status 하트비트 + TargetBBox 발행.
Nav2 미사용 — 벽 정지는 허브 LiDAR 게이트.
"""
import json
import os
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import String

from medi_interfaces.msg import TargetBBox
from medi_interfaces.srv import StartTracking

from .perception import PersonTracker
from .follow_control import FollowParams, FollowFSM

MODE = "round"


class TrackerNode(Node):
    def __init__(self):
        super().__init__("tracker_node")
        self.declare_parameter("namespace", os.environ.get("ROBOT_NAMESPACE", "robot6"))
        self.declare_parameter("model_path", "ward_model.pt")
        self.declare_parameter("conf", 0.5)
        self.declare_parameter("hfov_deg", 69.0)
        self.declare_parameter("desired_distance", 0.8)
        self.declare_parameter("lost_timeout", 5.0)
        self.declare_parameter("control_hz", 10.0)
        ns = str(self.get_parameter("namespace").value).strip("/")
        self._ns = ns

        self._perc = PersonTracker(
            self, ns,
            model_path=str(self.get_parameter("model_path").value),
            conf=float(self.get_parameter("conf").value),
            hfov_deg=float(self.get_parameter("hfov_deg").value))
        self._fsm = FollowFSM(
            FollowParams(desired_distance=float(self.get_parameter("desired_distance").value)),
            lost_timeout=float(self.get_parameter("lost_timeout").value))
        self._active = False

        self._cmd_pub = self.create_publisher(Twist, f"/{ns}/mode/{MODE}/cmd_vel", 10)
        self._status_pub = self.create_publisher(String, f"/{ns}/mode/{MODE}/status", 10)
        self._target_pub = self.create_publisher(TargetBBox, "/nurse_tracker/target", 10)
        self.create_subscription(String, f"/{ns}/mode/{MODE}/set", self._on_set, 10)
        self.create_service(StartTracking, f"/{ns}/start_tracking", self._on_start_tracking)

        hz = float(self.get_parameter("control_hz").value)
        self.create_timer(1.0 / hz, self._tick)
        self.get_logger().info(f"[tracker_node] round 모드 준비 ns={ns} @ {hz:.0f}Hz")

    def _on_set(self, msg):
        try:
            d = json.loads(msg.data)
        except (ValueError, TypeError):
            return
        active = bool(d.get("active"))
        if active and not self._active:
            self._fsm.reset()
            self._perc._locked_id = -1          # 활성화 시 재-lock(ACQUIRE)
        self._active = active
        self.get_logger().info(f"[tracker_node] active={active}")

    def _on_start_tracking(self, request, response):
        del request
        self._perc._locked_id = -1
        self._fsm.reset()
        response.success = True
        response.message = "re-lock requested"
        return response

    def _tick(self):
        if not self._active:
            return
        now = time.monotonic()
        target = self._perc.target
        lin, ang, detail = self._fsm.step(target, now)
        tw = Twist(); tw.linear.x = float(lin); tw.angular.z = float(ang)
        self._cmd_pub.publish(tw)
        s = String(); s.data = json.dumps(
            {"state": "running", "detail": detail, "ts": int(time.time() * 1000)})
        self._status_pub.publish(s)
        if target is not None and target.detected:
            tb = TargetBBox()
            tb.header.stamp = self.get_clock().now().to_msg()
            tb.tracking_id = int(target.track_id)
            tb.depth = float(target.distance)
            self._target_pub.publish(tb)


def main(args=None):
    rclpy.init(args=args)
    node = TrackerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 빌드·import**
`cd /home/rokey/MediCart/medicart_ws && colcon build --packages-select nurse_tracker --symlink-install && source install/setup.bash && python3 -c "import nurse_tracker.tracker_node; print('OK')"`
Expected: OK, `ros2 pkg executables nurse_tracker` → tracker_node

---

### Task 4: 통합 검증 (카메라 없이)

- [ ] **Step 1: 단위테스트** `cd nurse_tracker && PYTHONPATH=. python3 -m pytest test/test_follow_control.py -q` → 5 passed
- [ ] **Step 2: 허브+tracker 핸드셰이크**(격리 도메인, 카메라 없음 → target None):
```bash
# 터미널: mission_manager_node, tracker_node (ns testbot, 도메인 44)
# start round → tracker active, status 하트비트(detail=LOST_WAIT, 카메라 없으니), 허브가 cmd_vel(0) 중계
ros2 topic pub --once /testbot/mission_request std_msgs/String '{data: "{\"action\":\"start\",\"mode\":\"round\"}"}'
ros2 topic echo --once /testbot/mode/round/status   # state running, detail LOST_WAIT
ros2 topic echo --once /testbot/robot_mode          # round
```
Expected: round 활성·status 하트비트·robot_mode=round. (실추종은 OAK-D 스트림 있을 때 사용자 검증.)
- [ ] **Step 3: 커밋**(요청 시).

---

## Self-Review
- 포팅 충실: yolo_helper(무변경)·perception(적응3)·follow_cmd(복사). 재발명 최소.
- 사용자 사양 반영: 0.8m·후진·정면최근접 lock·정지대기 5s lost.
- 계약 일관: round=reactive(허브 레지스트리)·/mode/round/{set,cmd_vel,status}·TargetBBox.
- 범위: Phase A 추종 골격. ReID·depth게이트·시뮬 후속.
