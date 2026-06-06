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
