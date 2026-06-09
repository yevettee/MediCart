# WEB↔dashboard goto 통합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** dashboard에서 검증된 "침상/home 이동(dock-aware)"을 web→RTDB `mission_pool`→db_bridge→mission_manager(NavExecutor)→Nav2 경로로 실행 가능하게 한다.

**Architecture:** 웹이 목적지 좌표 `{x,y,yaw,dock_after}`를 RTDB `mission_pool`에 push → `db_node`가 FIFO로 `/{ns}/mission_request`(action=goto) 발행 → `mission_manager`가 goto 레인에서 `NavExecutor`(dashboard Nav2+Dock/Undock 이식)로 실행하며 ModeArbiter `goto`(nav, 우선순위 7)로 REACTIVE 선점·cmd_vel 양보. pose 출처는 RTDB `targets`(웹이 읽어 좌표 전송), 맵 클릭은 map meta로 픽셀→월드 변환.

**Tech Stack:** ROS2 Humble(rclpy, nav2_msgs/NavigateToPose, irobot_create_msgs/Dock·Undock·DockStatus), Firebase RTDB(firebase-admin), Flask, Next.js(App Router, canvas).

**스펙:** `docs/superpowers/specs/2026-06-08-web-goto-integration-design.md` (6602c36)

**규칙:** ROS 노드 직접 구동 금지(로봇 주행) — 빌드·단위테스트·import 검증만 하고, 실주행 통합검증은 사용자에게 명령·순서를 제공. 서버(Flask/Next) 직접 실행은 가능하나 본 계획은 단위테스트와 빌드로 검증.

---

## File Structure

**로봇 (medicart_ws)**
- `db_bridge/db_bridge/mission_queue.py` (수정) — `ACTION_TIMEOUTS`에 `goto` 워치독 타임아웃.
- `mission_manager/mission_manager/mode_arbitration.py` (수정) — `MODE_PRIORITY`에 `goto:7`.
- `mission_manager/mission_manager/nav_executor.py` (신규) — `pose_stamped_fields`(순수) + `NavExecutor`(Nav2+dock-aware).
- `mission_manager/mission_manager/mission_manager_node.py` (수정) — goto 라우팅 레인 + arbiter `goto`(nav) 등록.
- `mission_manager/package.xml` (수정) — `nav2_msgs`, `irobot_create_msgs` 의존성.

**웹 (web)**
- `web/backend/fb_read.py` (수정) — goto 페이로드 검증 + `targets_seed`/`get_targets`/`seed_targets`.
- `web/backend/app.py` (수정) — `GET /api/targets` + 기동 시 시드.
- `web/frontend/lib/api.ts` (수정) — `pushMission` params 인자 + `getTargets`/`GotoTarget`.
- `web/frontend/app/control/page.tsx` (수정) — "이동" 섹션(프리셋 버튼).
- `web/frontend/components/MapView.tsx` (수정) — 로봇 선택 + 캔버스 클릭 이동.

**테스트**
- `db_bridge/test/test_mission_queue.py`, `mission_manager/test/test_mode_arbitration.py`,
  `mission_manager/test/test_nav_executor.py`(신규), `web/backend/test/test_fb_read.py`.

---

### Task 1: db_node goto 워치독 타임아웃

`db_node`는 `ACTION_TIMEOUTS.get(action, DEFAULT_TIMEOUT)`로 명령별 워치독을 건다. nav는 길어서 goto 전용 긴 타임아웃이 필요하다.

**Files:**
- Modify: `medicart_ws/src/db_bridge/db_bridge/mission_queue.py`
- Test: `medicart_ws/src/db_bridge/test/test_mission_queue.py`

- [ ] **Step 1: 실패 테스트 작성** — `test_mission_queue.py` 끝에 추가:

```python
def test_goto_has_long_watchdog_timeout():
    from db_bridge.mission_queue import ACTION_TIMEOUTS, DEFAULT_TIMEOUT
    assert ACTION_TIMEOUTS.get("goto", DEFAULT_TIMEOUT) >= 180.0
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ~/MediCart/medicart_ws/src/db_bridge && python3 -m pytest test/test_mission_queue.py::test_goto_has_long_watchdog_timeout -v`
Expected: FAIL (goto 키 없음 → DEFAULT_TIMEOUT(<180) 반환)

- [ ] **Step 3: 구현** — `mission_queue.py`의 `ACTION_TIMEOUTS` 딕셔너리에 항목 추가:

```python
    "goto": 300.0,        # Nav2 이동은 길다 — 긴 워치독
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd ~/MediCart/medicart_ws/src/db_bridge && python3 -m pytest test/test_mission_queue.py -v`
Expected: PASS (전체)

- [ ] **Step 5: 커밋**

```bash
cd ~/MediCart && git add medicart_ws/src/db_bridge/db_bridge/mission_queue.py medicart_ws/src/db_bridge/test/test_mission_queue.py
git commit -m "feat(db_bridge): goto 워치독 타임아웃(300s) 추가"
```

---

### Task 2: goto 모드 우선순위

ModeArbiter는 `mode_arbitration.MODE_PRIORITY`로 선점을 결정한다. 운영자 goto는 모든 자율모드를 선점해야 하므로 최상위(7).

