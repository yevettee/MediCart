"""Firebase Firestore client wrapper."""


class FirebaseClient:
    """Placeholder Firebase client."""

    def get_prescription(self, patient_id):
        """Return patient info and medicines ordered by admin_order ascending."""
        return None

    def verify_medicine_at_step(self, patient_id, step_index, scanned_text):
        """Verify scanned text against prescription medicine at step_index."""
        return False, None, scanned_text, 'not implemented'
