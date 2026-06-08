"""redis_bus — PC1(robot3)·PC2(amr2) 두 Redis를 읽어 병합.

ward_bridge 스키마: <src>:state Hash의 'snapshot' 필드(최신 JSON),
<src>:telemetry Pub/Sub 채널(10Hz 실시간). 로컬 개발은 두 호스트가 같아도 무방.
"""
import json
import os
import queue
import re
import threading
import time

import redis

_PID_RE = re.compile(r"^P-\d{4}-\d{4}$")   # 키 주입 방지(defense in depth)

_R1 = redis.Redis(host=os.environ.get("REDIS_AMR1_HOST", "127.0.0.1"),
                  port=int(os.environ.get("REDIS_AMR1_PORT", 6379)),
                  decode_responses=True)
_R2 = redis.Redis(host=os.environ.get("REDIS_AMR2_HOST", "127.0.0.1"),
                  port=int(os.environ.get("REDIS_AMR2_PORT", 6379)),
                  decode_responses=True)

PRIMARY_NS = os.environ.get("ROBOT_NAMESPACE", "robot3")

# (source, redis, state_key, telemetry_channel)
SOURCES = [
    (PRIMARY_NS, _R1, f"{PRIMARY_NS}:state", f"{PRIMARY_NS}:telemetry"),
    ("amr2",   _R2, "amr2:state",   "amr2:telemetry"),
]


def snapshots():
    """두 AMR의 최신 스냅샷 {source: {...}|None}."""
    out = {}
    for src, r, state_key, _ in SOURCES:
        snap = None
        try:
            raw = r.hget(state_key, "snapshot")
            if raw:
                snap = json.loads(raw)
                snap["source"] = src
        except (redis.RedisError, json.JSONDecodeError):
            snap = None
        out[src] = snap
    return out


def _sse_merge(channels):
    """여러 (source, redis, channel)의 Pub/Sub 메시지를 병합한 SSE 제너레이터.
    각 메시지에 source 필드를 주입한다. 끊기면 1초 후 재구독."""
    q = queue.Queue(maxsize=200)

    def _listen(src, r, chan):
        while True:
            try:
                ps = r.pubsub()
                ps.subscribe(chan)
                for m in ps.listen():
                    if m["type"] != "message":
                        continue
                    try:
                        d = json.loads(m["data"])
                        d["source"] = src
                        q.put(json.dumps(d, separators=(",", ":")), block=False)
                    except (json.JSONDecodeError, queue.Full):
                        pass
            except redis.RedisError:
                time.sleep(1.0)

    for src, r, chan in channels:
        threading.Thread(target=_listen, args=(src, r, chan), daemon=True).start()

    while True:
        try:
            yield f"data: {q.get(timeout=15)}\n\n"
        except queue.Empty:
            yield ": keepalive\n\n"   # SSE 연결 유지


def telemetry_stream():
    """두 AMR telemetry 채널 병합 SSE(10Hz 상태 스트림)."""
    return _sse_merge([(src, r, chan) for src, r, _, chan in SOURCES])


def alert_stream():
    """두 AMR alert 채널({src}:alert) 병합 SSE(순찰 탐지 알림)."""
    return _sse_merge([(src, r, f"{src}:alert") for src, r, _, _ in SOURCES])


_MODE_RE = re.compile(r"^(mapping|patrol|errand|guide|intake|round)$")
_ACTION_RE = re.compile(r"^(start|stop|clear)$")


def publish_mode_cmd(action, mode, params=None):
    """웹→로봇: robot3:mode_cmd 채널로 모드 명령 발행. 화이트리스트 검증."""
    if not _ACTION_RE.match(str(action)):
        raise ValueError("invalid action")
    if action != "clear" and not _MODE_RE.match(str(mode or "")):
        raise ValueError("invalid mode")
    payload = json.dumps({"action": action, "mode": mode, "params": params or {}},
                         ensure_ascii=False)
    _R1.publish(f"{PRIMARY_NS}:mode_cmd", payload)


def save_intake(pid, data):
    """문진표 저장(Redis hash intake:<pid>). pid 형식 미일치 시 무시."""
    if not _PID_RE.match(str(pid)):
        raise ValueError("invalid patientId")
    _R1.hset(f"intake:{pid}", mapping={
        "data": json.dumps(data, ensure_ascii=False),
        "stamp": str(time.time()),
    })


def get_intake(pid):
    if not _PID_RE.match(str(pid)):
        return None
    raw = _R1.hget(f"intake:{pid}", "data")
    return json.loads(raw) if raw else None
