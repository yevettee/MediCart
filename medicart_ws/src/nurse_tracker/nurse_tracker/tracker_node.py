#!/usr/bin/env python3
"""tracker_node — round(추종) 모드 노드. 허브 계약(set/cmd_vel/status) + perception + follow_control.

active 시 PersonTracker(perception) 의 target 을 FollowFSM 으로 추종 Twist 로 변환해
/{ns}/mode/round/cmd_vel 발행(허브가 safety_gate). status 하트비트 + TargetBBox 발행.
Nav2 미사용 — 벽 정지는 허브 LiDAR 게이트.
"""
import json
import os
import time

from ament_index_python.packages import get_package_share_directory
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from geometry_msgs.msg import Twist
from std_msgs.msg import String

# set 토픽 래치 — 허브 ModeProxy(LATCHED_QOS)와 일치해야 마지막 활성상태 수신.
_LATCHED_QOS = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                          durability=DurabilityPolicy.TRANSIENT_LOCAL)

from std_srvs.srv import Trigger

from .perception import PersonTracker
from .follow_control import FollowParams, FollowFSM

MODE = "round"

# 학습된 nurse/obstacle 모델(yolo11n 파인튜닝, models/yolo11n.pt) — 패키지 share 설치 경로.
_DEFAULT_MODEL_PATH = os.path.join(
    get_package_share_directory("nurse_tracker"), "models", "yolo11n.pt")


class TrackerNode(Node):
    def __init__(self):
        super().__init__("tracker_node")
        self.declare_parameter("namespace", os.environ.get("ROBOT_NAMESPACE", "robot6"))
        self.declare_parameter("base_frame", "base_link")
        self.declare_parameter("model_path", _DEFAULT_MODEL_PATH)
        self.declare_parameter("target_class", "nurse")
        self.declare_parameter("conf", 0.5)
        self.declare_parameter("desired_distance", 0.30)
        self.declare_parameter("deadband", 0.12)
        self.declare_parameter("angle_deadzone", 0.45)
        self.declare_parameter("max_lin", 0.05)
        self.declare_parameter("max_ang", 0.25)
        self.declare_parameter("lost_timeout", 5.0)
        self.declare_parameter("control_hz", 10.0)
        ns = str(self.get_parameter("namespace").value).strip("/")
        self._ns = ns
        base_frame = str(self.get_parameter("base_frame").value).strip() or "base_link"
        target_class = str(self.get_parameter("target_class").value).strip().lower()
        desired_distance = float(self.get_parameter("desired_distance").value)
        deadband = float(self.get_parameter("deadband").value)
        angle_deadzone = float(self.get_parameter("angle_deadzone").value)
        max_lin = float(self.get_parameter("max_lin").value)
        max_ang = float(self.get_parameter("max_ang").value)

        hz = float(self.get_parameter("control_hz").value)
        self._perc = PersonTracker(
            self, ns,
            model_path=str(self.get_parameter("model_path").value),
            target_classes=(target_class,),
            conf=float(self.get_parameter("conf").value),
            infer_hz=hz,
            base_frame=base_frame)  # YOLO 추론을 control_hz에 맞춰 rate-limit
        self._fsm = FollowFSM(
            FollowParams(
                desired_distance=desired_distance,
                deadband=deadband,
                angle_deadzone=angle_deadzone,
                max_lin=max_lin,
                max_ang=max_ang),
            lost_timeout=float(self.get_parameter("lost_timeout").value))
        self._round_active = False
        self._nav_active = False
        self._smooth_lin = 0.0   # EMA 스무딩 상태
        self._smooth_ang = 0.0

        self._cmd_pub = self.create_publisher(Twist, f"/{ns}/mode/{MODE}/cmd_vel", 10)
        self._status_pub = self.create_publisher(String, f"/{ns}/mode/{MODE}/status", 10)
        # 타깃 정보는 std_msgs/String(JSON) 으로 발행(medi_interfaces 제거 — 커스텀 msg 불요).
        self._target_pub = self.create_publisher(String, "/nurse_tracker/target", 10)
        self.create_subscription(
            String, f"/{ns}/mode/{MODE}/set",
            lambda msg: self._on_set(MODE, msg), _LATCHED_QOS)
        self.create_subscription(
            String, f"/{ns}/mode/round_nav/set",
            lambda msg: self._on_set("round_nav", msg), _LATCHED_QOS)
        self.create_service(Trigger, f"/{ns}/start_tracking", self._on_start_tracking)

        self.create_timer(1.0 / hz, self._tick)
        self.get_logger().info(
            f"[tracker_node] round 모드 준비 ns={ns} target={target_class} "
            f"base_frame={base_frame} "
            f"dist={desired_distance:.2f}m angle_deadzone={angle_deadzone:.2f} "
            f"@ {hz:.0f}Hz")

    def _on_set(self, mode, msg):
        try:
            d = json.loads(msg.data)
        except (ValueError, TypeError):
            return
        active = bool(d.get("active"))
        was_active = self._round_active or self._nav_active
        if mode == MODE:
            self._round_active = active
        elif mode == "round_nav":
            self._nav_active = active
        now_active = self._round_active or self._nav_active

        if now_active and not was_active:
            self._fsm.reset()
            self._smooth_lin = 0.0              # 활성화 시 스무딩 초기값 리셋
            self._smooth_ang = 0.0
        if not now_active:
            self._smooth_lin = 0.0
            self._smooth_ang = 0.0
        self._perc.set_active(now_active)
        self.get_logger().info(
            f"[tracker_node] {mode} active={active} "
            f"(perception={now_active}, cmd_vel={self._round_active})")

    def _on_start_tracking(self, request, response):
        del request
        self._fsm.reset()
        response.success = True
        response.message = "follow state reset"
        return response

    def _tick(self):
        if not (self._round_active or self._nav_active):
            return
        now = time.monotonic()
        target = self._perc.target
        if target is not None and target.detected:
            self._publish_target(target)
        if not self._round_active:
            return
        lin, ang, detail = self._fsm.step(target, now)
        # 선속도 EMA 스무딩(α=0.3): 급출발·급정지 완화. 각속도는 즉각 반응이 자연스러움.
        self._smooth_lin = 0.3 * lin + 0.7 * self._smooth_lin
        tw = Twist(); tw.linear.x = float(self._smooth_lin); tw.angular.z = float(ang)
        self._cmd_pub.publish(tw)
        s = String(); s.data = json.dumps(
            {"state": "running", "detail": detail, "ts": int(time.time() * 1000)})
        self._status_pub.publish(s)

    def _publish_target(self, target):
        tb = String()
        tb.data = json.dumps({"tracking_id": int(target.track_id),
                              "distance": round(float(target.distance), 3),
                              "x_robot":  round(float(target.x_robot), 3),
                              "y_robot":  round(float(target.y_robot), 3),
                              "ts": int(time.time() * 1000)})
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
