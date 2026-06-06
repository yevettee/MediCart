#!/usr/bin/env python3
"""app — 병동 보조 로봇 웹 백엔드 (Flask).

PC3에서 PC1/PC2 두 Redis + 환자 데이터를 읽어 REST + SSE로 프론트(Next.js)에 제공.
실행: venv/bin/python app.py  (기본 0.0.0.0:5000)
"""
import os
import re

import yaml
from flask import Flask, Response, jsonify, request, send_file
from flask_cors import CORS

import patient_data
import redis_bus

HERE = os.path.dirname(os.path.abspath(__file__))
# 등록번호 형식 검증 — 키 주입·IDOR 방지 (P-YYYY-NNNN)
_PID_RE = re.compile(r"^P-\d{4}-\d{4}$")
_FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")

# ── 데모 비밀번호 게이트 ─────────────────────────────────────────────────────
# 단일 공유 비밀번호. 맞으면 서버가 쿠키(AUTH_TOKEN)를 발급하고, Next 미들웨어와
# 이 Flask가 같은 쿠키를 검증한다. 공개 호스팅(터널) 앞단 접근 통제용(데모 수준).
INTEL_PASSWORD = os.environ.get("INTEL_PASSWORD", "rokey1234")
AUTH_COOKIE    = "intel_auth"
AUTH_TOKEN     = os.environ.get("INTEL_AUTH_TOKEN", "intel-demo-token-2026")
COOKIE_SECURE  = os.environ.get("COOKIE_SECURE", "0") == "1"   # https(터널)면 1
_OPEN_PATHS    = {"/api/health", "/api/login", "/api/me"}      # 인증 없이 허용

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024   # 문진표 본문 상한 256KB
# CORS: 프론트 오리진만 허용 + 쿠키 자격증명(로그인 쿠키). 와일드카드 금지.
CORS(app, resources={r"/api/*": {"origins": [_FRONTEND_ORIGIN]}}, supports_credentials=True)


@app.before_request
def _require_auth():
    if request.method == "OPTIONS" or request.path in _OPEN_PATHS:
        return None
    if not request.path.startswith("/api/"):
        return None
    if request.cookies.get(AUTH_COOKIE) != AUTH_TOKEN:
        return jsonify({"error": "auth required"}), 401
    return None


# 맵 파일 위치(있으면 서빙). 없으면 available:false.
MAP_PNG  = os.environ.get("MAP_PNG",  "/home/rokey/rokey_ws/src/intel1/common/maps/ward_map.png")
MAP_YAML = os.environ.get("MAP_YAML", "/home/rokey/rokey_ws/src/intel1/common/maps/ward_map.yaml")


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


# ── 인증 ────────────────────────────────────────────────────────────────────
@app.post("/api/login")
def login():
    body = request.get_json(force=True, silent=True) or {}
    if str(body.get("password") or "") != INTEL_PASSWORD:
        return jsonify({"ok": False, "error": "비밀번호가 올바르지 않습니다"}), 401
    resp = jsonify({"ok": True})
    resp.set_cookie(AUTH_COOKIE, AUTH_TOKEN, max_age=60 * 60 * 12,
                    httponly=True, samesite="Lax", secure=COOKIE_SECURE)
    return resp


@app.post("/api/logout")
def logout():
    resp = jsonify({"ok": True})
    resp.delete_cookie(AUTH_COOKIE, samesite="Lax", secure=COOKIE_SECURE)
    return resp


@app.get("/api/me")
def me():
    return jsonify({"authed": request.cookies.get(AUTH_COOKIE) == AUTH_TOKEN})


# ── 환자 ────────────────────────────────────────────────────────────────────
@app.get("/api/patients")
def patients():
    return jsonify(patient_data.load_patients())


@app.get("/api/patients/<pid>")
def patient(pid):
    if not _PID_RE.match(pid):
        return jsonify({"error": "invalid id"}), 400
    p = patient_data.get_patient(pid)
    if not p:
        return jsonify({"error": "not found"}), 404
    p = dict(p)
    p["intake"] = redis_bus.get_intake(pid)   # 저장된 문진표(있으면)
    return jsonify(p)


# ── AMR 상태/스트림 ──────────────────────────────────────────────────────────
@app.get("/api/amrs")
def amrs():
    return jsonify(redis_bus.snapshots())


@app.get("/api/stream")
def stream():
    return Response(redis_bus.telemetry_stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/alerts")
def alerts():
    return Response(redis_bus.alert_stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/mode")
def mode_cmd():
    body = request.get_json(force=True, silent=True) or {}
    try:
        redis_bus.publish_mode_cmd(body.get("action"), body.get("mode"), body.get("params"))
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True})


# ── 문진표 저장 ──────────────────────────────────────────────────────────────
@app.post("/api/intake")
def intake():
    body = request.get_json(force=True, silent=True) or {}
    pid = str(body.get("patientId") or "")
    # 형식 검증 + 실제 환자 명부에 존재해야 저장(임의 키 쓰기·존재하지 않는 환자 차단)
    if not _PID_RE.match(pid) or patient_data.get_patient(pid) is None:
        return jsonify({"error": "invalid or unknown patientId"}), 400
    redis_bus.save_intake(pid, body)
    return jsonify({"ok": True, "patientId": pid})


# ── 병실→pose + 맵 ───────────────────────────────────────────────────────────
@app.get("/api/rooms")
def rooms():
    with open(os.path.join(HERE, "rooms.yaml")) as f:
        return jsonify(yaml.safe_load(f) or {})


@app.get("/api/map")
def map_meta():
    if not (MAP_YAML and os.path.exists(MAP_YAML) and os.path.exists(MAP_PNG)):
        return jsonify({"available": False})
    try:
        with open(MAP_YAML) as f:
            y = yaml.safe_load(f) or {}
        return jsonify({
            "available": True,
            "resolution": float(y.get("resolution", 0.05)),
            "origin": [float(v) for v in (y.get("origin") or [0, 0, 0])],
        })
    except (OSError, ValueError, yaml.YAMLError):
        return jsonify({"available": False})


@app.get("/api/map.png")
def map_png():
    if os.path.exists(MAP_PNG):
        return send_file(MAP_PNG, mimetype="image/png")
    return jsonify({"error": "no map"}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), threaded=True)
