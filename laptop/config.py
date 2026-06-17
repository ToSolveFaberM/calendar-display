"""
Configuration for the calendar + tasks data server.

Edit the values below before first run. The two token cache files and
credentials.json should NOT be committed to version control.
"""

# ---------------------------------------------------------------------------
# Microsoft / Outlook Calendar (MSAL)
# ---------------------------------------------------------------------------

# Application (client) ID from your Azure app registration.
MS_CLIENT_ID = "41bc440d-5a77-4618-abce-25b47d8bf16f"

# Tenant: "common" works for most accounts.
#   "common"      -> work/school AND personal Microsoft accounts
#   "consumers"   -> personal Microsoft accounts only
#   "organizations" or a tenant GUID -> work/school only
MS_AUTHORITY = "https://login.microsoftonline.com/cb6a9163-a40a-49a8-8dc8-e2d204654bfd"

# Delegated scope. Calendars.Read is enough to read events.
MS_SCOPES = ["Calendars.Read"]

# Where MSAL persists its token cache (auto-created).
MS_TOKEN_CACHE = "ms_token_cache.json"


# ---------------------------------------------------------------------------
# Google Tasks
# ---------------------------------------------------------------------------

# OAuth client secret downloaded from Google Cloud Console (Desktop app type).
GOOGLE_CREDENTIALS_FILE = "credentials.json"

# Where the Google token is persisted after first login (auto-created).
GOOGLE_TOKEN_FILE = "google_token.json"

# Read-only access to Google Tasks.
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/tasks.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

# Name of the Google Calendar to fetch events from (case-insensitive).
GOOGLE_CALENDAR_NAME = "Calendar"

# Exact names of the task lists you want, as they appear in Google Tasks.
# Names are case-insensitive matched. Empty list => all lists.
TASK_LIST_NAMES = ["My Tasks", "Work"]

# Include tasks that have no due date (you chose: yes, show all).
INCLUDE_TASKS_WITHOUT_DUE = True


# ---------------------------------------------------------------------------
# Server / general
# ---------------------------------------------------------------------------

# Flask bind host/port. 0.0.0.0 makes it reachable from the ESP32 on the LAN.
HTTP_HOST = "0.0.0.0"
HTTP_PORT = 5000

# Background refresh interval in seconds.
REFRESH_INTERVAL_SECONDS = 300  # 5 minutes

# Payload size caps (keeps the ESP32 JSON buffer small and predictable).
MAX_EVENTS = 10
MAX_TASKS = 20

# Truncate task notes to this many characters before sending.
MAX_NOTES_CHARS = 80

# Your local timezone. Used to convert UTC times from the APIs to local
# "Today"/"Tomorrow" labels and HH:MM strings.
# Uses the IANA name; Python's zoneinfo resolves DST automatically.
LOCAL_TIMEZONE = "America/Sao_Paulo"
