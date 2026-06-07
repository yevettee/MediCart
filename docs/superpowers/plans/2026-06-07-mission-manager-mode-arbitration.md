# mission_manager 모드 중재 허브 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 또는 executing-plans 로 태스크별 실행. 체크박스(`- [ ]`)로 추적.

**Goal:** mission_manager 를 모드 중재 허브로 확장 — 우선순위 선점/복귀 + cmd_vel 게이트 + 외부 모드 노드 enable/disable·status 중재(경량 토픽 계약).

**Architecture:** 순수 결정로직(arbitrate·safety_gate)은 ROS 무관 모듈로 분리해 단위테스트. 외부 모드 노드와는 토픽 계약(`mode/<m>/set·status·cmd_vel`). 허브가 10Hz로 중재→전환 lifecycle→REACTIVE만 게이트 통과해 `/cmd_vel` 중계. 단순·평탄 구조(파일 2 신규 + 더미 1 + 테스트 1 + 노드 수정).

**Tech Stack:** ROS2 Humble, rclpy, std_msgs/String·geometry_msgs/Twist·sensor_msgs/LaserScan. 기존 mission_manager(MissionExecutor·system_commands) 보존.

**스펙:** `docs/superpowers/specs/2026-06-07-mission-manager-mode-arbitration-design.md`

## 파일 구조
- 생성 `medicart_ws/src/mission_manager/mission_manager/mode_arbitration.py` — 순수: MODE_PRIORITY·arbitrate·safety_gate
- 생성 `…/mission_manager/mode_arbiter.py` — ModeProxy(ROS 핸들) + ModeArbiter(중재·lifecycle·워치독)
- 생성 `…/mission_manager/stub_mode_node.py` — 계약 검증용 더미 REACTIVE 모드
- 수정 `…/mission_manager/mission_manager_node.py` — 허브 결선 + mission_request 2-lane 라우팅
- 수정 `…/mission_manager/setup.py` — stub_mode_node 엔트리
- 생성 `…/mission_manager/test/test_mode_arbitration.py` — 순수 단위테스트

---

### Task 1: 순수 중재 로직 + 단위테스트

**Files:** Create `mode_arbitration.py`, `test/test_mode_arbitration.py`

- [ ] **Step 1: 실패 테스트 작성** — `test/test_mode_arbitration.py`
```python
"""mode_arbitration 순수 로직 테스트(ROS 무관).
실행: cd mission_manager && python3 -m pytest test/test_mode_arbitration.py -v
"""
from mission_manager.mode_arbitration import (MODE_PRIORITY, arbitrate,
                                              safety_gate, SafetyParams)


def test_arbitrate_empty_is_idle():
    assert arbitrate(set()) == "idle"


def test_arbitrate_picks_highest_priority():
    assert arbitrate({"patrol", "round"}) == "round"
    assert arbitrate({"patrol", "guide", "intake"}) == "intake"
    assert arbitrate({"patrol"}) == "patrol"


def test_arbitrate_unknown_excluded():
    assert arbitrate({"bogus"}) == "idle"
    assert arbitrate({"bogus", "patrol"}) == "patrol"


def test_priority_order_spec():
    p = MODE_PRIORITY
    assert p["mapping"] > p["intake"] > p["round"] > p["errand"] > p["guide"] > p["patrol"] > p["idle"]


def test_safety_gate_blocks_forward_on_lidar():
    lin, ang, blocked = safety_gate(0.2, 0.3, 0.1, None)   # 정면 0.1m < 0.30
    assert blocked and lin == 0.0 and ang == 0.3           # 회전은 유지


def test_safety_gate_allows_clear_and_reverse():
    lin, ang, blocked = safety_gate(0.2, 0.0, 1.0, None)   # 트임
    assert not blocked and lin == 0.2
    lin, _, _ = safety_gate(-0.1, 0.0, 0.1, None)          # 막혀도 후진 허용
    assert lin == -0.1


def test_safety_gate_depth_block():
    lin, _, blocked = safety_gate(0.2, 0.0, None, 0.15)    # depth 0.15<0.20
    assert blocked and lin == 0.0
```

- [ ] **Step 2: 실패 확인**
Run: `cd /home/rokey/MediCart/medicart_ws/src/mission_manager && PYTHONPATH=. python3 -m pytest test/test_mode_arbitration.py -q`
Expected: FAIL (ModuleNotFoundError: mode_arbitration)

