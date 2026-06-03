"""Data models for Firebase documents."""


class Patient:
    """Patient record model."""

    def __init__(self, patient_id='', name='', room=''):
        self.patient_id = patient_id
        self.name = name
        self.room = room


class Medicine:
    """Medicine record model."""

    def __init__(self, name='', dosage='', manufacturer=''):
        self.name = name
        self.dosage = dosage
        self.manufacturer = manufacturer
