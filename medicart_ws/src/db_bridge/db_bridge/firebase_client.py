"""Firebase Firestore client wrapper."""


class FirebaseClient:
    """Placeholder Firebase client."""

    def get_prescription(self, patient_id):
        """Return patient info and medicines ordered by admin_order ascending."""
        return None

    def verify_medicine_at_step(self, patient_id, step_index, scanned_text):
        """Verify scanned text against prescription medicine at step_index."""
        return False, None, scanned_text, 'not implemented'

    def update_visit_status(self, patient_id, room, status, session_id=''):
        """Record a patrol visit outcome into the ``patient_visits`` collection.

        Backs the ``/robot6/db/update_visit_status`` (``UpdateVisitStatus``)
        service called by ``mission_manager`` during patrol (scenario A).

        :param patient_id: id of the patient (may be empty for absent rooms).
        :param room: room visited.
        :param status: one of identified / absent / mismatch / no_qr / db_error.
        :param session_id: robot_session_id grouping a patrol run (optional).
        :return: tuple (success, message).
        """
        return False, 'not implemented'
