"""YOLO11n person detection from OAK-D RGB images.

Mirrors the structure of nurse_tracker's yolo_detector: a thin wrapper around
an ultralytics YOLO model that runs inference on a single BGR frame. Here the
only thing the caller needs is whether a person is currently in view, so the
detector collapses the model output to a boolean.
"""

# COCO class id for "person" used by the YOLO11n default weights.
PERSON_CLASS_ID = 0


class PersonDetector:
    """Detect whether a person is present in an RGB frame using YOLO11n."""

    def __init__(self, model_path='yolo11n.pt', conf=0.5):
        """Store config and lazily create the model on first use.

        The model is loaded lazily so the node can be constructed (and unit
        tested) without the heavy ultralytics import or the weights file.
        """
        self._model_path = model_path
        self._conf = conf
        self._model = None

    def _ensure_model(self):
        """Load the YOLO model on first inference call."""
        if self._model is None:
            from ultralytics import YOLO
            self._model = YOLO(self._model_path)
        return self._model

    def detect(self, image):
        """Return True if at least one person is detected in the image.

        :param image: BGR image as a numpy array (sensor_msgs Image decoded).
        :return: bool, True when a person is detected above the threshold.
        """
        if image is None:
            return False

        model = self._ensure_model()
        results = model(image, classes=[PERSON_CLASS_ID], conf=self._conf, verbose=False)

        for result in results:
            if result.boxes is not None and len(result.boxes) > 0:
                return True
        return False
