"""
Shared helpers for converting API datetimes into the human-readable, flat
strings the ESP32 expects ("Today", "Tomorrow", "Wed 18 Jun", "09:00", ...).

All date math happens here so neither the firmware nor the fetch modules need
to repeat it.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import config

LOCAL_TZ = ZoneInfo(config.LOCAL_TIMEZONE)


def to_local(dt):
    """Convert an aware datetime to local time. Naive input is assumed UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(LOCAL_TZ)


def parse_graph_datetime(value, tz_hint="UTC"):
    """
    Parse a Microsoft Graph dateTime string into an aware datetime.

    Graph returns e.g. "2025-06-17T09:00:00.0000000" plus a separate timeZone
    field. We treat the supplied value as being in tz_hint, then normalize.
    """
    # Trim fractional seconds to 6 digits max for fromisoformat compatibility.
    clean = value.replace("Z", "")
    if "." in clean:
        head, frac = clean.split(".", 1)
        frac = frac[:6]
        clean = f"{head}.{frac}"
    dt = datetime.fromisoformat(clean)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz_hint))
    return dt


def day_label(d, today=None):
    """
    Return a human label for a date relative to today:
      'Today', 'Tomorrow', or 'Wed 18 Jun' for anything else.
    """
    if today is None:
        today = datetime.now(LOCAL_TZ).date()
    delta = (d - today).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    return d.strftime("%a %d %b")


def hhmm(dt_local):
    """Return 24h HH:MM string from a local datetime."""
    return dt_local.strftime("%H:%M")


def is_overdue(d, today=None):
    """True if date d is strictly before today."""
    if today is None:
        today = datetime.now(LOCAL_TZ).date()
    return d < today


def today_local():
    return datetime.now(LOCAL_TZ).date()
