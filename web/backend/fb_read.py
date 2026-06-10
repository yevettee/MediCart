"""fb_read — Flask 백엔드의 Firebase RTDB 경계 (redis_bus.py 대체).

순수 로직(토픽별 노드→snapshot 조립·병합·검증·cmd 페이로드)은 firebase/Flask 무관이라 단위테스트한다.
firebase-admin 결선(리스너→SSE·get·cmd set·intake)은 같은 모듈에 있다.
프론트는 이 백엔드의 SSE/REST만 쓰고 RTDB를 직접 만지지 않는다.

RTDB 레이아웃: 최상위 robot3/robot6 노드에 ward_bridge가 구독하는 토픽 basename이 키로 들어온다
(amcl_pose/odom/scan/battery_state/dock_status/imu/robot_mode + online/stamp, 제어=cmd, 이벤트=alerts).
이 모듈이 토픽별 노드를 프론트가 쓰는 평탄 snapshot(pose/vel/battery/dock/imu/scan/mode/...)으로 조립한다.
"""
import os
import re

# NS는 common/robot.env(단일 소스)의 ROBOT_NAMESPACE를 따른다(PRIMARY_NS로 명시 override 가능).
# 웹은 두 AMR(robot3·robot6)을 모두 보여주므로 SECONDARY는 PRIMARY의 나머지로 자동 도출.
_PRIMARY = (os.environ.get("PRIMARY_NS") or os.environ.get("ROBOT_NAMESPACE") or "robot3").strip("/")
_COMPLEMENT = {"robot3": "robot6", "robot6": "robot3"}.get(_PRIMARY, "robot6")
PRIMARY_NS = _PRIMARY
SECONDARY_NS = (os.environ.get("SECONDARY_NS") or _COMPLEMENT).strip("/")
SOURCES = [PRIMARY_NS, SECONDARY_NS]

_PID_RE = re.compile(r"^P-\d{4}-\d{4}$")
_MODE_RE = re.compile(r"^(mapping|patrol|errand|guide|intake|round)$")
_ACTION_RE = re.compile(r"^(start|stop|clear)$")

# RTDB 토픽 basename → 프론트 snapshot 필드 (ward_bridge.state_payload 와 짝)
_TOPIC_TO_FIELD = {
    "amcl_pose":     "pose",
    "odom":          "vel",
    "battery_state": "battery",
    "dock_status":   "dock",
    "imu":           "imu",
    "scan":          "scan",
}


def valid_pid(pid):
    return bool(_PID_RE.match(str(pid)))


def topics_to_snapshot(node):
    """RTDB {ns} 토픽별 노드 → 프론트 평탄 snapshot. 토픽 데이터 없으면 None.

    amcl_pose→pose, odom→vel, battery_state→battery, dock_status→dock, imu→imu, scan→scan,
    robot_mode→mode. online/stamp 는 그대로 전달. cmd/alerts 같은 비-토픽 키는 무시.
    """
    if not isinstance(node, dict):
        return None
    snap = {}
    for topic, field in _TOPIC_TO_FIELD.items():
        if topic in node:
            snap[field] = node[topic]
    has_topic = bool(snap)
    snap["mode"] = node.get("robot_mode", "idle")
    snap["online"] = bool(node.get("online", False))
    snap["stamp"] = node.get("stamp", 0)
    # 센서 토픽이 하나도 없고 stamp 도 없으면(예: cmd 만 있는 노드) 미존재로 취급
    if not has_topic and not node.get("stamp"):
        return None
    return snap


def merge_snapshots(per_ns_raw, sources):
    """{ns: 토픽별 노드|None} → {src: snapshot(+source)|None}."""
    raw = per_ns_raw or {}
    out = {}
    for src in sources:
        node = raw.get(src) if isinstance(raw, dict) else None
        snap = topics_to_snapshot(node)
        if snap is not None:
            snap["source"] = src
        out[src] = snap
    return out


