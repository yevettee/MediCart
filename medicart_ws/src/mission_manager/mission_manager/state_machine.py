"""Mission state machine for MediCart.

Supports two mission types on the same platform:

* ``patrol``     IDLE -> UNDOCK -> PATROL -> IDENTIFY -> INTERVIEW
                 -> NEXT_ROOM -> RETURN -> DOCK
* ``medication`` IDLE -> UNDOCK -> MOVE -> SCAN -> RETURN -> DOCK

NEXT_ROOM loops back to PATROL while rooms remain; once the patrol list is
exhausted it proceeds to RETURN.

For ``medication`` the baseline move step is autonomous navigation (``MOVE``).
The nurse-following challenge replaces ``MOVE`` with ``FOLLOW`` when
``/robot6/start_tracking`` is active; both lead to ``SCAN``.
"""


MISSION_PATROL = 'patrol'
MISSION_MEDICATION = 'medication'

# Ordered transition tables per mission type. ERROR is reachable from any state.
PATROL_FLOW = {
    'IDLE': ('UNDOCK',),
    'UNDOCK': ('PATROL',),
    'PATROL': ('IDENTIFY',),
    'IDENTIFY': ('INTERVIEW', 'NEXT_ROOM'),
    'INTERVIEW': ('NEXT_ROOM',),
    'NEXT_ROOM': ('PATROL', 'RETURN'),
    'RETURN': ('DOCK',),
    'DOCK': ('IDLE',),
    'ERROR': ('IDLE',),
}

MEDICATION_FLOW = {
    'IDLE': ('UNDOCK',),
    'UNDOCK': ('MOVE', 'FOLLOW'),   # MOVE=autonomous (baseline), FOLLOW=tracking challenge
    'MOVE': ('SCAN',),
    'FOLLOW': ('SCAN',),
    'SCAN': ('RETURN',),
    'RETURN': ('DOCK',),
    'DOCK': ('IDLE',),
    'ERROR': ('IDLE',),
}

FLOWS = {
    MISSION_PATROL: PATROL_FLOW,
    MISSION_MEDICATION: MEDICATION_FLOW,
}


class StateMachine:
    """Mission state machine parameterised by mission type."""

    STATES = ('IDLE', 'UNDOCK', 'PATROL', 'IDENTIFY', 'INTERVIEW', 'NEXT_ROOM',
              'MOVE', 'FOLLOW', 'SCAN', 'RETURN', 'DOCK', 'ERROR')

    def __init__(self, mission_type=MISSION_MEDICATION):
        """Start in IDLE for the given mission type (defaults to medication)."""
        self.mission_type = mission_type
        self.state = 'IDLE'

    @property
    def flow(self):
        """Return the transition table for the active mission type."""
        return FLOWS.get(self.mission_type, MEDICATION_FLOW)

    def allowed_next(self):
        """Return the tuple of states reachable from the current state."""
        return self.flow.get(self.state, ())

    def can_transition(self, new_state):
        """Return True if ``new_state`` is a valid next state (ERROR always ok)."""
        if new_state == 'ERROR':
            return True
        return new_state in self.allowed_next()

    def transition(self, new_state):
        """Move to ``new_state`` if the transition is valid; return success."""
        if self.can_transition(new_state):
            self.state = new_state
            return True
        return False

    def reset(self):
        """Return the machine to IDLE."""
        self.state = 'IDLE'
