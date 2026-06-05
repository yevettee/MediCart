"""QR code scanning from OAK-D RGB images using OpenCV.

Decodes a patient QR whose payload is JSON of the form::

    {"patient_id": "P-001", "room": "301"}

The decode is retried a few times because a single frame can fail to resolve
the code (motion blur, glare, partial occlusion). The caller passes a fresh
frame on each attempt via ``frame_provider``.
"""

import json

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
        """Decode a single frame, returning (patient_id, room) or None."""
        if image is None:
            return None

        data, _points, _straight = self._detector.detectAndDecode(image)
        if not data:
            return None

        try:
            payload = json.loads(data)
        except (ValueError, TypeError):
            return None

        patient_id = payload.get('patient_id')
        room = payload.get('room')
        if not patient_id or not room:
            return None

        return patient_id, room

    def scan(self, frame_provider):
        """Try to decode a QR code, retrying up to ``max_retries`` times.

        :param frame_provider: callable returning the latest BGR frame (or
            None when no frame is available yet).
        :return: tuple (patient_id, room) on success, otherwise None.
        """
        for _attempt in range(self._max_retries):
            image = frame_provider() if callable(frame_provider) else frame_provider
            result = self._decode_frame(image)
            if result is not None:
                return result
        return None
