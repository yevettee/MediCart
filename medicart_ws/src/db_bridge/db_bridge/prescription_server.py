#!/usr/bin/env python3
"""prescription_server — GetPrescription 서비스 서버 (RTDB 조회).

클라이언트(patient_identifier 등)가 ``/{ns}/db/get_prescription`` 으로 patient_id 를
보내면 RTDB(/patients·/patient_rooms·/rooms)를 조회해 PatientInfo(이름·병실)를 응답한다.
시나리오 A 의 QR 환자/병실 검증에 쓰인다.

medicines 는 빈 배열로 둔다 — RTDB 에 아직 구조화된 처방(/prescriptions) 경로가 없다
(아키텍처 문서 §1.4). 처방 스키마가 추가되면 여기서 채운다.

파라미터:
  namespace   기본 'robot6'(env ROBOT_NAMESPACE). 서비스명 = /{namespace}/db/get_prescription
  fb_cred     서비스계정 JSON 경로(env FB_CRED)
  fb_db_url   RTDB databaseURL(env FB_DB_URL)
"""
import os

import rclpy
from rclpy.node import Node

from medi_interfaces.srv import GetPrescription
from medi_interfaces.msg import PatientInfo

from db_bridge.firebase_client import FirebaseClient
from db_bridge.patient_lookup import resolve_patient


class PrescriptionServer(Node):
    """RTDB 조회로 GetPrescription 을 응답하는 서비스 서버."""

    def __init__(self):
        super().__init__('prescription_server')

        self.declare_parameter('namespace', os.environ.get('ROBOT_NAMESPACE', 'robot6'))
        self.declare_parameter('fb_cred', os.environ.get('FB_CRED', ''))
        self.declare_parameter('fb_db_url', os.environ.get('FB_DB_URL', ''))

        self.ns = str(self.get_parameter('namespace').value).strip('/')
        cred = str(self.get_parameter('fb_cred').value)
        url = str(self.get_parameter('fb_db_url').value)

        self.get_logger().info(f'[prescription_server] RTDB 연결 시도 ns=/{self.ns} url={url}')
        self._fb = FirebaseClient(cred, url, logger=self.get_logger())

        srv_name = f'/{self.ns}/db/get_prescription'
        self._srv = self.create_service(GetPrescription, srv_name, self._on_get_prescription)
        self.get_logger().info(f'[prescription_server] 준비 완료 — service={srv_name}')

    def _on_get_prescription(self, request, response):
        pid = (request.patient_id or '').strip()
        self.get_logger().info(f'[prescription_server] GetPrescription patient_id={pid!r}')
        try:
            res = resolve_patient(self._fb, pid)
        except Exception as exc:                       # noqa: BLE001 (서비스 안정성)
            self.get_logger().error(f'[prescription_server] RTDB 조회 오류: {exc}')
            response.success = False
            response.patient = PatientInfo(patient_id=pid)
            response.medicines = []
            response.message = f'db error: {exc}'
            return response

        info = PatientInfo()
        info.patient_id = pid
        info.name = res['name']
        info.room = res['room']
        response.patient = info
        response.medicines = []                        # 구조화 처방 미존재(RTDB)
        response.success = res['found']
        response.message = res['message']
        self.get_logger().info(
            f"[prescription_server] → success={res['found']} name={res['name']!r} "
            f"room={res['room']!r} msg={res['message']}")
        return response


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = PrescriptionServer()
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
