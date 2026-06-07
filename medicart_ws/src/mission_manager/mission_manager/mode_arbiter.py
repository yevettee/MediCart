"""mode_arbiter — 외부 모드 노드 중재(허브 핵심).

ModeProxy: 모드 노드 1개의 ROS 핸들(set 발행 / cmd_vel 후보·status 캐시).
ModeArbiter: 활성 요청 집합 + 우선순위 중재(mode_arbitration) + 선점/복귀 lifecycle
             + REACTIVE cmd_vel 게이트 + status 워치독(무응답 lost abort).
결정은 순수 mode_arbitration 에 위임, 여기서는 ROS 결선만.
"""
import json
import time

from geometry_msgs.msg import Twist
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from mission_manager.mode_arbitration import arbitrate, safety_gate, SafetyParams

REACTIVE = "reactive"
NAV = "nav"

# set 토픽: 래치(transient_local) — 늦게/재시작한 모드 노드가 마지막 활성상태를 받게 함.
LATCHED_QOS = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)


class ModeProxy:
    """외부 모드 노드 한 개 핸들."""

    def __init__(self, node, ns, name, actuation):
        self.name = name
        self.actuation = actuation
        self._set_pub = node.create_publisher(String, f"/{ns}/mode/{name}/set", LATCHED_QOS)
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
                self._log.warn(
                    f"[arbiter] {self._current} status 무응답 {self._status_timeout}s → lost abort")
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
