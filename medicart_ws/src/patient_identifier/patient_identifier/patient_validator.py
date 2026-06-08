"""Validate a scanned patient against the prescription DB.

Calls the db_bridge ``/robot3/db/get_prescription`` service with the
patient_id extracted from the QR code, then checks that the room recorded in
the DB matches the room the robot is currently visiting.
"""

import rclpy

from medi_interfaces.srv import GetPrescription


# Service exposed by db_bridge under the /robot3 namespace.
GET_PRESCRIPTION_SERVICE = '/robot3/db/get_prescription'


class ValidationResult:
    """Outcome of a patient validation attempt.

    ``db_ok`` is False when the DB lookup itself failed (service unavailable,
    no response, or success flag False). When ``db_ok`` is True, ``matched``
    reports whether the visited room matches the DB room.
    """

    def __init__(self, db_ok=False, matched=False, patient=None, message=''):
        """Store the validation outcome fields."""
        self.db_ok = db_ok
        self.matched = matched
        self.patient = patient
        self.message = message


class PatientValidator:
    """Look up a patient in the DB and verify the visited room."""

    def __init__(self, node, timeout_sec=5.0, callback_group=None):
        """Create the service client on the owning node."""
        self._node = node
        self._timeout_sec = timeout_sec
        self._client = node.create_client(
            GetPrescription, GET_PRESCRIPTION_SERVICE, callback_group=callback_group)

    def validate(self, patient_id, current_room):
        """Validate ``patient_id`` against the DB for ``current_room``.

        :param patient_id: patient id decoded from the QR code.
        :param current_room: room number the robot is currently visiting.
        :return: ValidationResult describing the lookup and room match.
        """
        if not self._client.wait_for_service(timeout_sec=self._timeout_sec):
            return ValidationResult(db_ok=False, message='db service unavailable')

        request = GetPrescription.Request()
        request.patient_id = patient_id

        future = self._client.call_async(request)
        rclpy.spin_until_future_complete(self._node, future, timeout_sec=self._timeout_sec)

        response = future.result()
        if response is None:
            return ValidationResult(db_ok=False, message='db request timed out')
        if not response.success:
            return ValidationResult(db_ok=False, message=response.message)

        patient = response.patient
        matched = str(patient.room) == str(current_room)
        return ValidationResult(db_ok=True, matched=matched, patient=patient,
                                message=response.message)