**Files:**
- Modify: `medicart_ws/src/mission_manager/mission_manager/mode_arbitration.py:9-12`
- Test: `medicart_ws/src/mission_manager/test/test_mode_arbitration.py`

- [ ] **Step 1: 실패 테스트 작성** — `test_mode_arbitration.py`에 추가:

```python
def test_goto_preempts_all_autonomous_modes():
    from mission_manager.mode_arbitration import arbitrate, MODE_PRIORITY
    assert MODE_PRIORITY["goto"] > MODE_PRIORITY["mapping"]
    assert arbitrate({"patrol", "round", "mapping", "goto"}) == "goto"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ~/MediCart/medicart_ws/src/mission_manager && python3 -m pytest test/test_mode_arbitration.py::test_goto_preempts_all_autonomous_modes -v`
Expected: FAIL (KeyError: 'goto')

- [ ] **Step 3: 구현** — `MODE_PRIORITY` 딕셔너리를 다음으로 교체:

```python
# 높을수록 선점: goto(운영자) > mapping > 문진 > 회진 > 지시 > 가이드 > 순찰 > idle
MODE_PRIORITY = {
    "goto": 7,
    "mapping": 6, "intake": 5, "round": 4,
    "errand": 3, "guide": 2, "patrol": 1, "idle": 0,
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd ~/MediCart/medicart_ws/src/mission_manager && python3 -m pytest test/test_mode_arbitration.py -v`
Expected: PASS (전체)

- [ ] **Step 5: 커밋**

```bash
cd ~/MediCart && git add medicart_ws/src/mission_manager/mission_manager/mode_arbitration.py medicart_ws/src/mission_manager/test/test_mode_arbitration.py
git commit -m "feat(mission_manager): goto 모드 우선순위(7, 최상위) 추가"
```

---

### Task 3: nav_executor pose 헬퍼(순수)

`NavExecutor`의 좌표→PoseStamped 변환 중 순수 부분(yaw→쿼터니언, map 프레임)을 먼저 TDD로 만든다.

**Files:**
- Create: `medicart_ws/src/mission_manager/mission_manager/nav_executor.py`
- Test: `medicart_ws/src/mission_manager/test/test_nav_executor.py`

- [ ] **Step 1: 실패 테스트 작성** — 신규 `test/test_nav_executor.py`:

```python
import math


def test_pose_stamped_fields_zero_yaw():
    from mission_manager.nav_executor import pose_stamped_fields
    f = pose_stamped_fields(1.5, -2.0, 0.0)
    assert f["frame_id"] == "map"
    assert f["x"] == 1.5 and f["y"] == -2.0
    assert abs(f["qz"] - 0.0) < 1e-9 and abs(f["qw"] - 1.0) < 1e-9


def test_pose_stamped_fields_half_pi_yaw():
    from mission_manager.nav_executor import pose_stamped_fields
    f = pose_stamped_fields(0.0, 0.0, math.pi / 2)
    assert abs(f["qz"] - math.sin(math.pi / 4)) < 1e-9
    assert abs(f["qw"] - math.cos(math.pi / 4)) < 1e-9
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ~/MediCart/medicart_ws/src/mission_manager && python3 -m pytest test/test_nav_executor.py -v`
Expected: FAIL (ModuleNotFoundError: nav_executor)

- [ ] **Step 3: 구현** — 신규 `nav_executor.py`(순수 함수만 우선, 클래스는 Task 4):

```python
#!/usr/bin/env python3
"""nav_executor — goto(좌표 이동) 실행기. dashboard 의 Nav2+dock-aware 로직 이식.

mission_manager 허브 내부에서 NavigateToPose(map 프레임)로 이동:
  · 현재 도킹 상태(dock_status)면 먼저 Undock 후 이동
  · params.dock_after 면 도착 후 자동 Dock
create3 중복 액션 디바운스(in-flight 시 재전송 금지, SIGSEGV 방지). 모든 콜백은
노드 executor 에서 처리(별도 스레드 없음). 결과는 on_done(status, detail) 콜백 1회.
"""
import math


def pose_stamped_fields(x, y, yaw):
    """map 프레임 목표 pose 의 위치/쿼터니언(순수) — 단위테스트용."""
    return {"frame_id": "map", "x": float(x), "y": float(y),
            "qz": math.sin(float(yaw) / 2.0), "qw": math.cos(float(yaw) / 2.0)}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd ~/MediCart/medicart_ws/src/mission_manager && python3 -m pytest test/test_nav_executor.py -v`
Expected: PASS (2개)

- [ ] **Step 5: 커밋**

```bash
cd ~/MediCart && git add medicart_ws/src/mission_manager/mission_manager/nav_executor.py medicart_ws/src/mission_manager/test/test_nav_executor.py
git commit -m "feat(mission_manager): nav_executor pose_stamped_fields(순수) 추가"
```

---

### Task 4: NavExecutor 클래스(Nav2 + dock-aware)

dashboard의 검증된 undock→nav→dock async 체인을 허브 내부 클래스로 이식. ROS 액션 비동기 콜백 — 단위테스트 불가(로봇 통합검증). 검증은 import + 빌드.