def cmd_payload(action, mode, params, ts):
    """웹→로봇 명령 페이로드 빌드(화이트리스트 검증). {ns}/cmd 에 set 될 dict."""
    if not _ACTION_RE.match(str(action)):
        raise ValueError("invalid action")
    if action != "clear" and not _MODE_RE.match(str(mode or "")):
        raise ValueError("invalid mode")
    return {"action": action, "mode": mode, "params": params or {}, "ts": int(ts)}


# ── 환자 외래방문/수정 페이로드(순수) ──────────────────────────────────────────
_KEY_BAD = re.compile(r"[/.#$\[\]]")          # RTDB 키 금지문자
# 문진/생체징후 중 숫자로 저장할 키(상세 페이지가 Number()로 비교) — 빈문자열은 제외
_NUMERIC_KEYS = {"수축기혈압", "이완기혈압", "맥박", "호흡", "체온", "SpO2",
                 "통증점수", "신장(cm)", "체중(kg)", "나이", "BMI"}
# visit 레코드에서 추려 vitals(최근 생체징후)로도 반영할 키
VISIT_VITALS_KEYS = ["수축기혈압", "이완기혈압", "맥박", "호흡", "체온", "SpO2",
                     "통증점수", "통증부위", "의식상태", "낙상위험"]


def _safe_key(k):
    return _KEY_BAD.sub("_", str(k))


def _coerce(key, value):
    """숫자 키는 가능하면 int/float 로(빈값·비숫자는 원본 유지)."""
    if key in _NUMERIC_KEYS and isinstance(value, str) and value.strip():
        try:
            f = float(value)
            return int(f) if f.is_integer() else f
        except ValueError:
            return value
    return value


def sanitize_fields(data):
    """입력 dict → RTDB 안전 키 + 숫자 보정. patientId 등 제어키는 제외."""
    out = {}
    for k, v in (data or {}).items():
        if k in ("patientId", "id", "등록번호"):
            continue
        sk = _safe_key(k)
        out[sk] = _coerce(sk, v)
    return out


def visit_payload(pid, data):
    """문진 입력 → 외래방문 기록 dict(키 정제·숫자 보정·등록번호 주입)."""
    out = sanitize_fields(data)
    out["등록번호"] = pid
    return out


def vitals_from_visit(visit):
    """visit 레코드에서 생체징후 부분만 추출(최근 생체징후 노드 갱신용)."""
    return {k: visit[k] for k in VISIT_VITALS_KEYS if k in visit}


# ── mission_pool (웹→로봇 DB 명령 하달, ROS 노드 통신 없음) ────────────────────
ROBOT_NAMESPACES = ("robot3", "robot6")
MISSION_ACTIONS = ("shutdown", "reboot", "ros_restart", "dock", "undock",
                   "nurse_cart_mission", "patrol_intake_mission")           # 시스템(momentary)
MODE_ACTIONS = ("start", "stop", "clear")                                   # 모드 중재(continuous)
MODE_NAMES = ("round", "patrol", "errand", "guide", "intake")               # mission_manager 모드


def valid_robot_ns(ns):
    return ns in ROBOT_NAMESPACES


