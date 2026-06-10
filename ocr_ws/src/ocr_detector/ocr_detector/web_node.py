#!/usr/bin/env python3
"""Gradio 웹UI — OCR 약물 검증 + Firebase DB 연동."""

import threading

import cv2
import gradio as gr
import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from ocr_detector.text_cleaner import clean_text
from ocr_detector.db_bridge import (
    get_patients_with_injections,
    save_ocr_result,
    update_injection_status,
)
from ocr_detector.medicine_checker import check_medicine


class WebNode(Node):
    def __init__(self):
        super().__init__('ocr_web_node')

        self.declare_parameter('engine', 'easyocr')
        self.declare_parameter('webcam_device', 2)
        self.declare_parameter('confidence_threshold', 0.2)
        self.declare_parameter('gcp_rate_hz', 1.0)
        self.declare_parameter('web_port', 7864)

        engine_name = self.get_parameter('engine').value
        webcam_device = self.get_parameter('webcam_device').value
        conf_threshold = self.get_parameter('confidence_threshold').value
        gcp_rate = self.get_parameter('gcp_rate_hz').value
        self._web_port = self.get_parameter('web_port').value

        self._engine = self._load_engine(engine_name, conf_threshold, gcp_rate)

        self._cap = cv2.VideoCapture(webcam_device)
        if not self._cap.isOpened():
            self.get_logger().error(f'웹캠 장치 {webcam_device} 열기 실패')

        self._latest_frame = None
        self._frame_lock = threading.Lock()
        self._pub = self.create_publisher(String, 'ocr_result', 10)

        threading.Thread(target=self._webcam_loop, daemon=True).start()

        try:
            self._patients = get_patients_with_injections()
            self.get_logger().info(f'DB 로드 완료 — 환자 {len(self._patients)}명')
        except Exception as e:
            self._patients = {}
            self.get_logger().error(f'DB 로드 실패: {e}')

        self.get_logger().info(
            f'ocr_web_node 시작  engine={engine_name}  webcam={webcam_device}  port={self._web_port}'
        )

    # ------------------------------------------------------------------
    def _load_engine(self, name, conf_threshold, gcp_rate):
        if name == 'gcp':
            from ocr_detector.engines.gcp_engine import GcpVisionEngine
            return GcpVisionEngine(rate_hz=gcp_rate)
        from ocr_detector.engines.easyocr_engine import EasyOcrEngine
        return EasyOcrEngine(conf_threshold=conf_threshold)

    def _webcam_loop(self):
        while True:
            ret, frame = self._cap.read()
            if not ret:
                continue
            with self._frame_lock:
                self._latest_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # ------------------------------------------------------------------
    def _get_frame(self):
        with self._frame_lock:
            f = self._latest_frame
        return f if f is not None else np.zeros((480, 640, 3), dtype=np.uint8)

    def _run_ocr(self) -> str:
        with self._frame_lock:
            frame = self._latest_frame
        if frame is None:
            return '카메라 연결 대기 중...'
        try:
            raw, _ = self._engine.recognize(frame)
            text = clean_text(raw) or '인식된 텍스트 없음'
        except Exception as e:
            self.get_logger().error(f'OCR 오류: {e}', throttle_duration_sec=5.0)
            return f'[오류] {e}'

        save_ocr_result(text)
        msg = String()
        msg.data = text
        self._pub.publish(msg)
        return text

    def _patient_choices(self) -> list[str]:
        return [f"{pid}  {d['name']}" for pid, d in self._patients.items()]

    def _prescription_info(self, choice: str) -> str:
        if not choice:
            return ''
        pid = choice.split()[0]
        injections = self._patients.get(pid, {}).get('injections', {})
        lines = []
        for inj_id, inj in injections.items():
            lines.append(
                f"[{inj_id}]  {inj.get('약물명')}  {inj.get('용량')}"
                f"  ({inj.get('투여방법')})  {inj.get('투여시간')}"
                f"  → 상태: {inj.get('상태')}"
            )
        return '\n'.join(lines) or '처방 정보 없음'

    def _verify(self, choice: str, inj_id: str, ocr_text: str) -> str:
        if not choice:
            return '환자를 먼저 선택하세요.'
        if not ocr_text or ocr_text.startswith('[오류]') or ocr_text == '인식된 텍스트 없음':
            return 'OCR 스캔을 먼저 실행하세요.'

        pid = choice.split()[0]
        inj = self._patients.get(pid, {}).get('injections', {}).get(inj_id, {})
        if not inj:
            return f'주사 ID [{inj_id}] 를 찾을 수 없습니다.'

        expected = inj.get('약물명', '')
        is_match, reason = check_medicine(ocr_text, expected)

        if is_match:
            update_injection_status(pid, inj_id, '완료')
            return f'✅ 일치\n{reason}\nDB 상태 업데이트 → 완료'
        else:
            update_injection_status(pid, inj_id, '불일치')
            return f'⚠️ 불일치\n{reason}\nDB 상태 업데이트 → 불일치'

    # ------------------------------------------------------------------
    def launch_gradio(self):
        node = self

        with gr.Blocks(title='MediCart OCR 약물 검증') as demo:
            gr.Markdown('## MediCart — OCR 약물 검증 시스템')

            with gr.Row():
                with gr.Column(scale=1):
                    cam_view = gr.Image(label='웹캠 화면', height=360)
                    timer = gr.Timer(value=0.5)
                    timer.tick(fn=node._get_frame, outputs=[cam_view])

                with gr.Column(scale=1):
                    patient_dd = gr.Dropdown(
                        choices=node._patient_choices(),
                        label='환자 선택',
                        interactive=True,
                    )
                    prescription_box = gr.Textbox(
                        label='처방 주사 정보', lines=5, interactive=False
                    )
                    inj_id_box = gr.Textbox(
                        label='주사 ID', value='inj001', interactive=True
                    )
                    patient_dd.change(
                        fn=node._prescription_info,
                        inputs=[patient_dd],
                        outputs=[prescription_box],
                    )

            with gr.Row():
                scan_btn = gr.Button('📷 OCR 스캔', variant='primary', scale=1)
                verify_btn = gr.Button('✅ 투약 확인 (DB 업데이트)', variant='secondary', scale=1)

            with gr.Row():
                ocr_box = gr.Textbox(label='OCR 인식 결과', lines=6, interactive=False)
                result_box = gr.Textbox(label='검증 결과', lines=6, interactive=False)

            scan_btn.click(fn=node._run_ocr, outputs=[ocr_box])
            verify_btn.click(
                fn=node._verify,
                inputs=[patient_dd, inj_id_box, ocr_box],
                outputs=[result_box],
            )

        demo.launch(server_name='0.0.0.0', server_port=self._web_port)


def main(args=None):
    rclpy.init(args=args)
    node = WebNode()

    threading.Thread(target=lambda: rclpy.spin(node), daemon=True).start()

    try:
        node.launch_gradio()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
