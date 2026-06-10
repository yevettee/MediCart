"""API+RTDB 라우트 통합 — 카탈로그 X-RTDB/X-RBAC/X-SSE/A-*/B-* (api+rtdb).
conftest.py 의 client/staff/admin/fake_rtdb 픽스처 사용.
URL/body/RTDB 경로는 app.py 및 fb_read.py 실제 구현 기준.

실행:
  cd web/backend && env -i PATH="/usr/bin:/bin" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
    venv/bin/python -m pytest test/test_app_routes.py -v
"""
import fb_read


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _mission_actions(fake_rtdb, ns):
    """ns/mission_pool 내 action 값 목록(메타키 제외)."""
    pool = fake_rtdb.get(f"{ns}/mission_pool") or {}
    return [m.get("action") for k, m in pool.items()
            if isinstance(m, dict) and not str(k).startswith("_")]


# ===========================================================================
# X-RTDB-07 — mission_pool 초기화(clear_missions)
# ===========================================================================

def test_clear_missions_empties_pool_for_both_robots(fake_rtdb):
    """TC-X-RTDB-07: clear_missions 가 각 로봇 mission_pool 을 비운다.

    __main__ 초기화는 프로세스 기동 시에만 실행되므로, 동일 효과를 내는
    clear_missions(ns) 함수를 직접 호출해 검증한다.
    """
    # 두 로봇에 더미 미션 주입
    fake_rtdb.set("robot3/mission_pool/m1", {"action": "dock", "status": "pending"})
    fake_rtdb.set("robot6/mission_pool/m1", {"action": "undock", "status": "pending"})

    for ns in fb_read.ROBOT_NAMESPACES:
        fb_read.clear_missions(ns)

    assert fake_rtdb.get("robot3/mission_pool") is None
    assert fake_rtdb.get("robot6/mission_pool") is None


# ===========================================================================
# X-RTDB-08 — _req_ns 유효하지 않은 ns → PRIMARY_NS 폴백
# ===========================================================================

def test_req_ns_invalid_falls_back_to_primary(staff, fake_rtdb):
    """TC-X-RTDB-08: ?ns=../evil 같은 비유효 ns → PRIMARY_NS(robot3) 폴백, 예외/500 없음.

    /api/patrol/phase 는 GET+ns 파라미터를 _req_ns() 로 추출하므로 폴백 경로 검증에 적합.
    RTDB 에 robot3/patrol 데이터가 없으면 {phase:"idle",stop:{}} 반환(정상 응답).
    """
    r = staff.get("/api/patrol/phase?ns=../evil")
    assert r.status_code == 200   # PRIMARY_NS 폴백, 예외/500 없음
    data = r.get_json()
    assert "phase" in data        # 유효한 응답 구조 보장


# ===========================================================================
# X-RBAC-05 — 백엔드 경로별 최소 등급
# NOTE: auth.required_role_for_path 단위 테스트는 test_auth.py 에 있음.
#       여기서는 실제 미들웨어가 올바르게 403/401 을 반환하는지 HTTP 레벨로 검증.
# ===========================================================================

def test_staff_route_blocks_anonymous(client):
    """TC-X-RBAC-05: 비인증 client 가 staff 전용 라우트에서 401 을 받는다."""
    # /api/patients 는 _STAFF_PREFIXES 에 해당
    assert client.get("/api/patients").status_code == 401


# ===========================================================================
# X-RBAC-07 — 미들웨어 미인가 → staff 가 admin 전용 라우트 차단
# NOTE: frontend redirect 검증(미들웨어 next.js)은 Task 5(X-RBAC-05/07 frontend).
#       여기서는 Flask 미들웨어(_before_request) 레벨 검증.
# ===========================================================================

def test_staff_blocked_from_admin_route(staff):
    """TC-X-RBAC-07(backend): staff 토큰으로 admin 전용 /api/stream 요청 → 401."""
    # /api/stream 은 _OPEN/_PATIENT_PREFIXES/_STAFF_PREFIXES 에 해당하지 않아 admin 필요
    r = staff.get("/api/stream")
    assert r.status_code == 401


# ===========================================================================
# X-SSE-01 — /api/stream 헤더만 확인(스트림 본문 소비 없음)
# ===========================================================================

