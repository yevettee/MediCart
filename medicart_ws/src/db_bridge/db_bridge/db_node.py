#!/usr/bin/env python3
"""db_node — 로봇측 RTDB mission_pool 브리지/오케스트레이터.

평소 RTDB 최상위 {ns}/mission_pool 을 대기(listen)하다가, 들어온 order(명령)를 push-key(시간)
순으로 하나씩 mission_manager 로 전달(/{ns}/mission_request)하고, 완료 신호
(/{ns}/mission_feedback)를 받으면 해당 order 를 mission_pool 에서 비우고(아카이브 후 삭제)
다음 order 를 수행한다. web 은 ROS 노드 없이 mission_pool 에 쓰기만 하고, 이 노드가 ROS 로 중계.

설계 포인트
  · 순차 처리: 동시에 여러 order 가 들어와도 FIFO 1건씩(현재 1건 완료 전 다음 미시작).
  · 무한대기 방지: 명령별 워치독 타임아웃 + 1Hz {ns}/mission_status 하트비트 + 상세 디버그 로그.
  · 진행 가시화: 진행 중 상태/경과를 매 tick 로깅 + RTDB(status/progress/mission_status)에 기록.
"""
import json
import os
import threading
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from db_bridge.firebase_client import FirebaseClient
from db_bridge.mission_queue import (ACTION_TIMEOUTS, DEFAULT_TIMEOUT,
                                     active_count, is_mission, ordered_pending)


def _now_ms():
    return int(time.time() * 1000)