- [ ] **Step 3: 구현** — `mission_manager/mode_arbitration.py`
```python
"""mode_arbitration — mission_manager 모드 중재 순수 로직(ROS 무관).

우선순위 선점 중재 + 정면 안전 게이트. intel1 ward_robot/control.py 해당부 포팅.
부수효과 없음 → 로봇 없이 단위 테스트.
"""
from dataclasses import dataclass

# 높을수록 선점: mapping > 문진 > 회진 > 지시 > 가이드 > 순찰 > idle
MODE_PRIORITY = {
    "mapping": 6, "intake": 5, "round": 4,
    "errand": 3, "guide": 2, "patrol": 1, "idle": 0,
}


def arbitrate(active):
    """활성 요청 집합에서 최우선 모드. 비었거나 모두 미지원이면 'idle'."""
    best, best_p = "idle", -1
    for m in active:
        p = MODE_PRIORITY.get(m, -1)
        if p > best_p:
            best, best_p = m, p
    return best


@dataclass
class SafetyParams:
    lidar_stop: float = 0.30   # 정면 LiDAR 최소 여유(m)
    depth_stop: float = 0.20   # 정면 depth(m) 최소(있을 때)


def safety_gate(lin, ang, forward_clearance, front_depth_m, p=SafetyParams()):
    """정면이 막히면 전진(lin>0)만 0으로. 회전·후진 허용. 반환 (lin, ang, blocked)."""
    blocked = False
    if forward_clearance is not None and forward_clearance < p.lidar_stop:
        blocked = True
    if front_depth_m is not None and front_depth_m > 0.0 and front_depth_m < p.depth_stop:
        blocked = True
    if blocked and lin > 0.0:
        lin = 0.0
    return lin, ang, blocked
```

- [ ] **Step 4: 통과 확인**
Run: `cd /home/rokey/MediCart/medicart_ws/src/mission_manager && PYTHONPATH=. python3 -m pytest test/test_mode_arbitration.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: 커밋** (요청 시) `git add mission_manager/mode_arbitration.py test/test_mode_arbitration.py`

---

### Task 2: ModeProxy + ModeArbiter

**Files:** Create `mission_manager/mode_arbiter.py`

- [ ] **Step 1: 구현**
```python
"""mode_arbiter — 외부 모드 노드 중재(허브 핵심).

ModeProxy: 모드 노드 1개의 ROS 핸들(set 발행 / cmd_vel 후보·status 캐시).
ModeArbiter: 활성 요청 집합 + 우선순위 중재(mode_arbitration) + 선점/복귀 lifecycle
             + REACTIVE cmd_vel 게이트 + status 워치독(무응답 lost abort).
결정은 순수 mode_arbitration 에 위임, 여기서는 ROS 결선만.
"""
import json
import time

from geometry_msgs.msg import Twist
from std_msgs.msg import String

from mission_manager.mode_arbitration import arbitrate, safety_gate, SafetyParams

REACTIVE = "reactive"
NAV = "nav"


class ModeProxy:
    """외부 모드 노드 한 개 핸들."""

    def __init__(self, node, ns, name, actuation):
        self.name = name
        self.actuation = actuation
        self._set_pub = node.create_publisher(String, f"/{ns}/mode/{name}/set", 10)
        self._twist = None
        self._twist_t = 0.0
        self._status = None
        self._status_t = 0.0
        if actuation == REACTIVE:
            node.create_subscription(Twist, f"/{ns}/mode/{name}/cmd_vel", self._on_twist, 10)
        node.create_subscription(String, f"/{ns}/mode/{name}/status", self._on_status, 10)

    def set_active(self, active, params=None):
        msg = String()
        msg.data = json.dumps({"active": bool(active), "params": params or {}}, ensure_ascii=False)
        self._set_pub.publish(msg)

    def _on_twist(self, msg):
        self._twist = (msg.linear.x, msg.angular.z)
        self._twist_t = time.monotonic()

    def _on_status(self, msg):
        try:
            self._status = json.loads(msg.data)
        except (ValueError, TypeError):
            self._status = None
        self._status_t = time.monotonic()

    def latest_twist(self, now, max_age=0.5):
        if self._twist is None or (now - self._twist_t) > max_age:
            return None
        return self._twist

    def status_state(self):
        return (self._status or {}).get("state")

    def status_age(self, now):
        return (now - self._status_t) if self._status_t else float("inf")

    def got_status(self):
        return self._status_t > 0.0


