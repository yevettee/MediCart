"""mission_queue 순수 로직 테스트(ROS/Firebase 무관).

실행: cd db_bridge && python3 -m pytest test/test_mission_queue.py -v
"""
from db_bridge.mission_queue import (active_count, is_mission, ordered_pending)


def test_is_mission_excludes_meta_and_nondict():
    assert is_mission("m1", {"action": "dock"}) is True
    assert is_mission("_meta", {"x": 1}) is False
    assert is_mission("m2", "notdict") is False


def test_ordered_pending_fifo_by_ts():
    pool = {
        "_meta": {"purpose": "x"},
        "kB": {"action": "undock", "status": "pending", "ts": 300},
        "kA": {"action": "dock", "status": "pending", "ts": 100},
        "kC": {"action": "reboot", "status": "running", "ts": 200},   # 진행중 제외
        "kD": {"action": "dock", "status": "done", "ts": 50},         # 완료 제외
    }
    assert ordered_pending(pool) == ["kA", "kB"]   # ts 오름차순, pending 만


def test_ordered_pending_defaults_status_pending():
    # status 없는 항목은 pending 으로 간주
    pool = {"k1": {"action": "dock", "ts": 10}}
    assert ordered_pending(pool) == ["k1"]


def test_ordered_pending_empty_and_bad_input():
    assert ordered_pending({}) == []
    assert ordered_pending(None) == []
    assert ordered_pending("nope") == []


def test_active_count_excludes_terminal_and_meta():
    pool = {
        "_meta": {"x": 1},
        "a": {"action": "dock", "status": "pending", "ts": 1},
        "b": {"action": "undock", "status": "running", "ts": 2},
        "c": {"action": "reboot", "status": "done", "ts": 3},
        "d": {"action": "dock", "status": "failed", "ts": 4},
    }
    assert active_count(pool) == 2   # pending + running
    assert active_count(None) == 0
