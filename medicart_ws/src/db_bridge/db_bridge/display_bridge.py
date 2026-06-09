#!/usr/bin/env python3
"""display_bridge — patient_identified(ROS) → RTDB display 브리지.

시나리오 A에서 patient_identifier 가 QR 환자/병실 검증 후 ``/{ns}/patient_identified``
로 결과를 발행한다. 이 노드가 그 결과를 받아, 신원 확인된 환자ID를 RTDB
``display/current_patient`` 에 기록한다. 웹 /display 페이지가 이 값을 폴링해
문진표(/intake?pid=...)를 자동으로 띄운다.

웹 백엔드 fb_read.set_display_patient() 와 동일 스키마로 쓴다:
  display/current_patient = patient_id (str)
  display/updated_at      = epoch ms (int)

is_identified=True(status='identified') 인 경우에만 기록한다. mismatch/absent 는
무시한다(웹은 current_patient 변화에만 반응하므로 오작동 방지).

파라미터:
  namespace   기본 'robot6'(env ROBOT_NAMESPACE). 구독 토픽 = /{namespace}/patient_identified
  fb_cred     서비스계정 JSON 경로(env FB_CRED)
  fb_db_url   RTDB databaseURL(env FB_DB_URL)
"""
import os
import time

import rclpy
from rclpy.node import Node

from medi_interfaces.msg import PatientIdentified

from db_bridge.firebase_client import FirebaseClient


class DisplayBridge(Node):
    """patient_identified 를 구독해 RTDB display/current_patient 에 반영하는 브리지."""

    def __init__(self):
        super().__init__('display_bridge')

        self.declare_parameter('namespace', os.environ.get('ROBOT_NAMESPACE', 'robot6'))
        self.declare_parameter('fb_cred', os.environ.get('FB_CRED', ''))
        self.declare_parameter('fb_db_url', os.environ.get('FB_DB_URL', ''))

        self.ns = str(self.get_parameter('namespace').value).strip('/')
        cred = str(self.get_parameter('fb_cred').value)
        url = str(self.get_parameter('fb_db_url').value)

        self.get_logger().info(f'[display_bridge] RTDB 연결 시도 ns=/{self.ns} url={url}')
        self._fb = FirebaseClient(cred, url, logger=self.get_logger())

        # 같은 환자ID 연속 기록 방지(웹은 변화에만 반응) — 중복 RTDB 쓰기 억제.
        self._last_pid = ''

        topic = f'/{self.ns}/patient_identified'
        self._sub = self.create_subscription(
            PatientIdentified, topic, self._on_identified, 10)
        self.get_logger().info(f'[display_bridge] 준비 완료 — subscribe={topic}')

    def _on_identified(self, msg: PatientIdentified):
        pid = (msg.patient_id or '').strip()
        if not (msg.is_identified and pid):
            # mismatch/absent/빈 ID 는 무시.
            self.get_logger().debug(
                f'[display_bridge] skip status={msg.status!r} pid={pid!r} '
                f'identified={msg.is_identified}')
            return

        if pid == self._last_pid:
            self.get_logger().debug(f'[display_bridge] 동일 환자 재확인 — 기록 생략 pid={pid!r}')
            return

        try:
            self._fb.update('display', {
                'current_patient': pid,
                'updated_at': int(time.time() * 1000),
            })
        except Exception as exc:                       # noqa: BLE001 (브리지 안정성)
            self.get_logger().error(f'[display_bridge] RTDB 기록 오류: {exc}')
            return

        self._last_pid = pid
        self.get_logger().info(
            f'[display_bridge] display/current_patient ← {pid!r} '
            f'(name={msg.patient_name!r} room={msg.room!r})')


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = DisplayBridge()
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
