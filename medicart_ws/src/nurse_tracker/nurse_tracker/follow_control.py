"""follow_control — depth→robot_frame 좌표 기반 추종 제어 순수 로직(ROS 무관).

입력: (x_robot, y_robot) — base_link 프레임 미터 좌표
  x_robot: 전방 거리 (+앞)
  y_robot: 좌우  (+왼쪽, ROS 규약)

제어 전략:
  1. angle = atan2(y_robot, x_robot)  — 실제 각도(rad)
  2. dist  = hypot(x_robot, y_robot)  — 실제 거리(m)
  3. |angle| > angle_deadzone → 회전만(직진 금지)
  4. 그 외 → 거리 오차 비례 직진 + 각도 비례 회전 병행
"""
import math
from dataclasses import dataclass


@dataclass
class FollowParams:
    desired_distance: float = 0.8    # 유지 거리(m)
    deadband:         float = 0.15   # ±15cm 이내 직진 정지
    angle_deadzone:   float = 0.35   # rad(~20°) 초과 시 회전만, 직진 금지
    k_lin:            float = 0.25   # 거리 오차(m) → 선속도(m/s)
    k_ang:            float = 1.0    # 각도(rad)   → 각속도(rad/s)
    max_lin:          float = 0.22   # 최대 선속도(m/s)
    max_ang:          float = 0.6    # 최대 각속도(rad/s)


def follow_cmd(x_robot: float, y_robot: float, p: FollowParams):
    """base_link 프레임 좌표 (x, y) → (lin m/s, ang rad/s).

    angle = atan2(y, x): 로봇이 사람을 바라봐야 하는 실제 각도
    dist  = hypot(x, y): 사람까지 실제 거리
    """
    dist  = math.hypot(x_robot, y_robot)
    angle = math.atan2(y_robot, x_robot)

    # 각도 제어 (항상 활성)
    ang = max(-p.max_ang, min(p.k_ang * angle, p.max_ang))

    # 크게 틀어졌으면 회전만
    if abs(angle) > p.angle_deadzone:
        return 0.0, ang

    # 거리 제어
    lin = 0.0
    err = dist - p.desired_distance
    if abs(err) > p.deadband:
        lin = max(-p.max_lin, min(p.k_lin * err, p.max_lin))

    return lin, ang


class FollowFSM:
    """FOLLOW ↔ LOST_WAIT. 손실 5s 초과 시 detail='lost'."""

    def __init__(self, params: FollowParams = None, follow_timeout=1.0, lost_timeout=5.0):
        self.p = params or FollowParams()
        self.follow_timeout = follow_timeout
        self.lost_timeout   = lost_timeout
        self._lost_since    = None

    def reset(self):
        self._lost_since = None

    def step(self, target, now):
        """target(x_robot·y_robot·detected·stamp) | None, now → (lin, ang, detail)."""
        fresh = (target is not None
                 and getattr(target, "detected", False)
                 and target.distance > 0.0
                 and (now - target.stamp) <= self.follow_timeout)
        if fresh:
            self._lost_since = None
            lin, ang = follow_cmd(target.x_robot, target.y_robot, self.p)
            return lin, ang, "FOLLOW"
        if self._lost_since is None:
            self._lost_since = now
        detail = "lost" if (now - self._lost_since) > self.lost_timeout else "LOST_WAIT"
        return 0.0, 0.0, detail
