#!/usr/bin/env python3

import threading

import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String
from cv_bridge import CvBridge

from ocr_interfaces.srv import GetOcrResult
from ocr_detector.text_cleaner import clean_text


class OcrNode(Node):
    def __init__(self):
        super().__init__('ocr_node')

        self.declare_parameter('engine', 'easyocr')
        self.declare_parameter('image_topic', '/robot6/color/image')
        self.declare_parameter('confidence_threshold', 0.2)
        self.declare_parameter('gcp_rate_hz', 1.0)
        self.declare_parameter('use_webcam', False)
        self.declare_parameter('webcam_device', 2)

        engine_name = self.get_parameter('engine').value
        image_topic = self.get_parameter('image_topic').value
        conf_threshold = self.get_parameter('confidence_threshold').value
        gcp_rate = self.get_parameter('gcp_rate_hz').value
        use_webcam = self.get_parameter('use_webcam').value
        webcam_device = self.get_parameter('webcam_device').value

        self._engine = self._load_engine(engine_name, conf_threshold, gcp_rate)
        self._bridge = CvBridge()

        self._latest_frame = None
        self._latest_result = ('', '', 0.0)  # (raw, cleaned, confidence)
        self._frame_lock = threading.Lock()
        self._result_lock = threading.Lock()

        if use_webcam:
            self._cap = cv2.VideoCapture(webcam_device)
            if not self._cap.isOpened():
                self.get_logger().error(f'Cannot open webcam device {webcam_device}')
            threading.Thread(target=self._webcam_loop, daemon=True).start()
            self.get_logger().info(
                f'ocr_node started  engine={engine_name}  source=webcam({webcam_device})'
            )
        else:
            self.create_subscription(Image, image_topic, self._image_callback, 10)
            self.get_logger().info(
                f'ocr_node started  engine={engine_name}  topic={image_topic}'
            )

        self._pub = self.create_publisher(String, 'ocr_result', 10)
        self.create_service(GetOcrResult, 'get_ocr_result', self._srv_callback)

        threading.Thread(target=self._ocr_loop, daemon=True).start()

    # ------------------------------------------------------------------
    def _load_engine(self, name, conf_threshold, gcp_rate):
        if name == 'gcp':
            from ocr_detector.engines.gcp_engine import GcpVisionEngine
            return GcpVisionEngine(rate_hz=gcp_rate)
        from ocr_detector.engines.easyocr_engine import EasyOcrEngine
        return EasyOcrEngine(conf_threshold=conf_threshold)

    def _image_callback(self, msg: Image):
        frame = self._bridge.imgmsg_to_cv2(msg, desired_encoding='rgb8')
        with self._frame_lock:
            self._latest_frame = frame

    def _webcam_loop(self):
        while True:
            ret, frame = self._cap.read()
            if not ret:
                continue
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            with self._frame_lock:
                self._latest_frame = frame_rgb

    def _ocr_loop(self):
        while True:
            with self._frame_lock:
                frame = self._latest_frame
            if frame is None:
                continue

            try:
                raw, confidence = self._engine.recognize(frame)
            except Exception as e:
                self.get_logger().error(f'OCR 오류: {e}', throttle_duration_sec=5.0)
                continue
            cleaned = clean_text(raw)

            with self._result_lock:
                self._latest_result = (raw, cleaned, confidence)

            msg = String()
            msg.data = cleaned
            self._pub.publish(msg)

    def _srv_callback(self, _request, response: GetOcrResult.Response):
        with self._result_lock:
            raw, cleaned, confidence = self._latest_result

        response.success = bool(cleaned)
        response.raw_text = raw
        response.cleaned_text = cleaned
        response.confidence = float(confidence)
        response.message = 'ok' if cleaned else 'no text recognized'
        return response


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
