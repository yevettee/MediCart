"""QR code scanning from camera RGB frames — robust multi-decoder pipeline.

Decodes a patient QR whose payload is the **patient id string** itself, e.g.::

    P-2026-0001

(실제 환자 QR 포맷 — ~/Downloads/qrscan/qrpatient.py 참조. JSON 아님.)

실환경(USB 웹캠 640x480, 비스듬/원거리/저조도)에서는 한 디코더·원본 한 장만으로는
자주 실패한다. 그래서 다단계로 시도한다:

  1) 디코더 우선순위: pyzbar(가장 강건, libzbar0 필요) → QRCodeDetectorAruco
     (OpenCV 4.7+) → 기본 QRCodeDetector.
  2) 프레임 변형 멀티패스: 원본 → 그레이 → 2x 업스케일(작/원거리 QR) →
     CLAHE 대비강화(저조도/역광) → 적응형 이진화(글레어).

pyzbar 는 import 가능할 때만 1순위로 쓰고, 없으면(libzbar0 미설치) OpenCV
경로로 자동 폴백한다 — 의존성 없이도 기존보다 강건하게 동작.
"""

import cv2
import numpy as np

try:                                            # libzbar0 있으면 가장 강건한 1순위 디코더
    from pyzbar.pyzbar import decode as _zbar_decode
except Exception:                               # 시스템 lib 없으면 OpenCV 경로로 폴백
    _zbar_decode = None


# Default number of decode attempts (fresh frames) before giving up.
MAX_RETRIES = 3


class QrScanner:
    """Detect and decode a patient QR code from RGB frames."""

    def __init__(self, max_retries=MAX_RETRIES):
        """Create the scanner with a configurable retry budget."""
        self._cv = cv2.QRCodeDetector()
        # Aruco 기반 QR 검출기(OpenCV 4.7+) — 기본 detector 보다 검출률 높음.
        self._aruco = (cv2.QRCodeDetectorAruco()
                       if hasattr(cv2, 'QRCodeDetectorAruco') else None)
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        self._max_retries = max_retries

    def _variants(self, image):
        """Yield progressively enhanced views to maximize decode odds."""
        yield image                                          # 원본(컬러)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        yield gray                                           # 그레이
        h, w = gray.shape[:2]
        yield cv2.resize(gray, (w * 2, h * 2),               # 2x 업스케일 — 작/원거리 QR
                         interpolation=cv2.INTER_CUBIC)
        yield self._clahe.apply(gray)                        # 대비강화 — 저조도/역광
        yield cv2.adaptiveThreshold(                         # 이진화 — 글레어/그림자
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 31, 5)

    def _try_decode(self, img):
        """Run every available decoder on one image, return id or None."""
        if _zbar_decode is not None:                         # pyzbar 1순위
            for r in _zbar_decode(img):
                data = r.data.decode('utf-8', 'ignore').strip()
                if data:
                    return data
        for det in (self._aruco, self._cv):                  # OpenCV 폴백
            if det is None:
                continue
            try:
                data, _points, _straight = det.detectAndDecode(img)
            except cv2.error:
                continue
            data = (data or '').strip()
            if data:
                return data
        return None

    def _decode_frame(self, image):
        """Decode a single frame across all variants, return id or None."""
        if image is None:
            return None
        if not isinstance(image, np.ndarray):
            return None
        for view in self._variants(image):
            data = self._try_decode(view)
            if data:
                return data
        return None

    def scan(self, frame_provider):
        """Try to decode a QR code, retrying up to ``max_retries`` times.

        :param frame_provider: callable returning the latest BGR frame (or
            None when no frame is available yet).
        :return: patient_id string on success, otherwise None.
        """
        for _attempt in range(self._max_retries):
            image = frame_provider() if callable(frame_provider) else frame_provider
            result = self._decode_frame(image)
            if result is not None:
                return result
        return None
