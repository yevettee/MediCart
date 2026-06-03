#!/usr/bin/env python3
"""Simulation node — Gazebo simulation placeholder."""

import rclpy
from rclpy.node import Node


class SimulationNode(Node):
    """Placeholder node for Gazebo simulation integration."""

    def __init__(self):
        super().__init__('simulation_node')
        self.get_logger().info('simulation_node started')


def main(args=None):
    rclpy.init(args=args)
    node = SimulationNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
