"""fb_read — Flask 백엔드의 Firebase RTDB 경계 (redis_bus.py 대체).

순수 로직(snapshot 병합·검증·cmd 페이로드)은 firebase/Flask 무관이라 단위테스트한다.
firebase-admin 결선(리스너→SSE·get·cmd set·intake)은 같은 모듈에 Task 3에서 추가한다.
프론트는 이 백엔드의 SSE/REST만 쓰고 RTDB를 직접 만지지 않는다.
"""
import os
import re

PRIMARY_NS = os.environ.get("PRIMARY_NS", "robot6")
SECONDARY_NS = os.environ.get("SECONDARY_NS", "amr2")
SOURCES = [PRIMARY_NS, SECONDARY_NS]

_PID_RE = re.compile(r"^P-\d{4}-\d{4}$")
_MODE_RE = re.compile(r"^(mapping|patrol|errand|guide|intake|round)$")
_ACTION_RE = re.compile(r"^(start|stop|clear)$")


def valid_pid(pid):
    return bool(_PID_RE.match(str(pid)))


def merge_snapshots(robots_raw, sources):
    """RTDB robots/ get() 결과({ns: state}) → {src: state(+source)|None}."""
    raw = robots_raw or {}
    out = {}
    for src in sources:
        st = raw.get(src) if isinstance(raw, dict) else None
        if isinstance(st, dict):
            st = dict(st)
            st["source"] = src
            out[src] = st
        else:
            out[src] = None
    return out


def cmd_payload(action, mode, params, ts):
    """웹→로봇 명령 페이로드 빌드(화이트리스트 검증). robots/{ns}/cmd 에 set 될 dict."""
    if not _ACTION_RE.match(str(action)):
        raise ValueError("invalid action")
    if action != "clear" and not _MODE_RE.match(str(mode or "")):
        raise ValueError("invalid mode")
    return {"action": action, "mode": mode, "params": params or {}, "ts": int(ts)}


# ---------------------------------------------------------------------------
# firebase-admin 결선 (Task 3)
# ---------------------------------------------------------------------------
import json
import queue
import threading
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
    """두 AMR 최신 스냅샷 {src: state|None}. (RTDB robots/ 1회 읽기)"""
    db = _init()
    raw = db.reference("robots").get()
    return merge_snapshots(raw, SOURCES)


def _sse_listen(path_of, channels):
    """ns별 RTDB 경로 변경을 큐로 모아 SSE 제너레이터로 push(source 주입)."""
    db = _init()
    q = queue.Queue(maxsize=200)

    def _mk(src):
        def _on(event):
            if event.data is None:
                return
            payload = {"source": src, "data": event.data, "path": event.path}
            try:
                q.put(json.dumps(payload, separators=(",", ":")), block=False)
            except queue.Full:
                pass
        return _on

    for src in channels:
        db.reference(path_of(src)).listen(_mk(src))

    while True:
        try:
            yield f"data: {q.get(timeout=15)}\n\n"
        except queue.Empty:
            yield ": keepalive\n\n"


def telemetry_stream():
    return _sse_listen(lambda s: f"robots/{s}/state", SOURCES)


def alert_stream():
    return _sse_listen(lambda s: f"robots/{s}/alerts", SOURCES)


def publish_mode_cmd(action, mode, params=None):
    db = _init()
    payload = cmd_payload(action, mode, params, ts=int(time.time() * 1000))
    db.reference(f"robots/{PRIMARY_NS}/cmd").set(payload)


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
