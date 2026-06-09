#!/usr/bin/env python3
"""app — 병동 보조 로봇 웹 백엔드 (Flask).

Firebase RTDB + 환자 데이터를 읽어 REST + SSE로 프론트(Next.js)에 제공.
실행: venv/bin/python app.py  (기본 0.0.0.0:5000)
"""
import hmac
import os
import re
import sys

import yaml
from flask import Flask, Response, jsonify, request, send_file
from flask_cors import CORS

import auth
import patients as patient_store
import fb_read
import ocr

# ── 약품명 매칭 (한글→영문 별명) ────────────────────────────────────────────────
_MEDICINE_ALIASES: dict[str, list[str]] = {
    "호르몬 주사": ["hormone", "insulin", "estrogen", "testosterone", "hgh", "growth hormone"],
    "비타민 주사": ["vitamin", "ascorbic", "riboflavin", "thiamine", "b12", "vit"],
    "스테로이드 주사": ["steroid", "dexamethasone", "methylprednisolone", "hydrocortisone", "prednisolone"],
    "항생제": ["antibiotic", "amoxicillin", "penicillin", "cephalosporin", "ciprofloxacin"],
    "진통제": ["painkiller", "analgesic", "acetaminophen", "ibuprofen", "morphine", "tramadol"],
    "수액": ["saline", "dextrose", "lactated", "ringer", "ns", "d5w", "normal saline"],
    "항암제": ["chemotherapy", "taxol", "cisplatin", "doxorubicin", "vincristine"],
}


def _check_medicine(prescription: str, ocr_text: str) -> tuple[bool, str]:
    """처방 약품명이 OCR 텍스트에 포함되는지 확인 (한글·영문 별명 모두 허용)."""
    prx = " ".join(prescription.split()).lower()
    # 줄바꿈·연속 공백을 단일 공백으로 정규화 (OCR이 줄바꿈으로 단어를 쪼갤 수 있음)
    ocr_normalized = " ".join(ocr_text.split()).lower()
    # 공백 제거 버전도 준비 (붙여쓰기 대응)
    ocr_nospace = re.sub(r"\s+", "", ocr_normalized)
    prx_nospace = re.sub(r"\s+", "", prx)

    # 직접 포함 여부 (정규화 + 공백제거 둘 다 시도)
    if prx in ocr_normalized or prx_nospace in ocr_nospace:
        return True, f"'{prescription}' 직접 확인됨"

    ocr = ocr_normalized

    # 한글 별명 그룹 검색
    for kor_name, aliases in _MEDICINE_ALIASES.items():
        group_names = [kor_name.lower()] + [a.lower() for a in aliases]
        prx_in_group = any(g in prx or prx in g for g in group_names)
        if prx_in_group:
            for alias in aliases:
                if alias in ocr:
                    return True, f"'{prescription}' → '{alias}' 별명 확인됨"
            # 처방이 이 그룹에 속하지만 OCR에서 못 찾은 경우
            break

    return False, f"'{prescription}'을(를) OCR 텍스트에서 확인할 수 없습니다"

HERE = os.path.dirname(os.path.abspath(__file__))
# 등록번호 형식 검증 — 키 주입·IDOR 방지 (P-YYYY-NNNN)
_PID_RE = re.compile(r"^P-\d{4}-\d{4}$")
_FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000,http://localhost:3001")


# ── 데모 비밀번호 게이트 ─────────────────────────────────────────────────────
# 단일 공유 비밀번호. 맞으면 서버가 쿠키(AUTH_TOKEN)를 발급하고, Next 미들웨어와
# 이 Flask가 같은 쿠키를 검증한다. 공개 호스팅(터널) 앞단 접근 통제용(데모 수준).
# 비밀번호·토큰은 env 필수(.env 참고) — 소스에 기본값 하드코딩하지 않는다.
INTEL_PASSWORD = os.environ.get("INTEL_PASSWORD")
ADMIN_PASSWORD = os.environ.get("INTEL_ADMIN_PASSWORD")
AUTH_COOKIE    = "intel_auth"
AUTH_TOKEN     = os.environ.get("INTEL_AUTH_TOKEN")
ADMIN_TOKEN    = os.environ.get("INTEL_ADMIN_TOKEN")
COOKIE_SECURE  = os.environ.get("COOKIE_SECURE", "0") == "1"   # https(터널)면 1
_OPEN_PATHS    = {"/api/health", "/api/login", "/api/me", "/api/intake", "/api/display/current"}  # 인증 없이 허용
if not INTEL_PASSWORD or not AUTH_TOKEN:
    sys.exit("INTEL_PASSWORD / INTEL_AUTH_TOKEN 환경변수를 설정하세요 (.env.example 참고)")


def _ct_eq(a, b):
    """타이밍-세이프 문자열 비교."""
    return hmac.compare_digest(str(a or ""), str(b or ""))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024   # 이미지 업로드 허용(OCR)
