"""mission_sequencer — 시나리오 A 단일 명령(undock→순찰→dock) 오케스트레이션.

mission_request 의 단일 action='patrol_mission' 을 받아 세 단계를 순차 실행한다:

  1. UNDOCK  — MissionExecutor 로 Create3 undock 액션(완료까지 대기)
  2. PATROL  — ModeArbiter 로 patrol 모드 활성화 후, 모드 status 가
               'done'/'failed' 가 되거나 arbiter 가 모드를 내릴 때까지 대기
  3. DOCK    — MissionExecutor 로 Create3 dock 액션(완료까지 대기)

진행/결과는 부모 mission id 로 publish_feedback(accepted→running…→done|failed) 발행.
db_node 는 이 한 건을 done 받을 때까지 다음 order 를 시작하지 않으므로, 시나리오 A 가
끝날 때까지 mission_pool 이 막혀(블록) 순서가 보장된다.

설계 포인트
  · 단일 스레드(rclpy.spin) 전제 — 상태전이는 모두 tick()(노드 메인 스레드)에서만 일어난다.
    executor 워커 스레드는 on_complete 로 결과만 잠금 보호 후 저장하고, tick 이 읽어 진행한다.
  · undock/dock 타임아웃은 MissionExecutor 가 소유(ACTION_TIMEOUTS). 여기선 patrol 시작
    지연만 자체 워치독(start_timeout)으로 본다.
  · 안전: undock 실패 → 로봇은 여전히 도크에 있으니 중단(failed). patrol 실패/lost →
    로봇을 회수하기 위해 dock 으로 진행. dock 실패 → failed.
"""
import threading
import time

# 시퀀스 상태
IDLE, UNDOCK, PATROL_START, PATROL_RUN, DOCK, DONE, FAILED = (
    'idle', 'undock', 'patrol_start', 'patrol_run', 'dock', 'done', 'failed')

# 시퀀스를 기동하는 mission_request action.
SEQUENCE_ACTION = 'patrol_mission'


def _now_ms():
    return int(time.time() * 1000)


