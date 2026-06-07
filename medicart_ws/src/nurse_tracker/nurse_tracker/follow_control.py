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
