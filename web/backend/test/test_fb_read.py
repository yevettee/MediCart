"""fb_read 순수 로직 단위 테스트 (firebase/Flask 무관).

실행: cd MediCart/web/backend && python3 -m pytest test/test_fb_read.py -v
"""
import pytest

import fb_read
from fb_read import (merge_snapshots, topics_to_snapshot, cmd_payload, valid_pid)


def test_topics_to_snapshot_maps_topic_keys_to_fields():
    node = {
        "amcl_pose": {"x": 1.0, "y": 2.0, "yaw": 0.5},
        "odom": {"lin": 0.1, "ang": 0.0},
        "battery_state": {"pct": 63.0, "voltage": 12.1},
        "dock_status": {"is_docked": True},
        "imu": {"yaw_rate": 0.02},
        "scan": {"angle_min": -3.14, "angle_inc": 0.01, "range_max": 12.0, "ranges": [1.0]},
        "robot_mode": "patrol", "online": True, "stamp": 1700000000000,
    }
    s = topics_to_snapshot(node)
    assert s["pose"] == {"x": 1.0, "y": 2.0, "yaw": 0.5}
    assert s["vel"] == {"lin": 0.1, "ang": 0.0}
    assert s["battery"] == {"pct": 63.0, "voltage": 12.1}
    assert s["dock"] == {"is_docked": True}
    assert s["imu"] == {"yaw_rate": 0.02}
    assert s["scan"]["range_max"] == 12.0
    assert s["mode"] == "patrol" and s["online"] is True and s["stamp"] == 1700000000000


def test_topics_to_snapshot_none_or_control_only():
    assert topics_to_snapshot(None) is None
    assert topics_to_snapshot("nope") is None
    # cmd 만 있는 노드(센서 토픽·stamp 없음) → 미존재 취급
    assert topics_to_snapshot({"cmd": {"action": "start"}}) is None


def test_topics_to_snapshot_defaults_mode_idle():
    s = topics_to_snapshot({"amcl_pose": {"x": 0.0}, "stamp": 5})
    assert s["mode"] == "idle" and s["online"] is False and s["stamp"] == 5


def test_merge_snapshots_injects_source_and_handles_missing():
    raw = {"robot3": {"amcl_pose": {"x": 1.0}, "robot_mode": "idle", "stamp": 5}}
    out = merge_snapshots(raw, ["robot3", "robot6"])
    assert out["robot3"]["mode"] == "idle"
    assert out["robot3"]["pose"] == {"x": 1.0}
    assert out["robot3"]["source"] == "robot3"
    assert out["robot6"] is None      # RTDB에 없는 소스


def test_merge_snapshots_none_raw():
    out = merge_snapshots(None, ["robot3"])
    assert out == {"robot3": None}


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


def test_ocr_payload():
    from fb_read import ocr_payload
    assert ocr_payload("타이레놀", 0.9, 1000) == {"text": "타이레놀", "conf": 0.9, "ts": 1000}
    assert ocr_payload("x", None, 5)["conf"] is None


def test_sanitize_fields_keys_and_numbers():
    from fb_read import sanitize_fields
    out = sanitize_fields({
        "patientId": "P-2026-0001",       # 제어키 → 제외
        "음식/기타 알레르기": "없음",       # '/' → '_'
        "수축기혈압": "152",               # 숫자키 → int
        "체온": "36.8",                    # 숫자키 → float
        "통증부위": "두부",                # 문자 유지
        "SpO2": "",                        # 빈 숫자 → 원본 유지
    })
    assert "patientId" not in out
    assert out["음식_기타 알레르기"] == "없음"
    assert out["수축기혈압"] == 152 and isinstance(out["수축기혈압"], int)
    assert out["체온"] == 36.8
    assert out["통증부위"] == "두부"
    assert out["SpO2"] == ""


def test_visit_payload_injects_pid():
    from fb_read import visit_payload
    v = visit_payload("P-2026-0007", {"주호소(CC)": "기침", "맥박": "88"})
    assert v["등록번호"] == "P-2026-0007"
    assert v["주호소(CC)"] == "기침" and v["맥박"] == 88


def test_vitals_from_visit_extracts_subset():
    from fb_read import vitals_from_visit
    visit = {"수축기혈압": 152, "맥박": 88, "주호소(CC)": "x", "방문일": "2026-06-06"}
    vit = vitals_from_visit(visit)
    assert vit == {"수축기혈압": 152, "맥박": 88}   # 생체징후 키만


def test_mission_payload_whitelist():
    from fb_read import mission_payload
    m = mission_payload("dock", None, 1000)
    assert m == {"action": "dock", "params": {}, "status": "pending", "ts": 1000}
    for bad in ("rm-rf", "format", ""):
        with pytest.raises(ValueError):
            mission_payload(bad, None, 1)


