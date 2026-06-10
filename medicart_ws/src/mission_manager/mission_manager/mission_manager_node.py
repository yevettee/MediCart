#!/usr/bin/env python3
"""mission_manager — 모드 중재 허브 + mission_pool 명령 실행.

db_node 가 보내는 명령(/{ns}/mission_request, mission_pool 유래)을 2-lane 라우팅:
  - 시스템 액션(dock/undock/ros_restart/reboot/shutdown) → MissionExecutor(bashrc 참고)
  - 모드 액션(start/stop/clear + mode) → ModeArbiter(우선순위 선점/복귀·cmd_vel 게이트)
/{ns}/mission_feedback 으로 결과 보고. (구 StartPatrol/state_machine 경로는 모드 체계로 대체·제거.)
"""
import json
import math
import os
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String

from .mission_executor import MissionExecutor
from .mission_sequencer import MissionSequencer, SEQUENCE_ACTION
from .mode_arbiter import ModeArbiter
from .nav_executor import NavExecutor
from .nurse_cart_sequencer import NurseCartSequencer, NURSE_CART_ACTION
from .patrol_intake_sequencer import PatrolIntakeSequencer, PATROL_INTAKE_ACTION
from .system_commands import SYSTEM_ACTIONS


# 모드 레지스트리 — 이름: actuation. 외부 노드가 /{ns}/mode/<name>/* 계약 따름.
MODE_REGISTRY = {
    "goto": "nav",         # 운영자 좌표 이동(허브 내부 NavExecutor)
    "round": "reactive",   # 회진/추종 (nurse_tracker)
    "patrol": "nav", "errand": "nav", "guide": "nav", "intake": "nav",
}
MODE_ACTIONS = ("start", "stop", "clear")
SEQUENCE_ACTIONS = (SEQUENCE_ACTION,)   # patrol_mission: undock→patrol→dock 시퀀스


