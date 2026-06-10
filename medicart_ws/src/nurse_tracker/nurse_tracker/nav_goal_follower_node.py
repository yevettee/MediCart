#!/usr/bin/env python3
"""Nav2 goal follower for nurse tracking.

This node keeps the existing YOLO/depth perception pipeline and changes only the
actuation style: /nurse_tracker/target is converted into a moving Nav2
NavigateToPose goal behind the nurse. Nav2 then owns obstacle avoidance and
cmd_vel generation.
"""
import json
import math
import os
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
import rclpy.duration
import rclpy.time
import tf2_geometry_msgs  # noqa: F401  # registers geometry conversions
import tf2_ros
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PointStamped, PoseStamped
from nav2_msgs.action import NavigateToPose
from nav2_msgs.msg import SpeedLimit
from std_msgs.msg import String


_LATCHED_QOS = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                          durability=DurabilityPolicy.TRANSIENT_LOCAL)


def _quat_from_yaw(yaw):
    return math.sin(yaw / 2.0), math.cos(yaw / 2.0)


class NavGoalFollowerNode(Node):
    """Convert nurse target coordinates into throttled Nav2 goals."""

    def __init__(self):
        super().__init__("nav_goal_follower_node")
        self.declare_parameter("namespace", os.environ.get("ROBOT_NAMESPACE", "robot6"))
        self.declare_parameter("desired_distance", 0.30)
        self.declare_parameter("deadband", 0.12)
        self.declare_parameter("goal_update_period", 0.5)
        self.declare_parameter("goal_shift_min", 0.15)
        self.declare_parameter("target_timeout", 1.2)
        self.declare_parameter("map_frame", "map")
        self.declare_parameter("base_frame", "base_link")
        self.declare_parameter("tracking_speed_limit", 0.08)
        self.declare_parameter("speed_limit_topic", "")

        self.ns = str(self.get_parameter("namespace").value).strip("/")
        self.base_frame = str(self.get_parameter("base_frame").value).strip() or "base_link"
        self.map_frame = str(self.get_parameter("map_frame").value)
        self.desired_distance = float(self.get_parameter("desired_distance").value)
        self.deadband = float(self.get_parameter("deadband").value)
        self.goal_update_period = float(self.get_parameter("goal_update_period").value)
        self.goal_shift_min = float(self.get_parameter("goal_shift_min").value)
        self.target_timeout = float(self.get_parameter("target_timeout").value)
        self.tracking_speed_limit = float(self.get_parameter("tracking_speed_limit").value)
        self.speed_limit_topic = (
            str(self.get_parameter("speed_limit_topic").value).strip()
            or f"/{self.ns}/speed_limit")

        self._active = False
        self._last_target = None
        self._last_goal_xy = None
        self._last_goal_t = 0.0
        self._last_speed_limit_t = 0.0
        self._goal_handle = None
        self._busy = False
        self._last_detail = "idle"

        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)
        self._nav = ActionClient(self, NavigateToPose, f"/{self.ns}/navigate_to_pose")

        self.create_subscription(String, f"/{self.ns}/mode/round_nav/set",
                                 self._on_set, _LATCHED_QOS)
        self.create_subscription(String, "/nurse_tracker/target", self._on_target, 10)
        self._status_pub = self.create_publisher(
            String, f"/{self.ns}/mode/round_nav/status", 10)
        self._speed_limit_pub = self.create_publisher(
            SpeedLimit, self.speed_limit_topic, 10)

        self.create_timer(0.2, self._tick)
        self.get_logger().info(
            f"[nav_goal_follower] ready ns={self.ns} desired={self.desired_distance:.2f}m "
            f"base_frame={self.base_frame} map_frame={self.map_frame} "
            f"speed_limit={self.tracking_speed_limit:.2f}m/s topic={self.speed_limit_topic} "
            f"update={self.goal_update_period:.1f}s shift={self.goal_shift_min:.2f}m")

    def _on_set(self, msg):
        try:
            data = json.loads(msg.data)
        except (ValueError, TypeError):
            return
        active = bool(data.get("active"))
        if active and not self._active:
            self._last_goal_xy = None
            self._last_goal_t = 0.0
            self._last_speed_limit_t = 0.0
            self._last_detail = "waiting_target"
            self._publish_speed_limit(self.tracking_speed_limit)
        if not active and self._active:
            self._cancel_goal()
            self._publish_speed_limit(0.0)
            self._last_detail = "idle"
        self._active = active
        self.get_logger().info(f"[nav_goal_follower] active={active}")

    def _on_target(self, msg):
        try:
            data = json.loads(msg.data)
        except (ValueError, TypeError):
            return
        self._last_target = data

    def _tick(self):
        if not self._active:
            return
        now = time.monotonic()
        if now - self._last_speed_limit_t > 1.0:
            self._publish_speed_limit(self.tracking_speed_limit)
        target = self._fresh_target(now)
        if target is None:
            self._cancel_goal()
            self._publish_status("running", "lost")
            return

        x = float(target.get("x_robot", 0.0))
        y = float(target.get("y_robot", 0.0))
        dist = math.hypot(x, y)
        if dist <= self.desired_distance + self.deadband:
            self._cancel_goal()
            self._publish_status("running", "hold")
            return

        goal = self._target_to_goal(x, y)
        if goal is None:
            self._publish_status("running", f"tf_wait:{self.base_frame}->{self.map_frame}")
            return

        gx = goal.pose.position.x
        gy = goal.pose.position.y
        if not self._should_send_goal(gx, gy, now):
            self._publish_status("running", self._last_detail)
            return

        self._send_goal(goal, gx, gy, now)

    def _fresh_target(self, now):
        target = self._last_target
        if not isinstance(target, dict):
            return None
        ts_ms = target.get("ts")
        if ts_ms:
            age = time.time() - (float(ts_ms) / 1000.0)
            if age > self.target_timeout:
                return None
        return target

    def _target_to_goal(self, x, y):
        dist = math.hypot(x, y)
        if dist <= 1e-6:
            return None
        ux, uy = x / dist, y / dist
        travel = max(0.0, dist - self.desired_distance)
        goal_base = (ux * travel, uy * travel)

        nurse_map = self._transform_point(x, y)
        goal_map = self._transform_point(goal_base[0], goal_base[1])
        if nurse_map is None or goal_map is None:
            return None

        yaw = math.atan2(
            nurse_map.point.y - goal_map.point.y,
            nurse_map.point.x - goal_map.point.x)
        qz, qw = _quat_from_yaw(yaw)

        ps = PoseStamped()
        ps.header.frame_id = self.map_frame
        ps.header.stamp = self.get_clock().now().to_msg()
        ps.pose.position.x = goal_map.point.x
        ps.pose.position.y = goal_map.point.y
        ps.pose.orientation.z = qz
        ps.pose.orientation.w = qw
        return ps

    def _transform_point(self, x, y):
        pt = PointStamped()
        pt.header.frame_id = self.base_frame
        pt.header.stamp = rclpy.time.Time().to_msg()
        pt.point.x = float(x)
        pt.point.y = float(y)
        pt.point.z = 0.0
        try:
            return self._tf_buffer.transform(
                pt, self.map_frame,
                timeout=rclpy.duration.Duration(seconds=0.05))
        except Exception:
            return None

    def _should_send_goal(self, gx, gy, now):
        if (now - self._last_goal_t) < self.goal_update_period:
            return False
        if self._last_goal_xy is None:
            return True
        dx = gx - self._last_goal_xy[0]
        dy = gy - self._last_goal_xy[1]
        return math.hypot(dx, dy) >= self.goal_shift_min

    def _send_goal(self, pose, gx, gy, now):
        if not self._nav.wait_for_server(timeout_sec=0.1):
            self._publish_status("failed", "Nav2 미연결")
            return
        goal = NavigateToPose.Goal()
        goal.pose = pose
        self._busy = True
        self._last_goal_xy = (gx, gy)
        self._last_goal_t = now
        self._last_detail = f"nav_goal ({gx:.2f},{gy:.2f})"
        self._nav.send_goal_async(goal).add_done_callback(self._goal_response)
        self._publish_status("running", self._last_detail)

    def _goal_response(self, future):
        try:
            gh = future.result()
        except Exception as exc:  # noqa: BLE001
            self._busy = False
            self._publish_status("running", f"goal_error:{exc}")
            return
        if not gh.accepted:
            self._busy = False
            self._publish_status("running", "goal_rejected")
            return
        self._goal_handle = gh
        gh.get_result_async().add_done_callback(self._goal_result)

    def _goal_result(self, future):
        self._busy = False
        self._goal_handle = None
        try:
            status = future.result().status
        except Exception as exc:  # noqa: BLE001
            self._publish_status("running", f"result_error:{exc}")
            return
        if status == GoalStatus.STATUS_SUCCEEDED:
            self._last_detail = "goal_reached"
        else:
            self._last_detail = f"nav_status={status}"
        self._publish_status("running", self._last_detail)

    def _cancel_goal(self):
        gh = self._goal_handle
        self._goal_handle = None
        self._busy = False
        if gh is not None:
            try:
                gh.cancel_goal_async()
            except Exception as exc:  # noqa: BLE001
                self.get_logger().warn(f"[nav_goal_follower] cancel error: {exc}")

    def _publish_status(self, state, detail):
        msg = String()
        msg.data = json.dumps(
            {"state": state, "detail": detail, "ts": int(time.time() * 1000)},
            ensure_ascii=False)
        self._status_pub.publish(msg)

    def _publish_speed_limit(self, speed_limit):
        msg = SpeedLimit()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.percentage = False
        msg.speed_limit = float(speed_limit)
        self._speed_limit_pub.publish(msg)
        self._last_speed_limit_t = time.monotonic()

    def destroy_node(self):
        if self._active:
            self._publish_speed_limit(0.0)
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = NavGoalFollowerNode()
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
