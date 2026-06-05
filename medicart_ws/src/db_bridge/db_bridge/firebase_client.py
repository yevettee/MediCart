"""Firebase Firestore client wrapper."""


class FirebaseClient:
    """Placeholder Firebase client."""

    def get_prescription(self, patient_id):
        """Return patient info and medicines ordered by admin_order ascending."""
        return None

    def verify_medicine_at_step(self, patient_id, step_index, scanned_text):
        """Verify scanned text against prescription medicine at step_index."""
        return False, None, scanned_text, 'not implemented'

    def update_patient_status(self, patient_id, status):
        """Record a patrol outcome status for a patient.

        :param patient_id: id of the patient (may be empty for absent rooms).
        :param status: one of identified / absent / mismatch / no_qr / db_error.
        :return: tuple (success, message).
        """
        return False, 'not implemented'
