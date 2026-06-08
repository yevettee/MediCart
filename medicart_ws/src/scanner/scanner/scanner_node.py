#!/usr/bin/env python3
"""Scanner node — orchestrates OCR and DB verification for medicine scanning."""

import rclpy
from rclpy.node import Node


class ScannerNode(Node):
    """Verifies scanned medicine against patient prescription via OCR and DB."""

    def __init__(self):
        super().__init__('scanner_node')
        self.get_logger().info('scanner_node started')


def main(args=None):
    rclpy.init(args=args)
    node = ScannerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
