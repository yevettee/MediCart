"""QR code scanning from OAK-D RGB images using OpenCV.

Decodes a patient QR whose payload is the **patient id string** itself, e.g.::

    P-2026-0001

(실제 환자 QR 포맷 — ~/Downloads/qrscan/qrpatient.py 참조. JSON 아님.)
cv2.QRCodeDetector 로 실제 QR PNG 디코드 검증 완료(pyzbar 불필요).

The decode is retried a few times because a single frame can fail to resolve
the code (motion blur, glare, partial occlusion). The caller passes a fresh
frame on each attempt via ``frame_provider``.
"""

import cv2


# Default number of decode attempts before giving up.
MAX_RETRIES = 3


class QrScanner:
    """Detect and decode a patient QR code from RGB frames."""

    def __init__(self, max_retries=MAX_RETRIES):
        """Create the scanner with a configurable retry budget."""
        self._detector = cv2.QRCodeDetector()
        self._max_retries = max_retries

    def _decode_frame(self, image):
        """Decode a single frame, returning the patient_id string or None."""
        if image is None:
            return None

        data, _points, _straight = self._detector.detectAndDecode(image)
        data = (data or '').strip()
        if not data:
            return None

        return data

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
