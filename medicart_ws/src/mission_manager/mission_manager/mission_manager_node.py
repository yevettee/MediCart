#!/usr/bin/env python3
"""Mission manager node — orchestrates navigation, docking, and scan workflows."""

import rclpy
from rclpy.node import Node


class MissionManagerNode(Node):
    """Central state machine coordinating robot missions."""

    def __init__(self):
        super().__init__('mission_manager_node')
        self.get_logger().info('mission_manager_node started')


def main(args=None):
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