class ModeArbiter:
    """우선순위 중재 + 선점/복귀 + cmd_vel 게이트 + 워치독."""

    def __init__(self, node, ns, registry, logger, status_timeout=3.0, safety=None):
        # registry: {mode_name: actuation('reactive'|'nav')}
        self._log = logger
        self._proxies = {n: ModeProxy(node, ns, n, a) for n, a in registry.items()}
        self._active = set()
        self._params = {}
        self._current = "idle"
        self._status_timeout = status_timeout
        self._safety = safety or SafetyParams()

    @property
    def current(self):
        return self._current

    @property
    def active(self):
        return sorted(self._active)

    def apply(self, action, mode=None, params=None):
        """모드 요청 반영. 반환 (ok, detail)."""
        if action == "clear":
            self._active.clear()
            return True, "cleared"
        if action == "stop":
            self._active.discard(mode)
            return True, f"stopped {mode}"
        if action == "start":
            if mode not in self._proxies:
                return False, f"unknown mode: {mode}"
            self._params[mode] = params or {}
            self._active.add(mode)
            return True, f"started {mode}"
        return False, f"unknown action: {action}"

    def tick(self, now, forward_clearance=None, front_depth_m=None):
        """제어주기 1회. 반환 (current_mode, twist|None).

        twist: REACTIVE 활성 시 (lin,ang)(게이트 통과), 그 외 None(NAV) / idle은 노드가 0.
        """
        # 워치독 + 완료 처리(현재 모드 기준)
        if self._current in self._proxies and self._current in self._active:
            px = self._proxies[self._current]
            st = px.status_state()
            if st in ("done", "failed"):
                self._log.info(f"[arbiter] {self._current} status={st} → active 제거")
                self._active.discard(self._current)
            elif px.got_status() and px.status_age(now) > self._status_timeout:
                self._log.warn(f"[arbiter] {self._current} status 무응답 {self._status_timeout}s → lost abort")
                self._active.discard(self._current)

        mode = arbitrate(self._active)

        if mode != self._current:
            if self._current in self._proxies:
                self._proxies[self._current].set_active(False)
            if mode in self._proxies:
                self._proxies[mode].set_active(True, self._params.get(mode))
            self._log.info(f"[arbiter] 모드 전환 {self._current} → {mode} (active={self.active})")
            self._current = mode

        twist = None
        px = self._proxies.get(mode)
        if px is not None and px.actuation == REACTIVE:
            cand = px.latest_twist(now)
            if cand is None:
                twist = (0.0, 0.0)
            else:
                lin, ang, _ = safety_gate(cand[0], cand[1], forward_clearance, front_depth_m, self._safety)
                twist = (lin, ang)
        return mode, twist
```

- [ ] **Step 2: import 확인**
Run: `cd /home/rokey/MediCart/medicart_ws && colcon build --packages-select mission_manager --symlink-install && source install/setup.bash && python3 -c "import mission_manager.mode_arbiter"`
Expected: import OK (빌드 성공)

- [ ] **Step 3: 커밋**(요청 시) `git add mission_manager/mode_arbiter.py`

---

### Task 3: mission_manager_node 결선(허브)

**Files:** Modify `mission_manager/mission_manager_node.py`

- [ ] **Step 1: import·상수 추가** — 파일 상단 import 블록에 추가
```python
import math
import time

from geometry_msgs.msg import Twist
from sensor_msgs.msg import LaserScan

from .mode_arbiter import ModeArbiter
from .system_commands import SYSTEM_ACTIONS
```
그리고 클래스 위에 상수:
```python
# 모드 레지스트리 — 이름: actuation. 외부 노드가 /{ns}/mode/<name>/* 계약 따름.
MODE_REGISTRY = {
    "round": "reactive",   # 회진/추종 (nurse_tracker)
    "patrol": "nav", "errand": "nav", "guide": "nav", "intake": "nav",
}
MODE_ACTIONS = ("start", "stop", "clear")
```

- [ ] **Step 2: `__init__` 끝에 허브 결선 추가** (기존 mission_executor 블록 다음)
```python
        # ── 모드 중재 허브 ───────────────────────────────────────────────
        self.declare_parameter("control_hz", 10.0)
        self.declare_parameter("front_cone_deg", 30.0)
        self._front_cone = math.radians(float(self.get_parameter("front_cone_deg").value))
        self._forward_clearance = None
        self._arbiter = ModeArbiter(self, ns, MODE_REGISTRY, self.get_logger())
        self._cmd_pub = self.create_publisher(Twist, f"/{ns}/cmd_vel", 10)
        self._robot_mode_pub = self.create_publisher(String, f"/{ns}/robot_mode", 10)
        self.create_subscription(LaserScan, f"/{ns}/scan", self._on_scan, 10)
        hz = float(self.get_parameter("control_hz").value)
        self.create_timer(1.0 / hz, self._control_tick)
        self.get_logger().info(f"[mission_manager] 모드 허브 결선: {list(MODE_REGISTRY)} @ {hz:.0f}Hz")
