"""mode_arbitration — mission_manager 모드 중재 순수 로직(ROS 무관).

우선순위 선점 중재 + 정면 안전 게이트. intel1 ward_robot/control.py 해당부 포팅.
부수효과 없음 → 로봇 없이 단위 테스트.
"""
from dataclasses import dataclass

# 높을수록 선점: mapping > 문진 > 회진 > 지시 > 가이드 > 순찰 > idle
MODE_PRIORITY = {
    "goto": 7,
    "mapping": 6, "intake": 5, "round": 4, "round_nav": 4,
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
