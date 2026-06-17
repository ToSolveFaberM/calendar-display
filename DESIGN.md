# Outlook Calendar + Google Tasks Display on ESP32 — Design Plan

## Overview

Display upcoming Outlook calendar events and Google Tasks on an ESP32 using a Python
script running on a laptop as a local HTTP data bridge. The ESP32 polls the laptop
over the shared work WiFi network and outputs data to the serial port.

**Target hardware:**
- **Phase 1 (now):** Generic ESP32-S3 dev board — serial output only, no display
- **Phase 2 (later):** ESP32-2432S028R (CYD) — TFT display, touch, full UI

This document covers both phases. Phase 2 display sections are marked accordingly
and can be ignored until the hardware arrives.

---

## Architecture

```
Microsoft Graph API       Google Tasks API
        │                        │
        │ HTTPS (OAuth/MSAL)     │ HTTPS (OAuth2/google-auth)
        └──────────┬─────────────┘
                   ▼
           Laptop (Python)
           ┌──────────────────────────────┐
           │  msal       → Outlook token  │
           │  google-auth → Tasks token   │
           │  requests   → both APIs      │
           │  flask      → HTTP :8080     │
           └──────────────────────────────┘
                   │
                   │ HTTP GET /data  (same LAN)
                   ▼
     ESP32-S3 (Phase 1)              ESP32-2432S028R (Phase 2)
     ┌─────────────────────────┐     ┌─────────────────────────┐
     │  WiFi + HTTPClient      │     │  WiFi + HTTPClient      │
     │  ArduinoJson (parse)    │     │  ArduinoJson (parse)    │
     │  Serial output          │     │  TFT_eSPI (render)      │
     │  Deep sleep             │     │  Deep sleep / backlight │
     └─────────────────────────┘     └─────────────────────────┘
```

**Key design decisions:**
- Auth for both services lives entirely on the laptop — no OAuth complexity on device
- Single endpoint `/data` returns both calendar events and tasks in one payload
- Laptop script runs as a background process; ESP32 polls on wake, then deep sleeps
- No external dependencies beyond the work LAN — no cloud proxy, no Tailscale
- Phase 1 firmware is a strict subset of Phase 2 — same WiFi, HTTP, JSON, and sleep
  logic; only the output layer changes

---

## Component 1: Laptop Python Script

### Responsibilities

1. Authenticate to Microsoft Graph (MSAL, once, then token-cached)
2. Authenticate to Google Tasks API (OAuth2, once, then token-cached)
3. Fetch today's and tomorrow's Outlook calendar events
4. Fetch tasks from specified Google Tasks lists
5. Normalize both into a single flat JSON payload
6. Serve that payload on a local HTTP endpoint (`GET /data`)
7. Refresh both data sources in the background every 5 minutes

### Dependencies

| Package              | Purpose                             |
|----------------------|-------------------------------------|
| `msal`               | Microsoft OAuth2 token cache        |
| `google-auth`        | Google OAuth2 base                  |
| `google-auth-oauthlib` | Google interactive auth flow      |
| `google-api-python-client` | Google Tasks REST client      |
| `requests`           | Microsoft Graph HTTP calls          |
| `flask`              | Local HTTP server                   |

Install: `pip install msal requests flask google-auth google-auth-oauthlib google-api-python-client`

### Microsoft Authentication (Outlook Calendar)

Use **MSAL PublicClientApplication** with the interactive browser flow. On first
run the user logs in via browser. The token (including refresh token) is persisted
to `ms_token_cache.json`. On subsequent runs MSAL silently refreshes from cache.

**Azure app registration required:**
- Platform: Mobile and desktop applications
- Redirect URI: `http://localhost`
- API permissions: `Calendars.Read` (delegated)
- Account type: work/school or personal Microsoft account

### Google Authentication (Tasks)

Use **google-auth-oauthlib** InstalledAppFlow. On first run the user logs in via
browser. Credentials are persisted to `google_token.json`. On subsequent runs the
token is refreshed silently.

**Google Cloud project required:**
- Enable the **Google Tasks API** in the project
- Create OAuth2 credentials (Desktop app type)
- Download `credentials.json` — place next to the script
- Scopes required: `https://www.googleapis.com/auth/tasks.readonly`

