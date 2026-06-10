"""OCR 텍스트와 처방 약물명 대조."""

# 한국어 약물명 → 영문 성분/제품명 매핑
_ALIASES: dict[str, list[str]] = {
    '호르몬 주사': ['hormone', 'insulin', 'hgh', 'estrogen', 'testosterone', 'oxytocin', '호르몬'],
    '비타민 주사': ['vitamin', 'vit', 'ascorbic', 'b12', 'thiamine', 'riboflavin', 'pyridoxine', '비타민'],
    '스테로이드 주사': [
        'steroid', 'dexamethasone', 'methylprednisolone', 'hydrocortisone',
        'prednisolone', 'triamcinolone', 'betamethasone', '스테로이드',
    ],
    '아세트아미노펜': ['acetaminophen', 'paracetamol', 'tylenol'],
    '페니실린': ['penicillin', 'amoxicillin', 'ampicillin'],
}


def check_medicine(ocr_text: str, expected_medicine: str) -> tuple[bool, str]:
    """
    OCR 결과와 처방 약물명을 대조한다.
    Returns: (일치여부, 사유)
    """
    text_lower = ocr_text.lower()

    # 한국어 약물명 직접 포함 여부
    if expected_medicine in ocr_text:
        return True, f'약물명 직접 일치: {expected_medicine}'

    # 영문 별칭 매핑
    aliases = _ALIASES.get(expected_medicine, [])
    for alias in aliases:
        if alias.lower() in text_lower:
            return True, f'성분명 일치: {alias} → {expected_medicine}'

    return False, f'처방 약물 미인식 (처방: {expected_medicine})'
