"""mission_executor — mission_request 시스템 명령을 워커 스레드 subprocess 로 실행.

db_node 가 /{ns}/mission_request(JSON {id,action,params})를 보내면, 여기서 명령을
실행하고 /{ns}/mission_feedback(JSON {id,status,detail,ts})로 진행/결과를 보고한다.
  status: accepted → running(진행 stdout 라인) → done | failed
실행 자체는 db_node 가 직렬화하지만(완료 전 다음 미발행) 안전을 위해 한 번에 1건만 처리.
"""
import os
import subprocess
import threading
import time

from mission_manager.system_commands import (ACTION_TIMEOUTS, DEFAULT_TIMEOUT,
                                              build_argv, is_valid,
                                              success_returncodes)


def _now_ms():
    return int(time.time() * 1000)


class MissionExecutor:
    """시스템 명령 실행기. publish_feedback(dict) 콜백으로 피드백 발행."""

    def __init__(self, ns, discovery_ip, ssh_pass, publish_feedback, logger):
        self.ns = str(ns).strip('/')
        self.discovery_ip = discovery_ip
        self.ssh_pass = ssh_pass
        self._publish = publish_feedback
        self._log = logger
        self._busy = threading.Lock()

    def handle(self, request):
        """mission_request dict 처리 시작(논블로킹 — 워커 스레드)."""
        mid = request.get('id')
        action = request.get('action')
        self._log.info(f'[executor] 요청 수신 id={mid} action={action}')
        threading.Thread(target=self._run, args=(mid, action), daemon=True).start()

    # ── 워커 ─────────────────────────────────────────────────────────────
    def _run(self, mid, action):
        if not self._busy.acquire(blocking=False):
            self._feedback(mid, 'failed', 'executor busy (다른 명령 실행 중)')
            self._log.warn(f'[executor] busy 거부 id={mid} action={action}')
            return
        try:
            self._execute(mid, action)
        finally:
            self._busy.release()

    def _execute(self, mid, action):
        if not is_valid(action):
            self._feedback(mid, 'failed', f'unknown action: {action}')
            self._log.error(f'[executor] 잘못된 action id={mid} action={action}')
            return
        try:
            argv = build_argv(action, self.ns, self.discovery_ip, self.ssh_pass)
        except ValueError as exc:
            self._feedback(mid, 'failed', str(exc))
            self._log.error(f'[executor] argv 생성 실패 id={mid}: {exc}')
            return

        timeout = ACTION_TIMEOUTS.get(action, DEFAULT_TIMEOUT)
        # 로그/피드백엔 비밀번호 노출 방지(sshpass -p <pw> 마스킹)
        safe_argv = ['***' if a == self.ssh_pass else a for a in argv]
        self._feedback(mid, 'accepted', f'starting {action}')
        self._log.info(f'[executor] ▶ RUN id={mid} action={action} '
                       f'timeout={timeout:.0f}s argv={safe_argv}')

        try:
            proc = subprocess.Popen(
                argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=os.environ.copy())
        except FileNotFoundError as exc:
            self._feedback(mid, 'failed', f'command not found: {exc}')
            self._log.error(f'[executor] 실행파일 없음 id={mid}: {exc}')
            return
        except Exception as exc:                       # noqa: BLE001
            self._feedback(mid, 'failed', f'spawn error: {exc}')
            self._log.error(f'[executor] spawn 오류 id={mid}: {exc}')
            return

        start = time.time()
        lines = []
        try:
            for line in proc.stdout:                    # 진행 stdout 스트리밍
                line = line.rstrip()
                if not line:
                    continue
                lines.append(line)
                self._log.info(f'[executor] {action}#{mid} | {line}')
                self._feedback(mid, 'running', line[:160])
                if time.time() - start > timeout:
                    proc.kill()
                    self._feedback(mid, 'failed', f'timeout {timeout:.0f}s')
                    self._log.error(f'[executor] ⏰ TIMEOUT kill id={mid} action={action}')
                    return
            proc.wait(timeout=5)
        except Exception as exc:                       # noqa: BLE001
            try:
                proc.kill()
            except Exception:                          # noqa: BLE001
                pass
            self._feedback(mid, 'failed', f'exec error: {exc}')
            self._log.error(f'[executor] 실행 오류 id={mid}: {exc}')
            return

        rc = proc.returncode
        tail = ' / '.join(lines[-4:])[-200:]
        if rc in success_returncodes(action):
            self._feedback(mid, 'done', f'rc={rc} {tail}'.strip())
            self._log.info(f'[executor] ■ DONE id={mid} action={action} rc={rc}')
        else:
            self._feedback(mid, 'failed', f'rc={rc} {tail}'.strip())
            self._log.error(f'[executor] ■ FAILED id={mid} action={action} rc={rc} :: {tail}')

    def _feedback(self, mid, status, detail):
        self._publish({'id': mid, 'status': status, 'detail': str(detail), 'ts': _now_ms()})