**Task list configuration** — specify list names in `config.py`:

```python
TASK_LIST_NAMES = ["My Tasks", "Work"]   # exact names as they appear in Google Tasks
```

The script resolves these names to list IDs on startup via the `tasklists.list`
API call, then fetches tasks from each.

### Microsoft Graph API Call

```
GET https://graph.microsoft.com/v1.0/me/calendarView
    ?startDateTime={today_00:00:00Z}
    &endDateTime={tomorrow_23:59:59Z}
    &$select=subject,start,end,location,isAllDay
    &$orderby=start/dateTime asc
    &$top=20
```

### Google Tasks API Calls

```
GET https://tasks.googleapis.com/tasks/v1/lists/{listId}/tasks
    ?showCompleted=false
    &showHidden=false
    &maxResults=100
```

Repeat for each configured list. Tasks are merged into a single list, de-duplicated
by task ID, and sorted: overdue first, then by due date ascending, then no-date
tasks alphabetically.

### Combined JSON Output Format

The Flask endpoint `GET /data` returns:

```json
{
  "updated": "2025-06-17T09:15:02",
  "events": [
    {
      "title":    "Sprint Planning",
      "start":    "09:00",
      "end":      "10:00",
      "date":     "Today",
      "location": "Room 3B",
      "allDay":   false
    }
  ],
  "tasks": [
    {
      "title":    "Review NanoDaq EXi schematics",
      "due":      "Today",
      "overdue":  false,
      "list":     "Work",
      "notes":    ""
    },
    {
      "title":    "Buy milk",
      "due":      "",
      "overdue":  false,
      "list":     "My Tasks",
      "notes":    ""
    }
  ]
}
```

**Design choices:**
- Event times pre-formatted as `HH:MM` — no time parsing on ESP32
- `date` / `due` fields are `"Today"`, `"Tomorrow"`, `"Mon 16 Jun"` (for further
  out), or `""` (no due date) — all human-readable strings
- `overdue: true` when due date is before today — allows the ESP32 to flag it
- `notes` included but may be empty; truncated to 80 chars on the laptop side
- Maximum 10 events + 20 tasks in the payload to cap JSON size

### Script Structure

```
data_server.py
├── ms_auth.py          — MSAL token cache wrapper (get_ms_token())
├── google_auth.py      — google-auth flow wrapper (get_google_creds())
├── fetch_events.py     — Graph API call → normalized event list
├── fetch_tasks.py      — Tasks API calls → normalized task list
├── server.py           — Flask app
│   ├── GET /           — health check: "OK" + timestamp
│   └── GET /data       — combined JSON payload
└── config.py           — TASK_LIST_NAMES, CLIENT_ID, TENANT_ID, etc.
```

Background thread refreshes both sources every 5 minutes independently; a stale
source does not block the other from serving fresh data.

### Laptop IP Discovery

- **mDNS hostname** (preferred): Flask binds to `0.0.0.0`; ESP32 uses
  `http://LAPTOP-NAME.local:8080/data`. Works on most networks unless mDNS is blocked.
- **Hardcoded IP** (fallback): set in `config.h` on the firmware side.

---

## Component 2: ESP32 Firmware (Arduino)

### Phase 1 — ESP32-S3, Serial Output + Deep Sleep

#### Libraries

| Library       | Purpose                    |
|---------------|----------------------------|
| `WiFi.h`      | WiFi connection            |
| `HTTPClient.h`| HTTP GET to laptop         |
| `ArduinoJson` | Parse JSON response        |
| `esp_sleep.h` | Deep sleep / wake timer    |

#### Deep Sleep Strategy

The ESP32-S3 wakes, does one fetch-print-sleep cycle, then goes back to deep sleep.
No `loop()` logic needed — the wake is effectively a reset.

