"""In-memory prescription session for sequential medicine verification."""


class PrescriptionSession:
    """Tracks ordered prescription and current scan step for one patient."""

    def __init__(self):
        self.patient_id = ''
        self.medicines = []
        self.current_step = 0

    @property
    def total_steps(self):
        return len(self.medicines)

    @property
    def is_active(self):
        return bool(self.patient_id) and self.total_steps > 0

    @property
    def is_complete(self):
        return self.is_active and self.current_step >= self.total_steps

    def start(self, patient_id, medicines):
        self.patient_id = patient_id
        self.medicines = list(medicines)
        self.current_step = 0

    def clear(self):
        self.patient_id = ''
        self.medicines = []
        self.current_step = 0

    def expected_medicine(self):
        if not self.is_active or self.is_complete:
            return None
        return self.medicines[self.current_step]

    def advance_if_match(self, match):
        if match and not self.is_complete:
            self.current_step += 1
            return True
        return False
