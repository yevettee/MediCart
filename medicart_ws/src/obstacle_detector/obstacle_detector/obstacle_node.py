#!/usr/bin/env python3
"""Obstacle detector node — depth image to filtered PointCloud2."""

import rclpy
from rclpy.node import Node


class ObstacleNode(Node):
    """Converts depth images to filtered obstacle point clouds."""

    def __init__(self):
        super().__init__('obstacle_node')
        self.get_logger().info('obstacle_node started')


def main(args=None):
    rclpy.init(args=args)
    node = ObstacleNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
