"""
Fetch Google Tasks from the configured lists and normalize them into the flat
structure the ESP32 consumes.

Order: tasks are returned in the same order as they appear in Google Tasks.
"""

from datetime import datetime

from googleapiclient.discovery import build

import config
import timefmt
from google_auth import get_google_creds


def _service():
    creds = get_google_creds()
    return build("tasks", "v1", credentials=creds, cache_discovery=False)


def _resolve_list_ids(svc):
    """
    Map configured list names to (name, id) pairs. If TASK_LIST_NAMES is empty,
    return all lists.
    """
    result = svc.tasklists().list(maxResults=100).execute()
    all_lists = result.get("items", [])

    if not config.TASK_LIST_NAMES:
        return [(lst["title"], lst["id"]) for lst in all_lists]

    wanted = {name.lower() for name in config.TASK_LIST_NAMES}
    matched = [(lst["title"], lst["id"]) for lst in all_lists if lst["title"].lower() in wanted]

    found_names = {title.lower() for title, _ in matched}
    for name in config.TASK_LIST_NAMES:
        if name.lower() not in found_names:
            print(f"[tasks] WARNING: list '{name}' not found in your Google Tasks")

    return matched


def _parse_due(due_raw):
    """
    Google Tasks 'due' is an RFC3339 date at UTC midnight, e.g.
    '2025-06-17T00:00:00.000Z'. Only the date part is meaningful.
    Returns a date or None.
    """
    if not due_raw:
        return None
    try:
        dt = datetime.fromisoformat(due_raw.replace("Z", "+00:00"))
        return dt.date()
    except ValueError:
        return None


def fetch_tasks():
    """Return a list of normalized task dicts, sorted as described above."""
    svc = _service()
    lists = _resolve_list_ids(svc)
    today = timefmt.today_local()

    tasks = []
    seen_ids = set()

    for list_name, list_id in lists:
        result = (
            svc.tasks()
            .list(
                tasklist=list_id,
                showCompleted=False,
                showHidden=False,
                maxResults=100,
            )
            .execute()
        )
        for item in result.get("items", []):
            tid = item.get("id")
            if tid in seen_ids:
                continue
            seen_ids.add(tid)

            due_date = _parse_due(item.get("due"))

            if due_date is None and not config.INCLUDE_TASKS_WITHOUT_DUE:
                continue

            notes = (item.get("notes") or "").strip().replace("\n", " ")
            if len(notes) > config.MAX_NOTES_CHARS:
                notes = notes[: config.MAX_NOTES_CHARS - 1] + "\u2026"

            overdue = timefmt.is_overdue(due_date, today) if due_date else False

            tasks.append(
                {
                    "title": item.get("title", "(untitled)").strip() or "(untitled)",
                    "due": timefmt.day_label(due_date, today) if due_date else "",
                    "overdue": overdue,
                    "list": list_name,
                    "notes": notes,
                }
            )

    return tasks[: config.MAX_TASKS]