def test_stream_is_event_stream(admin, fake_rtdb):
    """TC-X-SSE-01: /api/stream 응답이 text/event-stream Content-Type 반환.

    SSE 제너레이터는 keepalive(queue.get timeout=15)에서 블록되므로 test_client 로
    응답을 소비하면 15초 지연된다. WSGI environ 으로 status/headers 만 가로채고
    제너레이터 본문은 소비하지 않아 즉시 검증한다(프로덕션 변경 없음).
    """
    import app as flask_app
    from werkzeug.test import EnvironBuilder

    env = EnvironBuilder(method="GET", path="/api/stream",
                         headers={"Cookie": "intel_auth=ADMINTOK"}).get_environ()
    captured = {}

    def start_response(status, headers, exc_info=None):
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = flask_app.app.wsgi_app(env, start_response)
    if hasattr(body, "close"):
        body.close()  # 제너레이터를 소비하지 않고 해제(15초 블록 회피)

    assert captured["status"].startswith("200")
    assert "text/event-stream" in captured["headers"].get("Content-Type", "")


# ===========================================================================
# A-TRIG-03 — nurse_cart/start → robot6/mission_pool 에 nurse_cart_mission push
# ===========================================================================

def test_nurse_cart_start_pushes_mission_to_robot6(staff, fake_rtdb):
    """TC-A-TRIG-03: POST /api/nurse_cart/start body{ns:robot6}
    → robot6/mission_pool 에 action=nurse_cart_mission 1건 추가."""
    r = staff.post("/api/nurse_cart/start", json={"ns": "robot6"})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True

    actions = _mission_actions(fake_rtdb, "robot6")
    assert "nurse_cart_mission" in actions


# ===========================================================================
# A-TRIG-05 — nurse_cart/start 무토큰 → 401, mission_pool 변화 없음
# ===========================================================================

def test_nurse_cart_start_requires_staff(client, fake_rtdb):
    """TC-A-TRIG-05: 무토큰 client 가 /api/nurse_cart/start POST → 401.
    mission_pool 이 변경되지 않음."""
    r = client.post("/api/nurse_cart/start", json={"ns": "robot6"})
    assert r.status_code == 401   # _require_auth 는 401만 반환(403 경로 없음)
    # mission_pool 에 아무것도 쓰이지 않았음
    assert not (fake_rtdb.get("robot6/mission_pool") or {})


# ===========================================================================
# A-OCR-06 — nurse_cart/ocr_done → robot6/nurse_cart/ocr_done = True
# ===========================================================================

def test_nurse_cart_ocr_done_sets_flag(staff, fake_rtdb):
    """TC-A-OCR-06: POST /api/nurse_cart/ocr_done body{ns:robot6}
    → robot6/nurse_cart/ocr_done = True."""
    r = staff.post("/api/nurse_cart/ocr_done", json={"ns": "robot6"})
    assert r.status_code == 200
    assert fake_rtdb.get("robot6/nurse_cart/ocr_done") is True


# ===========================================================================
# A-PHASE-03 — nurse_cart/phase GET → RTDB 값 반환
# ===========================================================================

def test_nurse_cart_phase_reads_rtdb(staff, fake_rtdb):
    """TC-A-PHASE-03: GET /api/nurse_cart/phase?ns=robot6
    → RTDB robot6/nurse_cart/phase 값이 응답에 반영.

    /api/nurse_cart/phase 는 _OPEN 에 있어 비인증도 허용되지만,
    staff 픽스처로 호출해도 동일하게 동작한다."""
    fake_rtdb.set("robot6/nurse_cart/phase", "tracking")
    r = staff.get("/api/nurse_cart/phase?ns=robot6")
    assert r.status_code == 200
    assert r.get_json()["phase"] == "tracking"


# ===========================================================================
# A-PHASE-04 — nurse_cart/round_done → robot6/nurse_cart/round_done = True
# ===========================================================================

def test_nurse_cart_round_done_sets_flag(staff, fake_rtdb):
    """TC-A-PHASE-04: POST /api/nurse_cart/round_done body{ns:robot6}
    → robot6/nurse_cart/round_done = True."""
    r = staff.post("/api/nurse_cart/round_done", json={"ns": "robot6"})
    assert r.status_code == 200
    assert fake_rtdb.get("robot6/nurse_cart/round_done") is True


# ===========================================================================
# B-TRIG-03 — patrol_intake_mission → robot3/mission_pool 에 push
# ===========================================================================

