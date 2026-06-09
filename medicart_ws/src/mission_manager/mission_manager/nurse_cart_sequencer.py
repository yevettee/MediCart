#!/usr/bin/env python3
"""nurse_cart_sequencer — 간호사 카트 시나리오 오케스트레이션.

mission_request action='nurse_cart_mission' 을 받아 단계를 순차 실행한다:

  1. GOTO_PHARMACY  — NavExecutor 로 약품실 이동 (undock 자동 포함)
  2. WAIT_OCR       — 약품실 도착 신호 발행 + signal_ocr_done() 대기
  3. GOTO_STANDBY   — NavExecutor 로 약품실 입구 standby 위치 이동
  4. START_ROUND    — ModeArbiter 로 round(추종) 모드 활성화
  5. DONE

진행/결과는 부모 mission id 로 publish_feedback(accepted→running→done|failed) 발행.

설계 포인트:
  · NavExecutor 가 도킹 상태를 스스로 확인 후 필요 시 undock 처리 — 별도 undock 단계 불요.
  · signal_ocr_done() 은 mission_manager_node 가 /{ns}/nurse_cart/ocr_done ROS topic
    수신 시 호출 — db_node 가 RTDB 변화를 감지해 topic 발행.
  · threading.Lock 으로 _nav_result / _ocr_done 플래그 멀티스레드 안전 보호.
  · MissionSequencer(patrol_mission) 와 동일한 계약 구조.
"""
import threading
import time

# 시퀀스 상태
IDLE, GOTO_PHARMACY, WAIT_OCR, GOTO_STANDBY, START_ROUND, DONE, FAILED = (
    'idle', 'goto_pharmacy', 'wait_ocr', 'goto_standby', 'start_round', 'done', 'failed')

NURSE_CART_ACTION = 'nurse_cart_mission'

# 약품실 기본 좌표 — ninety-frame (fb_read.py targets_seed 의 pharmacy 와 동일)
_DEFAULT_PHARMACY = {'x': -0.302782, 'y': -3.3757, 'yaw': -0.0545105}

# 약품실 입구 대기 위치 (amcl_pose 실측 2026-06-09)
_DEFAULT_STANDBY = {'x': -0.9296, 'y': -3.3393, 'yaw': 2.8293}


def _now_ms():
    return int(time.time() * 1000)


