#!/usr/bin/env python3
"""patrol_intake_sequencer — 시나리오 A 순회 문진 하이브리드 오케스트레이션.

mission_request action='patrol_intake_mission' 을 받아 정차 목록을 순차 순회한다:

  1. GOTO_STOP[i]  — NavExecutor 로 i 번째 병상 이동 (undock 자동 포함)
  2. WAIT_INTAKE   — 병상 도착 신호('stop_arrived:{i}:{room}') 발행 + signal_intake_done() 대기
                     (웹 iPad 가 QR 스캔→문진/부재중 후 intake_done 신호를 보냄)
  3. i+1 이 남아있으면 GOTO_STOP[i+1] 로, 아니면 GOTO_HOME
  4. GOTO_HOME     — NavExecutor 로 홈(도킹 스테이션) 이동 + dock
  5. DONE

설계 포인트 (nurse_cart_sequencer 와 동일한 핸드셰이크 패턴):
  · NavExecutor 가 도킹 상태를 스스로 확인 후 필요 시 undock 처리 — 별도 undock 단계 불요.
  · 정차 사이 이동은 로봇 내부(NavExecutor)에서 처리 → 스텝마다 Firebase 왕복 없음.
  · signal_intake_done() 은 mission_manager_node 가 ROS topic 수신 시 호출.
  · GOTO_HOME 은 dock_after=True → NavExecutor 가 도착 후 자동 dock.
  · threading.Lock 으로 _nav_result / _intake_done 플래그 멀티스레드 안전 보호.
"""
import threading
import time

# 시퀀스 상태
IDLE, GOTO_STOP, WAIT_INTAKE, GOTO_HOME, DONE, FAILED = (
    'idle', 'goto_stop', 'wait_intake', 'goto_home', 'done', 'failed')

PATROL_INTAKE_ACTION = 'patrol_intake_mission'

# 홈(도킹 스테이션) 위치 — patrol_mode_node DEFAULT_TARGETS 'Docking Station' 동일
_DEFAULT_HOME = {'x': -0.354229, 'y': -0.118972, 'yaw': -0.0042011, 'dock_after': True}


def _now_ms():
    return int(time.time() * 1000)