def _validate_goto_params(params):
    """goto params 검증·정규화 → {x,y,yaw,(dock_after),(label)}."""
    if not isinstance(params, dict):
        raise ValueError("goto params required")
    try:
        x = float(params["x"])
        y = float(params["y"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("goto requires numeric x,y")
    out = {"x": x, "y": y, "yaw": float(params.get("yaw", 0.0))}
    if params.get("dock_after"):
        out["dock_after"] = True
    if params.get("label"):
        out["label"] = str(params["label"])[:60]
    return out


def mission_payload(action, params, ts, mode=None):
    """{ns}/mission_pool 에 push 될 명령(화이트리스트 검증).

    두 종류: 시스템 액션(dock/undock/…, mode 없음) 또는 모드 액션(start/stop/clear + mode).
    clear 는 mode 불요(전체 모드 해제).
    """
    if action in MISSION_ACTIONS:
        return {"action": action, "params": params or {}, "status": "pending", "ts": int(ts)}
    if action == "goto":
        return {"action": "goto", "params": _validate_goto_params(params),
                "status": "pending", "ts": int(ts)}
    if action in MODE_ACTIONS:
        if action != "clear" and mode not in MODE_NAMES:
            raise ValueError("invalid mode")
        out = {"action": action, "params": params or {}, "status": "pending", "ts": int(ts)}
        if mode:
            out["mode"] = mode
        return out
    raise ValueError("invalid action")


def list_missions(pool_raw):
    """mission_pool get() 결과 → 최신순 리스트(_meta 등 '_' 키 제외, id 주입)."""
    raw = pool_raw or {}
    if not isinstance(raw, dict):
        return []
    out = [dict(v, id=k) for k, v in raw.items()
           if not k.startswith("_") and isinstance(v, dict)]
    out.sort(key=lambda m: m.get("ts", 0), reverse=True)
    return out


# ---------------------------------------------------------------------------
# firebase-admin 결선 (Task 3)
# ---------------------------------------------------------------------------
import json
import queue
import time

_db = None


def _init():
    global _db
    if _db is not None:
        return _db
    import firebase_admin
    from firebase_admin import credentials, db
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            credentials.Certificate(os.environ["FB_CRED"]),
            {"databaseURL": os.environ["FB_DB_URL"]})
    _db = db
    return _db


def snapshots():
    """두 AMR 최신 스냅샷 {src: snapshot|None}. (RTDB 최상위 {ns} 노드 각 1회 읽기)"""
    db = _init()
    raw = {s: db.reference(s).get() for s in SOURCES}
    return merge_snapshots(raw, SOURCES)


def _drain(q):
    """SSE 제너레이터 공통 루프 — 큐에서 꺼내 data 프레임으로, 비면 keepalive."""
    while True:
        try:
            yield f"data: {q.get(timeout=15)}\n\n"
        except queue.Empty:
            yield ": keepalive\n\n"


def telemetry_stream():
    """{ns} 노드 변경 → 토픽별 노드를 평탄 snapshot으로 조립해 push(source 주입).

    어떤 토픽이 갱신되든 그 ns 전체를 재조립해 일관된 snapshot을 보낸다(부분 갱신 누락 방지).
    """
    db = _init()
    q = queue.Queue(maxsize=200)

    def _mk(src):
        ref = db.reference(src)
        def _on(event):
            if event.data is None:
                return
            snap = topics_to_snapshot(ref.get())
            if snap is None:
                return
            snap["source"] = src
            try:
                q.put(json.dumps(snap, separators=(",", ":")), block=False)
            except queue.Full:
                pass
        return _on

    for src in SOURCES:
        db.reference(src).listen(_mk(src))
    return _drain(q)


def _valid_ns(ns):
    ns = str(ns or "").strip("/")
    return ns if ns in SOURCES else PRIMARY_NS


def logs(ns):
    """{ns}/logs 최신순 리스트(amr_bridge 가 /rosout WARN+ 를 적재). 없으면 []."""
    return _init().reference(f"{_valid_ns(ns)}/logs").get() or []


def log_stream(ns):
    """{ns}/logs 변경 → 전체 리스트(최신순)를 SSE push."""
    db = _init()
    src = _valid_ns(ns)
    q = queue.Queue(maxsize=50)
    ref = db.reference(f"{src}/logs")

    def _on(event):
        try:
            q.put(json.dumps(ref.get() or [], separators=(",", ":")), block=False)
        except queue.Full:
            pass

    ref.listen(_on)
    return _drain(q)


def clear_missions(ns):
    """{ns}/mission_pool 을 통째로 비운다(관리자 '명령 초기화')."""
    _init().reference(f"{_valid_ns(ns)}/mission_pool").delete()
    return True


def robots_health():
    """각 로봇 {ns}/health(ping/create3/turtlebot4) 스냅샷 — amr_bridge 가 2s 갱신."""
    db = _init()
    return {s: (db.reference(f"{s}/health").get() or {}) for s in SOURCES}


def camera_request(ns, on):
    """{ns}/camera/request 에 패널 열림 하트비트 기록 — camera_bridge 송출 게이트."""
    _init().reference(f"{_valid_ns(ns)}/camera/request").set(
        {"on": bool(on), "ts": int(time.time() * 1000)})
    return True


def set_ocr_done(ns, done=True):
    """{ns}/nurse_cart/ocr_done 설정 — 웹 OCR 완료 버튼 → 로봇측 nurse_cart 신호."""
    _init().reference(f"{_valid_ns(ns)}/nurse_cart/ocr_done").set(bool(done))
    return True


def set_round_done(ns, done=True):
    """{ns}/nurse_cart/round_done 설정 — 회진 종료 버튼 → 로봇 추종 중지·홈 도킹."""
    _init().reference(f"{_valid_ns(ns)}/nurse_cart/round_done").set(bool(done))
    return True


def _phase_or_idle(v):
    """RTDB 값 → 단계 문자열(순수). 미설정/비문자열은 idle."""
    return v if isinstance(v, str) and v else "idle"


def get_nurse_cart_phase(ns):
    """{ns}/nurse_cart/phase 읽기(로봇이 기록) → idle|arrived|tracking|done."""
    return _phase_or_idle(_init().reference(f"{_valid_ns(ns)}/nurse_cart/phase").get())


def camera_stream(ns):
    """{ns}/camera 변경 → 최신 프레임(rgb/depth base64) SSE push(최신만 유지)."""
    db = _init()
    src = _valid_ns(ns)
    q = queue.Queue(maxsize=2)        # 프레임은 큼 — 최신 프레임만 유지
    ref = db.reference(f"{src}/camera")

    def _on(event):
        snap = ref.get()
        if not isinstance(snap, dict):
            return
        frame = {k: snap.get(k) for k in ("rgb", "depth", "ts", "w", "h", "src")}
        if not frame.get("rgb") and not frame.get("depth"):
            return
        data = json.dumps(frame, separators=(",", ":"))
        try:
            q.put(data, block=False)
        except queue.Full:
            try:
                q.get_nowait()
                q.put(data, block=False)
            except Exception:          # noqa: BLE001
                pass

    ref.listen(_on)
    return _drain(q)


def alert_stream():
    """{ns}/alerts push → 평탄 알림({source, ...alert})으로 push."""
    db = _init()
    q = queue.Queue(maxsize=200)

    def _emit(src, alert):
        if not isinstance(alert, dict):
            return
        try:
            q.put(json.dumps({"source": src, **alert}, separators=(",", ":")), block=False)
        except queue.Full:
            pass

    def _mk(src):
        def _on(event):
            d = event.data
            if d is None:
                return
            # 초기 스냅샷: path="/" 면 {pushid: alert} 묶음, 단일 push 면 alert dict.
            if event.path == "/" and isinstance(d, dict) and not d.get("class"):
                for alert in d.values():
                    _emit(src, alert)
            else:
                _emit(src, d)
        return _on

    for src in SOURCES:
        db.reference(f"{src}/alerts").listen(_mk(src))
    return _drain(q)


def publish_mode_cmd(action, mode, params=None):
    db = _init()
    payload = cmd_payload(action, mode, params, ts=int(time.time() * 1000))
    db.reference(f"{PRIMARY_NS}/cmd").set(payload)


def save_intake(pid, data):
    if not valid_pid(pid):
        raise ValueError("invalid patientId")
    db = _init()
    db.reference(f"patients/{pid}/intake").set(
        {"data": data, "ts": int(time.time() * 1000)})


def get_intake(pid):
    if not valid_pid(pid):
        return None
    db = _init()
    node = db.reference(f"patients/{pid}/intake").get()
    return (node or {}).get("data") if isinstance(node, dict) else None


# ── 순회 문진 회차 플래그 (patients/{pid}/intake_done) ────────────────────────
def _intake_reset_updates(raw):
    """patients get() 결과 → {pid/intake_done: False} 멀티패스 업데이트 dict(순수)."""
    return {f"{pid}/intake_done": False for pid in (raw or {}).keys()}


def reset_intake_flags():
    """순회 시작 — 전 환자 intake_done=False 일괄 리셋. 리셋된 환자 수 반환."""
    ref = _init().reference("patients")
    updates = _intake_reset_updates(ref.get() or {})
    if updates:
        ref.update(updates)
    return len(updates)


def mark_intake_done(pid):
    """문진 완료 — 해당 환자 intake_done=True. 잘못된 pid면 False."""
    if not valid_pid(pid):
        return False
    _init().reference(f"patients/{pid}/intake_done").set(True)
    return True


# ── 순회 문진 하이브리드 핸드셰이크 (로봇 정차↔웹) — 기본 ns=PRIMARY_NS(robot3) ──────
def get_patrol_phase(ns: str = PRIMARY_NS) -> dict:
    """RTDB /{ns}/patrol 의 {phase, stop} 반환. phase 없으면 'idle'.

    phase: 'idle' | 'arrived'.  stop: {'idx','room','ts'} (로봇이 도착한 병상).
    db_node 가 patrol_intake_sequencer 의 'stop_arrived' 피드백을 받아 기록한다.
    웹 PatrolIntakeOverlay 가 폴링해 도착 시 QR/문진 단계로 전이한다.
    """
    node = _init().reference(f"{ns}/patrol").get() or {}
    if not isinstance(node, dict):
        node = {}
    return {"phase": str(node.get("phase") or "idle"),
            "stop": node.get("stop") or {}}


def set_patrol_advance(ns: str = PRIMARY_NS):
    """정차 종료(문진/부재중) → RTDB /{ns}/patrol/intake_done=true 기록.

    db_node 가 감지해 ROS topic /{ns}/patrol/intake_done 을 발행하고,
    patrol_intake_sequencer 가 WAIT_INTAKE → 다음 병상(또는 홈 복귀) 으로 전이한다.
    """
    _init().reference(f"{ns}/patrol/intake_done").set(True)


def intake_pending_payload(data, ts):
    """비로그인 환자 자기제출 문진 → intake_pending 레코드(순수)."""
    data = data or {}
    sections = data.get("sections")
    return {
        "name": str(data.get("name") or "").strip(),
        "room": str(data.get("room") or "").strip(),
        "sections": sections if isinstance(sections, dict) else {},
        "status": "pending",
        "ts": ts,
    }


def add_intake_pending(data):
    """intake_pending 큐에 push. 기존 환자 레코드는 건드리지 않음."""
    payload = intake_pending_payload(data, int(time.time() * 1000))
    ref = _init().reference("intake_pending").push(payload)
    return ref.key, payload


def add_visit(pid, data):
    """문진 입력을 새 외래방문 기록으로 추가(최신 먼저) + 최근 생체징후(vitals) 갱신.

    patients/{pid}/visits 리스트 맨 앞에 prepend → 상세 페이지 '최근 생체징후'(visits[0])에 즉시 반영.
    """
    if not valid_pid(pid):
        raise ValueError("invalid patientId")
    visit = visit_payload(pid, data)
    db = _init()
    ref = db.reference(f"patients/{pid}/visits")
    cur = ref.get() or []
    if isinstance(cur, dict):           # RTDB가 sparse list를 dict로 줄 때 방어
        cur = [cur[k] for k in sorted(cur)]
    elif not isinstance(cur, list):
        cur = []
    cur = [v for v in cur if v is not None]
    cur.insert(0, visit)                # 최신 방문을 맨 앞에
    ref.set(cur)
    vit = vitals_from_visit(visit)
    if vit:
        db.reference(f"patients/{pid}/vitals").update(vit)
    return visit


def update_patient(pid, info=None, vitals=None):
    """환자 정적정보(info)·최근 생체징후(vitals) 부분 수정(상세 페이지 직접 편집)."""
    if not valid_pid(pid):
        raise ValueError("invalid patientId")
    db = _init()
    if info:
        db.reference(f"patients/{pid}/info").update(sanitize_fields(info))
    if vitals:
        db.reference(f"patients/{pid}/vitals").update(sanitize_fields(vitals))


def push_mission(ns, action, params=None, mode=None):
    """웹 명령을 {ns}/mission_pool 뒤에 push(시간순 key). 로봇측 리스너가 읽어 실행."""
    if not valid_robot_ns(ns):
        raise ValueError("invalid robot")
    payload = mission_payload(action, params, int(time.time() * 1000), mode)
    ref = _init().reference(f"{ns}/mission_pool").push(payload)
    return ref.key, payload


def get_missions(ns):
    """{ns}/mission_pool 의 명령 목록(최신순). 잘못된 ns 면 빈 리스트."""
    if not valid_robot_ns(ns):
        return []
    return list_missions(_init().reference(f"{ns}/mission_pool").get())


# ── 이동 목적지(침상/home) pose — RTDB `targets`(dashboard DEFAULT_TARGETS 미러) ──
def targets_seed():
    """goto 프리셋 시드(순수). dashboard 실측 좌표(map=ninety)."""
    return {
        "t101_1": {"label": "101호 1번", "x": -4.39228, "y": -0.701007, "yaw": 2.47368},
        "t101_2": {"label": "101호 2번", "x": -4.21788, "y": -1.58667, "yaw": -2.63024},
        "t102":   {"label": "102호 호출", "x": -3.94329, "y": -3.34683, "yaw": -3.1113},
        "pharmacy": {"label": "약품실", "x": -0.302782, "y": -3.3757, "yaw": -0.0545105},
        "dock":   {"label": "Docking Station", "x": -0.354229, "y": -0.118972,
                   "yaw": -0.0042011, "dock_after": True},
    }


def get_targets():
    """RTDB `targets` 조회(없으면 빈 dict)."""
    return _init().reference("targets").get() or {}


def seed_targets():
    """`targets` 가 비어있으면 시드(멱등). 반환: 시드했으면 True."""
    ref = _init().reference("targets")
    if ref.get():
        return False
    ref.set(targets_seed())
    return True


def ocr_payload(text, conf, ts):
    """RTDB ocr/latest 페이로드(순수)."""
    return {"text": text, "conf": conf, "ts": int(ts)}


def set_ocr(text, conf=None):
    """OCR 결과를 RTDB ocr/latest 에 기록."""
    db = _init()
    db.reference("ocr/latest").set(ocr_payload(text, conf, int(time.time() * 1000)))


# ── 주사/투약 검증 ──────────────────────────────────────────────────────────────
def get_injections(pid):
    """patients/{pid}/injections 전체 반환 (dict: inj_id → injection_data)."""
    if not valid_pid(pid):
        return {}
    db = _init()
    raw = db.reference(f"patients/{pid}/injections").get()
    if not isinstance(raw, dict):
        return {}
    return raw


def update_injection_status(pid, inj_id, status, ocr_text=None):
    """patients/{pid}/injections/{inj_id} 상태 갱신.

    status: 'confirmed' | 'mismatch' | 'pending'
    """
    if not valid_pid(pid):
        raise ValueError("invalid patientId")
    db = _init()
    patch = {"status": status, "verified_at": int(time.time() * 1000)}
    if ocr_text is not None:
        patch["ocr_text"] = ocr_text
    db.reference(f"patients/{pid}/injections/{inj_id}").update(patch)


# ── 병실 디스플레이 현재 환자 ──────────────────────────────────────────────────

def get_display_patient() -> str:
    """display/current_patient 에서 현재 표시 환자 ID 반환. 없으면 빈문자열."""
    db = _init()
    val = db.reference("display/current_patient").get()
    return str(val) if val else ""


def set_display_patient(pid: str):
    """QR 스캔 후 병실 디스플레이에 표시할 환자 ID를 Firebase에 기록."""
    db = _init()
    db.reference("display").update({
        "current_patient": pid,
        "updated_at": int(time.time() * 1000),
    })
