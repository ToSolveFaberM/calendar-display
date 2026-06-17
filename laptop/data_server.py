"""
data_server.py - main entry point.

Serves a combined calendar + tasks JSON payload on the local network for the
ESP32 to poll. A background thread refreshes both data sources every few
minutes so the HTTP handler always returns instantly from cache.

Run:
    python data_server.py

On first run two browser windows open (Microsoft, then Google). After that,
tokens are cached and refresh silently.
"""

import threading
import time
from datetime import datetime

from flask import Flask, jsonify

import config
import timefmt
from fetch_events import fetch_events
from fetch_tasks import fetch_tasks

app = Flask(__name__)

# Shared cache, guarded by a lock. Each source updates independently so one
# failing API does not wipe the other's good data.
_lock = threading.Lock()
_cache = {
    "updated": None,
    "events": [],
    "tasks": [],
    "events_error": None,
    "tasks_error": None,
}


def _refresh_once():
    """Refresh both sources, updating cache fields independently."""
    # Events
    try:
        events = fetch_events()
        with _lock:
            _cache["events"] = events
            _cache["events_error"] = None
        print(f"[refresh] events: {len(events)}")
    except Exception as exc:  # noqa: BLE001 - we want to keep serving stale data
        with _lock:
            _cache["events_error"] = str(exc)
        print(f"[refresh] events ERROR: {exc}")

    # Tasks
    try:
        tasks = fetch_tasks()
        with _lock:
            _cache["tasks"] = tasks
            _cache["tasks_error"] = None
        print(f"[refresh] tasks: {len(tasks)}")
    except Exception as exc:  # noqa: BLE001
        with _lock:
            _cache["tasks_error"] = str(exc)
        print(f"[refresh] tasks ERROR: {exc}")

    with _lock:
        _cache["updated"] = datetime.now(timefmt.LOCAL_TZ).strftime("%Y-%m-%dT%H:%M:%S")


def _refresh_loop():
    while True:
        _refresh_once()
        time.sleep(config.REFRESH_INTERVAL_SECONDS)


@app.route("/")
def health():
    with _lock:
        updated = _cache["updated"]
    return jsonify(
        {
            "status": "ok",
            "updated": updated,
            "endpoints": ["/data", "/calendar", "/tasks"],
        }
    )


@app.route("/data")
def data():
    """Combined payload: events + tasks. This is what the ESP32 polls."""
    with _lock:
        return jsonify(
            {
                "updated": _cache["updated"],
                "events": _cache["events"],
                "tasks": _cache["tasks"],
            }
        )


@app.route("/calendar")
def calendar_only():
    with _lock:
        return jsonify({"updated": _cache["updated"], "events": _cache["events"]})


@app.route("/tasks")
def tasks_only():
    with _lock:
        return jsonify({"updated": _cache["updated"], "tasks": _cache["tasks"]})


def main():
    # Do one synchronous refresh up front so the first HTTP hit has data and
    # so the interactive logins happen before the server starts serving.
    print("Authenticating and fetching initial data...")
    _refresh_once()

    worker = threading.Thread(target=_refresh_loop, daemon=True)
    worker.start()

    print(f"Serving on http://{config.HTTP_HOST}:{config.HTTP_PORT}/data")
    # threaded=True so the background thread and requests don't block each other.
    app.run(host=config.HTTP_HOST, port=config.HTTP_PORT, threaded=True)


if __name__ == "__main__":
    main()