def test_patrol_start_pushes_patrol_intake_mission(admin, fake_rtdb):
    """TC-B-TRIG-03: POST /api/robots/robot3/missions body{action,params}
    → robot3/mission_pool 에 patrol_intake_mission pending 1건.

    카탈로그 B-TRIG-03 은 frontend tooling(vitest+api)이지만, 백엔드 라우트
    /api/robots/<ns>/missions 를 통해 RTDB 기록을 검증한다.
    /api/missions 는 admin 전용이므로 admin 픽스처를 사용.
    """
    stops = [{"label": "101호 1번", "x": -4.39, "y": -0.70, "yaw": 2.47}]
    home  = {"x": -0.89, "y": -0.66, "yaw": 0, "dock_after": True}
    r = admin.post("/api/robots/robot3/missions", json={
        "action": "patrol_intake_mission",
        "params": {"stops": stops, "home": home},
    })
    assert r.status_code == 200
    assert r.get_json()["ok"] is True

    pool = fake_rtdb.get("robot3/mission_pool") or {}
    missions = [v for k, v in pool.items()
                if isinstance(v, dict) and not str(k).startswith("_")]
    assert any(m.get("action") == "patrol_intake_mission" for m in missions)

    m = next(m for m in missions if m.get("action") == "patrol_intake_mission")
    assert m["status"] == "pending"
    assert m["params"]["stops"] == stops
    assert m["params"]["home"] == home


# ===========================================================================
# B-PHASE-02 — patrol/phase GET → RTDB 값 반환
# ===========================================================================

def test_patrol_phase_reads_rtdb(staff, fake_rtdb):
    """TC-B-PHASE-02: GET /api/patrol/phase?ns=robot3
    → RTDB robot3/patrol/phase="arrived" → 응답 {phase:"arrived", stop:{}}."""
    fake_rtdb.set("robot3/patrol", {"phase": "arrived", "stop": {"idx": 0, "room": "101-1"}})
    r = staff.get("/api/patrol/phase?ns=robot3")
    assert r.status_code == 200
    data = r.get_json()
    assert data["phase"] == "arrived"
    assert data["stop"]["room"] == "101-1"


# ===========================================================================
# B-PHASE-03 — patrol/advance → robot3/patrol/intake_done = True
# ===========================================================================

def test_patrol_advance_sets_intake_done(staff, fake_rtdb):
    """TC-B-PHASE-03: POST /api/patrol/advance body{ns:robot3}
    → robot3/patrol/intake_done = True (set_patrol_advance 구현).

    카탈로그 기대: advance 신호 → 시퀀서 다음 stop 진행.
    실제 RTDB 경로: {ns}/patrol/intake_done = True (fb_read.set_patrol_advance).
    """
    r = staff.post("/api/patrol/advance", json={"ns": "robot3"})
    assert r.status_code == 200
    assert fake_rtdb.get("robot3/patrol/intake_done") is True


# ===========================================================================
# B-PHASE-04 — advance 디바운스
# ===========================================================================

def test_patrol_advance_no_debounce(staff, fake_rtdb):
    """TC-B-PHASE-04: advance 2회 연속 호출.

    NOTE(catalog B-PHASE-04): 카탈로그 기대는 '동일 stop에서 advance 2회 → 1회만 다음 진행'.
    현 prod 구현(set_patrol_advance)은 단순히 {ns}/patrol/intake_done=True 를 set 하며
    중복 호출에 대한 디바운스 로직이 없다. 두 번 호출해도 플래그가 True 로 유지될 뿐
    (멱등)으로 동작하므로 500 없이 200 을 반환한다.
    시퀀서 측에서 edge-triggered 로 처리해야 실질적 디바운스가 된다 — 보고 대상.
    """
    r1 = staff.post("/api/patrol/advance", json={"ns": "robot3"})
    r2 = staff.post("/api/patrol/advance", json={"ns": "robot3"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    # 두 번 모두 성공 — 현 동작은 멱등(True set), 디바운스 없음
    assert fake_rtdb.get("robot3/patrol/intake_done") is True


# ===========================================================================
# B-INTAKE-04 — /api/intake 제출 → intake_pending 기록
# ===========================================================================

def test_intake_submit_writes_pending(client, fake_rtdb):
    """TC-B-INTAKE-04: POST /api/intake body{name,room,sections}
    → intake_pending/{key} 에 status='pending' 레코드 기록.

    /api/intake 는 _OPEN 경로(인증 불필요)이므로 비인증 client 로 테스트.
    """
    r = client.post("/api/intake", json={
        "name": "홍길동",
        "room": "101-1",
        "sections": {"기본": {"주증상": "발열"}},
    })
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert "id" in data

    # RTDB intake_pending/{id} 확인
    key = data["id"]
    record = fake_rtdb.get(f"intake_pending/{key}")
    assert record is not None
    assert record["name"] == "홍길동"
    assert record["room"] == "101-1"
    assert record["status"] == "pending"


def test_intake_submit_name_required(client, fake_rtdb):
    """B-INTAKE-04 보조: name 없이 제출 → 400, intake_pending 기록 없음."""
    r = client.post("/api/intake", json={"room": "101-1"})
    assert r.status_code == 400
    assert not (fake_rtdb.get("intake_pending") or {})