class MissionManagerNode(Node):
    """모드 중재 허브 + 시스템 명령 실행 노드."""

    def __init__(self):
        super().__init__('mission_manager_node')

        # ── mission_pool 시스템 명령 경로 ────────────────────────────────
        self.declare_parameter('namespace', os.environ.get('ROBOT_NAMESPACE', 'robot6'))
        self.declare_parameter('discovery_ip', os.environ.get('DISCOVERY_IP', ''))
        self.declare_parameter('ssh_pass', os.environ.get('ROBOT_SSH_PASS', 'turtlebot4'))
        ns = str(self.get_parameter('namespace').value).strip('/')
        discovery_ip = str(self.get_parameter('discovery_ip').value)
        ssh_pass = str(self.get_parameter('ssh_pass').value)

        self._feedback_pub = self.create_publisher(String, f'/{ns}/mission_feedback', 10)
        self._executor = MissionExecutor(
            ns=ns, discovery_ip=discovery_ip, ssh_pass=ssh_pass,
            publish_feedback=self._publish_feedback, logger=self.get_logger())
        self.create_subscription(String, f'/{ns}/mission_request', self._on_mission_request, 10)
        if not discovery_ip:
            self.get_logger().warn(
                '[mission_manager] DISCOVERY_IP 미설정 — ros_restart/reboot/shutdown(ssh) '
                '불가. robot.env 를 source 후 실행하세요.')

        # ── 모드 중재 허브 ───────────────────────────────────────────────
        self.declare_parameter('control_hz', 10.0)
        self.declare_parameter('front_cone_deg', 30.0)
        self._front_cone = math.radians(float(self.get_parameter('front_cone_deg').value))
        self._forward_clearance = None
        self._arbiter = ModeArbiter(self, ns, MODE_REGISTRY, self.get_logger())
        # 시나리오 A 시퀀서 — patrol_mission(undock→patrol→dock) 오케스트레이션.
        self._sequencer = MissionSequencer(
            self._executor, self._arbiter, self._publish_feedback, self.get_logger())
        self._nav = NavExecutor(self, ns, self.get_logger())
        # 간호사 카트 시퀀서 — nurse_cart_mission(goto_pharmacy→...) 오케스트레이션.
        self._nurse_cart = NurseCartSequencer(
            self._nav, self._arbiter, self._publish_feedback, self.get_logger())
        # 시나리오 A 순회 문진 시퀀서 — patrol_intake_mission(병상별 goto→intake 대기 루프).
        self._patrol_intake = PatrolIntakeSequencer(
            self._nav, self._arbiter, self._publish_feedback, self.get_logger())
        # db_node 가 RTDB ocr_done 을 감지해 발행하는 topic 을 받아 시퀀서에 전달.
        self.create_subscription(
            String, f'/{ns}/nurse_cart/ocr_done', self._on_nurse_cart_ocr_done, 10)
        self.create_subscription(
            String, f'/{ns}/nurse_cart/round_done', self._on_nurse_cart_round_done, 10)
        # db_node 가 RTDB patrol/intake_done 을 감지해 발행하는 topic → 순회 문진 시퀀서 전달.
        self.create_subscription(
            String, f'/{ns}/patrol/intake_done', self._on_patrol_intake_done, 10)
        self._cmd_pub = self.create_publisher(Twist, f'/{ns}/cmd_vel', 10)
        self._robot_mode_pub = self.create_publisher(String, f'/{ns}/robot_mode', 10)
        self.create_subscription(LaserScan, f'/{ns}/scan', self._on_scan, 10)
        hz = float(self.get_parameter('control_hz').value)
        self.create_timer(1.0 / hz, self._control_tick)

        self.get_logger().info(
            'mission_manager_node started (ns={}, 모드={} @ {:.0f}Hz)'
            .format(ns, list(MODE_REGISTRY), hz))

    # ── mission_request 2-lane 라우팅 (시스템 액션 / 모드 액션) ───────────
    def _on_mission_request(self, msg):
        try:
            req = json.loads(msg.data)
        except (ValueError, TypeError) as exc:
            self.get_logger().warn(
                '[mission_manager] mission_request 파싱 실패: {} raw={!r}'.format(exc, msg.data))
            return
        action = req.get('action')
        if action == SEQUENCE_ACTION:                  # patrol_mission(undock→patrol→dock)
            self._sequencer.start(req.get('id'), req.get('params'))
        elif action == NURSE_CART_ACTION:             # nurse_cart_mission(goto_pharmacy→...)
            self._nurse_cart.start(req.get('id'), req.get('params'))
        elif action == PATROL_INTAKE_ACTION:          # patrol_intake_mission(병상 순회+문진 대기)
            self._patrol_intake.start(req.get('id'), req.get('params'))
        elif action in SYSTEM_ACTIONS:               # dock/undock/ros_restart/reboot/shutdown
            self._executor.handle(req)
        elif action == 'goto':                        # 좌표 이동(Nav2 + dock-aware)
            self._handle_goto(req)
        elif action in MODE_ACTIONS:                  # start/stop/clear (+mode)
            ok, detail = self._arbiter.apply(action, req.get('mode'), req.get('params'))
            self._publish_feedback({'id': req.get('id'),
                                    'status': 'done' if ok else 'failed',
                                    'detail': detail, 'ts': int(time.time() * 1000)})
        else:
            self._publish_feedback({'id': req.get('id'), 'status': 'failed',
                                    'detail': 'unknown action: {}'.format(action),
                                    'ts': int(time.time() * 1000)})

    def _on_nurse_cart_ocr_done(self, _msg):
        """db_node 경유 OCR 완료 신호 → nurse_cart 시퀀서 WAIT_OCR 해제."""
        self._nurse_cart.signal_ocr_done()

    def _on_nurse_cart_round_done(self, _msg):
        """db_node 경유 회진 완료 신호 → nurse_cart 시퀀서 WAIT_ROUND_DONE 해제 → 홈 복귀."""
        self._nurse_cart.signal_round_done()

    def _on_patrol_intake_done(self, _msg):
        """db_node 경유 문진 완료 신호 → patrol_intake 시퀀서 WAIT_INTAKE 해제 → 다음 병상."""
        self._patrol_intake.signal_intake_done()

    def _handle_goto(self, req):
        """goto 좌표 이동: arbiter 'goto'(nav) 점거 → NavExecutor 실행 → 종료 시 해제·보고."""
        mid = req.get('id')
        params = req.get('params') or {}
        try:
            float(params['x']); float(params['y'])
        except (KeyError, TypeError, ValueError):
            self._publish_feedback({'id': mid, 'status': 'failed',
                                    'detail': 'goto requires numeric x,y',
                                    'ts': int(time.time() * 1000)})
            return
        if self._nav.active:                          # 신규 goto 가 기존 이동 선점
            self._nav.cancel()
        self._arbiter.apply('start', 'goto', params)  # nav 점거(REACTIVE 선점, cmd_vel 양보)

        def _done(status, detail):
            self._arbiter.apply('stop', 'goto')
            self._publish_feedback({'id': mid, 'action': 'goto', 'status': status,
                                    'detail': detail, 'ts': int(time.time() * 1000)})

        self._nav.start(params, _done)
        self._publish_feedback({'id': mid, 'action': 'goto', 'status': 'running',
                                'detail': 'navigating', 'ts': int(time.time() * 1000)})

    def _publish_feedback(self, payload):
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self._feedback_pub.publish(msg)

    # ── 안전 입력 + 제어 루프 ────────────────────────────────────────────
    def _on_scan(self, scan):
        front = None
        a = scan.angle_min
        for r in scan.ranges:
            if math.isfinite(r) and r > 0.0 and abs(a) <= self._front_cone:
                front = r if front is None else min(front, r)
            a += scan.angle_increment
        self._forward_clearance = front

    def _control_tick(self):
        now = time.monotonic()
        self._sequencer.tick(now)             # 시나리오 A 자율 (undock→patrol→dock)
        self._nurse_cart.tick(now)            # 간호사 카트 (goto_pharmacy→...)
        self._patrol_intake.tick(now)         # 시나리오 A 순회 문진 (병상 순회+문진 대기)
        mode, twist = self._arbiter.tick(now, self._forward_clearance, None)
        if twist is not None:                 # REACTIVE 활성 → 게이트된 속도
            self._publish_cmd(twist[0], twist[1])
        elif mode == 'idle' and not self._sequencer.owns_base():
            self._publish_cmd(0.0, 0.0)       # 대기 → 정지 (dock/undock 중엔 Create3 소유)
        # NAV 활성 → 미발행(Nav2 소유)
        m = String(); m.data = mode
        self._robot_mode_pub.publish(m)

    def _publish_cmd(self, lin, ang):
        tw = Twist(); tw.linear.x = float(lin); tw.angular.z = float(ang)
        self._cmd_pub.publish(tw)


def main(args=None):
    """Spin the mission manager node."""
    rclpy.init(args=args)
    node = MissionManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