class PatrolIntakeSequencer:
    """순회 문진 시나리오 시퀀서.

    GOTO_STOP[0] → WAIT_INTAKE → GOTO_STOP[1] → WAIT_INTAKE → … → GOTO_HOME → DONE
    """

    def __init__(self, nav, arbiter, publish_feedback, logger):
        """
        nav    : NavExecutor — goto 이동(undock 자동 포함)
        arbiter: ModeArbiter — goto 모드 점거·해제
        """
        self._nav = nav
        self._arbiter = arbiter
        self._publish = publish_feedback
        self._log = logger

        self._state = IDLE
        self._id = None
        self._lock = threading.Lock()
        self._nav_result = None     # (status, detail) | None — nav 콜백→tick 전달용
        self._intake_done = False   # signal_intake_done() 호출 시 True
        self._stops = []            # [{x,y,yaw,room,label}, …]
        self._home_params = None
        self._idx = 0

    # ── 외부 인터페이스 ──────────────────────────────────────────────────
    def active(self):
        """시퀀스 진행 중 여부."""
        return self._state not in (IDLE, DONE, FAILED)

    def start(self, mission_id, params=None):
        """patrol_intake_mission 시퀀스 시작.

        params = {
          'stops': [{'x','y','yaw','room','label'}, …],   # 필수
          'home':  {'x','y','yaw'},                        # 선택 — 없으면 기본 도킹 스테이션
        }
        """
        if self.active():
            self._emit_to(mission_id, 'failed', 'patrol_intake sequencer busy (진행 중)')
            self._log.warn(f'[patrol_intake] busy 거부 id={mission_id}')
            return
        p = params or {}
        stops = self._normalize_stops(p.get('stops'))
        if not stops:
            self._emit_to(mission_id, 'failed', 'stops 비어있음 — 순회 대상 없음')
            self._log.error(f'[patrol_intake] stops 없음 — 거부 id={mission_id}')
            return
        self._id = mission_id
        self._stops = stops
        self._idx = 0
        h = p.get('home') or {}
        self._home_params = {
            'x':          float(h.get('x',   _DEFAULT_HOME['x'])),
            'y':          float(h.get('y',   _DEFAULT_HOME['y'])),
            'yaw':        float(h.get('yaw', _DEFAULT_HOME['yaw'])),
            'dock_after': True,
        }
        with self._lock:
            self._intake_done = False
        self._emit('accepted', f'순회 문진: {len(stops)}개 병상 순회 시작')
        self._log.info(
            f'[patrol_intake] ▶ START id={mission_id} stops={len(stops)} → 첫 병상 이동')
        self._enter_goto_stop()

    def signal_intake_done(self):
        """외부(mission_manager_node)에서 문진(또는 부재중) 완료 신호를 주입.

        웹 iPad 가 QR 스캔→문진/부재중 처리 후 RTDB {ns}/patrol/intake_done=true 설정 →
        db_node → /{ns}/patrol/intake_done ROS topic → 이 메서드 호출.
        WAIT_INTAKE → 다음 병상(GOTO_STOP) 또는 GOTO_HOME 전이.
        """
        with self._lock:
            self._intake_done = True
        self._log.info('[patrol_intake] 문진 완료 신호 수신')

    def tick(self, now):  # noqa: ARG002
        """제어주기 1회 — 결과/플래그를 확인해 다음 단계로 전이."""
        if self._state == GOTO_STOP:
            res = self._take_result()
            if res is None:
                return
            status, detail = res
            if status == 'done':
                self._enter_wait_intake()
            else:
                self._fail(f'{self._cur_room()} 이동 실패: {detail}')

        elif self._state == WAIT_INTAKE:
            with self._lock:
                done, self._intake_done = self._intake_done, False
            if done:
                self._idx += 1
                if self._idx < len(self._stops):
                    self._enter_goto_stop()
                else:
                    self._enter_goto_home()

        elif self._state == GOTO_HOME:
            res = self._take_result()
            if res is None:
                return
            status, detail = res
            if status == 'done':
                self._done('시나리오 A 순회 문진 완료 — 홈 복귀 및 도킹 완료')
            else:
                self._fail(f'홈 복귀/도킹 실패: {detail}')

    # ── 단계 전이 ────────────────────────────────────────────────────────
    def _enter_goto_stop(self):
        """현재 idx 병상으로 이동 (첫 이동은 undock 자동 포함)."""
        stop = self._stops[self._idx]
        self._state = GOTO_STOP
        self._set_result(None)
        self._emit('running', f'{self._cur_room()} 이동 중')
        self._log.info(
            f'[patrol_intake] → GOTO_STOP[{self._idx}] id={self._id} '
            f'room={stop.get("room")} ({stop["x"]:.3f}, {stop["y"]:.3f})')
        if self._nav.active:
            self._nav.cancel()
        params = {'x': stop['x'], 'y': stop['y'], 'yaw': stop['yaw'], 'dock_after': False}
        self._arbiter.apply('start', 'goto', params)

        def _on_done(status, detail):
            self._arbiter.apply('stop', 'goto')
            self._set_result((status, detail))

        self._nav.start(params, _on_done)

    def _enter_wait_intake(self):
        """병상 도착 — 'stop_arrived:{idx}:{room}' 피드백으로 RTDB phase=arrived 트리거."""
        self._state = WAIT_INTAKE
        room = self._cur_room()
        self._emit('running', f'stop_arrived:{self._idx}:{room}')
        self._log.info(
            f'[patrol_intake] ⏳ WAIT_INTAKE[{self._idx}] id={self._id} room={room} '
            '— 문진 완료 신호 대기 중')

    def _enter_goto_home(self):
        """모든 병상 순회 완료 → 홈(도킹 스테이션) 복귀 + 자동 dock."""
        p = self._home_params
        self._state = GOTO_HOME
        self._set_result(None)
        self._emit('running', '순회 완료 — 홈 복귀 중 (도킹 포함)')
        self._log.info(
            f'[patrol_intake] → GOTO_HOME id={self._id} '
            f'({p["x"]:.3f}, {p["y"]:.3f}) dock_after=True')
        if self._nav.active:
            self._nav.cancel()
        self._arbiter.apply('start', 'goto', p)

        def _on_done(status, detail):
            self._arbiter.apply('stop', 'goto')
            self._set_result((status, detail))

        self._nav.start(p, _on_done)

    # ── 유틸 ─────────────────────────────────────────────────────────────
    def _cur_room(self):
        if 0 <= self._idx < len(self._stops):
            return self._stops[self._idx].get('room') or f'stop{self._idx}'
        return f'stop{self._idx}'

    @staticmethod
    def _normalize_stops(raw):
        """params['stops'] → [{x,y,yaw,room,label}] (x,y 숫자 검증, 잘못된 항목 제외)."""
        out = []
        for s in raw or []:
            if not isinstance(s, dict):
                continue
            try:
                x = float(s['x'])
                y = float(s['y'])
            except (KeyError, TypeError, ValueError):
                continue
            out.append({
                'x': x, 'y': y, 'yaw': float(s.get('yaw', 0.0)),
                'room': str(s.get('room', '')), 'label': str(s.get('label', '')),
            })
        return out

    # ── 스레드 안전 결과 버퍼 ────────────────────────────────────────────
    def _take_result(self):
        with self._lock:
            res, self._nav_result = self._nav_result, None
        return res

    def _set_result(self, value):
        with self._lock:
            self._nav_result = value

    # ── 피드백/종료 ──────────────────────────────────────────────────────
    def _emit(self, status, detail):
        self._emit_to(self._id, status, detail)

    def _emit_to(self, mission_id, status, detail):
        self._publish({'id': mission_id, 'status': status,
                       'detail': str(detail), 'ts': _now_ms()})

    def _done(self, detail):
        self._emit('done', detail)
        self._log.info(f'[patrol_intake] ■ DONE id={self._id} :: {detail}')
        self._state = DONE
        self._id = None

    def _fail(self, detail):
        self._emit('failed', detail)
        self._log.error(f'[patrol_intake] ■ FAILED id={self._id} :: {detail}')
        self._state = FAILED
        self._id = None
