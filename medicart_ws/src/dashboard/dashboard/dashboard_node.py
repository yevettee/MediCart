#!/usr/bin/env python3
# Copyright 2026 MediCart Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Web dashboard node for sending Nav2 goals from a map UI."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import json
import math
import mimetypes
from pathlib import Path
from queue import Empty, Queue
import subprocess
import threading
import time
from typing import Any
from urllib.parse import unquote, urlparse

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from irobot_create_msgs.action import Dock, Undock
from irobot_create_msgs.msg import DockStatus
from message_filters import ApproximateTimeSynchronizer, Subscriber
from nav2_msgs.action import NavigateToPose
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage


DEFAULT_TARGETS = (
    {
        'name': '101호 1번',
        'x': -12.0,
        'y': -5.0,
        'yaw': -0.00143,
        'color': '#0f8b7b',
    },
    {
        'name': '101호 2번',
        'x': -12.0,
        'y': -6.0,
        'yaw': -0.00143,
        'color': '#3f6fb5',
    },
    {
        'name': '102호 호출',
        'x': -13.0,
        'y': -8.0,
        'yaw': -0.00143,
        'color': '#d35f35',
    },
    {
        'name': '약품실',
        'x': -9.0,
        'y': -9.0,
        'yaw': -0.00143,
        'color': '#c18b1c',
    },
    {
        'name': 'Docking Station',
        'x': -8.0,
        'y': -6.0,
        'yaw': -0.00142,
        'color': '#6f4bb5',
        'dock_after': True,
    },
)


STATUS_TEXT = {
    GoalStatus.STATUS_UNKNOWN: 'UNKNOWN',
    GoalStatus.STATUS_ACCEPTED: 'ACCEPTED',
    GoalStatus.STATUS_EXECUTING: 'EXECUTING',
    GoalStatus.STATUS_CANCELING: 'CANCELING',
    GoalStatus.STATUS_SUCCEEDED: 'SUCCEEDED',
    GoalStatus.STATUS_CANCELED: 'CANCELED',
    GoalStatus.STATUS_ABORTED: 'ABORTED',
}


@dataclass(frozen=True)
class NavigationTarget:
    """Goal target in the ROS map frame."""

    x: float
    y: float
    yaw: float
    name: str = '선택 지점'
    dock_after: bool = False


class EventBroker:
    """Keeps recent logs and fans out live dashboard events."""

    def __init__(self, history_size: int = 80):
        self._history: deque[dict[str, Any]] = deque(maxlen=history_size)
        self._listeners: set[Queue] = set()
        self._lock = threading.Lock()
        self._next_id = 1

    def publish(
        self,
        payload: dict[str, Any],
        event_type: str = 'log',
        store: bool = False,
    ) -> dict[str, Any]:
        event = {
            'id': self._next_id,
            'event_type': event_type,
            'time': datetime.now(timezone.utc).isoformat(),
            **payload,
        }

        with self._lock:
            self._next_id += 1
            if store:
                self._history.append(event)
            listeners = tuple(self._listeners)

        for listener in listeners:
            listener.put(event)

        return event

    def add_listener(self, replay_history: bool = True) -> Queue:
        listener: Queue = Queue()
        with self._lock:
            if replay_history:
                for event in self._history:
                    listener.put(event)
            self._listeners.add(listener)
        return listener

    def remove_listener(self, listener: Queue) -> None:
        with self._lock:
            self._listeners.discard(listener)


