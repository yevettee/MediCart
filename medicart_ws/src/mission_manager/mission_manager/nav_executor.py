#!/usr/bin/env python3
"""nav_executor — goto(좌표 이동) 실행기. dashboard 의 Nav2+dock-aware 로직 이식.

mission_manager 허브 내부에서 NavigateToPose(map 프레임)로 이동:
  · 현재 도킹 상태(dock_status)면 먼저 Undock 후 이동
  · params.dock_after 면 도착 후 자동 Dock
create3 중복 액션 디바운스(in-flight 시 재전송 금지, SIGSEGV 방지). 모든 콜백은
노드 executor 에서 처리(별도 스레드 없음). 결과는 on_done(status, detail) 콜백 1회.
"""
import math


def pose_stamped_fields(x, y, yaw):
    """map 프레임 목표 pose 의 위치/쿼터니언(순수) — 단위테스트용."""
    return {"frame_id": "map", "x": float(x), "y": float(y),
            "qz": math.sin(float(yaw) / 2.0), "qw": math.cos(float(yaw) / 2.0)}
