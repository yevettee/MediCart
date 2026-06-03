"""Mission state machine for MediCart."""


class StateMachine:
    """Placeholder state machine: IDLE → UNDOCK → FOLLOW → SCAN → RETURN → DOCK."""

    STATES = ('IDLE', 'UNDOCK', 'FOLLOW', 'SCAN', 'RETURN', 'DOCK', 'ERROR')

    def __init__(self):
        self.state = 'IDLE'

    def transition(self, new_state):
        if new_state in self.STATES:
            self.state = new_state
