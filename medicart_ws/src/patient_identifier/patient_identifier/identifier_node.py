#!/usr/bin/env python3
"""Patient identifier node — arrival-triggered QR identification (no presence check).

patrol_mode 가 병상 좌표에 '도착'하면 ``/{ns}/identify/start`` 로 room_id 를 보낸다.
그 순간부터 ``scan_timeout`` 초 동안 QR 만 스캔한다(재실 YOLO 판정은 제거):

    QR 인식 → DB 병실 검증 → 'identified' | 'mismatch' | 'db_error'
    scan_timeout 안에 QR 없음 → 'absent' (재실 판정을 대체: 사람 없다고 가정)

결과는 ``/{ns}/patient_identified`` 로 1회 발행한다. status 로 모든 경로를 구분하며,
웹/대시보드(또는 후속 RTDB 브리지)가 이를 받아 'QR 인식해주세요'/'부재' 등을 표시한다.
"""

import os

import numpy as np

import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from medi_interfaces.msg import PatientIdentified

from sensor_msgs.msg import Image
from std_msgs.msg import String

from .patient_validator import PatientValidator
from .qr_scanner import QrScanner


# 토픽/서비스 이름은 namespace 파라미터(env ROBOT_NAMESPACE)로 구성한다.
# 카메라는 image_topic 파라미터로 oakd/webcam 자유롭게 지정 가능.

# Status values published in PatientIdentified.status.
#   identified : QR 디코드 + DB 조회 + 방문 방에 배정된 환자와 일치
#   mismatch   : QR 환자가 DB엔 있으나 방문 방 배정 환자와 다름(다른 환자) → 웹 알림용
#   absent     : scan_timeout 안에 QR 못 잡음(사람 없다고 가정)
# 방↔환자 매핑은 RTDB /rooms/{room_id}/patient. db_bridge lookup_room 이 역검색해
# 환자의 방을 돌려주므로, 방문 room_id 와 비교해 일치/불일치를 가린다.
STATUS_IDENTIFIED = 'identified'
STATUS_MISMATCH = 'mismatch'
STATUS_ABSENT = 'absent'


def imgmsg_to_bgr(msg):
    """Convert a sensor_msgs/Image (bgr8/rgb8) to a BGR numpy array.

    Kept dependency-free (no cv_bridge) so the node only relies on the
    declared rclpy/sensor_msgs/std_msgs/medi_interfaces stack plus numpy.
    """
    if msg is None or not msg.data:
        return None

    frame = np.frombuffer(bytes(msg.data), dtype=np.uint8)
    frame = frame.reshape(msg.height, msg.width, 3)
    if msg.encoding == 'rgb8':
        frame = frame[:, :, ::-1]
    return np.ascontiguousarray(frame)


