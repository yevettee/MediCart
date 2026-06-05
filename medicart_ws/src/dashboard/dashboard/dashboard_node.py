#!/usr/bin/env python3
"""Dashboard node — command interface for MediCart operators.

Adds the patrol-mode controls and displays on top of the existing operator
dashboard:

* a ``/robot6/start_patrol`` client behind the "start patrol" button
* live patrol progress from ``/robot6/patient_identified``
* operator pop-ups for failure statuses (no_qr / mismatch / db_error)

State is kept in GuiPanel; a GUI toolkit renders from it.
"""

import rclpy
from rclpy.node import Node

from medi_interfaces.msg import PatientIdentified
from medi_interfaces.srv import StartPatrol

from .gui_panel import GuiPanel


# Topics / services under the /robot6 namespace.
START_PATROL_SERVICE = '/robot6/start_patrol'
IDENTIFIED_TOPIC = '/robot6/patient_identified'

# Identification statuses that require operator attention.
ALERT_STATUSES = ('no_qr', 'mismatch', 'db_error')


class DashboardNode(Node):
    """Publishes operator commands and displays robot state."""

    def __init__(self):
        """Set up the patrol controls, displays and the view model."""
        super().__init__('dashboard_node')

        self.panel = GuiPanel()

        self._start_patrol_client = self.create_client(StartPatrol, START_PATROL_SERVICE)

        self.create_subscription(
            PatientIdentified, IDENTIFIED_TOPIC, self._on_identified, 10)

        self.get_logger().info('dashboard_node started')

    def start_patrol(self):
        """Invoke the start-patrol service (wired to the start button)."""
        if not self._start_patrol_client.wait_for_service(timeout_sec=2.0):
            self.get_logger().error('start_patrol service unavailable')
            return None
        self.panel.start_patrol(self.panel.total_rooms)
        return self._start_patrol_client.call_async(StartPatrol.Request())

    def _on_identified(self, msg):
        """Advance patrol progress and pop up failure statuses."""
        self.panel.update_progress(self.panel.current_room_index + 1)
        self.get_logger().info('patrol progress {} (status={})'.format(
            self.panel.progress_text(), msg.status))

        if msg.status in ALERT_STATUSES:
            text = 'Room {} [{}] patient {}'.format(
                msg.room, msg.status, msg.patient_id or '?')
            self.panel.push_alert(text)
            self.get_logger().warn('ATTENTION: {}'.format(text))


def main(args=None):
    """Spin the dashboard node."""
    rclpy.init(args=args)
    node = DashboardNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