**Files:**
- Modify: `medicart_ws/src/mission_manager/mission_manager/nav_executor.py`

- [ ] **Step 1: NavExecutor 클래스 추가** — `nav_executor.py`의 `pose_stamped_fields` 아래에 추가:

```python
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from irobot_create_msgs.action import Dock, Undock
from irobot_create_msgs.msg import DockStatus
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient


class NavExecutor:
    """goto 좌표 이동 실행기(허브 내부). on_done(status, detail) 으로 종료 보고."""

    def __init__(self, node, ns, logger):
        self._node = node
        self._log = logger
        self._nav = ActionClient(node, NavigateToPose, f"/{ns}/navigate_to_pose")
        self._dock = ActionClient(node, Dock, f"/{ns}/dock")
        self._undock = ActionClient(node, Undock, f"/{ns}/undock")
        node.create_subscription(DockStatus, f"/{ns}/dock_status", self._on_dock_status, 10)
        self._is_docked = None       # None=불명
        self._active = False         # goto 진행중
        self._dock_after = False
        self._target = None          # (x,y,yaw)
        self._goal_handle = None     # 현재 nav/dock/undock goal handle(취소용)
        self._busy = None            # 'undock'|'nav'|'dock' in-flight(디바운스)
        self._on_done = None

    @property
    def active(self):
        return self._active

    def _on_dock_status(self, msg):
        self._is_docked = bool(msg.is_docked)

    def start(self, params, on_done):
        """goto 시작. params={x,y,yaw,dock_after?}. on_done 은 종료 시 1회."""
        self._on_done = on_done
        self._active = True
        self._dock_after = bool(params.get("dock_after"))
        self._target = (float(params["x"]), float(params["y"]), float(params.get("yaw", 0.0)))
        # dock 타깃이 아니고 현재 도킹(또는 불명)이면 먼저 undock
        if not self._dock_after and self._is_docked is not False:
            self._send_undock()
        else:
            self._send_nav()

    def cancel(self):
        """진행중 goal 취소(선점/정지). on_done 미호출(상위가 처리)."""
        gh = self._goal_handle
        self._active = False
        self._busy = None
        self._goal_handle = None
        self._on_done = None
        if gh is not None:
            try:
                gh.cancel_goal_async()
            except Exception as exc:                   # noqa: BLE001
                self._log.warn(f"[nav] cancel 오류: {exc}")

    # ── undock → nav → dock 비동기 체인 ──────────────────────────────────
    def _send_undock(self):
        if self._busy == "undock":
            return
        if not self._undock.wait_for_server(timeout_sec=2.0):
            self._finish("failed", "undock 액션서버 미연결")
            return
        self._busy = "undock"
        self._undock.send_goal_async(Undock.Goal()).add_done_callback(self._undock_accepted)

    def _undock_accepted(self, future):
        gh = future.result()
        if not gh.accepted:
            self._finish("failed", "undock 거부")
            return
        self._goal_handle = gh
        gh.get_result_async().add_done_callback(self._undock_done)

    def _undock_done(self, future):
        self._busy = None
        self._goal_handle = None
        if not self._active:
            return
        self._is_docked = False
        self._send_nav()

    def _send_nav(self):
        if self._busy == "nav":
            return
        if not self._nav.wait_for_server(timeout_sec=3.0):
            self._finish("failed", "Nav2 미연결")
            return
        x, y, yaw = self._target
        f = pose_stamped_fields(x, y, yaw)
        ps = PoseStamped()
        ps.header.frame_id = f["frame_id"]
        ps.header.stamp = self._node.get_clock().now().to_msg()
        ps.pose.position.x = f["x"]
        ps.pose.position.y = f["y"]
        ps.pose.orientation.z = f["qz"]
        ps.pose.orientation.w = f["qw"]
        goal = NavigateToPose.Goal()
        goal.pose = ps
        self._busy = "nav"
        self._log.info(f"[nav] goto → ({x:.2f},{y:.2f},yaw {yaw:.3f}) dock_after={self._dock_after}")
        self._nav.send_goal_async(goal).add_done_callback(self._nav_accepted)

    def _nav_accepted(self, future):
        gh = future.result()
        if not gh.accepted:
            self._finish("failed", "Nav2 goal 거부")
            return
        self._goal_handle = gh
        gh.get_result_async().add_done_callback(self._nav_done)

    def _nav_done(self, future):
        self._busy = None
        self._goal_handle = None
        if not self._active:
            return
        status = future.result().status
        if status != GoalStatus.STATUS_SUCCEEDED:
            self._finish("failed", f"Nav2 종료 status={status}")
            return
        if self._dock_after:
            self._send_dock()
        else:
            self._finish("done", "도착")

    def _send_dock(self):
        if self._busy == "dock":
            return
        if not self._dock.wait_for_server(timeout_sec=2.0):
            self._finish("failed", "dock 액션서버 미연결")
            return
        self._busy = "dock"
        self._dock.send_goal_async(Dock.Goal()).add_done_callback(self._dock_accepted)

    def _dock_accepted(self, future):
        gh = future.result()
        if not gh.accepted:
            self._finish("failed", "dock 거부")
            return
        self._goal_handle = gh
        gh.get_result_async().add_done_callback(self._dock_done)

    def _dock_done(self, future):
        self._busy = None
        self._goal_handle = None
        if not self._active:
            return
        self._is_docked = True
        self._finish("done", "도착 후 도킹 완료")

    def _finish(self, status, detail):
        self._active = False
        self._busy = None
        self._goal_handle = None
        cb, self._on_done = self._on_done, None
        self._log.info(f"[nav] goto 종료 status={status} detail={detail}")
        if cb is not None:
            cb(status, detail)
```

