#!/usr/bin/env python3
"""patrol_mode_node — 시나리오 A '회진' 순찰 mode 노드 (NAV actuation).

mission_manager 의 ModeArbiter 가 기대하는 외부 mode 노드 계약을 구현한다:
  · 구독 /{ns}/mode/patrol/set   (래치 QoS) ← {"active":bool,"params":{}}
  · 발행 /{ns}/mode/patrol/status        → {"state":"running|done|failed","detail":..,"ts":..}
NAV 모드라 cmd_vel 은 발행하지 않고 Nav2 NavigateToPose 액션으로 직접 주행한다.
status 는 3초 워치독 안에 들도록 매 tick(1Hz) 발행한다.

순찰 흐름:
  active=True → ListRooms('bed')로 병상 waypoint 획득 → 각 방으로 Nav2 이동 →
  도착 시 identifier 의 current_room 파라미터를 해당 방으로 설정하고 dwell 동안
  PatientIdentified 를 포착 → 다음 방 → 병상 모두 끝나면 return_home 시 도킹
  스테이션으로 복귀(식별 없이 주행만) → status 'done'. (dock 자체는 시퀀서가 수행.)
  active=False → 진행 중 goal 취소 후 idle.

파라미터:
  namespace      env ROBOT_NAMESPACE (기본 robot6). robot.env 로 robot3 등 통일.
  dwell_sec      각 방 도착 후 식별 대기 시간(기본 4.0)
  identifier_node  current_room 을 설정할 노드 이름(기본 patient_identifier_node)
  return_home    순찰 후 도킹 스테이션 복귀 leg 추가 여부(기본 True)
  home_x/y/yaw   복귀(도킹 스테이션) pose — dashboard 'Docking Station' 좌표 기준
"""
import json
import math
import os

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from std_msgs.msg import String
from rcl_interfaces.srv import SetParameters
from rcl_interfaces.msg import Parameter, ParameterValue, ParameterType

from medi_interfaces.srv import ListRooms
from medi_interfaces.msg import PatientIdentified

_LATCHED_QOS = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                          durability=DurabilityPolicy.TRANSIENT_LOCAL)

# 내부 순찰 상태
IDLE, FETCH, NAV, DWELL, DONE, FAILED = 'idle', 'fetch', 'nav', 'dwell', 'done', 'failed'

# 회진 병상 waypoint — 맵 프레임 실좌표. 출처: dashboard/dashboard_node.py DEFAULT_TARGETS
# (RTDB /rooms 좌표가 부정확해 dashboard 의 검증된 좌표를 기준으로 둔다. RTDB 가 맵
#  프레임으로 보정되면 use_config_waypoints:=false 로 ListRooms 경로로 전환 가능.)
# room_id 는 RTDB /rooms 키(101-A 등)에 맞춰 식별 검증(current_room↔DB room)이 닫히게 한다.
BED_WAYPOINTS = [
    {'room_id': '101-A', 'x': -12.0, 'y': -5.0, 'yaw': -0.00143, 'patient_id': ''},  # 101호 1번
    {'room_id': '101-B', 'x': -12.0, 'y': -6.0, 'yaw': -0.00143, 'patient_id': ''},  # 101호 2번
    {'room_id': '102-A', 'x': -13.0, 'y': -8.0, 'yaw': -0.00143, 'patient_id': ''},  # 102호 호출
]


def _yaw_to_quat(yaw):
    return (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))


