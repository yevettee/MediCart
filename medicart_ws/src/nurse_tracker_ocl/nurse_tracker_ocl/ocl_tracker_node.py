#!/usr/bin/env python3
"""OCL-based nurse tracker node."""

import rclpy
from rclpy.node import Node


class OclTrackerNode(Node):
    """Tracks a nurse using OCL feature memory and ReID."""

    def __init__(self):
        super().__init__('ocl_tracker_node')
        self.get_logger().info('ocl_tracker_node started')


def main(args=None):
    rclpy.init(args=args)
    node = OclTrackerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