# CORS: 프론트 오리진만 허용 + 쿠키 자격증명(로그인 쿠키). 와일드카드 금지.
_ALLOWED_ORIGINS = [o.strip() for o in _FRONTEND_ORIGIN.split(",") if o.strip()]
CORS(app, resources={r"/api/*": {"origins": _ALLOWED_ORIGINS}}, supports_credentials=True)


@app.before_request
def _require_auth():
    if request.method == "OPTIONS" or not request.path.startswith("/api/"):
        return None
    role = auth.role_for_token(request.cookies.get(AUTH_COOKIE), AUTH_TOKEN, ADMIN_TOKEN)
    if not auth.allowed(role, auth.required_role_for_path(request.path)):
        return jsonify({"error": "auth required"}), 401
    return None


# 맵 파일 위치(있으면 서빙). 없으면 available:false.
MAP_PNG  = os.environ.get("MAP_PNG",  "/home/rokey/MediCart/common/maps/ward_map.png")
MAP_YAML = os.environ.get("MAP_YAML", "/home/rokey/MediCart/common/maps/ward_map.yaml")


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


# ── 인증 ────────────────────────────────────────────────────────────────────
@app.post("/api/login")
def login():
    body = request.get_json(force=True, silent=True) or {}
    role = auth.role_for_password(body.get("password"), INTEL_PASSWORD, ADMIN_PASSWORD)
    if role is None:
        return jsonify({"ok": False, "error": "비밀번호가 올바르지 않습니다"}), 401
    resp = jsonify({"ok": True, "role": role})
    resp.set_cookie(AUTH_COOKIE, auth.token_for_role(role, AUTH_TOKEN, ADMIN_TOKEN),
                    max_age=60 * 60 * 12, httponly=True, samesite="Lax", secure=COOKIE_SECURE)
    return resp


@app.post("/api/logout")
def logout():
    resp = jsonify({"ok": True})
    resp.delete_cookie(AUTH_COOKIE, samesite="Lax", secure=COOKIE_SECURE)
    return resp


@app.get("/api/me")
def me():
    role = auth.role_for_token(request.cookies.get(AUTH_COOKIE), AUTH_TOKEN, ADMIN_TOKEN)
    return jsonify({"authed": role != "patient", "role": role})


@app.post("/api/intake")
def intake_submit():
    body = request.get_json(force=True, silent=True) or {}
    if not str(body.get("name") or "").strip():
        return jsonify({"ok": False, "error": "성명을 입력하세요"}), 400
    key, payload = fb_read.add_intake_pending(body)
    return jsonify({"ok": True, "id": key, "intake": payload})


# ── 환자 ────────────────────────────────────────────────────────────────────
@app.get("/api/patients")
def patients():
    return jsonify(patient_store.load_patients())


@app.get("/api/patients/<pid>")
def patient(pid):
    if not _PID_RE.match(pid):
        return jsonify({"error": "invalid id"}), 400
    p = patient_store.get_patient(pid)
    if not p:
        return jsonify({"error": "not found"}), 404
    p = dict(p)
    p["intake"] = fb_read.get_intake(pid)   # 저장된 문진표(있으면)
    return jsonify(p)


# ── 주사/투약 검증 ────────────────────────────────────────────────────────────
@app.get("/api/patients/<pid>/injections")
def patient_injections(pid):
    if not _PID_RE.match(pid):
        return jsonify({"error": "invalid id"}), 400
    inj = fb_read.get_injections(pid)
    return jsonify(inj)


@app.post("/api/patients/<pid>/injections/<inj_id>/verify")
def verify_injection(pid, inj_id):
    if not _PID_RE.match(pid):
        return jsonify({"error": "invalid id"}), 400
    body = request.get_json(force=True, silent=True) or {}
    ocr_text = str(body.get("ocr_text", "")).strip()
    prescription = str(body.get("prescription", "")).strip()
    if not ocr_text or not prescription:
        return jsonify({"error": "ocr_text and prescription are required"}), 400

    match, reason = _check_medicine(prescription, ocr_text)
    status = "confirmed" if match else "mismatch"
    try:
        fb_read.update_injection_status(pid, inj_id, status, ocr_text)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"ok": True, "match": match, "status": status, "reason": reason})


@app.post("/api/patients/<pid>/injections/<inj_id>/confirm")
def confirm_injection(pid, inj_id):
    """QR 환자 확인 — 처방 완료를 DB에 직접 기록."""
    if not _PID_RE.match(pid):
        return jsonify({"error": "invalid id"}), 400
    try:
        fb_read.update_injection_status(pid, inj_id, "confirmed", "QR 환자 확인")
    except Exception as e:                      # noqa: BLE001
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True, "status": "confirmed"})


# ── AMR 상태/스트림 ──────────────────────────────────────────────────────────
@app.get("/api/amrs")
def amrs():
    return jsonify(fb_read.snapshots())