class PatrolMode(Node):
    """회진 순찰 mode 노드."""

    def __init__(self):
        super().__init__('patrol_mode_node')
        self.declare_parameter('namespace', os.environ.get('ROBOT_NAMESPACE', 'robot6'))
        self.declare_parameter('mode_name', 'patrol')
        self.declare_parameter('dwell_sec', 4.0)
        self.declare_parameter('identifier_node', 'patient_identifier_node')
        # True: dashboard 기준 config waypoint(BED_WAYPOINTS) 사용 / False: RTDB ListRooms
        self.declare_parameter('use_config_waypoints', True)
        # 순찰 종료 후 도킹 스테이션 복귀 leg(식별 없이 주행만) — dock 은 시퀀서가 수행.
        # 좌표 출처: dashboard DEFAULT_TARGETS 'Docking Station'(dock_after).
        self.declare_parameter('return_home', True)
        self.declare_parameter('home_x', -8.0)
        self.declare_parameter('home_y', -6.0)
        self.declare_parameter('home_yaw', -0.00142)

        self.ns = str(self.get_parameter('namespace').value).strip('/')
        self.name = str(self.get_parameter('mode_name').value)
        self.dwell = float(self.get_parameter('dwell_sec').value)
        self.id_node = str(self.get_parameter('identifier_node').value)
        self.use_config = bool(self.get_parameter('use_config_waypoints').value)
        self.return_home = bool(self.get_parameter('return_home').value)
        self.home_wp = {'room_id': 'station', 'identify': False, 'patient_id': '',
                        'x': float(self.get_parameter('home_x').value),
                        'y': float(self.get_parameter('home_y').value),
                        'yaw': float(self.get_parameter('home_yaw').value)}

        # 모드 계약 I/O
        self._status_pub = self.create_publisher(String, f'/{self.ns}/mode/{self.name}/status', 10)
        self.create_subscription(String, f'/{self.ns}/mode/{self.name}/set',
                                 self._on_set, _LATCHED_QOS)
        # Nav2 / DB / 식별
        self._nav = ActionClient(self, NavigateToPose, f'/{self.ns}/navigate_to_pose')
        self._rooms_cli = self.create_client(ListRooms, f'/{self.ns}/db/list_rooms')
        self._setparam_cli = self.create_client(
            SetParameters, f'/{self.ns}/{self.id_node}/set_parameters')
        self.create_subscription(PatientIdentified, f'/{self.ns}/patient_identified',
                                 self._on_identified, 10)

        # 상태
        self.active = False
        self.state = IDLE
        self._wps = []          # [{'room_id','x','y','yaw','patient_id'}]
        self._idx = 0
        self._goal_handle = None
        self._dwell_left = 0.0
        self._last_ident = None
        self._detail = 'idle'

        self.create_timer(1.0, self._tick)     # status 하트비트 + dwell 진행(1Hz)
        self.get_logger().info(f'[patrol] ready ns=/{self.ns} mode={self.name}')

    # ── 모드 set ──────────────────────────────────────────────────────────
    def _on_set(self, msg):
        try:
            data = json.loads(msg.data)
        except (ValueError, TypeError):
            return
        active = bool(data.get('active'))
        was_active = self.active
        # active 를 먼저 반영해야 _start()→_go_next() 의 'if not self.active: return'
        # 가드를 통과한다(아니면 첫 주행 시도가 즉시 bail → FETCH 에 멈춤).
        self.active = active
        if active and not was_active:
            self._start()
        elif not active and was_active:
            self._cancel('deactivated')

    def _start(self):
        self.state = FETCH
        self._detail = 'fetching waypoints'
        self._wps, self._idx, self._last_ident = [], 0, None
        if self.use_config:
            # dashboard 기준 실좌표(BED_WAYPOINTS) 사용 — RTDB 조회 건너뜀.
            self._wps = [dict(w) for w in BED_WAYPOINTS]
            self.get_logger().info(
                f'[patrol] 활성화 → config waypoint {len(self._wps)}개(dashboard 좌표): '
                f'{[w["room_id"] for w in self._wps]}')
            self._append_home()
            self._idx = 0
            self._go_next()
            return
        # RTDB 경로(ListRooms) — RTDB /rooms 좌표가 보정된 경우.
        self.get_logger().info('[patrol] 활성화 → ListRooms(RTDB) 병상 waypoint 조회')
        if not self._rooms_cli.wait_for_service(timeout_sec=2.0):
            return self._fail('list_rooms 서비스 없음(rooms_server 미기동?)')
        req = ListRooms.Request()
        req.filter = 'bed'
        self._rooms_cli.call_async(req).add_done_callback(self._on_rooms)

    def _on_rooms(self, future):
        try:
            resp = future.result()
        except Exception as exc:                       # noqa: BLE001
            return self._fail(f'list_rooms 오류: {exc}')
        if not resp or not resp.success or not resp.room_ids:
            return self._fail('병상 waypoint 없음')
        self._wps = [{'room_id': resp.room_ids[i], 'x': resp.xs[i], 'y': resp.ys[i],
                      'yaw': resp.yaws[i], 'patient_id': resp.patient_ids[i]}
                     for i in range(len(resp.room_ids))]
        self.get_logger().info(f'[patrol] waypoint {len(self._wps)}개: '
                               f'{[w["room_id"] for w in self._wps]}')
        self._append_home()
        self._idx = 0
        self._go_next()

    def _append_home(self):
        """순찰 종료 후 도킹 스테이션 복귀 waypoint(식별 없음)를 마지막에 추가."""
        if not self.return_home:
            return
        self._wps.append(dict(self.home_wp))
        self.get_logger().info(
            f'[patrol] 복귀 waypoint 추가 → station '
            f'({self.home_wp["x"]:.2f},{self.home_wp["y"]:.2f})')

    # ── waypoint 순회 ────────────────────────────────────────────────────
    def _go_next(self):
        if not self.active:
            return
        if self._idx >= len(self._wps):
            self.state = DONE
            beds = sum(1 for w in self._wps if w.get('identify', True))
            tail = ', returned to station' if self.return_home else ''
            self._detail = f'patrol complete ({beds} rooms{tail})'
            self.get_logger().info(f'[patrol] 모든 병상 순회 완료{tail} → done')
            return
        wp = self._wps[self._idx]
        if not self._nav.wait_for_server(timeout_sec=2.0):
            return self._fail('Nav2 navigate_to_pose 액션 서버 없음')
        goal = NavigateToPose.Goal()
        goal.pose = self._pose(wp)
        self.state = NAV
        self._detail = f'navigating to {wp["room_id"]} ({self._idx + 1}/{len(self._wps)})'
        self.get_logger().info(f'[patrol] → {wp["room_id"]} ({wp["x"]:.2f},{wp["y"]:.2f})')
        self._nav.send_goal_async(goal).add_done_callback(self._on_goal_resp)

    def _pose(self, wp):
        p = PoseStamped()
        p.header.frame_id = 'map'
        p.header.stamp = self.get_clock().now().to_msg()
        p.pose.position.x = float(wp['x'])
        p.pose.position.y = float(wp['y'])
        qx, qy, qz, qw = _yaw_to_quat(float(wp['yaw']))
        p.pose.orientation.x, p.pose.orientation.y = qx, qy
        p.pose.orientation.z, p.pose.orientation.w = qz, qw
        return p

    def _on_goal_resp(self, future):
        handle = future.result()
        if not handle.accepted:
            return self._fail(f'Nav2 goal 거부: {self._wps[self._idx]["room_id"]}')
        self._goal_handle = handle
        handle.get_result_async().add_done_callback(self._on_nav_result)

    def _on_nav_result(self, future):
        if not self.active:
            return
        wp = self._wps[self._idx]
        if not wp.get('identify', True):
            # 복귀(스테이션) 도착 — 식별 dwell 없이 다음(→ DONE), dock 은 시퀀서가 수행.
            self.get_logger().info(f'[patrol] {wp["room_id"]} 도착(복귀) → dwell 생략')
            self._idx += 1
            self._go_next()
            return
        self.get_logger().info(f'[patrol] {wp["room_id"]} 도착 → 식별 대기 {self.dwell:.0f}s')
        self._set_current_room(wp['room_id'])     # identifier 에 현재 방 통지(best-effort)
        self._last_ident = None
        self._dwell_left = self.dwell
        self.state = DWELL
        self._detail = f'identifying at {wp["room_id"]}'

    # ── 식별 연동 ────────────────────────────────────────────────────────
    def _set_current_room(self, room_id):
        if not self._setparam_cli.service_is_ready():
            self.get_logger().warn(
                f'[patrol] {self.id_node}/set_parameters 미가용 — current_room 생략')
            return
        req = SetParameters.Request()
        pval = ParameterValue(type=ParameterType.PARAMETER_STRING, string_value=room_id)
        req.parameters = [Parameter(name='current_room', value=pval)]
        self._setparam_cli.call_async(req)

    def _on_identified(self, msg):
        self._last_ident = msg
        if self.state == DWELL:
            self.get_logger().info(
                f'[patrol] PatientIdentified room={msg.room} patient={msg.patient_id} '
                f'status={msg.status}')

    # ── tick: status 하트비트 + dwell 진행 ───────────────────────────────
    def _tick(self):
        if self.state == DWELL:
            self._dwell_left -= 1.0
            if self._dwell_left <= 0.0:
                self._idx += 1
                self._go_next()
        self._publish_status()

    def _publish_status(self):
        if self.state in (IDLE,) and not self.active:
            return
        state = {NAV: 'running', FETCH: 'running', DWELL: 'running',
                 DONE: 'done', FAILED: 'failed'}.get(self.state, 'running')
        msg = String()
        msg.data = json.dumps({'state': state, 'detail': self._detail,
                               'ts': self.get_clock().now().nanoseconds // 1_000_000},
                              ensure_ascii=False)
        self._status_pub.publish(msg)

    def _cancel(self, reason):
        if self._goal_handle is not None:
            self._goal_handle.cancel_goal_async()
            self._goal_handle = None
        self.state = IDLE
        self._detail = reason
        self.get_logger().info(f'[patrol] 취소: {reason}')

    def _fail(self, reason):
        self.state = FAILED
        self._detail = reason
        self.get_logger().error(f'[patrol] 실패: {reason}')
        self._publish_status()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = PatrolMode()
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
