import gradio as gr
import easyocr
from PIL import Image as PILImage
import numpy as np

print("EasyOCR 모델 로딩 중... (최초 1회 다운로드, 잠시 대기)")
reader = easyocr.Reader(['ko', 'en'], gpu=False)
print("로딩 완료!")

def ocr_realtime(image):
    if image is None:
        return ""

    results = reader.readtext(image)
    if not results:
        return "인식된 텍스트 없음"

    return "\n".join([text for _, text, conf in results if conf > 0.3])

demo = gr.Interface(
    fn=ocr_realtime,
    inputs=gr.Image(
        label="웹캠",
        sources=["webcam"],
        streaming=True,
        webcam_options=gr.WebcamOptions(mirror=False),
    ),
    outputs=gr.Textbox(label="OCR 결과 (실시간)", lines=10),
    title="EasyOCR 실시간",
    live=True,
)

demo.launch(server_port=7863)
