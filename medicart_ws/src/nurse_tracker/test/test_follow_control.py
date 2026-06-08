"""follow_control 순수 테스트 — oakd_approach_node._tick_following 포팅 검증.
실행: cd nurse_tracker && PYTHONPATH=. python3 -m pytest test/test_follow_control.py -q"""
from nurse_tracker.follow_control import FollowParams, follow_cmd, FollowFSM


class T:  # 스텁 target
    def __init__(self, distance, error_x, detected=True, stamp=0.0):
        self.distance = distance; self.error_x = error_x
        self.detected = detected; self.stamp = stamp


def test_follow_cmd_far_forward():
    lin, ang = follow_cmd(2.0, 0.0, FollowParams(desired_distance=0.4))
    assert lin > 0.0 and abs(ang) < 1e-6


def test_follow_cmd_hold_in_deadband():
    lin, _ = follow_cmd(0.42, 0.0, FollowParams(desired_distance=0.4, deadband=0.05))
    assert lin == 0.0


def test_follow_cmd_close_reverse():
    p = FollowParams(desired_distance=0.4, deadband=0.05, max_lin=0.15)
    lin, _ = follow_cmd(0.2, 0.0, p)
    assert lin < 0.0 and lin >= -p.max_lin


def test_follow_cmd_large_offset_rotates_only_no_forward():
    """|error_x| > align_deadzone → 정렬 우선, 직진 금지(oakd_approach_node 규약)."""
    p = FollowParams(align_deadzone=0.25)
    lin, ang = follow_cmd(2.0, 0.5, p)             # 화면 오른쪽으로 크게 치우침
    assert lin == 0.0 and ang < 0.0                # 우측 치우침 → angular.z < 0 (시계방향 정렬)


def test_follow_cmd_small_offset_moves_and_fine_aligns():
    p = FollowParams(align_deadzone=0.25, fine_align=0.10)
    lin, ang = follow_cmd(2.0, 0.15, p)            # 정렬범위 내, 미세보정 임계는 초과
    assert lin > 0.0 and ang < 0.0


def test_follow_cmd_within_fine_threshold_no_correction():
    p = FollowParams(align_deadzone=0.25, fine_align=0.10)
    _, ang = follow_cmd(2.0, 0.05, p)              # 거의 정면 → 보정 불필요
    assert ang == 0.0


def test_fsm_follow_then_lost_then_recover():
    fsm = FollowFSM(FollowParams(desired_distance=0.4), follow_timeout=1.0, lost_timeout=5.0)
    lin, ang, d = fsm.step(T(2.0, 0.0, stamp=10.0), now=10.0)
    assert d == "FOLLOW" and lin > 0.0
    lin, ang, d = fsm.step(None, now=11.5)           # 미검출 → 정지 대기
    assert (lin, ang) == (0.0, 0.0) and d == "LOST_WAIT"
    _, _, d = fsm.step(None, now=16.6)               # 5s 초과 → lost
    assert d == "lost"
    _, _, d = fsm.step(T(1.5, 0.0, stamp=20.0), now=20.0)  # 재등장 → 복귀
    assert d == "FOLLOW"
