#!/usr/bin/env python3
"""DB bridge node — Firebase Firestore integration."""

import rclpy
from rclpy.node import Node


class DbNode(Node):
    """Provides prescription lookup and medicine verification via Firebase."""

    def __init__(self):
        super().__init__('db_node')
        self.get_logger().info('db_node started')


def main(args=None):
    rclpy.init(args=args)
    node = DbNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