@app.get("/api/stream")
def stream():
    return Response(fb_read.telemetry_stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/alerts")
def alerts():
    return Response(fb_read.alert_stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/robots/<ns>/missions/clear")
def clear_robot_missions(ns):
    fb_read.clear_missions(ns)
    return jsonify({"ok": True})


@app.get("/api/robots/health")
def robots_health():
    return jsonify(fb_read.robots_health())


@app.post("/api/camera/<ns>/request")
def camera_request(ns):
    body = request.get_json(silent=True) or {}
    fb_read.camera_request(ns, bool(body.get("on")))
    return jsonify({"ok": True})


@app.get("/api/camera/<ns>/stream")
def camera_stream(ns):
    return Response(fb_read.camera_stream(ns), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/logs/<ns>")
def robot_logs(ns):
    return jsonify({"logs": fb_read.logs(ns)})


@app.get("/api/logs/<ns>/stream")
def robot_logs_stream(ns):
    return Response(fb_read.log_stream(ns), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/mode")
def mode_cmd():
    body = request.get_json(force=True, silent=True) or {}
    try:
        fb_read.publish_mode_cmd(body.get("action"), body.get("mode"), body.get("params"))
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True})


# ── 문진표 → 새 외래방문 기록 ─────────────────────────────────────────────────
@app.post("/api/patients/<pid>/visits")
def add_visit(pid):
    # 형식 검증 + 실제 환자 존재해야 추가(임의 키 쓰기·존재하지 않는 환자 차단)
    if not _PID_RE.match(pid) or patient_store.get_patient(pid) is None:
        return jsonify({"error": "invalid or unknown patientId"}), 400
    body = request.get_json(force=True, silent=True) or {}
    visit = fb_read.add_visit(pid, body)
    return jsonify({"ok": True, "patientId": pid, "visit": visit})


# ── 환자 정보 직접 수정(info/vitals 부분 갱신) ────────────────────────────────
@app.put("/api/patients/<pid>")
def update_patient(pid):
    if not _PID_RE.match(pid) or patient_store.get_patient(pid) is None:
        return jsonify({"error": "invalid or unknown patientId"}), 400
    body = request.get_json(force=True, silent=True) or {}
    fb_read.update_patient(pid, body.get("info"), body.get("vitals"))
    return jsonify(patient_store.get_patient(pid))


# ── 병실 디스플레이 현재 환자 ────────────────────────────────────────────────────
@app.get("/api/display/current")
def display_current():
    pid = fb_read.get_display_patient()
    return jsonify({"pid": pid})


@app.post("/api/display/current")
def display_set():
    body = request.get_json(force=True, silent=True) or {}
    pid = str(body.get("pid", "")).strip()
    if not _PID_RE.match(pid):
        return jsonify({"error": "invalid id"}), 400
    fb_read.set_display_patient(pid)
    return jsonify({"ok": True, "pid": pid})


# ── OCR ─────────────────────────────────────────────────────────────────────
@app.post("/api/ocr")
def api_ocr():
    f = request.files.get("image")
    if f is None:
        return jsonify({"error": "no image"}), 400
    data = f.read()
    if not data:
        return jsonify({"error": "empty image"}), 400
    text = ocr.recognized_text(data)
    try:
        fb_read.set_ocr(text)
    except Exception:
        pass   # OCR 표시는 유지, RTDB 기록 실패는 비치명
    return jsonify({"text": text})


@app.post("/api/ocr/done")
def ocr_done():
    """OCR 완료 버튼 → {ns}/nurse_cart/ocr_done = true (기본 robot6). staff 권한."""
    body = request.get_json(silent=True) or {}
    fb_read.set_ocr_done(body.get("ns") or "robot6", True)
    return jsonify({"ok": True})


# ── 로봇 명령 하달 (mission_pool, ROS 노드 통신 없음) ─────────────────────────
@app.post("/api/robots/<ns>/missions")
def robot_mission(ns):
    body = request.get_json(force=True, silent=True) or {}
    try:
        mid, mission = fb_read.push_mission(
            ns, body.get("action"), body.get("params"), body.get("mode"))
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "id": mid, "mission": mission})


@app.get("/api/robots/<ns>/missions")
def robot_missions(ns):
    return jsonify({"missions": fb_read.get_missions(ns)})


# ── 순회 대상 ────────────────────────────────────────────────────────────────
@app.get("/api/targets")
def targets():
    return jsonify({"targets": fb_read.get_targets()})


# ── 병실→pose + 맵 ───────────────────────────────────────────────────────────
@app.get("/api/rooms")
def rooms():
    fb_read._init()
    from fb_read import _db
    return jsonify({"rooms": _db.reference("rooms").get() or {}})


# ── 순회 문진 (회차 플래그) ───────────────────────────────────────────────────
@app.post("/api/patrol/reset")
def patrol_reset():
    return jsonify({"ok": True, "count": fb_read.reset_intake_flags()})


@app.post("/api/patrol/intake-done")
def patrol_intake_done():
    body = request.get_json(force=True, silent=True) or {}
    if fb_read.mark_intake_done(str(body.get("pid") or "")):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "invalid pid"}), 400


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


try:
    if fb_read.seed_targets():
        print("[app] RTDB targets 시드 완료")
except Exception as exc:        # noqa: BLE001 — 시드 실패해도 서비스는 계속
    print(f"[app] targets 시드 건너뜀: {exc}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), threaded=True)
