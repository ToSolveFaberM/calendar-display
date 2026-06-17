# Outlook Calendar + Google Tasks on ESP32 — Phase 1

Shows your Outlook calendar (today + tomorrow) and Google Tasks on an ESP32,
output to the serial port. A Python script on your laptop handles all the
OAuth and serves a simple JSON feed on the local network; the ESP32 wakes
every few minutes, fetches it, prints it, and deep-sleeps.

```
Outlook (Graph)  Google Tasks
        \           /
      laptop/data_server.py  --HTTP-->  ESP32-S3 (serial out)
```

## Layout

```
laptop/                       Python data bridge (auth + fetch + serve)
firmware/phase1_serial_pio/   PlatformIO project (ESP32-S3, serial + deep sleep)
  platformio.ini              board, framework, ArduinoJson dependency
  include/config.h            WiFi, server, sleep, timezone, debug settings
  src/main.cpp                fetch + parse + serial print + deep sleep
```

## 1. Laptop setup

### Microsoft (Outlook Calendar)
1. portal.azure.com → App registrations → New registration
2. Platform: Mobile and desktop applications, redirect URI `http://localhost`
3. API permissions → Microsoft Graph → Delegated → `Calendars.Read`
4. Copy the Application (client) ID into `laptop/config.py` (`MS_CLIENT_ID`)

### Google (Tasks)
1. console.cloud.google.com → new project
2. Enable the **Google Tasks API**
3. Create OAuth credentials → **Desktop app** → download as
   `laptop/credentials.json`
4. Set your list names in `laptop/config.py` (`TASK_LIST_NAMES`)

### Run
```bash
cd laptop
pip install -r requirements.txt
# edit config.py: MS_CLIENT_ID, TASK_LIST_NAMES, LOCAL_TIMEZONE
python data_server.py
```
First run opens two browser windows (Microsoft, then Google). After that,
tokens are cached (`ms_token_cache.json`, `google_token.json`) and refresh
silently.

Test it from any machine on the network:
```
http://<laptop>:8080/data
```

## 2. ESP32-S3 setup (PlatformIO)

1. Open `firmware/phase1_serial_pio/` in VS Code with the PlatformIO extension
   (or use the `pio` CLI).
2. Edit `include/config.h`:
   - `WIFI_SSID`, `WIFI_PASS`
   - `SERVER_HOST` — your laptop's mDNS name (`name.local`) or its IP
   - `POSIX_TZ` is preset for Brazil (UTC-3, no DST)
3. Build and upload:
   ```bash
   cd firmware/phase1_serial_pio
   pio run --target upload
   pio device monitor          # 115200 baud, set in platformio.ini
   ```
   ArduinoJson is declared in `platformio.ini` and fetched automatically.

The board is set to `esp32-s3-devkitc-1`. If yours enumerates differently,
adjust `board` in `platformio.ini` (e.g. `esp32-s3-devkitm-1`).

You should see something like:

```
=== 2025-06-17 09:15:02  RSSI: -58 dBm ===

--- CALENDAR ---
Today
  09:00 - 10:00  Sprint Planning             [Room 3B]
  [ALL DAY]      Company Holiday
Tomorrow
  09:30 - 10:00  Daily Standup

--- TASKS ---
  [OVERDUE]     Send invoice to client ABC      (Work)
  [Today]       Review NanoDaq EXi schematics   (Work)
  [Wed 18 Jun]  Prepare sprint retrospective    (Work)
  [ ]           Buy milk                        (My Tasks)

Next fetch in 5 min. Sleeping...
```

### Debug mode (keep serial alive)

The ESP32-S3 USB-CDC port drops during deep sleep, so the monitor reconnects
each wake. While iterating, build with deep sleep disabled — the device stays
awake and re-fetches every `DEBUG_DELAY_SECONDS`:

```ini
; in platformio.ini
build_flags = -I include -D DEBUG_NO_SLEEP
```

Remove the flag for normal low-power operation.

## Notes

- The device deep-sleeps between fetches (5 min in work hours, 30 min outside
  07:00–19:00). Because the USB-CDC serial port drops during deep sleep, your
  serial monitor may need to reconnect on each wake — normal for this board.
- All date/time logic lives on the laptop. The ESP32 only displays pre-formatted
  strings, so timezone/DST changes are handled in one place (`config.py`
  `LOCAL_TIMEZONE`).
- Endpoints: `/data` (both), `/calendar`, `/tasks`, `/` (health check).

## Phase 2 (later)

When the ESP32-2432S028R (CYD) display arrives, the WiFi/HTTP/JSON/sleep logic
carries over unchanged — only `printEvents()` / `printTasks()` get swapped for
TFT rendering, and the PlatformIO `board` / `lib_deps` get the display libs
added. See the design plan document for the display layout.
