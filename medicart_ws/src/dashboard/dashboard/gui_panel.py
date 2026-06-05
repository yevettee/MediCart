"""GUI panel state for the MediCart dashboard.

Holds the operator-facing view model for the patrol scenario: patrol progress
(current room out of total) and a rolling list of nurse alert pop-ups. Kept
free of any GUI toolkit so it stays importable and lint-clean; a Qt/Tk
front-end can render directly from this state.
"""


# How many recent alerts to keep for the pop-up list.
MAX_ALERTS = 20


class GuiPanel:
    """View model backing the operator dashboard controls and displays."""

    def __init__(self):
        """Initialise an idle panel with empty progress and alert history."""
        self.patrol_active = False
        self.current_room_index = 0
        self.total_rooms = 0
        self.alerts = []

    def start_patrol(self, total_rooms):
        """Mark the patrol as started over ``total_rooms`` rooms."""
        self.patrol_active = True
        self.total_rooms = total_rooms
        self.current_room_index = 0

    def update_progress(self, current_room_index, total_rooms=None):
        """Update the 'room N of M' progress indicator."""
        self.current_room_index = current_room_index
        if total_rooms is not None:
            self.total_rooms = total_rooms

    def progress_text(self):
        """Return a human-readable patrol progress string."""
        return '{} / {}'.format(self.current_room_index, self.total_rooms)

    def push_alert(self, text):
        """Append a nurse alert pop-up, trimming to the most recent ones."""
        self.alerts.append(text)
        if len(self.alerts) > MAX_ALERTS:
            self.alerts = self.alerts[-MAX_ALERTS:]

    def finish_patrol(self):
        """Mark the patrol as finished."""
        self.patrol_active = False
