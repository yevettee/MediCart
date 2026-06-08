"""follow_control — 추종 제어 순수 로직(ROS 무관).
minicar_navigator.oakd_approach_node._tick_following 포팅 + 손실 FSM.
"""
from dataclasses import dataclass


@dataclass
class FollowParams:
    desired_distance: float = 0.4    # 유지 거리(m) — 40cm
    deadband: float = 0.06           # 거리 데드밴드(m) — 목표거리 부근 떨림(울컥거림) 완화 위해 소폭 확대
    align_deadzone: float = 0.25     # |error_x| 이 값 초과 시 정렬 우선(회전만, 직진 금지)
    fine_align: float = 0.10         # 정렬 단계에서 미세 회전 보정을 더하는 임계값
    k_lin: float = 0.4               # 거리오차 비례이득 — 상향(추종 반응성↑, max_lin 상향과 함께 가속감 보강)
    k_ang: float = 0.5               # 회전 비례이득 — 소폭 하향(좌우 미세 흔들림 완화 → 더 부드러운 정렬)
    max_lin: float = 0.22            # 최대 직진속도(m/s) — 0.15→0.22, 사람 보행속도에 더 근접해 덜 처짐
    max_ang: float = 0.6             # 최대 회전속도(rad/s) — 측면 이동 시 더 빠르게 따라 돌도록 상향


def follow_cmd(distance, error_x, p: FollowParams):
    """거리(m) · bbox 중심오차(error_x, -1~+1, += 화면 오른쪽) → (lin, ang).

    oakd_approach_node._tick_following 규약 포팅:
      |error_x| > align_deadzone → 그 자리에서 정렬 회전만(직진 금지)
      그 외                       → 거리오차 비례 직진 + (필요 시) 미세 회전 보정
    """
    lin = 0.0
    ang = 0.0
    if abs(error_x) > p.align_deadzone:
        ang = max(-p.max_ang, min(-p.k_ang * error_x, p.max_ang))
        return lin, ang

    if distance > 0.0:
        err = distance - p.desired_distance
        if abs(err) > p.deadband:
            lin = max(-p.max_lin, min(p.k_lin * err, p.max_lin))
    if abs(error_x) > p.fine_align:
        ang = max(-p.max_ang, min(-p.k_ang * error_x, p.max_ang))
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
        """target(거리·중심오차·detected·stamp) | None, now → (lin, ang, detail)."""
        fresh = (target is not None and getattr(target, "detected", False)
                 and target.distance > 0.0 and (now - target.stamp) <= self.follow_timeout)
        if fresh:
            self._lost_since = None
            lin, ang = follow_cmd(target.distance, target.error_x, self.p)
            return lin, ang, "FOLLOW"
        if self._lost_since is None:
            self._lost_since = now
        detail = "lost" if (now - self._lost_since) > self.lost_timeout else "LOST_WAIT"
        return 0.0, 0.0, detail