```
Power on / wake from deep sleep
        │
        ▼
setup()
├── Serial.begin(115200)
├── WiFi.begin(SSID, PASS)
├── wait for connection (timeout: 15s)
│     └── on timeout → Serial.println("WiFi failed") → deep sleep
├── syncNTP()                         // get local time for serial header
├── fetchData()
│   ├── HTTPClient GET http://{SERVER_HOST}:{PORT}/data
│   ├── check HTTP 200
│   └── deserializeJson() into DataPayload struct
│       ├── EventList  events[]
│       └── TaskList   tasks[]
├── printData()
│   ├── printHeader()                 // timestamp + RSSI
│   ├── printEvents()                 // calendar section
│   ├── printTasks()                  // tasks section
│   └── Serial.printf("Next fetch in %d min\n", sleepMinutes)
└── esp_deep_sleep(SLEEP_INTERVAL_US)
        │
        ▼
      [sleeping ~5 min]
        │
        ▼
      wake → repeat
```

#### Serial Output Format

```
=== 2025-06-17 09:15:02  RSSI: -58 dBm ===

--- CALENDAR ---
TODAY
  09:00 - 10:00  Sprint Planning              [Room 3B]
  12:30 - 13:30  Lunch with Arjan
  [ALL DAY]      Company Holiday

TOMORROW
  09:30 - 10:00  Daily Standup

--- TASKS ---
  [OVERDUE]  Send invoice to client ABC       (Work)
  [Today]    Review NanoDaq EXi schematics    (Work)
  [Today]    Call dentist                     (My Tasks)
  [Wed 18]   Prepare sprint retrospective     (Work)
  [ ]        Buy milk                         (My Tasks)
  [ ]        Read article on LoRaWAN ADR      (Work)

Next fetch in 5 min.
```

#### Sleep Interval

```cpp
#define SLEEP_MINUTES       5
#define SLEEP_INTERVAL_US   (SLEEP_MINUTES * 60ULL * 1000000ULL)
```

Outside work hours (before 07:00 or after 19:00), extend sleep to 30 minutes to
avoid pointless wakes. The laptop server can also be queried for a `"nextEvent"`
hint in the future to allow adaptive sleep duration.

#### Timezone Handling

The laptop script sends pre-formatted local time strings (`HH:MM`), so the ESP32
does not need to handle timezones at all. However, to print an accurate local
timestamp in the serial header, the ESP32 should sync time via NTP on each wake:

```cpp
configTzTime("CET-1CEST,M3.5.0,M10.5.0/3", "pool.ntp.org");
// Wait for sync (max 5s), then use struct tm for formatted output
```

Set the POSIX timezone string for your location. The example above is
Central European Time with automatic DST (CET/CEST). This is resolved once per wake
cycle — no persistent RTC needed.

#### Error Handling (Phase 1)

| Condition             | Behaviour                                              |
|-----------------------|--------------------------------------------------------|
| WiFi timeout          | Print error, deep sleep for normal interval            |
| Server not reachable  | Print "Server offline", deep sleep                     |
| HTTP non-200          | Print status code, deep sleep                          |
| JSON parse error      | Print "Parse error", deep sleep                        |
| No events             | Print "No events in window", deep sleep                |

In all error cases: sleep and retry on next wake. No retry loops on the device —
keeps the firmware simple and power consumption predictable.

#### config.h

```cpp
// WiFi
#define WIFI_SSID        "YourNetwork"
#define WIFI_PASS        "YourPassword"
#define WIFI_TIMEOUT_MS  15000

// Server
#define SERVER_HOST      "laptop-name.local"   // or hardcoded IP
#define SERVER_PORT      8080
#define SERVER_PATH      "/data"               // combined events + tasks endpoint

// Sleep
#define SLEEP_MINUTES          5
#define SLEEP_MINUTES_OFFHOURS 30
#define WORK_HOUR_START        7
#define WORK_HOUR_END         19

// Timezone (POSIX string)
#define TIMEZONE   "CET-1CEST,M3.5.0,M10.5.0/3"
#define NTP_SERVER "pool.ntp.org"
```

---

### Phase 2 — ESP32-2432S028R (CYD), TFT Display *(future)*

> Implement after the CYD hardware arrives. The WiFi, HTTP, JSON, sleep, and
> timezone logic from Phase 1 carries over unchanged. Only the output layer is
> replaced.

#### Additional Libraries

| Library               | Purpose                        |
|-----------------------|--------------------------------|
| `TFT_eSPI`            | ILI9341 display driver         |
| `XPT2046_Touchscreen` | Resistive touch                |