- [ ] **Step 2: import 검증(순수+pep8)**

Run: `cd ~/MediCart/medicart_ws/src/mission_manager && python3 -m pytest test/test_nav_executor.py -v && python3 -c "import ast; ast.parse(open('mission_manager/nav_executor.py').read()); print('syntax OK')"`
Expected: 순수 테스트 PASS + "syntax OK" (ROS 의존 import는 빌드 후 Task 5 통합검증에서 확인)

- [ ] **Step 3: 커밋**

```bash
cd ~/MediCart && git add medicart_ws/src/mission_manager/mission_manager/nav_executor.py
git commit -m "feat(mission_manager): NavExecutor(Nav2+dock-aware 이식) 추가"
```

---

### Task 5: mission_manager goto 라우팅 + arbiter 등록 + 의존성

mission_manager_node에 goto 레인을 추가하고, ModeArbiter에 `goto`(nav) 모드를 등록한다.

**Files:**
- Modify: `medicart_ws/src/mission_manager/mission_manager/mission_manager_node.py`
- Modify: `medicart_ws/src/mission_manager/package.xml`

- [ ] **Step 1: import + MODE_REGISTRY 수정** — `mission_manager_node.py` 상단 import 블록에 추가:

```python
from .nav_executor import NavExecutor
```

`MODE_REGISTRY` 딕셔너리에 goto 항목 추가:

```python
MODE_REGISTRY = {
    "goto": "nav",         # 운영자 좌표 이동(허브 내부 NavExecutor)
    "round": "reactive",   # 회진/추종 (nurse_tracker)
    "patrol": "nav", "errand": "nav", "guide": "nav", "intake": "nav",
}
```

- [ ] **Step 2: NavExecutor 생성** — `__init__`의 `self._arbiter = ModeArbiter(...)` 줄 바로 다음에 추가:

```python
        self._nav = NavExecutor(self, ns, self.get_logger())
```

- [ ] **Step 3: 라우팅에 goto 레인 추가** — `_on_mission_request`의 분기를 다음으로 교체:

```python
        action = req.get('action')
        if action in SYSTEM_ACTIONS:                 # dock/undock/ros_restart/reboot/shutdown
            self._executor.handle(req)
        elif action == 'goto':                        # 좌표 이동(Nav2 + dock-aware)
            self._handle_goto(req)
        elif action in MODE_ACTIONS:                  # start/stop/clear (+mode)
            ok, detail = self._arbiter.apply(action, req.get('mode'), req.get('params'))
            self._publish_feedback({'id': req.get('id'),
                                    'status': 'done' if ok else 'failed',
                                    'detail': detail, 'ts': int(time.time() * 1000)})
        else:
            self._publish_feedback({'id': req.get('id'), 'status': 'failed',
                                    'detail': 'unknown action: {}'.format(action),
                                    'ts': int(time.time() * 1000)})
```

- [ ] **Step 4: _handle_goto 메서드 추가** — `_on_mission_request` 아래에 추가:

```python
    def _handle_goto(self, req):
        """goto 좌표 이동: arbiter 'goto'(nav) 점거 → NavExecutor 실행 → 종료 시 해제·보고."""
        mid = req.get('id')
        params = req.get('params') or {}
        try:
            float(params['x']); float(params['y'])
        except (KeyError, TypeError, ValueError):
            self._publish_feedback({'id': mid, 'status': 'failed',
                                    'detail': 'goto requires numeric x,y',
                                    'ts': int(time.time() * 1000)})
            return
        if self._nav.active:                          # 신규 goto 가 기존 이동 선점
            self._nav.cancel()
        self._arbiter.apply('start', 'goto', params)  # nav 점거(REACTIVE 선점, cmd_vel 양보)

        def _done(status, detail):
            self._arbiter.apply('stop', 'goto')
            self._publish_feedback({'id': mid, 'action': 'goto', 'status': status,
                                    'detail': detail, 'ts': int(time.time() * 1000)})

        self._nav.start(params, _done)
        self._publish_feedback({'id': mid, 'action': 'goto', 'status': 'running',
                                'detail': 'navigating', 'ts': int(time.time() * 1000)})
```

- [ ] **Step 5: package.xml 의존성 추가** — `<depend>sensor_msgs</depend>` 줄 아래(또는 depend 블록 내)에 추가:

```xml
  <depend>nav2_msgs</depend>
  <depend>irobot_create_msgs</depend>
```

(이미 있는 의존성과 중복되지 않게 — 없을 때만 추가.)

- [ ] **Step 6: 빌드 + import 검증**

