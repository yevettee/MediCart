import cv2
import numpy as np
import easyocr

from ocr_detector.engines.base import BaseOcrEngine


class EasyOcrEngine(BaseOcrEngine):
    def __init__(self, conf_threshold: float = 0.2):
        self._conf_threshold = conf_threshold
        self._reader = easyocr.Reader(['ko', 'en'], gpu=False)

    def recognize(self, image: np.ndarray) -> tuple[str, float]:
        processed = self._preprocess(image)
        results = self._reader.readtext(
            processed,
            paragraph=False,
            contrast_ths=0.1,
            adjust_contrast=0.5,
            text_threshold=0.5,
            low_text=0.3,
        )
        lines = [(text, conf) for _, text, conf in results if conf > self._conf_threshold]
        if not lines:
            return '', 0.0
        raw = '\n'.join(t for t, _ in lines)
        avg_conf = sum(c for _, c in lines) / len(lines)
        return raw, float(avg_conf)

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        gray = cv2.filter2D(gray, -1, kernel)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
