#!/usr/bin/env python3
"""nurse_cart_sequencer — 간호사 카트 시나리오 오케스트레이션.

mission_request action='nurse_cart_mission' 을 받아 단계를 순차 실행한다:

  1. GOTO_PHARMACY   — NavExecutor 로 약품실 이동 (undock 자동 포함)
  2. WAIT_OCR        — 약품실 도착 신호 발행 + signal_ocr_done() 대기
  3. GOTO_STANDBY    — NavExecutor 로 약품실 입구 standby 위치 이동
  4. START_ROUND     — ModeArbiter 로 round(추종) 모드 활성화
  5. WAIT_ROUND_DONE — signal_round_done() 대기 (간호사가 회진 완료 트리거)
  6. GOTO_HOME       — round 모드 해제 + NavExecutor 로 홈(도킹 스테이션) 이동 + dock
  7. DONE

진행/결과는 부모 mission id 로 publish_feedback(accepted→running→done|failed) 발행.

설계 포인트:
  · NavExecutor 가 도킹 상태를 스스로 확인 후 필요 시 undock 처리 — 별도 undock 단계 불요.
  · signal_ocr_done() / signal_round_done() 은 mission_manager_node 가 ROS topic 수신 시 호출.
  · GOTO_HOME 은 dock_after=True → NavExecutor 가 도착 후 자동 dock.
  · threading.Lock 으로 _nav_result / _ocr_done / _round_done 플래그 멀티스레드 안전 보호.
"""
import threading
import time

# 시퀀스 상태
IDLE, GOTO_PHARMACY, WAIT_OCR, GOTO_STANDBY, START_ROUND, WAIT_ROUND_DONE, GOTO_HOME, DONE, FAILED = (
    'idle', 'goto_pharmacy', 'wait_ocr', 'goto_standby',
    'start_round', 'wait_round_done', 'goto_home', 'done', 'failed')

NURSE_CART_ACTION = 'nurse_cart_mission'
TRACK_MODE = 'round'

# 약품실 기본 좌표 — ninety-frame (fb_read.py targets_seed 의 pharmacy 와 동일)
_DEFAULT_PHARMACY = {'x': -0.302782, 'y': -3.3757, 'yaw': -0.0545105}

# 약품실 입구 대기 위치 (amcl_pose 실측 2026-06-09)
_DEFAULT_STANDBY = {'x': -0.9296, 'y': -3.3393, 'yaw': 2.8293}

