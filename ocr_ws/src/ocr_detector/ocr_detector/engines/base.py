from abc import ABC, abstractmethod
import numpy as np


class BaseOcrEngine(ABC):
    @abstractmethod
    def recognize(self, image: np.ndarray) -> tuple[str, float]:
        """Run OCR on an RGB image. Return (raw_text, confidence)."""
