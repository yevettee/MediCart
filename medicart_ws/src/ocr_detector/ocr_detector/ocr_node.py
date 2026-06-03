#!/usr/bin/env python3
"""OCR detector node — medicine label text recognition service."""

import rclpy
from rclpy.node import Node


class OcrNode(Node):
    """Provides OCR service using the latest camera frame."""

    def __init__(self):
        super().__init__('ocr_node')
        self.get_logger().info('ocr_node started')


def main(args=None):
    rclpy.init(args=args)
    node = OcrNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