class NurseCartSequencer:
    """간호사 카트 시나리오 시퀀서.

    GOTO_PHARMACY → WAIT_OCR → GOTO_STANDBY → START_ROUND → DONE
    """

    def __init__(self, nav, arbiter, publish_feedback, logger):
        """
        nav    : NavExecutor — goto 이동(undock 자동 포함)
        arbiter: ModeArbiter — goto/round 모드 점거·해제
        """
        self._nav = nav
        self._arbiter = arbiter
        self._publish = publish_feedback
        self._log = logger

        self._state = IDLE
        self._id = None
        self._lock = threading.Lock()
        self._nav_result = None   # (status, detail) | None — nav 콜백→tick 전달용
        self._ocr_done = False    # signal_ocr_done() 호출 시 True
        self._standby_params = None

    # ── 외부 인터페이스 ──────────────────────────────────────────────────
    def active(self):
        """시퀀스 진행 중 여부."""
        return self._state not in (IDLE, DONE, FAILED)

    def start(self, mission_id, params=None):
        """nurse_cart_mission 시퀀스 시작."""
        if self.active():
            self._emit_to(mission_id, 'failed', 'nurse_cart sequencer busy (진행 중)')
            self._log.warn(f'[nurse_cart] busy 거부 id={mission_id}')
            return
        self._id = mission_id
        p = params or {}
        pharmacy = {
            'x':         float(p.get('pharmacy_x',   _DEFAULT_PHARMACY['x'])),
            'y':         float(p.get('pharmacy_y',   _DEFAULT_PHARMACY['y'])),
            'yaw':       float(p.get('pharmacy_yaw', _DEFAULT_PHARMACY['yaw'])),
            'dock_after': False,
        }
        self._standby_params = {
            'x':         float(p.get('standby_x',   _DEFAULT_STANDBY['x'])),
            'y':         float(p.get('standby_y',   _DEFAULT_STANDBY['y'])),
            'yaw':       float(p.get('standby_yaw', _DEFAULT_STANDBY['yaw'])),
            'dock_after': False,
        }
        with self._lock:
            self._ocr_done = False
        self._emit('accepted', '간호사 카트: 약품실 이동 시작')
        self._log.info(
            f'[nurse_cart] ▶ START id={mission_id} → goto_pharmacy '
            f'({pharmacy["x"]:.3f}, {pharmacy["y"]:.3f})')
        self._enter_goto_pharmacy(pharmacy)

    def signal_ocr_done(self):
        """외부(mission_manager_node)에서 OCR 완료 신호를 주입.

        db_node 가 RTDB /{ns}/nurse_cart/ocr_done=true 를 감지하면
        /{ns}/nurse_cart/ocr_done ROS topic 을 발행하고,
        mission_manager_node 가 이 메서드를 호출한다.
        """
        with self._lock:
            self._ocr_done = True
        self._log.info('[nurse_cart] OCR 완료 신호 수신')

    def tick(self, now):  # noqa: ARG002
        """제어주기 1회 — 결과/플래그를 확인해 다음 단계로 전이."""
        if self._state == GOTO_PHARMACY:
            res = self._take_result()
            if res is None:
                return
            status, detail = res
            if status == 'done':
                self._enter_wait_ocr()
            else:
                self._fail(f'약품실 이동 실패: {detail}')

        elif self._state == WAIT_OCR:
            with self._lock:
                done, self._ocr_done = self._ocr_done, False
            if done:
                self._enter_goto_standby()

        elif self._state == GOTO_STANDBY:
            res = self._take_result()
            if res is None:
                return
            status, detail = res
            if status == 'done':
                self._enter_start_round()
            else:
                self._fail(f'약품실 입구 이동 실패: {detail}')

    # ── 단계 전이 ────────────────────────────────────────────────────────
    def _enter_wait_ocr(self):
        """약품실 도착 — 'pharmacy_arrived' 피드백으로 RTDB phase=arrived 트리거."""
        self._state = WAIT_OCR
        self._emit('running', 'pharmacy_arrived')
        self._log.info(f'[nurse_cart] ⏳ WAIT_OCR id={self._id} — OCR 완료 대기 중')

    def _enter_goto_pharmacy(self, pharmacy_params):
        self._state = GOTO_PHARMACY
        self._set_result(None)
        self._emit('running', '약품실로 이동 중 (undock 자동 포함)')
        if self._nav.active:
            self._nav.cancel()
        self._arbiter.apply('start', 'goto', pharmacy_params)

        def _on_done(status, detail):
            self._arbiter.apply('stop', 'goto')
            self._set_result((status, detail))

        self._nav.start(pharmacy_params, _on_done)

    def _enter_goto_standby(self):
        """OCR 완료 → 약품실 입구 standby 위치로 이동."""
        p = self._standby_params
        self._state = GOTO_STANDBY
        self._set_result(None)
        self._emit('running', '약품실 입구로 이동 중')
        self._log.info(
            f'[nurse_cart] → GOTO_STANDBY id={self._id} '
            f'({p["x"]:.3f}, {p["y"]:.3f}, yaw={p["yaw"]:.4f})')
        if self._nav.active:
            self._nav.cancel()
        self._arbiter.apply('start', 'goto', p)

        def _on_done(status, detail):
            self._arbiter.apply('stop', 'goto')
            self._set_result((status, detail))

        self._nav.start(p, _on_done)

    def _enter_start_round(self):
        """약품실 입구 도착 → round(간호사 추종) 모드 활성화."""
        self._state = START_ROUND
        self._emit('running', '간호사 추종 모드 시작')
        self._log.info(f'[nurse_cart] → START_ROUND id={self._id}')
        ok, detail = self._arbiter.apply('start', 'round', {})
        if ok:
            self._done('간호사 카트 시나리오 완료 — 추종 모드 활성')
        else:
            self._fail(f'추종 모드 활성화 실패: {detail}')

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
        self._log.info(f'[nurse_cart] ■ DONE id={self._id} :: {detail}')
        self._state = DONE
        self._id = None

    def _fail(self, detail):
        self._emit('failed', detail)
        self._log.error(f'[nurse_cart] ■ FAILED id={self._id} :: {detail}')
        self._state = FAILED
        self._id = None
