#!/usr/bin/env python3
"""webcam_node — USB 웹캠(cv2.VideoCapture) → sensor_msgs/Image(bgr8) 발행.

터틀봇4에 연결한 USB 웹캠 프레임을 ROS Image 로 발행해 identifier_node 가
QR 디코드에 쓰게 한다. cv_bridge 없이 수동으로 Image 를 구성한다(identifier 의
imgmsg_to_bgr 와 동일하게 bgr8/rgb8 만 기대하므로 bgr8 로 발행).

웹캠이 물리적으로 연결된 머신에서 실행해야 한다(터틀봇4 본체에 꽂았으면 본체에서).

파라미터:
  namespace    기본 env ROBOT_NAMESPACE. 발행 토픽 = /{namespace}/webcam/image_raw
  image_topic  발행 토픽 직접 지정(주면 namespace 조합 대신 이 값 사용)
  device       cv2.VideoCapture 입력. 정수 인덱스('0') 또는 경로('/dev/video0')
  width,height 캡처 해상도(0이면 카메라 기본값)
  fps          발행 주기(Hz)
  frame_id     Image header frame_id
"""
import os

import numpy as np
import cv2

import rclpy
from rclpy.node import Node

from rcl_interfaces.msg import ParameterDescriptor
from sensor_msgs.msg import Image


class WebcamNode(Node):
    """USB 웹캠을 bgr8 Image 로 발행하는 노드."""

    def __init__(self):
        super().__init__('webcam_node')

        ns = str(self.declare_parameter(
            'namespace', os.environ.get('ROBOT_NAMESPACE', 'robot6')).value).strip('/')
        self.declare_parameter('image_topic', '')
        # device 는 인덱스(0) 또는 경로('/dev/video0') 둘 다 허용 — 동적 타입.
        self.declare_parameter('device', '0',
                               ParameterDescriptor(dynamic_typing=True))
        self.declare_parameter('width', 1280)
        self.declare_parameter('height', 720)
        self.declare_parameter('fps', 15.0)
        self.declare_parameter('frame_id', f'{ns}/webcam')

        topic = str(self.get_parameter('image_topic').value).strip() \
            or f'/{ns}/webcam/image_raw'
        self._frame_id = str(self.get_parameter('frame_id').value)
        width = int(self.get_parameter('width').value)
        height = int(self.get_parameter('height').value)
        fps = float(self.get_parameter('fps').value)

        dev_raw = str(self.get_parameter('device').value).strip()
        device = int(dev_raw) if dev_raw.lstrip('-').isdigit() else dev_raw
        self._device = device

        self._cap = cv2.VideoCapture(device)
        # 다수 USB 웹캠은 YUYV 로는 640x480 까지만, 1280x720 은 MJPG 로만 준다.
        # FOURCC 를 MJPG 로 먼저 강제해야 요청 해상도가 실제로 적용된다.
        self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        if width > 0:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        if height > 0:
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if not self._cap.isOpened():
            self.get_logger().error(
                f'[webcam] 카메라 열기 실패 device={device!r} — '
                f'연결/권한(/dev/video*) 확인. 재시도 계속.')
        else:
            self.get_logger().info(
                f'[webcam] device={device!r} → publish {topic} '
                f'(요청 {width}x{height}, 실제 {actual_w}x{actual_h}@{fps}Hz)')

        self._pub = self.create_publisher(Image, topic, 10)
        self.create_timer(1.0 / max(fps, 1.0), self._tick)

    def _tick(self):
        if not self._cap.isOpened():
            # 카메라가 늦게 연결될 수 있으니 주기적으로 재오픈 시도.
            self._cap.open(self._device)
            return
        ok, frame = self._cap.read()
        if not ok or frame is None:
            self.get_logger().warn('[webcam] 프레임 읽기 실패', throttle_duration_sec=5.0)
            return

        # cv2 는 BGR 3채널 — identifier 의 bgr8 경로와 일치.
        if frame.ndim != 3 or frame.shape[2] != 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        if not frame.flags['C_CONTIGUOUS']:
            frame = np.ascontiguousarray(frame)

        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self._frame_id
        msg.height, msg.width = frame.shape[0], frame.shape[1]
        msg.encoding = 'bgr8'
        msg.is_bigendian = 0
        msg.step = frame.shape[1] * 3
        msg.data = frame.tobytes()
        self._pub.publish(msg)

    def destroy_node(self):
        try:
            if self._cap is not None:
                self._cap.release()
        finally:
            super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = WebcamNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
