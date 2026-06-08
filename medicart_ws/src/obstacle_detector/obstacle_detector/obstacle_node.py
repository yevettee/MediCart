#!/usr/bin/env python3
"""obstacle_node — OAK-D depth 하단 ROI 지면 평탄도 분석(standalone).

compressedDepth(하단 중앙 300×200 ROI) → project_depth_roi → 평면적합 + 거칠기 →
평탄/울퉁불퉁 분류. PointCloud2(시각화) + ground_status(JSON) 발행. 울퉁불퉁 시 로그.
주행 연동 없음(후속). 3DGS 미사용 — 목적적합 평면적합.
"""
import json
import os
import time

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

from sensor_msgs.msg import CameraInfo, CompressedImage, PointCloud2
from sensor_msgs_py import point_cloud2
from std_msgs.msg import Header, String

from .cloud_projection import project_depth_roi
from .ground_analysis import classify, fit_plane, roughness

_QOS_SENSOR = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE)
_CDEPTH_HEADER = 12   # compressed_depth_image_transport: enum+float+float = 12B 후 PNG


class ObstacleNode(Node):
    def __init__(self):
        super().__init__("obstacle_node")
        self.declare_parameter("namespace", os.environ.get("ROBOT_NAMESPACE", "robot3"))
        ns = str(self.get_parameter("namespace").value).strip("/")
        self.declare_parameter("depth_topic", f"/{ns}/oakd/stereo/image_raw/compressedDepth")
        self.declare_parameter("caminfo_topic", f"/{ns}/oakd/stereo/camera_info")
        self.declare_parameter("roi_w", 300)
        self.declare_parameter("roi_h", 200)
        self.declare_parameter("min_depth", 0.3)
        self.declare_parameter("max_depth", 6.0)
        self.declare_parameter("flat_std_thresh", 0.02)
        self.declare_parameter("inlier_tol", 0.02)
        self.declare_parameter("min_points", 200)
        self.declare_parameter("viz_stride", 3)
        self.declare_parameter("frame_id", "oakd_rgb_camera_optical_frame")
        self.declare_parameter("warn_period", 2.0)

        self._roi_w = int(self.get_parameter("roi_w").value)
        self._roi_h = int(self.get_parameter("roi_h").value)
        self._mind = float(self.get_parameter("min_depth").value)
        self._maxd = float(self.get_parameter("max_depth").value)
        self._std_thresh = float(self.get_parameter("flat_std_thresh").value)
        self._tol = float(self.get_parameter("inlier_tol").value)
        self._min_pts = int(self.get_parameter("min_points").value)
        self._stride = max(1, int(self.get_parameter("viz_stride").value))
        self._frame = str(self.get_parameter("frame_id").value)
        self._warn_period = float(self.get_parameter("warn_period").value)
        self._K = None   # (fx, fy, cx, cy)

        self.create_subscription(CameraInfo, str(self.get_parameter("caminfo_topic").value),
                                 self._on_caminfo, _QOS_SENSOR)
        self.create_subscription(CompressedImage, str(self.get_parameter("depth_topic").value),
                                 self._on_depth, _QOS_SENSOR)
        self._cloud_pub = self.create_publisher(PointCloud2, "/obstacle_detector/ground_cloud", 5)
        self._status_pub = self.create_publisher(String, "/obstacle_detector/ground_status", 10)
        self.get_logger().info(f"[obstacle_node] ns={ns} ROI 하단중앙 {self._roi_w}x{self._roi_h} 지면 평탄도")

    def _on_caminfo(self, msg):
        if self._K is None:
            k = msg.k
            self._K = (float(k[0]), float(k[4]), float(k[2]), float(k[5]))
            self.get_logger().info(f"[obstacle_node] intrinsics fx={k[0]:.1f} fy={k[4]:.1f} cx={k[2]:.1f} cy={k[5]:.1f}")

    def _on_depth(self, msg):
        if self._K is None:
            self.get_logger().warn("camera_info 대기 중(intrinsics 없음)", throttle_duration_sec=3.0)
            return
        try:
            buf = np.frombuffer(bytes(msg.data)[_CDEPTH_HEADER:], np.uint8)
            depth = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)   # 16UC1, mm
        except Exception as exc:                              # noqa: BLE001
            self.get_logger().warn(f"depth decode 실패: {exc}", throttle_duration_sec=3.0)
            return
        if depth is None or depth.ndim != 2:
            return

        h, w = depth.shape[:2]
        rw, rh = min(self._roi_w, w), min(self._roi_h, h)
        x1 = (w - rw) // 2
        roi = (x1, h - rh, x1 + rw, h)                        # 하단 중앙
        fx, fy, cx, cy = self._K
        pts = project_depth_roi(depth, fx, fy, cx, cy, roi, self._mind, self._maxd)

        plane = fit_plane(pts)
        metrics = roughness(pts, plane, self._tol)
        flat = classify(metrics, self._std_thresh, self._min_pts)

        self._publish_status(flat, metrics)
        self._publish_cloud(pts)
        if flat is False:
            self.get_logger().warn(
                f"표면이 울퉁불퉁 합니다 값 : {metrics['std']:.3f}m",
                throttle_duration_sec=self._warn_period)

    def _publish_status(self, flat, m):
        s = String()
        s.data = json.dumps({"flat": flat, "std": round(m["std"], 4),
                             "max_dev": round(m["max_dev"], 4),
                             "inlier_ratio": round(m["inlier_ratio"], 3),
                             "n": m["n"], "ts": int(time.time() * 1000)})
        self._status_pub.publish(s)

    def _publish_cloud(self, pts):
        if pts is None or len(pts) == 0:
            return
        header = Header()
        header.stamp = self.get_clock().now().to_msg()
        header.frame_id = self._frame
        sample = pts[::self._stride].tolist()                 # 시각화용 다운샘플
        self._cloud_pub.publish(point_cloud2.create_cloud_xyz32(header, sample))


def main(args=None):
    rclpy.init(args=args)
    node = ObstacleNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