class IdentifierNode(Node):
    """병상 도착 트리거로 QR 신원확인을 수행(재실 판정 없음)."""

    def __init__(self):
        """Set up publishers, subscriptions, helpers and the scan timer."""
        super().__init__('patient_identifier_node')

        self.declare_parameter('namespace', os.environ.get('ROBOT_NAMESPACE', 'robot6'))
        # 도착 후 QR 대기 시간(초). 이 안에 QR 없으면 부재(absent).
        self.declare_parameter('scan_timeout', 5.0)
        # 윈도우 동안 QR 재시도 주기(초) — 짧을수록 반응 빠름.
        self.declare_parameter('scan_period', 0.5)
        ns = str(self.get_parameter('namespace').value).strip('/')
        # 카메라 토픽 — oakd 기본, webcam 등은 image_topic 파라미터로 덮어쓰기.
        self.declare_parameter('image_topic', f'/{ns}/oakd/rgb/image_raw')
        image_topic = str(self.get_parameter('image_topic').value)
        result_topic = f'/{ns}/patient_identified'
        start_topic = f'/{ns}/identify/start'
        get_prescription_srv = f'/{ns}/db/get_prescription'

        self._scan_timeout = float(self.get_parameter('scan_timeout').value)
        self._latest_image = None

        self._qr_scanner = QrScanner()

        # Reentrant group lets the validator block on the service call from
        # inside the timer callback without deadlocking the executor.
        client_group = ReentrantCallbackGroup()
        timer_group = MutuallyExclusiveCallbackGroup()
        self._validator = PatientValidator(
            self, service_name=get_prescription_srv, callback_group=client_group)

        self._result_pub = self.create_publisher(PatientIdentified, result_topic, 10)

        self.create_subscription(Image, image_topic, self._on_image, 10)
        self.create_subscription(String, start_topic, self._on_start, 10)

        # 스캔 윈도우 상태 — 트리거 전엔 비활성(아무 것도 발행 안 함).
        self._active = False
        self._room = ''
        self._deadline = 0.0

        period = float(self.get_parameter('scan_period').value)
        self._timer = self.create_timer(period, self._scan_tick,
                                        callback_group=timer_group)

        self.get_logger().info(
            'patient_identifier_node started (ns={}, image_topic={}, start={}, timeout={:.0f}s)'
            .format(ns, image_topic, start_topic, self._scan_timeout))

    def _on_image(self, msg):
        """Cache the latest RGB frame."""
        self._latest_image = msg

    def _latest_frame(self):
        """Decode the most recent RGB frame to a BGR numpy array."""
        return imgmsg_to_bgr(self._latest_image)

    def _now(self):
        """Monotonic-ish seconds from the node clock."""
        return self.get_clock().now().nanoseconds / 1e9

    def _on_start(self, msg):
        """patrol_mode 도착 트리거 — 해당 방의 QR 스캔 윈도우를 연다."""
        self._room = str(msg.data).strip()
        self._deadline = self._now() + self._scan_timeout
        self._active = True
        self.get_logger().info(
            'scan start room={} (timeout={:.0f}s)'.format(self._room, self._scan_timeout))

    def _scan_tick(self):
        """윈도우 동안 QR 시도 → DB 방 일치/불일치 판정, 시간 초과 시 부재."""
        if not self._active:
            return

        # QR 스캔(매 시도 fresh frame) → 평문 patient_id.
        patient_id = self._qr_scanner.scan(self._latest_frame)
        if patient_id:
            result = self._validator.validate(patient_id, self._room)
            if result.db_ok:                  # DB 조회 성공 → 방 일치 여부로 판정
                if result.matched:            # 방문 방에 배정된 환자와 일치
                    self._finish(STATUS_IDENTIFIED, is_present=True, is_identified=True,
                                 patient_id=patient_id, patient=result.patient)
                else:                         # 다른 환자 — 웹 알림 대상
                    self._finish(STATUS_MISMATCH, is_present=True,
                                 patient_id=patient_id, patient=result.patient)
                return
            # QR 은 읽혔으나 DB 미확인(미등록/일시오류) — 윈도우 동안 계속 재시도.
            self.get_logger().warn(
                'QR={} DB 미확인({}) — 재시도'.format(patient_id, result.message))

        # 시간 초과까지 식별 못 함 → 부재(사람 없다고 가정).
        if self._now() >= self._deadline:
            self._finish(STATUS_ABSENT, is_present=False)

    def _finish(self, status, is_present=False, is_identified=False,
                patient_id='', patient=None):
        """결과 1회 발행 후 윈도우 종료(다음 트리거까지 비활성)."""
        self._active = False
        msg = PatientIdentified()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.patient_id = patient_id
        msg.patient_name = patient.name if patient is not None else ''
        msg.room = self._room                 # 방문 중인 방(도착 트리거의 room_id)으로 일관
        msg.is_present = is_present
        msg.is_identified = is_identified
        msg.status = status
        self._result_pub.publish(msg)
        self.get_logger().info(
            'room={} status={} patient_id={}'.format(self._room, status, patient_id))


def main(args=None):
    """Spin the identifier node under a multi-threaded executor."""
    rclpy.init(args=args)
    node = IdentifierNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