```

- [ ] **Step 3: mission_request 핸들러 2-lane 라우팅** — 기존 `_on_mission_request` 교체
```python
    def _on_mission_request(self, msg):
        try:
            req = json.loads(msg.data)
        except (ValueError, TypeError) as exc:
            self.get_logger().warn(
                '[mission_manager] mission_request 파싱 실패: {} raw={!r}'.format(exc, msg.data))
            return
        action = req.get("action")
        if action in SYSTEM_ACTIONS:                 # dock/undock/ros_restart/reboot/shutdown
            self._executor.handle(req)
        elif action in MODE_ACTIONS:                  # start/stop/clear (+mode)
            ok, detail = self._arbiter.apply(action, req.get("mode"), req.get("params"))
            self._publish_feedback({"id": req.get("id"),
                                    "status": "done" if ok else "failed",
                                    "detail": detail, "ts": int(time.time() * 1000)})
        else:
            self._publish_feedback({"id": req.get("id"), "status": "failed",
                                    "detail": f"unknown action: {action}", "ts": int(time.time() * 1000)})
```

- [ ] **Step 4: scan·control_tick 메서드 추가** (클래스 내, _publish_feedback 다음)
```python
    def _on_scan(self, scan):
        front = None
        a = scan.angle_min
        for r in scan.ranges:
            if math.isfinite(r) and r > 0.0 and abs(a) <= self._front_cone:
                front = r if front is None else min(front, r)
            a += scan.angle_increment
        self._forward_clearance = front

    def _control_tick(self):
        mode, twist = self._arbiter.tick(time.monotonic(), self._forward_clearance, None)
        if twist is not None:                 # REACTIVE 활성 → 게이트된 속도
            self._publish_cmd(twist[0], twist[1])
        elif mode == "idle":                  # 대기 → 정지
            self._publish_cmd(0.0, 0.0)
        # NAV 활성 → 미발행(Nav2 소유)
        m = String(); m.data = mode
        self._robot_mode_pub.publish(m)

    def _publish_cmd(self, lin, ang):
        tw = Twist(); tw.linear.x = float(lin); tw.angular.z = float(ang)
        self._cmd_pub.publish(tw)
```

- [ ] **Step 5: 빌드·import 확인**
Run: `cd /home/rokey/MediCart/medicart_ws && colcon build --packages-select mission_manager --symlink-install && source install/setup.bash && python3 -c "import mission_manager.mission_manager_node"`
Expected: 빌드 성공, import OK

- [ ] **Step 6: 커밋**(요청 시) `git add mission_manager/mission_manager_node.py`

---

### Task 4: 더미 모드 노드(계약 E2E용)

**Files:** Create `mission_manager/stub_mode_node.py`, Modify `setup.py`

- [ ] **Step 1: 구현** — `mission_manager/stub_mode_node.py`
```python
#!/usr/bin/env python3
"""stub_mode_node — 모드 계약 검증용 더미 REACTIVE 모드.

active 수신 시 작은 전진 twist + status running 발행, 비활성 시 무발행.
파라미터: namespace, mode_name, lin. (테스트 전용 — 실제 모드 노드 대체물)
"""
import json
import os

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import String


class StubMode(Node):
    def __init__(self):
        super().__init__("stub_mode_node")
        self.declare_parameter("namespace", os.environ.get("ROBOT_NAMESPACE", "robot6"))
        self.declare_parameter("mode_name", "round")
        self.declare_parameter("lin", 0.05)
        ns = str(self.get_parameter("namespace").value).strip("/")
        self.name = str(self.get_parameter("mode_name").value)
        self.lin = float(self.get_parameter("lin").value)
        self.active = False
        self._cmd = self.create_publisher(Twist, f"/{ns}/mode/{self.name}/cmd_vel", 10)
        self._st = self.create_publisher(String, f"/{ns}/mode/{self.name}/status", 10)
        self.create_subscription(String, f"/{ns}/mode/{self.name}/set", self._on_set, 10)
        self.create_timer(0.1, self._tick)
        self.get_logger().info(f"[stub_mode:{self.name}] ready (ns={ns})")

    def _on_set(self, msg):
        try:
            d = json.loads(msg.data)
        except (ValueError, TypeError):
            return
        self.active = bool(d.get("active"))
        self.get_logger().info(f"[stub_mode:{self.name}] active={self.active} params={d.get('params')}")

    def _tick(self):
        if not self.active:
            return
        t = Twist(); t.linear.x = self.lin; self._cmd.publish(t)
        s = String(); s.data = json.dumps({"state": "running", "detail": self.name, "ts": 0})
        self._st.publish(s)