class DashboardHttpServer(ThreadingHTTPServer):
    """HTTP server carrying a reference to the ROS dashboard node."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, handler_class, dashboard_node):
        super().__init__(server_address, handler_class)
        self.dashboard_node = dashboard_node


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """Serves the map UI and JSON/SSE endpoints."""

    server_version = 'MediCartDashboard/0.1'

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == '/api/config':
            self._write_json(HTTPStatus.OK, self.node.get_client_config())
            return
        if path == '/api/status':
            self._write_json(HTTPStatus.OK, self.node.get_status())
            return
        if path == '/api/events':
            self._handle_events()
            return
        if path == '/':
            self._serve_static_file('index.html')
            return
        if path.startswith('/maps/'):
            self._serve_file(self.node.maps_root, path.removeprefix('/maps/'))
            return

        self._serve_static_file(path.lstrip('/'))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == '/api/goals':
            payload = self._read_json_body()
            if payload is None:
                return
            ok, message = self.node.send_navigation_goal(payload)
            status = HTTPStatus.ACCEPTED if ok else HTTPStatus.BAD_REQUEST
            self._write_json(status, {'ok': ok, 'message': message})
            return

        if path == '/api/cancel':
            ok, message = self.node.cancel_current_goal()
            status = HTTPStatus.ACCEPTED if ok else HTTPStatus.BAD_REQUEST
            self._write_json(status, {'ok': ok, 'message': message})
            return

        if path == '/api/commands':
            payload = self._read_json_body()
            if payload is None:
                return
            ok, message = self.node.run_operator_command(payload)
            status = HTTPStatus.ACCEPTED if ok else HTTPStatus.BAD_REQUEST
            self._write_json(status, {'ok': ok, 'message': message})
            return

        if path == '/api/captures':
            payload = self._read_json_body(max_length=12_000_000)
            if payload is None:
                return
            ok, message = self.node.save_capture(payload)
            status = HTTPStatus.CREATED if ok else HTTPStatus.BAD_REQUEST
            self._write_json(status, {'ok': ok, 'message': message})
            return

        self._write_json(
            HTTPStatus.NOT_FOUND,
            {'ok': False, 'message': 'Unknown endpoint'},
        )

    @property
    def node(self) -> 'DashboardNode':
        return self.server.dashboard_node

    def log_message(self, fmt: str, *args) -> None:
        self.node.get_logger().debug(fmt % args)

    def _read_json_body(self, max_length: int = 8192) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            self._write_json(
                HTTPStatus.LENGTH_REQUIRED,
                {'ok': False, 'message': 'Invalid Content-Length'},
            )
            return None

        if length <= 0 or length > max_length:
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {'ok': False, 'message': 'Invalid request body'},
            )
            return None

        try:
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {'ok': False, 'message': 'Invalid JSON body'},
            )
            return None

        if not isinstance(payload, dict):
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {'ok': False, 'message': 'JSON body must be an object'},
            )
            return None

        return payload

    def _handle_events(self) -> None:
        listener = self.node.log_broker.add_listener()
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()

        try:
            while True:
                try:
                    event = listener.get(timeout=15.0)
                    payload = self._format_sse_event(event)
                except Empty:
                    payload = ': keepalive\n\n'
                self.wfile.write(payload.encode('utf-8'))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        finally:
            self.node.log_broker.remove_listener(listener)

    def _format_sse_event(self, event: dict[str, Any]) -> str:
        data = json.dumps(event, ensure_ascii=False)
        event_type = event.get('event_type', 'message')
        return f'id: {event["id"]}\nevent: {event_type}\ndata: {data}\n\n'

    def _serve_static_file(self, relative_path: str) -> None:
        self._serve_file(self.node.static_root, relative_path)

    def _serve_file(self, root: Path, relative_path: str) -> None:
        safe_path = relative_path or 'index.html'
        candidate = (root / safe_path).resolve()

        if not self._is_relative_to(candidate, root.resolve()):
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(candidate.name)[0]
        if candidate.suffix == '.js':
            content_type = 'application/javascript'
        content_type = content_type or 'application/octet-stream'

        data = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def _is_relative_to(candidate: Path, root: Path) -> bool:
        try:
            candidate.relative_to(root)
        except ValueError:
            return False
        return True


class DashboardNode(Node):
    """Publishes operator navigation goals and hosts the dashboard UI."""

    def __init__(self):
        super().__init__('dashboard_node')

        self.declare_parameter('host', '0.0.0.0')
        self.declare_parameter('port', 8080)
        self.declare_parameter('action_name', '/navigate_to_pose')
        self.declare_parameter('dock_action_name', '')
        self.declare_parameter('undock_action_name', '')
        self.declare_parameter('dock_status_topic', '')
        self.declare_parameter('pose_topic', '')
        self.declare_parameter('rgb_topic', '')
        self.declare_parameter('depth_topic', '')
        self.declare_parameter('camera_fps', 10.0)
        self.declare_parameter('capture_dir', '')
        self.declare_parameter('remote_host', 'ubuntu@192.168.109.106')
        self.declare_parameter('remote_sudo_password', 'turtlebot4')
        self.declare_parameter('map_frame', 'map')
        self.declare_parameter('default_yaw', 0.0)
        self.declare_parameter('auto_undock', True)

        self.web_root = Path(__file__).resolve().parent / 'web'
        self.static_root = self.web_root / 'static'
        self.maps_root = self.web_root / 'maps'
        self.capture_root = self._resolve_capture_root()

        self.log_broker = EventBroker()
        self._state_lock = threading.Lock()
        self._goal_handle = None
        self._dock_goal_handle = None
        self._undock_goal_handle = None
        self._goal_state = 'idle'
        self._last_goal: NavigationTarget | None = None
        self._last_feedback_log_time = 0.0
        self._last_dock_feedback_log_time = 0.0
        self._last_camera_time = 0.0
        self._last_rgb_time = 0.0
        self._last_depth_time = 0.0
        self._last_pose: dict[str, float] | None = None
        self._is_docked: bool | None = None

        action_name = self.get_parameter('action_name').value
        robot_namespace = self._namespace_from_action_name(action_name)
        default_rgb = self._join_namespace(
            robot_namespace,
            'oakd/rgb/image_raw/compressed',
        )
        default_depth = self._join_namespace(
            robot_namespace,
            'oakd/stereo/image_raw/compressedDepth',
        )
        self._dock_action_name = (
            self.get_parameter('dock_action_name').value
            or self._join_namespace(robot_namespace, 'dock')
        )
        self._undock_action_name = (
            self.get_parameter('undock_action_name').value
            or self._join_namespace(robot_namespace, 'undock')
        )
        self._dock_status_topic = (
            self.get_parameter('dock_status_topic').value
            or self._join_namespace(robot_namespace, 'dock_status')
        )
        self._pose_topic = (
            self.get_parameter('pose_topic').value
            or self._join_namespace(robot_namespace, 'amcl_pose')
        )
        self._rgb_topic = self.get_parameter('rgb_topic').value or default_rgb
        self._depth_topic = (
            self.get_parameter('depth_topic').value
            or default_depth
        )

        self._action_client = ActionClient(self, NavigateToPose, action_name)
        self._dock_action_client = ActionClient(
            self,
            Dock,
            self._dock_action_name,
        )
        self._undock_action_client = ActionClient(
            self,
            Undock,
            self._undock_action_name,
        )
        self._dock_status_sub = self.create_subscription(
            DockStatus,
            self._dock_status_topic,
            self._handle_dock_status,
            10,
        )
        self._pose_sub = self.create_subscription(
            PoseWithCovarianceStamped,
            self._pose_topic,
            self._handle_pose,
            10,
        )
        self._rgb_direct_sub = self.create_subscription(
            CompressedImage,
            self._rgb_topic,
            self._handle_rgb_frame,
            qos_profile_sensor_data,
        )
        self._depth_direct_sub = self.create_subscription(
            CompressedImage,
            self._depth_topic,
            self._handle_depth_frame,
            qos_profile_sensor_data,
        )
        self._rgb_sub = Subscriber(
            self,
            CompressedImage,
            self._rgb_topic,
            qos_profile=qos_profile_sensor_data,
        )
        self._depth_sub = Subscriber(
            self,
            CompressedImage,
            self._depth_topic,
            qos_profile=qos_profile_sensor_data,
        )
        self._rgbd_sync = ApproximateTimeSynchronizer(
            [self._rgb_sub, self._depth_sub],
            queue_size=10,
            slop=0.08,
        )
        self._rgbd_sync.registerCallback(self._handle_rgbd)

        self._map_config = self._load_map_config()
        self._http_server: DashboardHttpServer | None = None
        self._http_thread: threading.Thread | None = None
        self._start_http_server()

        self._publish_log('dashboard_node started')
        self._publish_log(f'RGB topic: {self._rgb_topic}')
        self._publish_log(f'Depth topic: {self._depth_topic}')

    def get_client_config(self) -> dict[str, Any]:
        return {
            'map': self._map_config,
            'targets': list(DEFAULT_TARGETS),
            'status': self.get_status(),
        }

    def get_status(self) -> dict[str, Any]:
        with self._state_lock:
            goal = self._last_goal
            goal_state = self._goal_state
            is_docked = self._is_docked
            pose = self._last_pose

        return {
            'goal_state': goal_state,
            'active_goal': self._target_to_dict(goal) if goal else None,
            'action_name': self.get_parameter('action_name').value,
            'dock_action_name': self._dock_action_name,
            'undock_action_name': self._undock_action_name,
            'dock_status_topic': self._dock_status_topic,
            'pose_topic': self._pose_topic,
            'rgb_topic': self._rgb_topic,
            'depth_topic': self._depth_topic,
            'capture_dir': str(self.capture_root),
            'map_frame': self.get_parameter('map_frame').value,
            'is_docked': is_docked,
            'amr_pose': pose,
        }

    @staticmethod
    def _namespace_from_action_name(action_name: str) -> str:
        normalized = '/' + action_name.strip('/')
        parts = normalized.strip('/').split('/')
        if len(parts) <= 1:
            return ''
        return '/' + '/'.join(parts[:-1])

    @staticmethod
    def _join_namespace(namespace: str, name: str) -> str:
        if namespace:
            return f'{namespace.rstrip("/")}/{name}'
        return f'/{name}'

    def _resolve_capture_root(self) -> Path:
        configured = str(self.get_parameter('capture_dir').value or '').strip()
        if configured:
            return Path(configured).expanduser().resolve()
        return (Path(__file__).resolve().parent / 'captures').resolve()

    def _handle_dock_status(self, message: DockStatus) -> None:
        with self._state_lock:
            previous = self._is_docked
            self._is_docked = message.is_docked

        if previous is None:
            state = '도킹 상태' if message.is_docked else '언도킹 상태'
            self._publish_log(f'로봇 dock 상태 확인: {state}')
        elif previous != message.is_docked:
            state = '도킹됨' if message.is_docked else '언도킹됨'
            self._publish_log(f'로봇 dock 상태 변경: {state}')

    def _handle_pose(self, message: PoseWithCovarianceStamped) -> None:
        pose = message.pose.pose
        yaw = self._yaw_from_quaternion(pose.orientation)
        data = {
            'x': pose.position.x,
            'y': pose.position.y,
            'yaw': yaw,
        }
        with self._state_lock:
            self._last_pose = data
        self.log_broker.publish(data, event_type='pose')

    def _handle_rgbd(
        self,
        rgb_msg: CompressedImage,
        depth_msg: CompressedImage,
    ) -> None:
        fps = max(float(self.get_parameter('camera_fps').value), 1.0)
        now = time.monotonic()
        if now - self._last_camera_time < 1.0 / fps:
            return
        self._last_camera_time = now

        self.log_broker.publish(
            {
                'rgb': self._compressed_image_data_url(rgb_msg),
                'depth': self._compressed_image_data_url(depth_msg),
                'rgb_format': rgb_msg.format,
                'depth_format': depth_msg.format,
            },
            event_type='rgbd',
        )

    def _handle_rgb_frame(self, message: CompressedImage) -> None:
        fps = max(float(self.get_parameter('camera_fps').value), 1.0)
        now = time.monotonic()
        if now - self._last_rgb_time < 1.0 / fps:
            return
        self._last_rgb_time = now
        self.log_broker.publish(
            {'rgb': self._compressed_image_data_url(message)},
            event_type='rgb',
        )

    def _handle_depth_frame(self, message: CompressedImage) -> None:
        fps = max(float(self.get_parameter('camera_fps').value), 1.0)
        now = time.monotonic()
        if now - self._last_depth_time < 1.0 / fps:
            return
        self._last_depth_time = now
        self.log_broker.publish(
            {'depth': self._compressed_image_data_url(message)},
            event_type='depth',
        )

    def run_operator_command(
        self,
        payload: dict[str, Any],
    ) -> tuple[bool, str]:
        command = str(payload.get('command') or '')
        if command == 'dock':
            self._publish_log('수동 Dock 요청')
            self._send_dock(NavigationTarget(0.0, 0.0, 0.0, 'Dock'))
            return True, 'Dock requested'
        if command == 'undock':
            self._publish_log('수동 Undock 요청')
            self._send_undock_only()
            return True, 'Undock requested'
        if command == 'ros_restart':
            return self._run_remote_command(
                'ROS2 서비스 재시작',
                'systemctl restart turtlebot4.service',
            )
        if command == 'reboot':
            return self._run_remote_command('Robot reboot', 'reboot')
        if command == 'shutdown':
            return self._run_remote_command('Robot shutdown', 'shutdown now')
        return False, 'Unknown command'

    def save_capture(self, payload: dict[str, Any]) -> tuple[bool, str]:
        rgb_data = payload.get('rgb')
        depth_data = payload.get('depth')
        if not rgb_data and not depth_data:
            return False, 'No image data'

        stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
        self.capture_root.mkdir(parents=True, exist_ok=True)
        saved: list[str] = []

        for name, data_url in (('rgb', rgb_data), ('depth', depth_data)):
            if not data_url:
                continue
            try:
                image_bytes = self._decode_capture_data_url(str(data_url))
            except ValueError as exc:
                return False, str(exc)

            path = self.capture_root / f'{stamp}_{name}.jpg'
            path.write_bytes(image_bytes)
            saved.append(path.name)

        return True, ', '.join(saved)

    @staticmethod
    def _decode_capture_data_url(data_url: str) -> bytes:
        prefix = 'data:image/jpeg;base64,'
        if not data_url.startswith(prefix):
            raise ValueError('Capture images must be degraded JPEG data URLs')
        try:
            return base64.b64decode(data_url[len(prefix):], validate=True)
        except ValueError as exc:
            raise ValueError('Invalid capture image data') from exc

    def _send_undock_only(self) -> None:
        if not self._undock_action_client.wait_for_server(timeout_sec=0.2):
            self._publish_log('Undock 액션 서버 연결 대기 중...')
            if not self._undock_action_client.wait_for_server(timeout_sec=4.8):
                self._publish_log('Undock 액션 서버 연결 실패', level='error')
                return

        with self._state_lock:
            self._goal_state = 'undocking'

        future = self._undock_action_client.send_goal_async(Undock.Goal())
        future.add_done_callback(self._handle_manual_undock_response)

    def _handle_manual_undock_response(self, future) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:  # noqa: BLE001
            self._publish_log(f'Undock 목표 전송 실패: {exc}', level='error')
            return

        if not goal_handle.accepted:
            self._publish_log('Undock 목표가 거부되었습니다.', level='error')
            return

        with self._state_lock:
            self._undock_goal_handle = goal_handle

        self._publish_log('Undock 진행 중...')
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._handle_manual_undock_result)

    def _handle_manual_undock_result(self, future) -> None:
        try:
            result = future.result()
        except Exception as exc:  # noqa: BLE001
            self._publish_log(f'Undock 결과 수신 실패: {exc}', level='error')
            return

        is_docked = getattr(result.result, 'is_docked', None)
        if result.status == GoalStatus.STATUS_SUCCEEDED and is_docked is False:
            with self._state_lock:
                self._is_docked = False
                self._goal_state = 'idle'
                self._undock_goal_handle = None
            self._publish_log('Undock 완료', level='success')
            return

        status_text = STATUS_TEXT.get(result.status, str(result.status))
        self._publish_log(f'Undock 실패: {status_text}', level='error')

    def _run_remote_command(
        self,
        label: str,
        sudo_command: str,
    ) -> tuple[bool, str]:
        self._publish_log(f'{label} 요청')
        thread = threading.Thread(
            target=self._run_remote_command_worker,
            args=(label, sudo_command),
            daemon=True,
        )
        thread.start()
        return True, f'{label} requested'

    def _run_remote_command_worker(
        self,
        label: str,
        sudo_command: str,
    ) -> None:
        remote_host = self.get_parameter('remote_host').value
        password = self.get_parameter('remote_sudo_password').value
        remote_command = f"echo {password} | sudo -S {sudo_command}"
        try:
            completed = subprocess.run(
                ['ssh', remote_host, remote_command],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._publish_log(f'{label} 실패: {exc}', level='error')
            return

        if completed.returncode == 0:
            self._publish_log(f'{label} 완료', level='success')
        else:
            detail = completed.stderr.strip() or completed.stdout.strip()
            self._publish_log(f'{label} 실패: {detail}', level='error')

    def _compressed_image_data_url(self, message: CompressedImage) -> str:
        image_bytes = bytes(message.data)
        mime, payload = self._extract_image_payload(
            message.format,
            image_bytes,
        )
        encoded = base64.b64encode(payload).decode('ascii')
        return f'data:{mime};base64,{encoded}'

    @staticmethod
    def _extract_image_payload(
        image_format: str,
        image_bytes: bytes,
    ) -> tuple[str, bytes]:
        png_start = image_bytes.find(b'\x89PNG\r\n\x1a\n')
        if png_start >= 0:
            return 'image/png', image_bytes[png_start:]

        jpg_start = image_bytes.find(b'\xff\xd8')
        if jpg_start >= 0:
            return 'image/jpeg', image_bytes[jpg_start:]

        if 'png' in image_format.lower():
            return 'image/png', image_bytes
        return 'image/jpeg', image_bytes

    @staticmethod
    def _yaw_from_quaternion(orientation) -> float:
        siny_cosp = 2.0 * (
            orientation.w * orientation.z + orientation.x * orientation.y
        )
        cosy_cosp = 1.0 - 2.0 * (
            orientation.y * orientation.y + orientation.z * orientation.z
        )
        return math.atan2(siny_cosp, cosy_cosp)

    def send_navigation_goal(
        self,
        payload: dict[str, Any],
    ) -> tuple[bool, str]:
        try:
            target = self._target_from_payload(payload)
        except ValueError as exc:
            message = str(exc)
            self._publish_log(f'목표 전송 실패: {message}', level='error')
            return False, message

        with self._state_lock:
            is_docked = self._is_docked
            goal_state = self._goal_state

        if goal_state in (
            'undocking',
            'sending',
            'accepted',
            'moving',
            'docking',
            'canceling',
        ):
            return False, 'Another goal is already running'

        self._publish_log(
            (
                f'목표 전송 요청: {target.name} '
                f'({target.x:.3f}, {target.y:.3f}, yaw {target.yaw:.3f})'
            ),
            data=self._target_to_dict(target),
        )

        if target.dock_after and is_docked is True:
            self._publish_log('이미 도킹 상태입니다.', level='success')
            with self._state_lock:
                self._goal_state = 'docked'
                self._last_goal = target
            return True, 'Already docked'

        auto_undock = bool(self.get_parameter('auto_undock').value)
        should_undock = (
            auto_undock
            and not target.dock_after
            and is_docked is not False
        )
        if should_undock:
            self._send_undock_then_navigation(
                target,
                strict=is_docked is True,
            )
            return True, 'Undock and navigation request sent'

        return self._send_navigation_only(target)

    def _send_navigation_only(
        self,
        target: NavigationTarget,
    ) -> tuple[bool, str]:
        if not self._action_client.wait_for_server(timeout_sec=0.2):
            self._publish_log('Nav2 액션 서버 연결 대기 중...')
            if not self._action_client.wait_for_server(timeout_sec=4.8):
                message = 'Nav2 액션 서버 연결 실패'
                self._publish_log(message, level='error')
                return False, message

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = self._make_pose(target)

        with self._state_lock:
            self._goal_state = 'sending'
            self._last_goal = target
            self._last_feedback_log_time = 0.0

        future = self._action_client.send_goal_async(
            goal_msg,
            feedback_callback=self._handle_feedback,
        )
        future.add_done_callback(
            lambda response: self._handle_goal_response(response, target)
        )

        return True, 'Goal request sent'

    def _send_undock_then_navigation(
        self,
        target: NavigationTarget,
        strict: bool,
    ) -> None:
        if strict:
            self._publish_log('도킹 상태 감지: undock 후 이동을 시작합니다.')
        else:
            self._publish_log('dock 상태 미확인: undock을 먼저 시도합니다.')

        if not self._undock_action_client.wait_for_server(timeout_sec=0.2):
            self._publish_log('Undock 액션 서버 연결 대기 중...')
            if not self._undock_action_client.wait_for_server(timeout_sec=4.8):
                message = 'Undock 액션 서버 연결 실패'
                level = 'error' if strict else 'warning'
                self._publish_log(message, level=level)
                if strict:
                    with self._state_lock:
                        self._goal_state = 'failed'
                    return
                self._send_navigation_only(target)
                return

        with self._state_lock:
            self._goal_state = 'undocking'
            self._last_goal = target

        future = self._undock_action_client.send_goal_async(Undock.Goal())
        future.add_done_callback(
            lambda response: self._handle_undock_response(
                response,
                target,
                strict,
            )
        )

    def _handle_undock_response(
        self,
        future,
        target: NavigationTarget,
        strict: bool,
    ) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:  # noqa: BLE001
            self._publish_log(f'Undock 목표 전송 실패: {exc}', level='error')
            if strict:
                with self._state_lock:
                    self._goal_state = 'failed'
                return
            self._send_navigation_only(target)
            return

        if not goal_handle.accepted:
            self._publish_log('Undock 목표가 거부되었습니다.', level='warning')
            if strict:
                with self._state_lock:
                    self._goal_state = 'failed'
                return
            self._send_navigation_only(target)
            return

        with self._state_lock:
            self._undock_goal_handle = goal_handle

        self._publish_log('Undock 진행 중...')
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            lambda result: self._handle_undock_result(
                result,
                goal_handle,
                target,
                strict,
            )
        )

    def _handle_undock_result(
        self,
        future,
        goal_handle,
        target: NavigationTarget,
        strict: bool,
    ) -> None:
        try:
            result = future.result()
        except Exception as exc:  # noqa: BLE001
            self._publish_log(f'Undock 결과 수신 실패: {exc}', level='error')
            if strict:
                with self._state_lock:
                    self._goal_state = 'failed'
                return
            self._send_navigation_only(target)
            return

        status = result.status
        status_text = STATUS_TEXT.get(status, str(status))
        is_docked = getattr(result.result, 'is_docked', None)

        with self._state_lock:
            if goal_handle is self._undock_goal_handle:
                self._undock_goal_handle = None

        if status == GoalStatus.STATUS_SUCCEEDED and is_docked is False:
            with self._state_lock:
                self._is_docked = False
            self._publish_log('Undock 완료', level='success')
            self._send_navigation_only(target)
            return

        message = f'Undock 확인 실패: {status_text}'
        if strict:
            self._publish_log(message, level='error')
            with self._state_lock:
                self._goal_state = 'failed'
            return

        self._publish_log(f'{message}, 네비게이션을 계속합니다.', 'warning')
        self._send_navigation_only(target)

    def _send_dock(self, target: NavigationTarget) -> None:
        if not self._dock_action_client.wait_for_server(timeout_sec=0.2):
            self._publish_log('Dock 액션 서버 연결 대기 중...')
            if not self._dock_action_client.wait_for_server(timeout_sec=4.8):
                self._publish_log('Dock 액션 서버 연결 실패', level='error')
                with self._state_lock:
                    self._goal_state = 'failed'
                return

        with self._state_lock:
            self._goal_state = 'docking'
            self._last_dock_feedback_log_time = 0.0

        self._publish_log('도킹 중...')
        future = self._dock_action_client.send_goal_async(
            Dock.Goal(),
            feedback_callback=self._handle_dock_feedback,
        )
        future.add_done_callback(
            lambda response: self._handle_dock_response(response, target)
        )

    def _handle_dock_response(self, future, target: NavigationTarget) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:  # noqa: BLE001
            self._publish_log(f'Dock 목표 전송 실패: {exc}', level='error')
            with self._state_lock:
                self._goal_state = 'failed'
            return

        if not goal_handle.accepted:
            self._publish_log('Dock 목표가 거부되었습니다.', level='error')
            with self._state_lock:
                self._goal_state = 'failed'
            return

        with self._state_lock:
            self._dock_goal_handle = goal_handle

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            lambda result: self._handle_dock_result(
                result,
                goal_handle,
                target,
            )
        )

    def _handle_dock_feedback(self, feedback_msg) -> None:
        now = time.monotonic()
        if now - self._last_dock_feedback_log_time < 2.0:
            return
        self._last_dock_feedback_log_time = now

        sees_dock = getattr(feedback_msg.feedback, 'sees_dock', None)
        if sees_dock:
            self._publish_log('도킹 중... 도킹 스테이션 감지')

    def _handle_dock_result(
        self,
        future,
        goal_handle,
        target: NavigationTarget,
    ) -> None:
        try:
            result = future.result()
        except Exception as exc:  # noqa: BLE001
            self._publish_log(f'Dock 결과 수신 실패: {exc}', level='error')
            with self._state_lock:
                self._goal_state = 'failed'
            return

        status = result.status
        status_text = STATUS_TEXT.get(status, str(status))
        is_docked = getattr(result.result, 'is_docked', None)

        with self._state_lock:
            if goal_handle is self._dock_goal_handle:
                self._dock_goal_handle = None

        if status == GoalStatus.STATUS_SUCCEEDED and is_docked is True:
            with self._state_lock:
                self._is_docked = True
                self._goal_state = 'docked'
            self._publish_log('Docking Station 도킹 완료!', level='success')
            return

        self._publish_log(
            f'Docking Station 도킹 실패: {status_text}',
            level='error',
            data={'target': self._target_to_dict(target)},
        )
        with self._state_lock:
            self._goal_state = 'failed'

    def cancel_current_goal(self) -> tuple[bool, str]:
        with self._state_lock:
            goal_handle = self._goal_handle
            dock_goal_handle = self._dock_goal_handle
            undock_goal_handle = self._undock_goal_handle
            goal_state = self._goal_state

        if goal_state == 'docking' and dock_goal_handle is not None:
            self._publish_log('Dock 취소 요청')
            with self._state_lock:
                self._goal_state = 'canceling'
            future = dock_goal_handle.cancel_goal_async()
            future.add_done_callback(self._handle_cancel_response)
            return True, 'Dock cancel request sent'

        if goal_state == 'undocking' and undock_goal_handle is not None:
            self._publish_log('Undock 취소 요청')
            with self._state_lock:
                self._goal_state = 'canceling'
            future = undock_goal_handle.cancel_goal_async()
            future.add_done_callback(self._handle_cancel_response)
            return True, 'Undock cancel request sent'

        if goal_handle is None or goal_state not in ('accepted', 'moving'):
            return False, 'No active goal to cancel'

        self._publish_log('목표 취소 요청')
        with self._state_lock:
            self._goal_state = 'canceling'

        future = goal_handle.cancel_goal_async()
        future.add_done_callback(self._handle_cancel_response)
        return True, 'Cancel request sent'

    def destroy_node(self) -> bool:
        self._stop_http_server()
        self._action_client.destroy()
        self._dock_action_client.destroy()
        self._undock_action_client.destroy()
        return super().destroy_node()

    def _start_http_server(self) -> None:
        host = self.get_parameter('host').value
        port = int(self.get_parameter('port').value)
        self._http_server = DashboardHttpServer(
            (host, port),
            DashboardRequestHandler,
            self,
        )
        self._http_thread = threading.Thread(
            target=self._http_server.serve_forever,
            name='dashboard_http_server',
            daemon=True,
        )
        self._http_thread.start()

        actual_host, actual_port = self._http_server.server_address[:2]
        display_host = '127.0.0.1' if actual_host == '0.0.0.0' else actual_host
        self._publish_log(
            f'대시보드 준비 완료: http://{display_host}:{actual_port}'
        )

    def _stop_http_server(self) -> None:
        if self._http_server is None:
            return

        self._http_server.shutdown()
        self._http_server.server_close()
        if self._http_thread is not None:
            self._http_thread.join(timeout=2.0)
        self._http_server = None
        self._http_thread = None

    def _handle_goal_response(self, future, target: NavigationTarget) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:  # noqa: BLE001
            self._publish_log(f'목표 전송 실패: {exc}', level='error')
            with self._state_lock:
                self._goal_state = 'error'
            return

        if not goal_handle.accepted:
            self._publish_log('목표 전송 실패: Nav2가 목표를 거부했습니다.', 'error')
            with self._state_lock:
                self._goal_state = 'rejected'
                self._goal_handle = None
            return

        with self._state_lock:
            self._goal_handle = goal_handle
            self._goal_state = 'accepted'

        self._publish_log(
            f'목표 전송 완료: {target.name}',
            data=self._target_to_dict(target),
        )

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            lambda result: self._handle_result(result, goal_handle, target)
        )

    def _handle_feedback(self, feedback_msg) -> None:
        now = time.monotonic()
        if now - self._last_feedback_log_time < 1.0:
            return
        self._last_feedback_log_time = now

        feedback = feedback_msg.feedback
        distance = getattr(feedback, 'distance_remaining', None)
        recoveries = getattr(feedback, 'number_of_recoveries', None)
        message = '이동 중...'
        data: dict[str, Any] = {}

        if distance is not None:
            message = f'{message} 남은 거리 {distance:.2f} m'
            data['distance_remaining'] = distance
        if recoveries is not None:
            data['number_of_recoveries'] = recoveries

        with self._state_lock:
            self._goal_state = 'moving'

        self._publish_log(message, data=data)

    def _handle_result(
        self,
        future,
        goal_handle,
        target: NavigationTarget,
    ) -> None:
        try:
            result = future.result()
        except Exception as exc:  # noqa: BLE001
            self._publish_log(f'이동 결과 수신 실패: {exc}', level='error')
            with self._state_lock:
                self._goal_state = 'error'
            return

        status = result.status
        status_text = STATUS_TEXT.get(status, str(status))

        with self._state_lock:
            is_current_goal = goal_handle is self._goal_handle
            if is_current_goal:
                self._goal_handle = None

        if status == GoalStatus.STATUS_SUCCEEDED:
            message = f'목표 도착 완료: {target.name}'
            level = 'success'
            state = 'succeeded'
        elif status == GoalStatus.STATUS_CANCELED:
            message = f'목표 취소 완료: {target.name}'
            level = 'warning'
            state = 'canceled'
        else:
            message = f'목표 도착 실패: {target.name} ({status_text})'
            level = 'error'
            state = 'failed'

        with self._state_lock:
            if is_current_goal:
                self._goal_state = state

        self._publish_log(
            message,
            level=level,
            data={
                'status': status_text,
                'target': self._target_to_dict(target),
            },
        )

        if (
            status == GoalStatus.STATUS_SUCCEEDED
            and target.dock_after
            and is_current_goal
        ):
            self._send_dock(target)

    def _handle_cancel_response(self, future) -> None:
        try:
            response = future.result()
        except Exception as exc:  # noqa: BLE001
            self._publish_log(f'목표 취소 실패: {exc}', level='error')
            return

        if response.goals_canceling:
            self._publish_log('목표 취소 처리 중...')
        else:
            self._publish_log('취소할 목표가 없습니다.', level='warning')

    def _publish_log(
        self,
        message: str,
        level: str = 'info',
        data: dict[str, Any] | None = None,
    ) -> None:
        self.log_broker.publish(
            {
                'level': level,
                'message': message,
                'data': data or {},
            },
            event_type='log',
            store=True,
        )
        if level == 'error':
            self.get_logger().error(message)
        elif level == 'warning':
            self.get_logger().warn(message)
        else:
            self.get_logger().info(message)

    def _make_pose(self, target: NavigationTarget) -> PoseStamped:
        pose = PoseStamped()
        pose.header.frame_id = self.get_parameter('map_frame').value
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = target.x
        pose.pose.position.y = target.y
        pose.pose.position.z = 0.0
        pose.pose.orientation.z = math.sin(target.yaw / 2.0)
        pose.pose.orientation.w = math.cos(target.yaw / 2.0)
        return pose

    def _target_from_payload(
        self,
        payload: dict[str, Any],
    ) -> NavigationTarget:
        default_yaw = float(self.get_parameter('default_yaw').value)

        try:
            x = float(payload['x'])
            y = float(payload['y'])
            yaw = float(payload.get('yaw', default_yaw))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('x, y, yaw must be numeric') from exc

        if not all(math.isfinite(value) for value in (x, y, yaw)):
            raise ValueError('x, y, yaw must be finite')

        name = str(payload.get('name') or '선택 지점')[:80]
        dock_after = bool(payload.get('dock_after', False))
        return NavigationTarget(
            x=x,
            y=y,
            yaw=yaw,
            name=name,
            dock_after=dock_after,
        )

    def _target_to_dict(
        self,
        target: NavigationTarget | None,
    ) -> dict[str, Any] | None:
        if target is None:
            return None
        return {
            'name': target.name,
            'x': target.x,
            'y': target.y,
            'yaw': target.yaw,
            'dock_after': target.dock_after,
        }

    def _load_map_config(self) -> dict[str, Any]:
        yaml_path = self.maps_root / 'ninety.yaml'
        map_info = self._read_map_yaml(yaml_path)

        map_image = str(map_info.get('image', 'ninety.pgm'))
        pgm_path = self.maps_root / Path(map_image).name
        png_path = pgm_path.with_suffix('.png')
        display_image = png_path if png_path.exists() else pgm_path
        width, height = self._read_pgm_size(pgm_path)
        origin = map_info.get('origin', [-14.3, -10.4, 0.0])

        return {
            'image': f'/maps/{display_image.name}',
            'width': width,
            'height': height,
            'resolution': float(map_info.get('resolution', 0.05)),
            'origin': {
                'x': float(origin[0]),
                'y': float(origin[1]),
                'yaw': float(origin[2]),
            },
        }

    def _read_map_yaml(self, path: Path) -> dict[str, Any]:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            return self._read_simple_map_yaml(path)

        with path.open('r', encoding='utf-8') as stream:
            loaded = yaml.safe_load(stream)
        return loaded or {}

    def _read_simple_map_yaml(self, path: Path) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for raw_line in path.read_text(encoding='utf-8').splitlines():
            line = raw_line.split('#', 1)[0].strip()
            if not line or ':' not in line:
                continue

            key, value = line.split(':', 1)
            data[key.strip()] = self._parse_simple_yaml_value(value.strip())

        return data

    @staticmethod
    def _parse_simple_yaml_value(value: str) -> Any:
        if value.startswith('[') and value.endswith(']'):
            items = value[1:-1].split(',')
            return [float(item.strip()) for item in items if item.strip()]

        lowered = value.lower()
        if lowered in ('true', 'false'):
            return lowered == 'true'

        try:
            number = float(value)
        except ValueError:
            return value.strip('"\'')

        return int(number) if number.is_integer() else number

    @staticmethod
    def _read_pgm_size(path: Path) -> tuple[int, int]:
        data = path.read_bytes()
        index = 0

        def next_token() -> bytes:
            nonlocal index
            while index < len(data):
                byte = data[index:index + 1]
                if byte == b'#':
                    while index < len(data) and data[index:index + 1] != b'\n':
                        index += 1
                elif byte.isspace():
                    index += 1
                else:
                    break

            start = index
            while index < len(data) and not data[index:index + 1].isspace():
                index += 1
            return data[start:index]

        magic = next_token()
        if magic not in (b'P2', b'P5'):
            raise ValueError(f'Unsupported PGM format: {path}')

        width = int(next_token())
        height = int(next_token())
        return width, height


def main(args=None):
    rclpy.init(args=args)
    node = DashboardNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