Run:
```bash
cd ~/MediCart/medicart_ws && colcon build --packages-select mission_manager db_bridge 2>&1 | tail -5
source install/setup.bash
python3 -c "from mission_manager.nav_executor import NavExecutor, pose_stamped_fields; from mission_manager.mode_arbitration import MODE_PRIORITY; print('goto prio', MODE_PRIORITY['goto']); print('import OK')"
```
Expected: 빌드 성공 + "goto prio 7" + "import OK"

- [ ] **Step 7: 단위테스트 재확인**

Run: `cd ~/MediCart/medicart_ws/src/mission_manager && python3 -m pytest test/test_mode_arbitration.py test/test_nav_executor.py -v`
Expected: PASS (전체)

- [ ] **Step 8: 커밋**

```bash
cd ~/MediCart && git add medicart_ws/src/mission_manager/mission_manager/mission_manager_node.py medicart_ws/src/mission_manager/package.xml
git commit -m "feat(mission_manager): goto 라우팅 레인 + arbiter goto(nav) 등록"
```

---

### Task 6: 웹 백엔드 goto 페이로드 검증

`mission_payload`에 goto 분기를 추가해 좌표를 검증·정규화한다.

**Files:**
- Modify: `web/backend/fb_read.py`
- Test: `web/backend/test/test_fb_read.py`

- [ ] **Step 1: 실패 테스트 작성** — `test_fb_read.py`에 추가:

```python
def test_mission_payload_goto_valid():
    import fb_read
    p = fb_read.mission_payload("goto", {"x": -8, "y": -6, "yaw": -0.0014,
                                         "dock_after": True, "label": "Dock"}, 1000)
    assert p["action"] == "goto" and p["status"] == "pending"
    assert p["params"]["x"] == -8.0 and p["params"]["y"] == -6.0
    assert p["params"]["dock_after"] is True and p["params"]["label"] == "Dock"


def test_mission_payload_goto_missing_coords_rejected():
    import fb_read
    import pytest
    with pytest.raises(ValueError):
        fb_read.mission_payload("goto", {"x": 1.0}, 1000)      # y 없음
    with pytest.raises(ValueError):
        fb_read.mission_payload("goto", {"x": "a", "y": "b"}, 1000)   # 비수치
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ~/MediCart/web/backend && python3 -m pytest test/test_fb_read.py::test_mission_payload_goto_valid -v`
Expected: FAIL (goto → "invalid action" ValueError)

- [ ] **Step 3: 구현** — `fb_read.py`의 `mission_payload` 위에 검증 헬퍼 추가:

```python
def _validate_goto_params(params):
    """goto params 검증·정규화 → {x,y,yaw,(dock_after),(label)}."""
    if not isinstance(params, dict):
        raise ValueError("goto params required")
    try:
        x = float(params["x"])
        y = float(params["y"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("goto requires numeric x,y")
    out = {"x": x, "y": y, "yaw": float(params.get("yaw", 0.0))}
    if params.get("dock_after"):
        out["dock_after"] = True
    if params.get("label"):
        out["label"] = str(params["label"])[:60]
    return out
```

`mission_payload`의 `if action in MISSION_ACTIONS:` 블록 바로 아래에 goto 분기 추가:

```python
    if action == "goto":
        return {"action": "goto", "params": _validate_goto_params(params),
                "status": "pending", "ts": int(ts)}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd ~/MediCart/web/backend && python3 -m pytest test/test_fb_read.py -v`
Expected: PASS (전체)

- [ ] **Step 5: 커밋**

```bash
cd ~/MediCart && git add web/backend/fb_read.py web/backend/test/test_fb_read.py
git commit -m "feat(web): goto mission 페이로드 검증 추가"
```

---

### Task 7: 웹 백엔드 targets 시드/조회

침상/home pose를 RTDB `targets`에 둔다. 순수 시드 딕셔너리(`targets_seed`)는 단위테스트, RTDB 결선(`get_targets`/`seed_targets`)은 멱등 기록.

**Files:**
- Modify: `web/backend/fb_read.py`
- Test: `web/backend/test/test_fb_read.py`

- [ ] **Step 1: 실패 테스트 작성** — `test_fb_read.py`에 추가:

```python
def test_targets_seed_shape():
    import fb_read
    seed = fb_read.targets_seed()
    assert len(seed) == 5
    assert seed["dock"]["dock_after"] is True
    assert seed["dock"]["x"] == -8.0 and seed["dock"]["y"] == -6.0
    for v in seed.values():
        assert "label" in v and "x" in v and "y" in v and "yaw" in v
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd ~/MediCart/web/backend && python3 -m pytest test/test_fb_read.py::test_targets_seed_shape -v`
Expected: FAIL (targets_seed 없음)

- [ ] **Step 3: 구현** — `fb_read.py`의 mission 섹션 근처에 추가(dashboard DEFAULT_TARGETS 실측값):