def main(args=None):
    rclpy.init(args=args)
    node = StubMode()
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

- [ ] **Step 2: setup.py 엔트리 추가** — console_scripts 에 한 줄
```python
            'stub_mode_node = mission_manager.stub_mode_node:main',
```

- [ ] **Step 3: 빌드** `cd /home/rokey/MediCart/medicart_ws && colcon build --packages-select mission_manager --symlink-install`
Expected: 성공, `ros2 pkg executables mission_manager` 에 stub_mode_node 표시

- [ ] **Step 4: 커밋**(요청 시) `git add mission_manager/stub_mode_node.py setup.py`

---

### Task 5: E2E 검증 (로봇 미구동 — 로컬 노드)

- [ ] **Step 1: 단위테스트 재확인**
Run: `cd /home/rokey/MediCart/medicart_ws/src/mission_manager && PYTHONPATH=. python3 -m pytest test/test_mode_arbitration.py -q`
Expected: 7 passed

- [ ] **Step 2: 허브 + 더미 2개 기동**(각 터미널, ROS+overlay+robot.env source)
```bash
ros2 run mission_manager mission_manager_node
ros2 run mission_manager stub_mode_node --ros-args -p mode_name:=patrol -p lin:=0.03
ros2 run mission_manager stub_mode_node --ros-args -p mode_name:=round  -p lin:=0.06
```

- [ ] **Step 3: 선점/복귀·게이트·워치독 확인** (mission_request 직접 발행)
```bash
NS=robot6
# 저우선(patrol) 시작 → /cmd_vel 에 patrol 후보(lin 0.03)
ros2 topic pub --once /$NS/mission_request std_msgs/String "{data: '{\"action\":\"start\",\"mode\":\"patrol\"}'}"
ros2 topic echo /$NS/cmd_vel --once          # linear.x≈0.03
ros2 topic echo /$NS/robot_mode --once       # data: patrol
# 고우선(round) 시작 → 선점, /cmd_vel 이 round(0.06)로
ros2 topic pub --once /$NS/mission_request std_msgs/String "{data: '{\"action\":\"start\",\"mode\":\"round\"}'}"
ros2 topic echo /$NS/cmd_vel --once          # linear.x≈0.06, robot_mode=round
# round 중지 → patrol 복귀
ros2 topic pub --once /$NS/mission_request std_msgs/String "{data: '{\"action\":\"stop\",\"mode\":\"round\"}'}"
ros2 topic echo /$NS/robot_mode --once       # data: patrol
# round 더미 종료(Ctrl-C) 후 다시 start round → 3s 내 status 없으면 워치독 lost 로그
```
Expected: 선점 시 cmd_vel/robot_mode 전환, stop 시 복귀, 더미 죽으면 워치독 lost→idle/다음.

- [ ] **Step 4: 안전 게이트 확인**(선택) `/$NS/scan` 에 정면 근접 LaserScan 발행 시 round 활성이어도 `/cmd_vel` linear.x→0(회전·후진은 유지).

- [ ] **Step 5: 최종 커밋**(요청 시) — 전체 묶음.

---

## Self-Review
- 스펙 커버리지: 중재(arbitrate)·게이트(safety_gate)·계약(set/status/cmd_vel)·2-lane 라우팅·선점/복귀·워치독·robot_mode — 전부 태스크 매핑됨.
- 타입 일관: ModeProxy/ModeArbiter 메서드명, MODE_REGISTRY 키(round/patrol/…)와 arbitrate 우선순위 키 일치.
- 단순성: 신규 모듈 2(순수1+허브1) + 더미1 + 테스트1 + 노드수정. 과한 추상화 없음.
- 범위 밖: 실제 모드 노드(nurse_tracker 등)·웹 mission whitelist 모드 확장·depth 게이트 입력 = 후속.
