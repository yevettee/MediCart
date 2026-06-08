"""ocr — GCP Vision API 텍스트 추출.

서비스 계정 키를 명시적으로 로드해 GOOGLE_APPLICATION_CREDENTIALS 환경변수와 무관하게 동작.
키 경로: GCP_VISION_KEY_PATH 환경변수 → 기본 경로 순으로 탐색.
"""
import os

_DEFAULT_KEY = "/home/jeon/ocr_ws/src/ocr_detector/credentials/gcp_vision_key.json"
_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    from google.cloud import vision
    from google.oauth2 import service_account

    key_path = os.environ.get("GCP_VISION_KEY_PATH", _DEFAULT_KEY)
    if not os.path.exists(key_path):
        raise FileNotFoundError(f"GCP Vision 키 파일을 찾을 수 없습니다: {key_path}")

    creds = service_account.Credentials.from_service_account_file(
        key_path, scopes=["https://www.googleapis.com/auth/cloud-vision"]
    )
    _client = vision.ImageAnnotatorClient(credentials=creds)
    return _client


def recognized_text(image_bytes, min_conf=0.0):
    """이미지 bytes → 인식 텍스트. GCP Vision API DOCUMENT_TEXT_DETECTION 사용."""
    from google.cloud import vision

    client = _get_client()
    image = vision.Image(content=image_bytes)
    response = client.document_text_detection(image=image)

    if response.error.message:
        raise RuntimeError(f"GCP Vision 오류: {response.error.message}")

    text = response.full_text_annotation.text.strip()
    return text if text else "인식된 텍스트 없음"
