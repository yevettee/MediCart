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
import os

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from medi_interfaces.srv import StartPatrol

from .mission_executor import MissionExecutor
from .state_machine import MISSION_MEDICATION, MISSION_PATROL, StateMachine


# Service that starts the autonomous patrol mission.
START_PATROL_SERVICE = '/robot6/start_patrol'


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

        self.get_logger().info(
            'mission_manager_node started (mission_type={}, ns={}, mission_request 구독)'
            .format(mission_type, ns))

    # ── mission_pool 시스템 명령 ─────────────────────────────────────────
    def _on_mission_request(self, msg):
        try:
            req = json.loads(msg.data)
        except (ValueError, TypeError) as exc:
            self.get_logger().warn(
                '[mission_manager] mission_request 파싱 실패: {} raw={!r}'.format(exc, msg.data))
            return
        self._executor.handle(req)

    def _publish_feedback(self, payload):
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self._feedback_pub.publish(msg)

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