```python
# ── 이동 목적지(침상/home) pose — RTDB `targets`(dashboard DEFAULT_TARGETS 미러) ──
def targets_seed():
    """goto 프리셋 시드(순수). dashboard 실측 좌표(map=ninety)."""
    return {
        "t101_1": {"label": "101호 1번", "x": -12.0, "y": -5.0, "yaw": -0.00143},
        "t101_2": {"label": "101호 2번", "x": -12.0, "y": -6.0, "yaw": -0.00143},
        "t102":   {"label": "102호 호출", "x": -13.0, "y": -8.0, "yaw": -0.00143},
        "pharmacy": {"label": "약품실", "x": -9.0, "y": -9.0, "yaw": -0.00143},
        "dock":   {"label": "Docking Station", "x": -8.0, "y": -6.0,
                   "yaw": -0.00142, "dock_after": True},
    }


def get_targets():
    """RTDB `targets` 조회(없으면 빈 dict)."""
    return _init().reference("targets").get() or {}


def seed_targets():
    """`targets` 가 비어있으면 시드(멱등). 반환: 시드했으면 True."""
    ref = _init().reference("targets")
    if ref.get():
        return False
    ref.set(targets_seed())
    return True
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd ~/MediCart/web/backend && python3 -m pytest test/test_fb_read.py -v`
Expected: PASS (전체)

- [ ] **Step 5: 커밋**

```bash
cd ~/MediCart && git add web/backend/fb_read.py web/backend/test/test_fb_read.py
git commit -m "feat(web): targets 시드/조회(get_targets/seed_targets) 추가"
```

---

### Task 8: 웹 백엔드 /api/targets + 기동 시드

**Files:**
- Modify: `web/backend/app.py`

- [ ] **Step 1: 엔드포인트 추가** — `app.py`의 `@app.get("/api/rooms")` 위에 추가:

```python
@app.get("/api/targets")
def targets():
    if (resp := _require_auth()) is not None:
        return resp
    return jsonify({"targets": fb_read.get_targets()})
```

(`_require_auth`/`fb_read`/`jsonify` 는 이미 import·정의됨 — `/api/rooms` 패턴 그대로.)

- [ ] **Step 2: 기동 시 시드** — `app.py` 하단의 `if __name__ == "__main__":` 블록 직전(앱 구성 완료 지점)에 추가. 시드 실패는 치명적이지 않으니 로그만:

```python
try:
    if fb_read.seed_targets():
        print("[app] RTDB targets 시드 완료")
except Exception as exc:        # noqa: BLE001 — 시드 실패해도 서비스는 계속
    print(f"[app] targets 시드 건너뜀: {exc}")
```

- [ ] **Step 3: 라우트 등록 검증(서버 미기동, import 레벨)**

Run: `cd ~/MediCart/web/backend && python3 -c "import app; rules=[r.rule for r in app.app.url_map.iter_rules()]; assert '/api/targets' in rules, rules; print('route OK')"`
Expected: "route OK" (firebase 미초기화 경고는 무방 — 라우트 등록만 확인)

- [ ] **Step 4: 커밋**

```bash
cd ~/MediCart && git add web/backend/app.py
git commit -m "feat(web): GET /api/targets + 기동 시 targets 시드"
```

---

### Task 9: 프론트 api.ts — pushMission params + getTargets

`pushMission` 시그니처에 `params`를 추가한다. 기존 호출부(control)도 새 시그니처로 맞춰 빌드를 깨지 않게 한다.

**Files:**
- Modify: `web/frontend/lib/api.ts`
- Modify: `web/frontend/app/control/page.tsx` (기존 호출부만 — 신규 섹션은 Task 10)

- [ ] **Step 1: api.ts 수정** — `pushMission`을 다음으로 교체하고 `getTargets`/타입 추가:

```ts
export type GotoTarget = { label: string; x: number; y: number; yaw?: number; dock_after?: boolean };
export const getTargets = () => getJSON<{ targets: Record<string, GotoTarget> }>("/api/targets");

export async function pushMission(
  ns: string, action: string,
  params?: Record<string, unknown>, mode?: string,
) {
  const r = await fetch(`${API_BASE}/api/robots/${ns}/missions`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, params: params || {}, mode }),
  });
  return r.json();
}
```

- [ ] **Step 2: 기존 control 호출부 시그니처 정합** — `control/page.tsx`에서 `dispatch` 내부의 호출을 교체:

찾기:
```ts
      const r = await pushMission(ns, action, mode);
```
교체:
```ts
      const r = await pushMission(ns, action, undefined, mode);
```

- [ ] **Step 3: 타입체크**

Run: `cd ~/MediCart/web/frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: 에러 없음(출력 없음)

- [ ] **Step 4: 커밋**

```bash
cd ~/MediCart && git add web/frontend/lib/api.ts web/frontend/app/control/page.tsx
git commit -m "feat(web): pushMission params 인자 + getTargets/GotoTarget"
```

---

### Task 10: control "이동" 섹션(프리셋 버튼)

선택된 로봇으로 침상/home 프리셋 goto를 하달한다.

**Files:**
- Modify: `web/frontend/app/control/page.tsx`

- [ ] **Step 1: targets 로드 + dispatch에 params 지원** — `control/page.tsx` 상단 import에 `getTargets, GotoTarget` 추가하고, 컴포넌트 내 상태/로드 추가:

```ts
  const [targets, setTargets] = useState<Record<string, GotoTarget>>({});
  useEffect(() => { getTargets().then((d) => setTargets(d.targets || {})).catch(() => {}); }, []);
