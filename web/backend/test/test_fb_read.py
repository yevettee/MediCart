"""fb_read 순수 로직 단위 테스트 (firebase/Flask 무관).

실행: cd MediCart/web/backend && python3 -m pytest test/test_fb_read.py -v
"""
import pytest

from fb_read import merge_snapshots, cmd_payload, valid_pid


def test_merge_snapshots_injects_source_and_handles_missing():
    raw = {"robot6": {"pose": {"x": 1.0}, "mode": "idle"}}
    out = merge_snapshots(raw, ["robot6", "amr2"])
    assert out["robot6"]["mode"] == "idle"
    assert out["robot6"]["source"] == "robot6"
    assert out["amr2"] is None        # RTDB에 없는 소스


def test_merge_snapshots_none_raw():
    out = merge_snapshots(None, ["robot6"])
    assert out == {"robot6": None}


def test_cmd_payload_valid():
    p = cmd_payload("start", "mapping", {"k": 1}, ts=1000)
    assert p == {"action": "start", "mode": "mapping", "params": {"k": 1}, "ts": 1000}


def test_cmd_payload_clear_allows_no_mode():
    p = cmd_payload("clear", None, None, ts=5)
    assert p["action"] == "clear" and p["params"] == {}


def test_cmd_payload_bad_action():
    with pytest.raises(ValueError):
        cmd_payload("danger", "mapping", None, ts=1)


def test_cmd_payload_bad_mode():
    with pytest.raises(ValueError):
        cmd_payload("start", "evil", None, ts=1)


def test_valid_pid():
    assert valid_pid("P-2026-0001") is True
    assert valid_pid("../x") is False
