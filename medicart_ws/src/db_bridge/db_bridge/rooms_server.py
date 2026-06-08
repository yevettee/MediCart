#!/usr/bin/env python3
"""rooms_server — ListRooms 서비스 서버 (RTDB /rooms waypoint 조회).

클라이언트(순찰 patrol 노드 등)가 ``/{ns}/db/list_rooms`` 로 filter('bed'|'')를 보내면
RTDB /rooms 를 읽어 room_id 와 x/y/yaw·patient_id 를 병렬 배열로 응답한다.
시나리오 A 순찰의 병상 waypoint 목록을 제공한다.

파라미터: namespace(env ROBOT_NAMESPACE), fb_cred(FB_CRED), fb_db_url(FB_DB_URL).
"""
import os

import rclpy
from rclpy.node import Node

from medi_interfaces.srv import ListRooms

from db_bridge.firebase_client import FirebaseClient
from db_bridge.room_lookup import list_rooms


class RoomsServer(Node):
    """RTDB /rooms 를 ListRooms 로 응답하는 서비스 서버."""

    def __init__(self):
        super().__init__('rooms_server')

        self.declare_parameter('namespace', os.environ.get('ROBOT_NAMESPACE', 'robot6'))
        self.declare_parameter('fb_cred', os.environ.get('FB_CRED', ''))
        self.declare_parameter('fb_db_url', os.environ.get('FB_DB_URL', ''))

        self.ns = str(self.get_parameter('namespace').value).strip('/')
        cred = str(self.get_parameter('fb_cred').value)
        url = str(self.get_parameter('fb_db_url').value)

        self.get_logger().info(f'[rooms_server] RTDB 연결 시도 ns=/{self.ns} url={url}')
        self._fb = FirebaseClient(cred, url, logger=self.get_logger())

        srv_name = f'/{self.ns}/db/list_rooms'
        self._srv = self.create_service(ListRooms, srv_name, self._on_list_rooms)
        self.get_logger().info(f'[rooms_server] 준비 완료 — service={srv_name}')

    def _on_list_rooms(self, request, response):
        room_filter = (request.filter or '').strip()
        self.get_logger().info(f'[rooms_server] ListRooms filter={room_filter!r}')
        try:
            rooms = list_rooms(self._fb, room_filter)
        except Exception as exc:                       # noqa: BLE001 (서비스 안정성)
            self.get_logger().error(f'[rooms_server] RTDB 조회 오류: {exc}')
            response.success = False
            response.message = f'db error: {exc}'
            return response

        response.room_ids = [r['room_id'] for r in rooms]
        response.xs = [r['x'] for r in rooms]
        response.ys = [r['y'] for r in rooms]
        response.yaws = [r['yaw'] for r in rooms]
        response.patient_ids = [r['patient_id'] for r in rooms]
        response.success = True
        response.message = f'{len(rooms)} rooms'
        self.get_logger().info(
            f'[rooms_server] → {len(rooms)} rooms {response.room_ids}')
        return response


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = RoomsServer()
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
