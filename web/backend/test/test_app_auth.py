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