class DbNode(Node):
    """RTDB mission_pool ↔ mission_manager 순차 오케스트레이터."""

    def __init__(self):
        super().__init__('db_node')

        self.declare_parameter('namespace', os.environ.get('ROBOT_NAMESPACE', 'robot3'))
        self.declare_parameter('fb_cred', os.environ.get('FB_CRED', ''))
        self.declare_parameter('fb_db_url', os.environ.get('FB_DB_URL', ''))
        self.declare_parameter('heartbeat_period', 1.0)

        self.ns = str(self.get_parameter('namespace').value).strip('/')
        cred = str(self.get_parameter('fb_cred').value)
        url = str(self.get_parameter('fb_db_url').value)
        period = float(self.get_parameter('heartbeat_period').value)

        self._pool_path = f'{self.ns}/mission_pool'
        self._status_path = f'{self.ns}/mission_status'
        self._log_path = f'{self.ns}/mission_log'

        self._lock = threading.Lock()
        self._pool = {}              # 최신 mission_pool 스냅샷(메타 제외)
        self._current = None         # {'id','action','started','feedback'}
        self._last_event = 'init'

        self.get_logger().info(f'[db_node] RTDB 연결 시도 ns=/{self.ns} url={url}')
        self._fb = FirebaseClient(cred, url, logger=self.get_logger())

        self._req_pub = self.create_publisher(String, f'/{self.ns}/mission_request', 10)
        self.create_subscription(String, f'/{self.ns}/mission_feedback', self._on_feedback, 10)

        self._refresh_pool('startup')
        self._fb.listen(self._pool_path, self._on_pool_event)   # RTDB 대기(listen)

        self._timer = self.create_timer(period, self._tick)
        self.get_logger().info(
            f'[db_node] 준비 완료 — mission_pool=/{self._pool_path} 대기 중, '
            f'request=/{self.ns}/mission_request feedback=/{self.ns}/mission_feedback')

    # ── RTDB 동기화 ──────────────────────────────────────────────────────
    def _refresh_pool(self, reason):
        raw = self._fb.read(self._pool_path)
        pool = {}
        if isinstance(raw, dict):
            pool = {k: v for k, v in raw.items() if is_mission(k, v)}
        with self._lock:
            self._pool = pool
        pend = ordered_pending(pool)
        self.get_logger().info(
            f'[db_node] pool 갱신({reason}): 총 {len(pool)}건, pending {len(pend)} {pend}')

    def _on_pool_event(self, event):
        # firebase 리스너 스레드 — 풀만 갱신하고 처리는 _tick(노드 스레드)에서.
        path = getattr(event, 'path', '?')
        self.get_logger().debug(f'[db_node] mission_pool 이벤트 path={path}')
        try:
            self._refresh_pool(f'event {path}')
        except Exception as exc:                       # noqa: BLE001 (브리지 안정성)
            self.get_logger().error(f'[db_node] pool 이벤트 처리 오류: {exc}')

    # ── 메인 tick(워치독 + 하트비트 + 다음 시작) ─────────────────────────
    def _tick(self):
        with self._lock:
            cur = dict(self._current) if self._current else None
        if cur:
            elapsed = time.time() - cur['started']
            timeout = ACTION_TIMEOUTS.get(cur['action'], DEFAULT_TIMEOUT)
            self.get_logger().info(
                f"[db_node] 진행중 id={cur['id']} action={cur['action']} "
                f"경과 {elapsed:.1f}/{timeout:.0f}s fb={cur.get('feedback')}")
            if elapsed > timeout:
                self.get_logger().error(
                    f"[db_node] ⏰ TIMEOUT id={cur['id']} action={cur['action']} "
                    f"({elapsed:.1f}s) → 실패 처리 후 다음 진행")
                self._finish(cur['id'], 'timeout', f'no result within {timeout:.0f}s')
        else:
            self._start_next()
        self._write_heartbeat()

    def _start_next(self):
        with self._lock:
            if self._current is not None:
                return
            pend = ordered_pending(self._pool)
            if not pend:
                return
            mid = pend[0]
            mission = dict(self._pool.get(mid, {}))
            action = mission.get('action')
            self._current = {'id': mid, 'action': action, 'started': time.time(),
                             'feedback': 'sent'}
            self._pool.setdefault(mid, {})['status'] = 'running'   # 로컬도 갱신(재선택 방지)

        try:
            self._fb.update(f'{self._pool_path}/{mid}',
                            {'status': 'running', 'updated_ts': _now_ms()})
        except Exception as exc:                       # noqa: BLE001
            self.get_logger().error(f'[db_node] status=running 기록 실패 id={mid}: {exc}')
        req = {'id': mid, 'action': action, 'params': mission.get('params', {})}
        if mission.get('mode'):                       # 모드 액션(start/stop)일 때 mode 전달
            req['mode'] = mission.get('mode')
        self._publish(self._req_pub, req)
        self._last_event = f'start {action}({mid})'
        self.get_logger().info(
            f'[db_node] ▶ START id={mid} action={action} → mission_request 발행')

    # ── 피드백 처리 ──────────────────────────────────────────────────────
    def _on_feedback(self, msg):
        try:
            fb = json.loads(msg.data)
        except (ValueError, TypeError) as exc:
            self.get_logger().warn(f'[db_node] feedback 파싱 실패: {exc} raw={msg.data!r}')
            return
        mid, status, detail = fb.get('id'), fb.get('status'), fb.get('detail', '')
        with self._lock:
            cur = dict(self._current) if self._current else None
        if not cur or cur['id'] != mid:
            self.get_logger().warn(
                f'[db_node] feedback 무시(현재 미션 불일치) id={mid} status={status} '
                f"current={cur['id'] if cur else None}")
            return
        self.get_logger().info(f'[db_node] ◀ FEEDBACK id={mid} status={status} detail={detail}')

        if status in ('accepted', 'running'):
            with self._lock:
                if self._current:
                    self._current['feedback'] = status
            try:
                self._fb.update(f'{self._pool_path}/{mid}',
                                {'status': 'running', 'progress': str(detail)[:200],
                                 'updated_ts': _now_ms()})
            except Exception as exc:                   # noqa: BLE001
                self.get_logger().warn(f'[db_node] progress 기록 실패 id={mid}: {exc}')
            self._last_event = f'{status} {mid}'
        elif status in ('done', 'failed'):
            self._finish(mid, status, detail)
        else:
            self.get_logger().warn(f'[db_node] 알 수 없는 status={status} id={mid}')

    def _finish(self, mid, status, detail):
        """terminal — mission_log 아카이브 후 mission_pool 에서 비우고 다음 진행."""
        with self._lock:
            cur = self._current
            started = cur['started'] if cur and cur['id'] == mid else time.time()
            action = cur['action'] if cur and cur['id'] == mid else None
            self._current = None
            self._pool.pop(mid, None)
        try:
            self._fb.write(f'{self._log_path}/{mid}', {
                'action': action, 'status': status, 'detail': str(detail)[:500],
                'started_ts': int(started * 1000), 'ended_ts': _now_ms()})
            self._fb.delete(f'{self._pool_path}/{mid}')        # order 비움
        except Exception as exc:                       # noqa: BLE001
            self.get_logger().error(f'[db_node] finish RTDB 오류 id={mid}: {exc}')
        self._last_event = f'{status} {action}({mid})'
        # rclpy 로거는 '같은 호출 위치'에서 심각도를 바꾸면 예외 → info/error 를 별도 라인으로.
        finish_msg = (f'[db_node] ■ FINISH id={mid} action={action} status={status} '
                      f'detail={detail} → mission_pool 비움')
        if status == 'done':
            self.get_logger().info(finish_msg)
        else:
            self.get_logger().error(finish_msg)
        self._start_next()                                     # 즉시 다음 order

    # ── 하트비트(무한대기 가시화) ────────────────────────────────────────
    def _write_heartbeat(self):
        with self._lock:
            cur = dict(self._current) if self._current else None
            qlen = active_count(self._pool)
            payload = {
                'alive': True, 'ts': _now_ms(), 'queue_len': qlen,
                'current_id': cur['id'] if cur else None,
                'current_action': cur['action'] if cur else None,
                'current_elapsed': round(time.time() - cur['started'], 1) if cur else 0,
                'last_event': self._last_event,
            }
        try:
            self._fb.write(self._status_path, payload)
        except Exception as exc:                       # noqa: BLE001
            self.get_logger().warn(f'[db_node] heartbeat 기록 실패: {exc}')

    def _publish(self, pub, obj):
        msg = String()
        msg.data = json.dumps(obj, ensure_ascii=False)
        pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = DbNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