class MissionSequencer:
    """undock→patrol→dock 시퀀스 상태기(상태전이는 tick 에서만)."""

    def __init__(self, executor, arbiter, publish_feedback, logger,
                 mode_name='patrol', start_timeout=15.0):
        self._executor = executor
        self._arbiter = arbiter
        self._publish = publish_feedback
        self._log = logger
        self._mode = mode_name
        self._start_timeout = float(start_timeout)

        self._state = IDLE
        self._id = None
        self._params = {}
        self._deadline = 0.0
        self._lock = threading.Lock()    # executor 워커 스레드와 공유하는 결과만 보호
        self._sys_result = None          # (status, detail) | None

    # ── 외부 인터페이스 ──────────────────────────────────────────────────
    def active(self):
        """시퀀스 진행 중 여부."""
        return self._state not in (IDLE, DONE, FAILED)

    def owns_base(self):
        """Create3 dock/undock 액션이 base 를 제어 중 — 노드의 idle cmd_vel 발행 억제용."""
        return self._state in (UNDOCK, DOCK)

    def start(self, mission_id, params=None):
        """시나리오 A 시퀀스 시작(mission_request action='patrol_mission')."""
        if self.active():
            self._emit_to(mission_id, 'failed', 'sequencer busy (시퀀스 진행 중)')
            self._log.warn(f'[sequencer] busy 거부 id={mission_id}')
            return
        self._id = mission_id
        self._params = params or {}
        self._emit('accepted', '시나리오 A: undock→patrol→dock')
        self._log.info(f'[sequencer] ▶ START id={mission_id} → undock')
        self._enter_undock()

    def tick(self, now):
        """제어주기 1회 — 단계 완료를 확인해 다음 단계로 전이."""
        if self._state == UNDOCK:
            res = self._take_result()
            if res is None:
                return
            status, detail = res
            if status == 'done':
                self._enter_patrol(now)
            else:
                self._fail(f'undock {status}: {detail}')
        elif self._state == PATROL_START:
            st = self._arbiter.mode_state(self._mode)
            if st == 'running':
                self._state = PATROL_RUN
                self._log.info('[sequencer] patrol 시작 확인 → 완료 대기')
            elif st in ('done', 'failed'):
                self._finish_patrol(st)
            elif now > self._deadline:
                self._log.error('[sequencer] patrol 시작 지연(status 없음) → 회수 dock')
                self._emit('running', 'patrol failed to start → docking')
                self._enter_dock()
        elif self._state == PATROL_RUN:
            st = self._arbiter.mode_state(self._mode)
            if st in ('done', 'failed'):
                self._finish_patrol(st)
            elif not self._arbiter.is_active(self._mode):
                # arbiter 가 모드를 내렸는데 done/failed 도 아님 = lost abort 등 → 회수.
                self._log.warn('[sequencer] patrol 비활성(lost) → 회수 dock')
                self._emit('running', 'patrol lost → docking')
                self._enter_dock()
        elif self._state == DOCK:
            res = self._take_result()
            if res is None:
                return
            status, detail = res
            if status == 'done':
                self._done('시나리오 A 완료 (docked)')
            else:
                self._fail(f'dock {status}: {detail}')

    # ── 단계 전이 ────────────────────────────────────────────────────────
    def _enter_undock(self):
        self._state = UNDOCK
        self._run_system('undock')

    def _enter_patrol(self, now):
        self._emit('running', 'undock done → patrol')
        self._arbiter.reset_status(self._mode)       # 직전 실행의 stale done 제거
        self._arbiter.apply('start', self._mode, self._params)
        self._state = PATROL_START
        self._deadline = now + self._start_timeout
        self._log.info(f'[sequencer] undock 완료 → patrol 활성화 '
                       f'(start_timeout={self._start_timeout:.0f}s)')

    def _finish_patrol(self, status):
        self._emit('running', f'patrol {status} → docking')
        self._log.info(f'[sequencer] patrol {status} → 회수 dock')
        self._enter_dock()

    def _enter_dock(self):
        self._arbiter.apply('stop', self._mode)      # patrol 확실히 해제(idempotent)
        self._state = DOCK
        self._run_system('dock')

    # ── 하위 시스템 액션(executor) ───────────────────────────────────────
    def _run_system(self, action):
        self._set_result(None)
        subid = f'{self._id}:{action}'
        self._executor.handle({'id': subid, 'action': action},
                              feedback_override=self._sys_feedback,
                              on_complete=self._sys_complete)

    def _sys_feedback(self, payload):
        """executor 워커 스레드 — 진행 피드백을 부모 id 의 running 으로 중계."""
        status = payload.get('status')
        if status in ('accepted', 'running'):
            self._emit('running', payload.get('detail', ''))

    def _sys_complete(self, status, detail):
        """executor 워커 스레드 — 종료 결과만 저장(전이는 tick 에서)."""
        self._set_result((status, detail))

    def _take_result(self):
        with self._lock:
            res, self._sys_result = self._sys_result, None
        return res

    def _set_result(self, value):
        with self._lock:
            self._sys_result = value

    # ── 피드백/종료 ──────────────────────────────────────────────────────
    def _emit(self, status, detail):
        self._emit_to(self._id, status, detail)

    def _emit_to(self, mission_id, status, detail):
        self._publish({'id': mission_id, 'status': status,
                       'detail': str(detail), 'ts': _now_ms()})

    def _done(self, detail):
        self._emit('done', detail)
        self._log.info(f'[sequencer] ■ DONE id={self._id} :: {detail}')
        self._state = DONE
        self._id = None

    def _fail(self, detail):
        self._emit('failed', detail)
        self._log.error(f'[sequencer] ■ FAILED id={self._id} :: {detail}')
        self._state = FAILED
        self._id = None
