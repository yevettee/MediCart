import os
import time
import cv2
import numpy as np
from google.cloud import vision
from google.oauth2 import service_account

from ocr_detector.engines.base import BaseOcrEngine

class GcpVisionEngine(BaseOcrEngine):
    def __init__(self, rate_hz: float = 1.0):
        from ament_index_python.packages import get_package_share_directory
        key_path = os.path.join(
            get_package_share_directory('ocr_detector'),
            'credentials',
            'gcp_vision_key.json',
        )
        credentials = service_account.Credentials.from_service_account_file(
            key_path,
            scopes=['https://www.googleapis.com/auth/cloud-vision'],
        )
        self._client = vision.ImageAnnotatorClient(credentials=credentials)
        self._min_interval = 1.0 / rate_hz
        self._last_call = 0.0

    def recognize(self, image: np.ndarray) -> tuple[str, float]:
        now = time.monotonic()
        remaining = self._min_interval - (now - self._last_call)
        if remaining > 0:
            time.sleep(remaining)

        upscaled = cv2.resize(image, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        bgr = cv2.cvtColor(upscaled, cv2.COLOR_RGB2BGR)
        _, encoded = cv2.imencode('.jpg', bgr)

        self._last_call = time.monotonic()

        try:
            response = self._client.text_detection(vision.Image(content=encoded.tobytes()))
        except Exception as e:
            raise RuntimeError(f'GCP Vision API call failed: {e}') from e

        if response.error.message:
            raise RuntimeError(f'GCP Vision API error: {response.error.message}')
        if not response.text_annotations:
            return '', 0.0
        return response.text_annotations[0].description.strip(), 1.0
