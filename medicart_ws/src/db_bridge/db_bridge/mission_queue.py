"""mission_queue — db_node 의 순수(ROS/Firebase 무관) 큐 로직.

RTDB {ns}/mission_pool 노드(dict)에서 처리 대기(pending) order 를 push-key(시간) 순으로
정렬해 FIFO 순서를 결정한다. '_' 접두 키(_meta 등)와 terminal(done/failed) 상태는 제외.

db_node 워치독 타임아웃(ACTION_TIMEOUTS)은 mission_manager 의 실행 타임아웃보다 약간 길게 둔다
(실행기가 먼저 failed 를 보고하도록 → 무한대기 방지의 2중 안전장치).
"""

# db 측 워치독 타임아웃(초) — 실행기 타임아웃 + 여유.
# patrol_mission 은 undock→여러 병상 순회→dock 전체라 길게 둔다(시퀀서가 단계별 진행).
ACTION_TIMEOUTS = {
    "goto": 300.0,        # Nav2 이동은 길다 — 긴 워치독
    "dock": 120.0,
    "undock": 120.0,
    "ros_restart": 90.0,
    "reboot": 60.0,
    "shutdown": 60.0,
    "patrol_mission": 900.0,
    "nurse_cart_mission": 3600.0,  # 간호사 카트: undock→약품실→OCR 대기→복귀 전체
}
DEFAULT_TIMEOUT = 90.0

# 더 이상 처리하지 않는 종료 상태.
TERMINAL_STATUS = ("done", "failed", "timeout")


def is_mission(key, value):
    """'_' 접두(메타) 아니고 dict 면 미션 항목."""
    return isinstance(key, str) and not key.startswith("_") and isinstance(value, dict)


def ordered_pending(pool):
    """mission_pool dict → 처리 대기(status=='pending') id 를 ts→key FIFO 정렬."""
    if not isinstance(pool, dict):
        return []
    items = [(k, v) for k, v in pool.items()
             if is_mission(k, v) and v.get("status", "pending") == "pending"]
    items.sort(key=lambda kv: (kv[1].get("ts", 0), kv[0]))
    return [k for k, _ in items]


def active_count(pool):
    """아직 끝나지 않은(미terminal) 미션 수 — 하트비트 큐 길이용."""
    if not isinstance(pool, dict):
        return 0
    return sum(1 for k, v in pool.items()
               if is_mission(k, v) and v.get("status", "pending") not in TERMINAL_STATUS)
