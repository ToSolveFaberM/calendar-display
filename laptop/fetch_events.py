"""
Fetch Google Calendar events and normalize them into the flat structure
the ESP32 consumes.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

import config
import timefmt
from google_auth import get_google_creds


def _find_calendar_id(service):
    result = service.calendarList().list().execute()
    name = config.GOOGLE_CALENDAR_NAME.lower()
    for cal in result.get("items", []):
        if cal.get("summary", "").lower() == name:
            return cal["id"]
    raise ValueError(f"Calendar '{config.GOOGLE_CALENDAR_NAME}' not found in Google Calendar.")


def fetch_events():
    """Return a list of normalized event dicts, sorted by start time."""
    creds = get_google_creds()
    service = build("calendar", "v3", credentials=creds)

    calendar_id = _find_calendar_id(service)

    today = timefmt.today_local()
    start_local = datetime(today.year, today.month, today.day, tzinfo=timefmt.LOCAL_TZ)
    end_local = start_local + timedelta(days=2)
    utc = ZoneInfo("UTC")
    time_min = start_local.astimezone(utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    time_max = end_local.astimezone(utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    result = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
        maxResults=config.MAX_EVENTS,
    ).execute()

    events = []
    for item in result.get("items", []):
        start = item["start"]
        end = item["end"]
        all_day = "date" in start and "dateTime" not in start

        if all_day:
            event_date = date.fromisoformat(start["date"])
            start_hhmm = ""
            end_hhmm = ""
            sortkey = datetime(event_date.year, event_date.month, event_date.day, tzinfo=timefmt.LOCAL_TZ)
        else:
            start_dt = timefmt.to_local(datetime.fromisoformat(start["dateTime"]))
            end_dt = timefmt.to_local(datetime.fromisoformat(end["dateTime"]))
            event_date = start_dt.date()
            start_hhmm = timefmt.hhmm(start_dt)
            end_hhmm = timefmt.hhmm(end_dt)
            sortkey = start_dt

        events.append({
            "title": item.get("summary", "(no title)"),
            "start": start_hhmm,
            "end": end_hhmm,
            "date": timefmt.day_label(event_date, today),
            "location": item.get("location", ""),
            "allDay": all_day,
            "_sortkey": sortkey,
        })

    events.sort(key=lambda e: e["_sortkey"])
    for e in events:
        e.pop("_sortkey", None)

    return events
