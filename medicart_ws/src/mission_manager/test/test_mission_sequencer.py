"""MissionSequencer 단위 테스트 — executor/arbiter 를 가짜로 주입(순수 로직).

undock→patrol→dock 전이와 실패/회수 경로를 ROS 없이 검증한다.
"""
from mission_manager.mission_sequencer import MissionSequencer


class FakeExecutor:
    """handle 시 즉시 on_complete 로 결과 통지(동기) — tick 이 읽어 진행."""

    def __init__(self, results=None):
        self.results = results or {}          # {action: (status, detail)}
        self.handled = []                     # [action, ...]

    def handle(self, request, feedback_override=None, on_complete=None):
        action = request.get('action')
        self.handled.append(action)
        status, detail = self.results.get(action, ('done', 'ok'))
        if feedback_override is not None:
            feedback_override({'id': request.get('id'), 'status': 'running', 'detail': 'x'})
        if on_complete is not None:
            on_complete(status, detail)


class FakeArbiter:
    """mode_state/is_active 를 테스트가 직접 설정."""

    def __init__(self):
        self.state = None
        self.active = False
        self.applied = []                     # [(action, mode), ...]
        self.reset = []                       # [mode, ...]

    def mode_state(self, name):
        return self.state

    def is_active(self, name):
        return self.active

    def reset_status(self, name):
        self.reset.append(name)

    def apply(self, action, mode=None, params=None):
        self.applied.append((action, mode))
        if action == 'start':
            self.active = True
        elif action in ('stop', 'clear'):
            self.active = False
        return True, 'ok'


class FakeLogger:
    def info(self, *a):
        pass

    def warn(self, *a):
        pass

    def error(self, *a):
        pass


def _make():
    fb = []
    ex = FakeExecutor()
    arb = FakeArbiter()
    seq = MissionSequencer(ex, arb, fb.append, FakeLogger())
    return seq, ex, arb, fb


def _statuses(fb):
    return [m['status'] for m in fb]


def test_happy_path_undock_patrol_dock():
    seq, ex, arb, fb = _make()

    seq.start('m1')
    assert ex.handled == ['undock']           # 먼저 undock 발행
    assert seq.active()

    seq.tick(0.0)                             # undock done → patrol 활성화
    assert ('start', 'patrol') in arb.applied
    assert arb.reset == ['patrol']            # stale status 초기화

    arb.state = 'running'
    seq.tick(1.0)                             # patrol 시작 확인 → RUN

    arb.state = 'done'
    seq.tick(2.0)                             # patrol done → dock
    assert ex.handled == ['undock', 'dock']
    assert ('stop', 'patrol') in arb.applied

    seq.tick(3.0)                             # dock done → 완료
    assert not seq.active()
    assert _statuses(fb)[0] == 'accepted'
    assert _statuses(fb)[-1] == 'done'


def test_undock_failure_aborts_without_dock():
    seq, ex, arb, fb = _make()
    ex.results['undock'] = ('failed', 'rc=1')

    seq.start('m1')
    seq.tick(0.0)                             # undock failed → 중단

    assert ex.handled == ['undock']           # dock 미발행
    assert ('start', 'patrol') not in arb.applied
    assert _statuses(fb)[-1] == 'failed'
    assert not seq.active()


def test_patrol_lost_recovers_by_docking():
    seq, ex, arb, fb = _make()

    seq.start('m1')
    seq.tick(0.0)                             # → PATROL_START
    arb.state = 'running'
    seq.tick(1.0)                             # → PATROL_RUN

    arb.active = False                        # mode_state 는 여전히 running, 하지만 lost
    seq.tick(2.0)                             # lost → 회수 dock

    assert ex.handled == ['undock', 'dock']


def test_patrol_start_timeout_falls_through_to_dock():
    seq, ex, arb, fb = _make()

    seq.start('m1')
    seq.tick(0.0)                             # → PATROL_START (deadline=15)
    arb.state = None                          # 시작 status 영영 안 옴

    seq.tick(20.0)                            # deadline 초과 → 회수 dock
    assert ex.handled == ['undock', 'dock']


def test_busy_rejects_second_start():
    seq, ex, arb, fb = _make()
    seq.start('m1')
    seq.start('m2')                           # 진행 중 두 번째 → 거부
    assert fb[-1]['id'] == 'm2'
    assert fb[-1]['status'] == 'failed'