def test_mission_payload_mode_actions():
    from fb_read import mission_payload
    # 모드 액션은 mode 포함
    m = mission_payload("start", None, 5, mode="round")
    assert m == {"action": "start", "params": {}, "status": "pending", "ts": 5, "mode": "round"}
    assert mission_payload("stop", None, 5, mode="patrol")["mode"] == "patrol"
    # clear 는 mode 불요
    c = mission_payload("clear", None, 5)
    assert c["action"] == "clear" and "mode" not in c
    # start/stop 에 잘못된/없는 mode → 거부
    with pytest.raises(ValueError):
        mission_payload("start", None, 5, mode="bogus")
    with pytest.raises(ValueError):
        mission_payload("start", None, 5)


def test_valid_robot_ns():
    from fb_read import valid_robot_ns
    assert valid_robot_ns("robot3") and valid_robot_ns("robot6")
    assert not valid_robot_ns("amr2") and not valid_robot_ns("../x")


def test_list_missions_filters_meta_and_sorts():
    from fb_read import list_missions
    pool = {
        "_meta": {"purpose": "x"},
        "m1": {"action": "dock", "ts": 100, "status": "pending"},
        "m2": {"action": "undock", "ts": 300, "status": "pending"},
        "m3": {"action": "reboot", "ts": 200, "status": "done"},
    }
    out = list_missions(pool)
    assert [m["id"] for m in out] == ["m2", "m3", "m1"]   # ts 내림차순, _meta 제외
    assert all(not m["id"].startswith("_") for m in out)
    assert list_missions(None) == [] and list_missions("x") == []


def test_mission_payload_goto_valid():
    import fb_read
    p = fb_read.mission_payload("goto", {"x": -8, "y": -6, "yaw": -0.0014,
                                         "dock_after": True, "label": "Dock"}, 1000)
    assert p["action"] == "goto" and p["status"] == "pending"
    assert p["params"]["x"] == -8.0 and p["params"]["y"] == -6.0
    assert p["params"]["dock_after"] is True and p["params"]["label"] == "Dock"


def test_mission_payload_goto_missing_coords_rejected():
    import fb_read
    import pytest
    with pytest.raises(ValueError):
        fb_read.mission_payload("goto", {"x": 1.0}, 1000)      # y 없음
    with pytest.raises(ValueError):
        fb_read.mission_payload("goto", {"x": "a", "y": "b"}, 1000)   # 비수치


def test_targets_seed_shape():
    import fb_read
    seed = fb_read.targets_seed()
    assert len(seed) == 5
    assert seed["dock"]["dock_after"] is True
    assert seed["dock"]["x"] == -8.0 and seed["dock"]["y"] == -6.0
    for v in seed.values():
        assert "label" in v and "x" in v and "y" in v and "yaw" in v


def test_intake_pending_payload():
    import fb_read
    p = fb_read.intake_pending_payload(
        {"name": " 김환자 ", "room": "101", "sections": {"주호소(CC)": "두통"}}, 1700000000000)
    assert p["name"] == "김환자"
    assert p["room"] == "101"
    assert p["sections"] == {"주호소(CC)": "두통"}
    assert p["status"] == "pending"
    assert p["ts"] == 1700000000000


def test_intake_pending_payload_defaults():
    import fb_read
    p = fb_read.intake_pending_payload({}, 1)
    assert p["name"] == "" and p["room"] == "" and p["sections"] == {}
    assert p["status"] == "pending"


def test_intake_reset_updates_builds_false_map():
    raw = {"P-2024-0001": {"info": {}}, "P-2024-0002": {"info": {}}}
    upd = fb_read._intake_reset_updates(raw)
    assert upd == {"P-2024-0001/intake_done": False, "P-2024-0002/intake_done": False}


def test_intake_reset_updates_empty():
    assert fb_read._intake_reset_updates(None) == {}
    assert fb_read._intake_reset_updates({}) == {}


def test_mark_intake_done_rejects_bad_pid():
    assert fb_read.mark_intake_done("not-a-pid") is False


# ── 시나리오 B — nurse_cart (pure) ─────────────────────────────────────────────
def test_mission_actions_includes_nurse_cart_mission():
    assert "nurse_cart_mission" in fb_read.MISSION_ACTIONS


def test_mission_payload_accepts_nurse_cart_mission():
    p = fb_read.mission_payload("nurse_cart_mission", None, 123)
    assert p["action"] == "nurse_cart_mission" and p["status"] == "pending"


def test_phase_or_idle():
    assert fb_read._phase_or_idle(None) == "idle"
    assert fb_read._phase_or_idle("") == "idle"
    assert fb_read._phase_or_idle(123) == "idle"
    assert fb_read._phase_or_idle("tracking") == "tracking"