#### TFT_eSPI Configuration (`User_Setup.h`)

```cpp
#define ILI9341_DRIVER
#define TFT_MISO 12
#define TFT_MOSI 13
#define TFT_SCLK 14
#define TFT_CS   15
#define TFT_DC    2
#define TFT_RST  -1   // tied to EN
#define TFT_BL   21   // backlight PWM
#define TOUCH_CS  33
#define SPI_FREQUENCY       55000000
#define SPI_TOUCH_FREQUENCY  2500000
```

#### Display Layout (320×240, landscape)

```
┌────────────────────────────────────────┐  y=0
│  Tuesday 17 June          08:32 ●WiFi  │  header (30px)
├────────────────────────────────────────┤  y=30
│  TODAY                                 │  section label (20px)
├────────────────────────────────────────┤
│  09:00–10:00  Sprint Planning          │  event row (38px)
│               Room 3B                  │
├────────────────────────────────────────┤
│  12:30–13:30  Lunch with Arjan         │
├────────────────────────────────────────┤
│  TOMORROW                              │  section label
├────────────────────────────────────────┤
│  09:30–10:00  Standup                  │
├────────────────────────────────────────┤  y=220
│  Next refresh in 4:32                  │  footer (20px)
└────────────────────────────────────────┘  y=240
```

#### Color Scheme

| Element       | Color (RGB565)        |
|---------------|-----------------------|
| Background    | `TFT_BLACK`           |
| Header bar    | `0x1082` (dark blue)  |
| Header text   | `TFT_WHITE`           |
| Section label | `TFT_DARKGREY`        |
| Event time    | `0x07FF` (cyan)       |
| Event title   | `TFT_WHITE`           |
| Event location| `TFT_LIGHTGREY`       |
| Footer        | `TFT_DARKGREY`        |
| WiFi OK dot   | `TFT_GREEN`           |
| WiFi fail dot | `TFT_RED`             |

#### Backlight / Power (Phase 2)

Deep sleep on the CYD also requires turning off the backlight before sleeping to
avoid it staying lit:

```cpp
ledcWrite(0, 0);           // backlight off
esp_deep_sleep(SLEEP_INTERVAL_US);
```

On wake, turn backlight on before drawing:

```cpp
ledcSetup(0, 5000, 8);
ledcAttachPin(TFT_BL, 0);
ledcWrite(0, 255);
```

Touch any area to restore brightness and reset dimming timer (if polling mode is
used instead of deep sleep in Phase 2).

---

## Component 3: Data Contract

The JSON schema between laptop and ESP32 is the critical interface. Both sides must
agree on field names and formats.

```json
{
  "updated": "string  — ISO datetime, for serial header / display",
  "events": [
    {
      "title":    "string  — max 24 chars for display; full string in serial",
      "start":    "string  — HH:MM 24h, or '' for all-day",
      "end":      "string  — HH:MM 24h, or '' for all-day",
      "date":     "string  — 'Today' or 'Tomorrow'",
      "location": "string  — may be empty",
      "allDay":   "bool"
    }
  ],
  "tasks": [
    {
      "title":    "string  — task title",
      "due":      "string  — 'Today', 'Tomorrow', 'Mon 16 Jun', or '' (no due date)",
      "overdue":  "bool    — true if due date is before today",
      "list":     "string  — source list name",
      "notes":    "string  — truncated to 80 chars, may be empty"
    }
  ]
}
```

**Sorting on the laptop side (before sending):**
- Events: by start datetime ascending
- Tasks: overdue first, then by due date ascending, then no-date tasks last
  (alphabetically within each group)

---

## Build & Run Sequence

### Phase 1 — ESP32-S3 + Serial

**One-time setup:**

1. **Azure app registration** (Outlook Calendar)
   - Go to portal.azure.com → App registrations → New registration
   - Platform: Mobile/desktop, redirect URI: `http://localhost`
   - Add permission: Microsoft Graph → Delegated → `Calendars.Read`
   - Grant admin consent (or user consent on first login)
   - Copy the **Application (client) ID**

2. **Google Cloud project** (Google Tasks)
   - Go to console.cloud.google.com → New project
   - Enable the **Google Tasks API**
   - Create OAuth2 credentials → Desktop app → download `credentials.json`
   - Place `credentials.json` next to `data_server.py`

