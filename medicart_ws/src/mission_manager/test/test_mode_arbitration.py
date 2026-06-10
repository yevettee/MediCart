"""mode_arbitration 순수 로직 테스트(ROS 무관).
실행: cd mission_manager && python3 -m pytest test/test_mode_arbitration.py -v
"""
from mission_manager.mode_arbitration import (MODE_PRIORITY, arbitrate,
                                              safety_gate, SafetyParams)


def test_arbitrate_empty_is_idle():
    assert arbitrate(set()) == "idle"


def test_arbitrate_picks_highest_priority():
    assert arbitrate({"patrol", "round"}) == "round"
    assert arbitrate({"patrol", "round_nav"}) == "round_nav"
    assert arbitrate({"patrol", "guide", "intake"}) == "intake"
    assert arbitrate({"patrol"}) == "patrol"


def test_arbitrate_unknown_excluded():
    assert arbitrate({"bogus"}) == "idle"
    assert arbitrate({"bogus", "patrol"}) == "patrol"


def test_priority_order_spec():
    p = MODE_PRIORITY
    assert p["mapping"] > p["intake"] > p["round"] > p["errand"] > p["guide"] > p["patrol"] > p["idle"]
    assert p["round_nav"] == p["round"]


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
