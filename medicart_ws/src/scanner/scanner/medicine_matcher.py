"""Medicine matching logic for sequential prescription verification."""


class MedicineMatcher:
    """Matches OCR text against the expected medicine at a given step."""

    def match(self, scanned_text, expected_medicine):
        if expected_medicine is None:
            return False, 'no expected medicine for current step'

        expected_name = expected_medicine.name.strip().lower()
        normalized_scan = scanned_text.strip().lower()

        if not normalized_scan or not expected_name:
            return False, 'empty scan or expected medicine name'

        if expected_name in normalized_scan or normalized_scan in expected_name:
            return True, ''

        step = expected_medicine.sequence_order
        return False, (
            f'order mismatch at step {step}: '
            f"expected '{expected_medicine.name}', scanned '{scanned_text}'"
        )
