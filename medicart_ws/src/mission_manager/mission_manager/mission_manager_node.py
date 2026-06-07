#!/usr/bin/env python3
"""Mission manager node — orchestrates navigation, docking, and scan workflows.

Selects a mission flow from the ``mission_type`` parameter (``patrol`` for the
autonomous patrol + interview scenario, ``medication`` for nurse-following
medication assistance) and drives the shared StateMachine. The patrol scenario
is kicked off through the ``/robot6/start_patrol`` service.

또한 db_node 가 보내는 시스템 명령(/{ns}/mission_request, mission_pool 유래)을 받아
MissionExecutor 로 실행하고 /{ns}/mission_feedback 으로 진행/결과를 보고한다
(dock/undock/ros_restart/reboot/shutdown — bashrc 명령 참고).
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

from medi_interfaces.srv import StartPatrol

from .mission_executor import MissionExecutor
from .mode_arbiter import ModeArbiter
from .state_machine import MISSION_MEDICATION, MISSION_PATROL, StateMachine
from .system_commands import SYSTEM_ACTIONS


# Service that starts the autonomous patrol mission.
START_PATROL_SERVICE = '/robot6/start_patrol'

# 모드 레지스트리 — 이름: actuation. 외부 노드가 /{ns}/mode/<name>/* 계약 따름.
MODE_REGISTRY = {
    "round": "reactive",   # 회진/추종 (nurse_tracker)
    "patrol": "nav", "errand": "nav", "guide": "nav", "intake": "nav",
}
MODE_ACTIONS = ("start", "stop", "clear")


class MissionManagerNode(Node):
    """Central state machine coordinating robot missions."""

    def __init__(self):
        """Set up the state machine for the configured mission type."""
        super().__init__('mission_manager_node')

        self.declare_parameter('mission_type', MISSION_MEDICATION)
        mission_type = self.get_parameter('mission_type').value
        self._sm = StateMachine(mission_type=mission_type)

        self._start_patrol_srv = self.create_service(
            StartPatrol, START_PATROL_SERVICE, self._on_start_patrol)

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
        self._cmd_pub = self.create_publisher(Twist, f'/{ns}/cmd_vel', 10)
        self._robot_mode_pub = self.create_publisher(String, f'/{ns}/robot_mode', 10)
        self.create_subscription(LaserScan, f'/{ns}/scan', self._on_scan, 10)
        hz = float(self.get_parameter('control_hz').value)
        self.create_timer(1.0 / hz, self._control_tick)

        self.get_logger().info(
            'mission_manager_node started (mission_type={}, ns={}, 모드={} @ {:.0f}Hz)'
            .format(mission_type, ns, list(MODE_REGISTRY), hz))

    # ── mission_request 2-lane 라우팅 (시스템 액션 / 모드 액션) ───────────
    def _on_mission_request(self, msg):
        try:
            req = json.loads(msg.data)
        except (ValueError, TypeError) as exc:
            self.get_logger().warn(
                '[mission_manager] mission_request 파싱 실패: {} raw={!r}'.format(exc, msg.data))
            return
        action = req.get('action')
        if action in SYSTEM_ACTIONS:                 # dock/undock/ros_restart/reboot/shutdown
            self._executor.handle(req)
        elif action in MODE_ACTIONS:                  # start/stop/clear (+mode)
            ok, detail = self._arbiter.apply(action, req.get('mode'), req.get('params'))
            self._publish_feedback({'id': req.get('id'),
                                    'status': 'done' if ok else 'failed',
                                    'detail': detail, 'ts': int(time.time() * 1000)})
        else:
            self._publish_feedback({'id': req.get('id'), 'status': 'failed',
                                    'detail': 'unknown action: {}'.format(action),
                                    'ts': int(time.time() * 1000)})

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
        mode, twist = self._arbiter.tick(time.monotonic(), self._forward_clearance, None)
        if twist is not None:                 # REACTIVE 활성 → 게이트된 속도
            self._publish_cmd(twist[0], twist[1])
        elif mode == 'idle':                  # 대기 → 정지
            self._publish_cmd(0.0, 0.0)
        # NAV 활성 → 미발행(Nav2 소유)
        m = String(); m.data = mode
        self._robot_mode_pub.publish(m)

    def _publish_cmd(self, lin, ang):
        tw = Twist(); tw.linear.x = float(lin); tw.angular.z = float(ang)
        self._cmd_pub.publish(tw)

    def _on_start_patrol(self, request, response):
        """Begin the patrol mission by leaving IDLE through UNDOCK."""
        del request  # StartPatrol has an empty request.
        if self._sm.mission_type != MISSION_PATROL:
            response.success = False
            response.message = 'mission_type is not "patrol"'
            return response
        if self._sm.state != 'IDLE':
            response.success = False
            response.message = 'patrol already running (state={})'.format(self._sm.state)
            return response

        self._sm.transition('UNDOCK')
        response.success = True
        response.message = 'patrol started'
        self.get_logger().info('patrol started; state={}'.format(self._sm.state))
        return response


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