# 홈(도킹 스테이션) 위치 — patrol_mode_node DEFAULT_TARGETS 'Docking Station' 동일
_DEFAULT_HOME = {'x': -0.354229, 'y': -0.118972, 'yaw': -0.0042011, 'dock_after': True}


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
        self._round_done = False  # signal_round_done() 호출 시 True
        self._bed_arrived = False
        self._bed_info = None
        self._tracking_stopped = False
        self._standby_params = None
        self._home_params = None

    # ── 외부 인터페이스 ──────────────────────────────────────────────────
    def active(self):
        """시퀀스 진행 중 여부."""
        return self._state not in (IDLE, DONE, FAILED)

    def awaiting_bed_arrival(self):
        """간호사 추종 중이며 병상 zone 도착 이벤트를 받을 수 있는지."""
        return self._state == WAIT_ROUND_DONE and not self._tracking_stopped

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
        self._home_params = {
            'x':         float(p.get('home_x',   _DEFAULT_HOME['x'])),
            'y':         float(p.get('home_y',   _DEFAULT_HOME['y'])),
            'yaw':       float(p.get('home_yaw', _DEFAULT_HOME['yaw'])),
            'dock_after': True,
        }
        with self._lock:
            self._ocr_done = False
            self._round_done = False
            self._bed_arrived = False
            self._bed_info = None
            self._tracking_stopped = False
        self._emit('accepted', '간호사 카트: 약품실 이동 시작')
        self._log.info(
            f'[nurse_cart] ▶ START id={mission_id} → goto_pharmacy '
            f'({pharmacy["x"]:.3f}, {pharmacy["y"]:.3f})')
        self._enter_goto_pharmacy(pharmacy)

    def signal_ocr_done(self):
        """외부(mission_manager_node)에서 OCR 완료 신호를 주입."""
        with self._lock:
            self._ocr_done = True
        self._log.info('[nurse_cart] OCR 완료 신호 수신')

    def signal_round_done(self):
        """외부(mission_manager_node)에서 회진 완료 신호를 주입.

        간호사가 회진을 마치면 웹/트리거로 RTDB robot6/nurse_cart/round_done=true 설정 →
        db_node → /{ns}/nurse_cart/round_done ROS topic → 이 메서드 호출.
        WAIT_ROUND_DONE → GOTO_HOME(+dock) 전이.
        """
        with self._lock:
            self._round_done = True
        self._log.info('[nurse_cart] 회진 완료 신호 수신 → 홈 복귀 준비')

    def signal_bed_arrived(self, info=None):
        """병상 앞 zone 진입 신호 — 추종을 자동 해제하고 QR/완료 대기로 전환."""
        if not self.awaiting_bed_arrival():
            return False
        with self._lock:
            self._bed_arrived = True
            self._bed_info = dict(info or {})
        zone = (info or {}).get('zone_id', 'unknown')
        self._log.info(f'[nurse_cart] 병상 zone 도착 신호 수신 zone={zone}')
        return True

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

        elif self._state == WAIT_ROUND_DONE:
            with self._lock:
                bed_arrived, bed_info = self._bed_arrived, self._bed_info
                self._bed_arrived = False
            if bed_arrived:
                self._handle_bed_arrived(bed_info)
            with self._lock:
                done, self._round_done = self._round_done, False
            if done:
                self._enter_goto_home()

        elif self._state == GOTO_HOME:
            res = self._take_result()
            if res is None:
                return
            status, detail = res
            if status == 'done':
                self._done('시나리오 B 완료 — 홈 복귀 및 도킹 완료')
            else:
                self._fail(f'홈 복귀/도킹 실패: {detail}')

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
        """약품실 입구 도착 → cmd_vel 기반 간호사 추종 모드 활성화 → 회진 완료 대기."""
        self._state = START_ROUND
        self._emit('running', '간호사 cmd_vel 추종 모드 시작')
        self._log.info(f'[nurse_cart] → START_ROUND_CMD_VEL id={self._id}')
        ok, detail = self._arbiter.apply('start', TRACK_MODE, {})
        if ok:
            self._state = WAIT_ROUND_DONE
            self._emit('running', 'tracking_started')
            self._log.info(f'[nurse_cart] → WAIT_ROUND_DONE id={self._id}')
        else:
            self._fail(f'추종 모드 활성화 실패: {detail}')

    def _handle_bed_arrived(self, info):
        """병상 앞 zone 진입 → round 추종 해제, 완료/복귀 버튼 대기."""
        if self._tracking_stopped:
            return
        self._tracking_stopped = True
        self._arbiter.apply('stop', TRACK_MODE)
        self._arbiter.apply('stop', 'round')
        zone = str((info or {}).get('zone_id') or 'unknown')
        room = str((info or {}).get('room_id') or '')
        bed = str((info or {}).get('bed_id') or '')
        detail = f'bed_arrived:{zone}:{room}:{bed}'
        self._emit('running', detail)
        self._log.info(
            f'[nurse_cart] → BED_ARRIVED id={self._id} zone={zone} '
            f'room={room} bed={bed} — 추종 해제, QR/완료 대기')

    def _enter_goto_home(self):
        """회진 완료 → round 모드 해제 + 홈(도킹 스테이션) 복귀 + 자동 dock."""
        p = self._home_params
        self._state = GOTO_HOME
        self._set_result(None)
        self._arbiter.apply('stop', TRACK_MODE)       # 추종 모드 해제
        self._arbiter.apply('stop', 'round')          # direct cmd_vel 추종도 방어적으로 해제
        self._emit('running', 'returning_home')
        self._log.info(
            f'[nurse_cart] → GOTO_HOME id={self._id} '
            f'({p["x"]:.3f}, {p["y"]:.3f}) dock_after=True')
        if self._nav.active:
            self._nav.cancel()
        self._arbiter.apply('start', 'goto', p)

        def _on_done(status, detail):
            self._arbiter.apply('stop', 'goto')
            self._set_result((status, detail))

        self._nav.start(p, _on_done)

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
