#!/usr/bin/env python3
"""stub_mode_node — 모드 계약 검증용 더미 REACTIVE 모드.

active 수신 시 작은 전진 twist + status running 발행, 비활성 시 무발행.
파라미터: namespace, mode_name, lin. (테스트 전용 — 실제 모드 노드 대체물)
"""
import json
import os

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from geometry_msgs.msg import Twist
from std_msgs.msg import String

_LATCHED_QOS = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                          durability=DurabilityPolicy.TRANSIENT_LOCAL)


class StubMode(Node):
    def __init__(self):
        super().__init__("stub_mode_node")
        self.declare_parameter("namespace", os.environ.get("ROBOT_NAMESPACE", "robot6"))
        self.declare_parameter("mode_name", "round")
        self.declare_parameter("lin", 0.05)
        ns = str(self.get_parameter("namespace").value).strip("/")
        self.name = str(self.get_parameter("mode_name").value)
        self.lin = float(self.get_parameter("lin").value)
        self.active = False
        self._cmd = self.create_publisher(Twist, f"/{ns}/mode/{self.name}/cmd_vel", 10)
        self._st = self.create_publisher(String, f"/{ns}/mode/{self.name}/status", 10)
        self.create_subscription(String, f"/{ns}/mode/{self.name}/set", self._on_set, _LATCHED_QOS)
        self.create_timer(0.1, self._tick)
        self.get_logger().info(f"[stub_mode:{self.name}] ready (ns={ns})")

    def _on_set(self, msg):
        try:
            d = json.loads(msg.data)
        except (ValueError, TypeError):
            return
        self.active = bool(d.get("active"))
        self.get_logger().info(f"[stub_mode:{self.name}] active={self.active} params={d.get('params')}")

    def _tick(self):
        if not self.active:
            return
        t = Twist(); t.linear.x = self.lin; self._cmd.publish(t)
        s = String(); s.data = json.dumps({"state": "running", "detail": self.name, "ts": 0})
        self._st.publish(s)


def main(args=None):
    rclpy.init(args=args)
    node = StubMode()
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
