#!/usr/bin/env python3
"""Dashboard node — command interface for MediCart operators."""

import rclpy
from rclpy.node import Node


class DashboardNode(Node):
    """Publishes operator commands and displays robot state."""

    def __init__(self):
        super().__init__('dashboard_node')
        self.get_logger().info('dashboard_node started')


def main(args=None):
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
