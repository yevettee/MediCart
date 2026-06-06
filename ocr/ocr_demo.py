import os
import gradio as gr
from google.cloud import vision

project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
if not project_id:
    raise ValueError("환경변수 GOOGLE_CLOUD_PROJECT 를 설정해주세요")
client = vision.ImageAnnotatorClient()

def ocr(image):
    from PIL import Image as PILImage
    import io

    if image is None:
        return "이미지를 먼저 업로드하거나 웹캠으로 스냅샷을 찍어주세요 (📷 버튼)"

    img = PILImage.fromarray(image)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    content = buf.getvalue()

    response = client.text_detection(vision.Image(content=content))

    if response.error.message:
        return f"에러: {response.error.message}"

    texts = response.text_annotations
    if not texts:
        return "인식된 텍스트 없음"

    return texts[0].description

demo = gr.Interface(
    fn=ocr,
    inputs=gr.Image(label="이미지 업로드", webcam_options=gr.WebcamOptions(mirror=False)),
    outputs=gr.Textbox(label="OCR 결과", lines=20),
    title="Google Cloud Vision OCR",
)

demo.launch()
