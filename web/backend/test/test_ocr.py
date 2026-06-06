"""ocr 순수 로직 단위 테스트 (easyocr 무관).

실행: cd MediCart/web/backend && python3 -m pytest test/test_ocr.py -v
"""
from ocr import filter_join


def test_filter_join_keeps_high_conf():
    results = [(None, "타이레놀", 0.92), (None, "noise", 0.10), (None, "500mg", 0.55)]
    assert filter_join(results, 0.3) == "타이레놀\n500mg"


def test_filter_join_empty_when_all_low():
    assert filter_join([(None, "x", 0.1)], 0.3) == "인식된 텍스트 없음"


def test_filter_join_no_results():
    assert filter_join([], 0.3) == "인식된 텍스트 없음"
