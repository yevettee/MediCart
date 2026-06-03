#!/usr/bin/env python3
"""Nurse tracker node — YOLO detection, tracking, and spatial estimation."""

import rclpy
from rclpy.node import Node


class TrackerNode(Node):
    """Tracks a nurse and publishes target pose in map frame."""

    def __init__(self):
        super().__init__('tracker_node')
        self.get_logger().info('tracker_node started')


def main(args=None):
    rclpy.init(args=args)
    node = TrackerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
