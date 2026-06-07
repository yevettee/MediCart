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