```

`dispatch` 함수 시그니처를 `params` 포함으로 확장하고 호출을 맞춘다. 현재:
```ts
  async function dispatch(key: string, action: string, label: string, mode?: string, confirm?: boolean) {
    ...
      const r = await pushMission(ns, action, undefined, mode);
```
교체:
```ts
  async function dispatch(key: string, action: string, label: string,
                          opts?: { mode?: string; params?: Record<string, unknown>; confirm?: boolean }) {
    const mode = opts?.mode, params = opts?.params, confirm = opts?.confirm;
    if (confirm && !window.confirm(`${ns.toUpperCase()} — "${label}" 하달할까요?`)) return;
    setSending(key);
    try {
      const r = await pushMission(ns, action, params, mode);
      setToast(r.ok ? { ok: true, msg: `${ns.toUpperCase()} ← ${label} 하달됨` } : { ok: false, msg: r.error || "실패" });
    } catch (e) {
      setToast({ ok: false, msg: String(e) });
    } finally {
      setSending(""); setTimeout(() => setToast(null), 2600);
    }
  }
```

> 참고: `sending` 은 `useState("")`(빈문자열) 이므로 리셋은 `setSending("")`. 기존 `finally` 의 토스트 자동해제(`setTimeout`) 패턴을 유지한다.

기존 호출부 3곳을 새 시그니처로 교체:
- 시스템: `onClick={() => dispatch(c.action, c.action, c.label, undefined, c.confirm)}` → `onClick={() => dispatch(c.action, c.action, c.label, { confirm: c.confirm })}`
- 전체해제: `dispatch("clear", "clear", "전체 모드 해제", undefined, true)` → `dispatch("clear", "clear", "전체 모드 해제", { confirm: true })`
- 모드 시작/정지: `dispatch(\`start:${m.mode}\`, "start", \`${m.label} 시작\`, m.mode)` → `dispatch(\`start:${m.mode}\`, "start", \`${m.label} 시작\`, { mode: m.mode })` (정지도 동일하게 `{ mode: m.mode }`)

- [ ] **Step 2: "이동" 섹션 UI 추가** — 모드 섹션(`MODES.map` 블록) 닫힌 직후에 추가:

```tsx
        <div className="mt-6">
          <div className="font-bold text-[15px] mb-2">이동 (goto)</div>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(targets).map(([id, t]) => (
              <button key={id} disabled={!!sending}
                onClick={() => dispatch(`goto:${id}`, "goto", t.label, {
                  params: { x: t.x, y: t.y, yaw: t.yaw ?? 0, dock_after: !!t.dock_after, label: t.label },
                  confirm: true,
                })}
                className="flex flex-col items-start bg-surface-2 border border-line rounded-xl px-4 py-3 hover:border-brand disabled:opacity-50">
                <span className="font-bold text-[14px]">{t.label}</span>
                <span className="mono text-[10.5px] opacity-60 mt-1">
                  {sending === `goto:${id}` ? "전송 중…" : `(${t.x}, ${t.y})${t.dock_after ? " · dock" : ""}`}
                </span>
              </button>
            ))}
            {Object.keys(targets).length === 0 && (
              <span className="text-ink-3 text-[13px]">등록된 목적지 없음(targets 시드 확인)</span>
            )}
          </div>
        </div>
```

- [ ] **Step 3: 타입체크**

Run: `cd ~/MediCart/web/frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: 에러 없음

- [ ] **Step 4: 프로덕션 빌드 확인**

Run: `cd ~/MediCart/web/frontend && npm run build 2>&1 | tail -8`
Expected: 빌드 성공(control 페이지 포함)

- [ ] **Step 5: 커밋**

```bash
cd ~/MediCart && git add web/frontend/app/control/page.tsx
git commit -m "feat(web): control 이동(goto) 프리셋 섹션"
```

---

### Task 11: MapView 캔버스 클릭 이동

미니맵에서 로봇을 선택하고 임의 점을 클릭하면 그 좌표로 goto를 하달한다.

**Files:**
- Modify: `web/frontend/components/MapView.tsx`

- [ ] **Step 1: 좌표 역변환 + 클릭 핸들러** — 렌더 effect에서 계산한 변환 파라미터를 ref에 저장하고, 캔버스 클릭에서 픽셀→월드로 역변환한다.

import에 `pushMission` 추가(`@/lib/api`). 컴포넌트 상태/ref 추가:

```ts
  const [selNs, setSelNs] = useState<string>(PRIMARY_NS);
  const viewRef = useRef<{ ox: number; oy: number; res: number; offx: number; offy: number; s: number; ih: number } | null>(null);
```

렌더 effect의 맵-available 분기 안에서 `X`/`Y` 정의 직후에 변환 파라미터 저장 추가:

```ts
      viewRef.current = { ox, oy, res, offx, offy, s, ih };
```

그리고 맵-미available 분기(else)에는:

```ts
      viewRef.current = null;     // 클릭 이동은 저장맵 있을 때만
```

- [ ] **Step 2: 클릭 핸들러 함수 추가** — 컴포넌트 내부(return 위)에 추가:

```ts
  async function onMapClick(e: React.MouseEvent<HTMLCanvasElement>) {
    const v = viewRef.current, cv = canvasRef.current;
    if (!v || !cv) return;     // 저장맵 없으면 클릭 이동 비활성
    const rect = cv.getBoundingClientRect();
    const sx = e.clientX - rect.left, sy = e.clientY - rect.top;
    // 화면 → 맵픽셀 → 월드(렌더의 X/Y 역함수)
    const wx = v.ox + ((sx - v.offx) / v.s) * v.res;
    const wy = v.oy + (v.ih - (sy - v.offy) / v.s) * v.res;
    if (!window.confirm(`${selNs.toUpperCase()} → (${wx.toFixed(2)}, ${wy.toFixed(2)}) 이동할까요?`)) return;
    await pushMission(selNs, "goto", { x: wx, y: wy, yaw: 0, label: "맵 클릭" });
  }
```

- [ ] **Step 3: 로봇 선택 UI + 캔버스에 onClick 연결** — 캔버스(`<canvas ref={canvasRef} ... />`)에 `onClick={onMapClick}` 추가하고 `style={{ cursor: "crosshair" }}`. 맵 영역 상단(`wrapRef` div 근처)에 선택 토글 추가:

```tsx
      <div className="flex gap-2 mb-2">
        {[PRIMARY_NS, SECONDARY_NS].map((ns) => (
          <button key={ns} onClick={() => setSelNs(ns)}
            className={`px-3 py-1.5 rounded-lg text-[13px] font-bold border ${selNs === ns ? "bg-brand text-white border-brand" : "bg-surface-2 border-line"}`}>
            {ns.toUpperCase()}
          </button>
        ))}
        <span className="text-ink-3 text-[12px] self-center">맵 클릭 → 선택 로봇 이동</span>
      </div>
```

- [ ] **Step 4: 타입체크 + 빌드**

Run: `cd ~/MediCart/web/frontend && npx tsc --noEmit 2>&1 | head -20 && npm run build 2>&1 | tail -8`
Expected: 타입에러 없음 + 빌드 성공

- [ ] **Step 5: 커밋**

```bash
cd ~/MediCart && git add web/frontend/components/MapView.tsx
git commit -m "feat(web): MapView 로봇 선택 + 맵 클릭 goto"
```

---

## 통합 검증(사용자 실행 — 로봇 필요, ROS 구동 직접 금지)

로봇측(robot6 예) 기동 순서(dashboard README 기준):

```bash
# 터미널 A~C: localization → (RViz 초기 pose) → Nav2
loc 6 ~/MediCart/medicart_ws/maps/ninety.yaml
rv 6                 # 2D Pose Estimate 로 초기 위치 지정
nav 6
ros2 action info /robot6/navigate_to_pose      # Action servers: 1 확인

# 터미널 D: db_node + mission_manager (robot.env source 후)
source ~/MediCart/common/robot.env 2>/dev/null; source ~/MediCart/medicart_ws/install/setup.bash
ros2 run db_bridge db_node --ros-args -p namespace:=robot6 &
ros2 run mission_manager mission_manager_node --ros-args -p namespace:=robot6
```

웹: 프론트 control "이동"에서 침상/`Docking Station` 버튼, 또는 map 페이지에서 robot6 선택 후 맵 클릭.
기대: `mission_pool`→`mission_request(goto)`→Nav2 이동, `Docking Station`은 도착 후 자동 도킹,
도킹 상태에서 일반 목적지는 자동 undock 후 이동. `mission_status`/로그에 running→done 반영.

검증 시나리오:
1. 침상 프리셋 이동 → 도착 done.
2. `Docking Station`(dock_after) → 이동 후 자동 도킹 done.
3. 도킹 상태에서 침상 클릭 → 자동 undock 후 이동.
4. 이동 중 다른 목적지 하달 → 기존 nav 취소 후 신규 이동(선점).
5. round 모드 활성 중 goto 하달 → goto 선점(우선순위 7), goto 종료 후 round 복귀.

---

## Self-Review

**Spec coverage:** §3 데이터계약(goto payload/targets seed)=Task6,7 / §4 로봇(nav_executor,routing,arbiter,db_node timeout,package.xml)=Task1~5 / §4 웹(fb_read,app,api,control,MapView)=Task6~11 / §5 픽셀↔월드=Task11 / §6 에러처리(Nav2 미연결·dock 불명·선점·워치독·디바운스)=Task1,4,5 / §7 테스트(payload·pose_stamped·seed·우선순위)=Task1,2,3,6,7. 모든 요구사항에 대응 태스크 존재.

**Placeholder scan:** 모든 코드 스텝에 실제 코드 포함, TBD/“적절히” 없음.

**Type consistency:** `pose_stamped_fields`(frame_id/x/y/qz/qw)·`NavExecutor.start(params,on_done)`/`.cancel()`/`.active`·`mission_payload("goto",...)`·`pushMission(ns,action,params?,mode?)`·`getTargets()→{targets}`·`GotoTarget{label,x,y,yaw?,dock_after?}` — 태스크 간 시그니처 일치. `MODE_REGISTRY`에 `goto:"nav"` 추가가 arbiter `apply("start","goto")`와 정합. control `dispatch(...,opts)` 신시그니처를 호출 3곳 모두 교체.
