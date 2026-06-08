#!/usr/bin/env python3
"""Patient identifier node — orchestrates person detection, QR scan and DB check.

Pipeline run on each tick:

    YOLO person detection -> QR scan -> DB validation -> publish result

Outcomes are published on ``/robot3/patient_identified``. The ``status`` field
distinguishes every path (identified / absent / mismatch / no_qr / db_error);
the dashboard surfaces the failure statuses to the operator.
"""

import numpy as np

import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from medi_interfaces.msg import PatientIdentified

from sensor_msgs.msg import Image

from .patient_validator import PatientValidator
from .person_detector import PersonDetector
from .qr_scanner import QrScanner


# Topic names under the /robot3 namespace.
IMAGE_TOPIC = '/robot3/oakd/image_raw'
DEPTH_TOPIC = '/robot3/oakd/depth_image'
RESULT_TOPIC = '/robot3/patient_identified'

# Status values published in PatientIdentified.status.
STATUS_IDENTIFIED = 'identified'
STATUS_ABSENT = 'absent'
STATUS_MISMATCH = 'mismatch'
STATUS_NO_QR = 'no_qr'
STATUS_DB_ERROR = 'db_error'


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
    """Identify the patient in the currently visited room."""

    def __init__(self):
        """Set up publishers, subscriptions, helpers and the pipeline timer."""
        super().__init__('patient_identifier_node')

        self.declare_parameter('current_room', '')
        self.declare_parameter('period_sec', 2.0)
        self.declare_parameter('model_path', 'yolo11n.pt')

        self._latest_image = None
        self._latest_depth = None

        self._detector = PersonDetector(
            model_path=self.get_parameter('model_path').value)
        self._qr_scanner = QrScanner()

        # Reentrant group lets the validator block on the service call from
        # inside the timer callback without deadlocking the executor.
        client_group = ReentrantCallbackGroup()
        timer_group = MutuallyExclusiveCallbackGroup()
        self._validator = PatientValidator(self, callback_group=client_group)

        self._result_pub = self.create_publisher(PatientIdentified, RESULT_TOPIC, 10)

        self.create_subscription(Image, IMAGE_TOPIC, self._on_image, 10)
        self.create_subscription(Image, DEPTH_TOPIC, self._on_depth, 10)

        period = self.get_parameter('period_sec').value
        self._timer = self.create_timer(period, self._run_pipeline,
                                        callback_group=timer_group)

        self.get_logger().info('patient_identifier_node started')

    def _on_image(self, msg):
        """Cache the latest RGB frame."""
        self._latest_image = msg

    def _on_depth(self, msg):
        """Cache the latest depth frame."""
        self._latest_depth = msg

    def _current_room(self):
        """Return the room the robot is currently visiting."""
        return str(self.get_parameter('current_room').value)

    def _latest_frame(self):
        """Decode the most recent RGB frame to a BGR numpy array."""
        return imgmsg_to_bgr(self._latest_image)

    def _run_pipeline(self):
        """Run detection -> QR -> DB validation and publish the outcome."""
        frame = self._latest_frame()
        if frame is None:
            return

        # 1) Person detection.
        if not self._detector.detect(frame):
            self._publish(STATUS_ABSENT, is_present=False)
            return

        # 2) QR scan with retries (fresh frame each attempt).
        qr = self._qr_scanner.scan(self._latest_frame)
        if qr is None:
            self._publish(STATUS_NO_QR, is_present=True)
            return
        patient_id, qr_room = qr

        # 3) DB validation against the visited room.
        result = self._validator.validate(patient_id, self._current_room())
        if not result.db_ok:
            self._publish(STATUS_DB_ERROR, is_present=True, patient_id=patient_id)
            return
        if not result.matched:
            self._publish(STATUS_MISMATCH, is_present=True, patient_id=patient_id,
                          patient=result.patient)
            return

        self._publish(STATUS_IDENTIFIED, is_present=True, is_identified=True,
                      patient_id=patient_id, patient=result.patient)

    def _publish(self, status, is_present=False, is_identified=False,
                 patient_id='', patient=None):
        """Publish a PatientIdentified message describing the outcome."""
        msg = PatientIdentified()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.patient_id = patient_id
        msg.patient_name = patient.name if patient is not None else ''
        msg.room = patient.room if patient is not None else self._current_room()
        msg.is_present = is_present
        msg.is_identified = is_identified
        msg.status = status
        self._result_pub.publish(msg)
        self.get_logger().info('status={} patient_id={}'.format(status, patient_id))


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
