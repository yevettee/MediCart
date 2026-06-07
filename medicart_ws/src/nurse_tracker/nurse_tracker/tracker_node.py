#!/usr/bin/env python3
"""tracker_node — round(추종) 모드 노드. 허브 계약(set/cmd_vel/status) + perception + follow_control.

active 시 PersonTracker(perception) 의 target 을 FollowFSM 으로 추종 Twist 로 변환해
/{ns}/mode/round/cmd_vel 발행(허브가 safety_gate). status 하트비트 + TargetBBox 발행.
Nav2 미사용 — 벽 정지는 허브 LiDAR 게이트.
"""
import json
import os
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from geometry_msgs.msg import Twist
from std_msgs.msg import String

# set 토픽 래치 — 허브 ModeProxy(LATCHED_QOS)와 일치해야 마지막 활성상태 수신.
_LATCHED_QOS = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                          durability=DurabilityPolicy.TRANSIENT_LOCAL)

from medi_interfaces.msg import TargetBBox
from medi_interfaces.srv import StartTracking

from .perception import PersonTracker
from .follow_control import FollowParams, FollowFSM

MODE = "round"


class TrackerNode(Node):
    def __init__(self):
        super().__init__("tracker_node")
        self.declare_parameter("namespace", os.environ.get("ROBOT_NAMESPACE", "robot6"))
        self.declare_parameter("model_path", "ward_model.pt")
        self.declare_parameter("conf", 0.5)
        self.declare_parameter("hfov_deg", 69.0)
        self.declare_parameter("desired_distance", 0.8)
        self.declare_parameter("lost_timeout", 5.0)
        self.declare_parameter("control_hz", 10.0)
        ns = str(self.get_parameter("namespace").value).strip("/")
        self._ns = ns

        self._perc = PersonTracker(
            self, ns,
            model_path=str(self.get_parameter("model_path").value),
            conf=float(self.get_parameter("conf").value),
            hfov_deg=float(self.get_parameter("hfov_deg").value))
        self._fsm = FollowFSM(
            FollowParams(desired_distance=float(self.get_parameter("desired_distance").value)),
            lost_timeout=float(self.get_parameter("lost_timeout").value))
        self._active = False

        self._cmd_pub = self.create_publisher(Twist, f"/{ns}/mode/{MODE}/cmd_vel", 10)
        self._status_pub = self.create_publisher(String, f"/{ns}/mode/{MODE}/status", 10)
        self._target_pub = self.create_publisher(TargetBBox, "/nurse_tracker/target", 10)
        self.create_subscription(String, f"/{ns}/mode/{MODE}/set", self._on_set, _LATCHED_QOS)
        self.create_service(StartTracking, f"/{ns}/start_tracking", self._on_start_tracking)

        hz = float(self.get_parameter("control_hz").value)
        self.create_timer(1.0 / hz, self._tick)
        self.get_logger().info(f"[tracker_node] round 모드 준비 ns={ns} @ {hz:.0f}Hz")

    def _on_set(self, msg):
        try:
            d = json.loads(msg.data)
        except (ValueError, TypeError):
            return
        active = bool(d.get("active"))
        if active and not self._active:
            self._fsm.reset()
            self._perc._locked_id = -1          # 활성화 시 재-lock(ACQUIRE)
        self._active = active
        self.get_logger().info(f"[tracker_node] active={active}")

    def _on_start_tracking(self, request, response):
        del request
        self._perc._locked_id = -1
        self._fsm.reset()
        response.success = True
        response.message = "re-lock requested"
        return response

    def _tick(self):
        if not self._active:
            return
        now = time.monotonic()
        target = self._perc.target
        lin, ang, detail = self._fsm.step(target, now)
        tw = Twist(); tw.linear.x = float(lin); tw.angular.z = float(ang)
        self._cmd_pub.publish(tw)
        s = String(); s.data = json.dumps(
            {"state": "running", "detail": detail, "ts": int(time.time() * 1000)})
        self._status_pub.publish(s)
        if target is not None and target.detected:
            tb = TargetBBox()
            tb.header.stamp = self.get_clock().now().to_msg()
            tb.tracking_id = int(target.track_id)
            tb.depth = float(target.distance)
            self._target_pub.publish(tb)


def main(args=None):
    rclpy.init(args=args)
    node = TrackerNode()
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
