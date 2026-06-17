"""
Fetch Outlook calendar events via Microsoft Graph and normalize them into the
flat structure the ESP32 consumes.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

import config
import timefmt
from ms_auth import get_ms_token

GRAPH_CALENDAR_VIEW = "https://graph.microsoft.com/v1.0/me/calendarView"


def _window_utc():
    """
    Build the start/end of the fetch window (today 00:00 -> tomorrow 23:59
    in local time) expressed as UTC ISO strings, which is what Graph wants.
    """
    today = timefmt.today_local()
    start_local = datetime(today.year, today.month, today.day, tzinfo=timefmt.LOCAL_TZ)
    end_local = start_local + timedelta(days=2)  # through end of tomorrow
    utc = ZoneInfo("UTC")
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return start_local.astimezone(utc).strftime(fmt), end_local.astimezone(utc).strftime(fmt)


def fetch_events():
    """Return a list of normalized event dicts, sorted by start time."""
    token = get_ms_token()
    start_utc, end_utc = _window_utc()

    params = {
        "startDateTime": start_utc,
        "endDateTime": end_utc,
        "$select": "subject,start,end,location,isAllDay",
        "$orderby": "start/dateTime asc",
        "$top": "25",
    }
    headers = {
        "Authorization": f"Bearer {token}",
        # Ask Graph to return times already converted to our local zone.
        "Prefer": f'outlook.timezone="{config.LOCAL_TIMEZONE}"',
    }

    resp = requests.get(GRAPH_CALENDAR_VIEW, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    raw = resp.json().get("value", [])

    today = timefmt.today_local()
    events = []
    for item in raw:
        all_day = bool(item.get("isAllDay"))
        start_tz = item["start"].get("timeZone", config.LOCAL_TIMEZONE)
        end_tz = item["end"].get("timeZone", config.LOCAL_TIMEZONE)
        start_dt = timefmt.parse_graph_datetime(item["start"]["dateTime"], start_tz)
        end_dt = timefmt.parse_graph_datetime(item["end"]["dateTime"], end_tz)
        start_local = timefmt.to_local(start_dt)
        end_local = timefmt.to_local(end_dt)

        location = (item.get("location") or {}).get("displayName", "") or ""

        events.append(
            {
                "title": item.get("subject", "(no title)"),
                "start": "" if all_day else timefmt.hhmm(start_local),
                "end": "" if all_day else timefmt.hhmm(end_local),
                "date": timefmt.day_label(start_local.date(), today),
                "location": location,
                "allDay": all_day,
                "_sortkey": start_local,  # internal, stripped before sending
            }
        )

    events.sort(key=lambda e: e["_sortkey"])
    for e in events:
        e.pop("_sortkey", None)

    return events[: config.MAX_EVENTS]
