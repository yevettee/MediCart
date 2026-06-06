"""ocr — EasyOCR 텍스트 추출 (ocr_realtime.py 이식).

순수 로직(신뢰도 필터·줄결합)은 easyocr 무관이라 단위테스트한다. EasyOCR Reader는
ko+en 로컬 추론으로 lazy 싱글톤(최초 1회 ~500MB 다운로드). 웹 백엔드 전용.
"""
_reader = None


def filter_join(results, min_conf):
    """easyocr readtext 결과 [(bbox, text, conf), ...] → conf>min_conf text 줄결합."""
    texts = [t for (_bbox, t, c) in results if c > min_conf]
    return "\n".join(texts) if texts else "인식된 텍스트 없음"


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(["ko", "en"], gpu=False)
    return _reader


def recognized_text(image_bytes, min_conf=0.3):
    """이미지 bytes → 인식 텍스트(여러 줄). easyocr 로컬 추론."""
    import io
    import numpy as np
    from PIL import Image
    img = np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
    return filter_join(_get_reader().readtext(img), min_conf)
