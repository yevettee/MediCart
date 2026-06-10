"""Bed-zone geofence helper for nurse-cart tracking stop.

The monitor is intentionally small: it receives the robot pose in the map
frame and reports once when the robot stays inside a configured bed-front
rectangle for a short dwell time.
"""
from dataclasses import dataclass
import time


@dataclass(frozen=True)
class BedZone:
    zone_id: str
    room_id: str
    bed_id: str
    points: tuple
    dwell_sec: float = 0.0

    def contains(self, x, y):
        """Return True when (x, y) is inside this axis-aligned bed zone."""
        xs = [float(p[0]) for p in self.points]
        ys = [float(p[1]) for p in self.points]
        return min(xs) <= float(x) <= max(xs) and min(ys) <= float(y) <= max(ys)

    def payload(self, x, y):
        return {
            "zone_id": self.zone_id,
            "room_id": self.room_id,
            "bed_id": self.bed_id,
            "x": float(x),
            "y": float(y),
            "ts": int(time.time() * 1000),
        }


DEFAULT_BED_ZONES = (
    BedZone(
        zone_id="room_101_bed_1",
        room_id="101",
        bed_id="1",
        points=((-3.7, -0.1), (-4.5, -0.1), (-4.5, -0.8), (-3.7, -0.8)),
    ),
    BedZone(
        zone_id="room_101_bed_2",
        room_id="101",
        bed_id="2",
        points=((-3.7, -1.4), (-4.5, -1.4), (-3.7, -2.0), (-4.5, -2.0)),
    ),
    BedZone(
        zone_id="room_102_bed_1",
        room_id="102",
        bed_id="1",
        points=((-3.8, -2.8), (-4.5, -2.8), (-3.8, -3.9), (-4.5, -3.9)),
    ),
)


class BedZoneMonitor:
    """Dwell-based detector for entering one of the configured bed zones."""

    def __init__(self, zones=None):
        self._zones = tuple(zones or DEFAULT_BED_ZONES)
        self._inside_id = None
        self._inside_since = None
        self._reported = set()

    def reset(self):
        self._inside_id = None
        self._inside_since = None
        self._reported.clear()

    def update(self, x, y, now=None):
        """Return a zone payload once, after dwell time, otherwise None."""
        now = time.monotonic() if now is None else float(now)
        zone = self._first_containing_zone(x, y)
        zone_id = zone.zone_id if zone is not None else None

        if zone_id != self._inside_id:
            self._inside_id = zone_id
            self._inside_since = now if zone is not None else None
            if zone is not None and zone_id not in self._reported and zone.dwell_sec <= 0.0:
                self._reported.add(zone_id)
                return zone.payload(x, y)
            return None

        if zone is None or zone_id in self._reported:
            return None

        if self._inside_since is not None and (now - self._inside_since) >= zone.dwell_sec:
            self._reported.add(zone_id)
            return zone.payload(x, y)

        return None

    def _first_containing_zone(self, x, y):
        for zone in self._zones:
            if zone.contains(x, y):
                return zone
        return None
