#!/usr/bin/env python3
"""nav_executor — goto(좌표 이동) 실행기. dashboard 의 Nav2+dock-aware 로직 이식.

mission_manager 허브 내부에서 NavigateToPose(map 프레임)로 이동:
  · 현재 도킹 상태(dock_status)면 먼저 Undock 후 이동
  · params.dock_after 면 도착 후 자동 Dock
create3 중복 액션 디바운스(in-flight 시 재전송 금지, SIGSEGV 방지). 모든 콜백은
노드 executor 에서 처리(별도 스레드 없음). 결과는 on_done(status, detail) 콜백 1회.
"""
import math


def pose_stamped_fields(x, y, yaw):
    """map 프레임 목표 pose 의 위치/쿼터니언(순수) — 단위테스트용."""
    return {"frame_id": "map", "x": float(x), "y": float(y),
            "qz": math.sin(float(yaw) / 2.0), "qw": math.cos(float(yaw) / 2.0)}


from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from irobot_create_msgs.action import Dock, Undock
from irobot_create_msgs.msg import DockStatus
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient


class NavExecutor:
    """goto 좌표 이동 실행기(허브 내부). on_done(status, detail) 으로 종료 보고."""

    def __init__(self, node, ns, logger):
        self._node = node
        self._log = logger
        self._nav = ActionClient(node, NavigateToPose, f"/{ns}/navigate_to_pose")
        self._dock = ActionClient(node, Dock, f"/{ns}/dock")
        self._undock = ActionClient(node, Undock, f"/{ns}/undock")
        node.create_subscription(DockStatus, f"/{ns}/dock_status", self._on_dock_status, 10)
        self._is_docked = None       # None=불명
        self._active = False         # goto 진행중
        self._dock_after = False
        self._target = None          # (x,y,yaw)
        self._goal_handle = None     # 현재 nav/dock/undock goal handle(취소용)
        self._busy = None            # 'undock'|'nav'|'dock' in-flight(디바운스)
        self._on_done = None

    @property
    def active(self):
        return self._active

    def _on_dock_status(self, msg):
        self._is_docked = bool(msg.is_docked)

    def start(self, params, on_done):
        """goto 시작. params={x,y,yaw,dock_after?}. on_done 은 종료 시 1회."""
        self._on_done = on_done
        self._active = True
        self._dock_after = bool(params.get("dock_after"))
        self._target = (float(params["x"]), float(params["y"]), float(params.get("yaw", 0.0)))
        # dock 타깃이 아니고 현재 도킹(또는 불명)이면 먼저 undock
        if not self._dock_after and self._is_docked is not False:
            self._send_undock()
        else:
            self._send_nav()

    def cancel(self):
        """진행중 goal 취소(선점/정지). on_done 미호출(상위가 처리)."""
        gh = self._goal_handle
        self._active = False
        self._busy = None
        self._goal_handle = None
        self._on_done = None
        if gh is not None:
            try:
                gh.cancel_goal_async()
            except Exception as exc:                   # noqa: BLE001
                self._log.warn(f"[nav] cancel 오류: {exc}")

    # ── undock → nav → dock 비동기 체인 ──────────────────────────────────
    def _send_undock(self):
        if self._busy == "undock":
            return
        if not self._undock.wait_for_server(timeout_sec=2.0):
            self._finish("failed", "undock 액션서버 미연결")
            return
        self._busy = "undock"
        self._undock.send_goal_async(Undock.Goal()).add_done_callback(self._undock_accepted)

    def _undock_accepted(self, future):
        gh = future.result()
        if not gh.accepted:
            self._finish("failed", "undock 거부")
            return
        self._goal_handle = gh
        gh.get_result_async().add_done_callback(self._undock_done)

    def _undock_done(self, future):
        self._busy = None
        self._goal_handle = None
        if not self._active:
            return
        self._is_docked = False
        self._send_nav()

    def _send_nav(self):
        if self._busy == "nav":
            return
        if not self._nav.wait_for_server(timeout_sec=3.0):
            self._finish("failed", "Nav2 미연결")
            return
        x, y, yaw = self._target
        f = pose_stamped_fields(x, y, yaw)
        ps = PoseStamped()
        ps.header.frame_id = f["frame_id"]
        ps.header.stamp = self._node.get_clock().now().to_msg()
        ps.pose.position.x = f["x"]
        ps.pose.position.y = f["y"]
        ps.pose.orientation.z = f["qz"]
        ps.pose.orientation.w = f["qw"]
        goal = NavigateToPose.Goal()
        goal.pose = ps
        self._busy = "nav"
        self._log.info(f"[nav] goto → ({x:.2f},{y:.2f},yaw {yaw:.3f}) dock_after={self._dock_after}")
        self._nav.send_goal_async(goal).add_done_callback(self._nav_accepted)

    def _nav_accepted(self, future):
        gh = future.result()
        if not gh.accepted:
            self._finish("failed", "Nav2 goal 거부")
            return
        self._goal_handle = gh
        gh.get_result_async().add_done_callback(self._nav_done)

    def _nav_done(self, future):
        self._busy = None
        self._goal_handle = None
        if not self._active:
            return
        status = future.result().status
        if status != GoalStatus.STATUS_SUCCEEDED:
            self._finish("failed", f"Nav2 종료 status={status}")
            return
        if self._dock_after:
            self._send_dock()
        else:
            self._finish("done", "도착")

    def _send_dock(self):
        if self._busy == "dock":
            return
        if not self._dock.wait_for_server(timeout_sec=2.0):
            self._finish("failed", "dock 액션서버 미연결")
            return
        self._busy = "dock"
        self._dock.send_goal_async(Dock.Goal()).add_done_callback(self._dock_accepted)

    def _dock_accepted(self, future):
        gh = future.result()
        if not gh.accepted:
            self._finish("failed", "dock 거부")
            return
        self._goal_handle = gh
        gh.get_result_async().add_done_callback(self._dock_done)

    def _dock_done(self, future):
        self._busy = None
        self._goal_handle = None
        if not self._active:
            return
        self._is_docked = True
        self._finish("done", "도착 후 도킹 완료")

    def _finish(self, status, detail):
        self._active = False
        self._busy = None
        self._goal_handle = None
        cb, self._on_done = self._on_done, None
        self._log.info(f"[nav] goto 종료 status={status} detail={detail}")
        if cb is not None:
            cb(status, detail)