3. **Laptop script**
   ```bash
   pip install msal requests flask google-auth google-auth-oauthlib google-api-python-client
   # Edit config.py: set CLIENT_ID, TENANT_ID, TASK_LIST_NAMES
   python data_server.py
   # Two browser windows open on first run: Microsoft login, then Google login
   # Tokens cached to ms_token_cache.json and google_token.json
   ```

4. **ESP32-S3 firmware**
   - Edit `config.h`: set `WIFI_SSID`, `WIFI_PASS`, `SERVER_HOST`, `TIMEZONE`
   - Flash via Arduino IDE (board: ESP32S3 Dev Module)
   - Open Serial Monitor at 115200 baud
   - Verify: WiFi connects → HTTP fetch → events + tasks printed → device sleeps

**Daily use:**
- Start `data_server.py` when arriving at work
- ESP32-S3 wakes every 5 min, prints to serial, sleeps again
- Serial monitor optional — mainly for debugging at this stage

### Phase 2 — CYD (when hardware arrives)

1. Copy Phase 1 firmware, add TFT/touch libraries
2. Add `User_Setup.h` for CYD pin config
3. Replace `printData()` with `renderDisplay()` — events above, tasks below
4. All other logic (WiFi, HTTP, JSON, sleep, timezone) unchanged

---

## File Structure

```
calendar-display/
├── laptop/
│   ├── data_server.py            — Flask app, background refresh thread
│   ├── ms_auth.py                — MSAL token cache wrapper
│   ├── google_auth.py            — google-auth flow wrapper
│   ├── fetch_events.py           — Graph API → normalized event list
│   ├── fetch_tasks.py            — Tasks API → normalized task list
│   ├── config.py                 — CLIENT_ID, TENANT_ID, TASK_LIST_NAMES
│   ├── requirements.txt          — all pip dependencies
│   ├── credentials.json          — Google OAuth client secret (do not commit)
│   ├── ms_token_cache.json       — auto-generated (do not commit)
│   └── google_token.json         — auto-generated (do not commit)
└── firmware/
    ├── phase1_serial/
    │   ├── calendar_serial.ino   — main sketch (WiFi, HTTP, JSON, sleep, serial)
    │   └── config.h              — WiFi, server, sleep, timezone constants
    └── phase2_display/           — (future, after CYD arrives)
        ├── calendar_display.ino  — main sketch
        ├── display.h/cpp         — TFT rendering (events + tasks sections)
        ├── data.h/cpp            — shared fetch + parse (copied from phase1)
        └── config.h              — extended with display constants
```

Add `credentials.json`, `ms_token_cache.json`, and `google_token.json` to
`.gitignore` if using version control.

---

## Open Questions / Future Improvements

- **mDNS reliability**: if `laptop-name.local` lookup fails on the work network,
  fall back to hardcoded IP with a compile-time flag in `config.h`
- **Adaptive sleep**: laptop server could return a `"minutesToNext"` hint so the
  ESP32 sleeps exactly until the next event rather than a fixed 5-minute interval
- **Work hours gating**: extend sleep outside 07:00–19:00 (already in config);
  consider skipping WiFi entirely and sleeping until 07:00 if woken at night
- **Multi-day events**: Graph returns these as spanning events; currently shown as
  all-day — may need de-duplication if they appear on both Today and Tomorrow
- **Timezone DST edge cases**: verify POSIX string handles DST transitions correctly;
  test around March/October clock changes
- **Completed task handling**: Google Tasks API `showCompleted=false` excludes them,
  but tasks completed after the last refresh will still appear until next refresh
- **Task subtasks**: Google Tasks supports subtasks; currently fetched as top-level
  items — consider indenting or filtering them
- **Phase 2 — display layout for tasks**: tasks section below events on 320×240;
  may need scrolling if combined count exceeds ~5 visible rows
- **Phase 2 — touch interaction**: tap event/task to show full text if truncated
- **Phase 2 — OTA updates**: add ArduinoOTA once on CYD for wireless firmware updates
- **Phase 2 — burn-in protection**: deep sleep between refreshes handles this
  naturally; no screensaver logic needed
