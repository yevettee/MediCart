#!/usr/bin/env python3
"""Mission manager node — orchestrates navigation, docking, and scan workflows.

Selects a mission flow from the ``mission_type`` parameter (``patrol`` for the
autonomous patrol + interview scenario, ``medication`` for nurse-following
medication assistance) and drives the shared StateMachine. The patrol scenario
is kicked off through the ``/robot6/start_patrol`` service.
"""

import rclpy
from rclpy.node import Node

from medi_interfaces.srv import StartPatrol

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

        self.get_logger().info(
            'mission_manager_node started (mission_type={})'.format(mission_type))

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
