import os

os.environ.setdefault("INTEL_PASSWORD", "spw")
os.environ.setdefault("INTEL_AUTH_TOKEN", "STAFFTOK")
os.environ.setdefault("INTEL_ADMIN_PASSWORD", "apw")
os.environ.setdefault("INTEL_ADMIN_TOKEN", "ADMINTOK")

import app as flask_app  # noqa: E402

client = flask_app.app.test_client()


def test_login_staff_sets_cookie_and_role():
    r = client.post("/api/login", json={"password": "spw"})
    assert r.status_code == 200 and r.get_json()["role"] == "staff"
    assert "intel_auth=STAFFTOK" in r.headers.get("Set-Cookie", "")


def test_login_admin_role():
    r = client.post("/api/login", json={"password": "apw"})
    assert r.get_json()["role"] == "admin"
    assert "intel_auth=ADMINTOK" in r.headers.get("Set-Cookie", "")


def test_login_bad_password():
    assert client.post("/api/login", json={"password": "x"}).status_code == 401


def test_me_reports_role():
    client.set_cookie("intel_auth", "ADMINTOK")
    assert client.get("/api/me").get_json()["role"] == "admin"
    client.set_cookie("intel_auth", "")
    assert client.get("/api/me").get_json()["role"] == "patient"


def test_before_request_blocks_by_role():
    client.set_cookie("intel_auth", "")
    assert client.get("/api/patients").status_code == 401
    client.set_cookie("intel_auth", "STAFFTOK")
    assert client.get("/api/amrs").status_code == 401
    client.set_cookie("intel_auth", "")
    assert client.post("/api/intake", json={}).status_code != 401


def test_patrol_reset_requires_staff(monkeypatch):
    monkeypatch.setattr(flask_app.fb_read, "reset_intake_flags", lambda: 3)
    client.set_cookie("intel_auth", "")           # patient
    assert client.post("/api/patrol/reset").status_code == 401
    client.set_cookie("intel_auth", "STAFFTOK")   # staff
    r = client.post("/api/patrol/reset")
    assert r.status_code == 200 and r.get_json() == {"ok": True, "count": 3}


def test_patrol_intake_done(monkeypatch):
    seen = {}
    monkeypatch.setattr(flask_app.fb_read, "mark_intake_done",
                        lambda pid: seen.setdefault("pid", pid) or True)
    client.set_cookie("intel_auth", "STAFFTOK")
    r = client.post("/api/patrol/intake-done", json={"pid": "P-2024-0001"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert seen["pid"] == "P-2024-0001"


def test_patrol_intake_done_bad_pid(monkeypatch):
    monkeypatch.setattr(flask_app.fb_read, "mark_intake_done", lambda pid: False)
    client.set_cookie("intel_auth", "STAFFTOK")
    assert client.post("/api/patrol/intake-done", json={"pid": "x"}).status_code == 400


def test_confirm_injection_records_confirmed(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        flask_app.fb_read, "update_injection_status",
        lambda pid, inj_id, status, ocr_text=None: seen.update(
            {"pid": pid, "inj": inj_id, "status": status, "note": ocr_text}),
    )
    client.set_cookie("intel_auth", "STAFFTOK")
    r = client.post("/api/patients/P-2024-0001/injections/inj1/confirm")
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "status": "confirmed"}
    assert seen == {"pid": "P-2024-0001", "inj": "inj1", "status": "confirmed", "note": "QR 환자 확인"}


def test_confirm_injection_bad_pid(monkeypatch):
    monkeypatch.setattr(flask_app.fb_read, "update_injection_status",
                        lambda *a, **k: None)
    client.set_cookie("intel_auth", "STAFFTOK")
    assert client.post("/api/patients/bad/injections/inj1/confirm").status_code == 400


def test_confirm_injection_requires_staff():
    client.set_cookie("intel_auth", "")
    assert client.post("/api/patients/P-2024-0001/injections/inj1/confirm").status_code == 401


# ── 시나리오 B — nurse_cart 트리거 라우트 ──────────────────────────────────────
def test_create_mission_requires_admin(monkeypatch):
    monkeypatch.setattr(flask_app.fb_read, "push_mission",
                        lambda ns, action, *a, **k: ("mid1", {"action": action}))
    client.set_cookie("intel_auth", "STAFFTOK")   # staff → 거부
    assert client.post("/api/missions", json={"action": "nurse_cart_mission"}).status_code == 401
    client.set_cookie("intel_auth", "ADMINTOK")
    r = client.post("/api/missions", json={"action": "nurse_cart_mission"})
    assert r.status_code == 200 and r.get_json()["ok"] is True


def test_nurse_cart_ocr_done_staff(monkeypatch):
    seen = {}
    monkeypatch.setattr(flask_app.fb_read, "set_ocr_done",
                        lambda ns, done=True: seen.setdefault("v", (ns, done)) or True)
    client.set_cookie("intel_auth", "")           # 비로그인 → 거부
    assert client.post("/api/nurse_cart/ocr_done").status_code == 401
    client.set_cookie("intel_auth", "STAFFTOK")
    assert client.post("/api/nurse_cart/ocr_done").status_code == 200
    assert seen["v"][1] is True


def test_nurse_cart_round_done_staff(monkeypatch):
    monkeypatch.setattr(flask_app.fb_read, "set_round_done", lambda ns, done=True: True)
    client.set_cookie("intel_auth", "")
    assert client.post("/api/nurse_cart/round_done").status_code == 401
    client.set_cookie("intel_auth", "STAFFTOK")
    assert client.post("/api/nurse_cart/round_done").status_code == 200


def test_nurse_cart_phase_public(monkeypatch):
    monkeypatch.setattr(flask_app.fb_read, "get_nurse_cart_phase", lambda ns: "tracking")
    client.set_cookie("intel_auth", "")           # 비로그인도 허용
    r = client.get("/api/nurse_cart/phase")
    assert r.status_code == 200 and r.get_json()["phase"] == "tracking"
