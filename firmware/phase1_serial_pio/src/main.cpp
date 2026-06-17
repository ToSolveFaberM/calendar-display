// main.cpp
// Phase 1: ESP32-S3 calendar + tasks client, serial output only.
//
// On each wake: connect WiFi, sync time via NTP, GET /data from the laptop,
// parse the JSON, print events and tasks to serial, then deep sleep until the
// next refresh. The wake is effectively a reset, so all logic lives in setup().
//
// PlatformIO project — see platformio.ini for board and dependencies.

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include "esp_sleep.h"

#include "config.h"

// --------------------------------------------------------------------------
// Small helpers
// --------------------------------------------------------------------------

// Pad/clip a String into a fixed-width column for tidy serial alignment.
static String col(const String &s, size_t width) {
  String out = s;
  if (out.length() > width) {
    out = out.substring(0, width);
  }
  while (out.length() < width) {
    out += ' ';
  }
  return out;
}

// Returns true if the given local hour is within working hours.
static bool isWorkHours(int hour) {
  return hour >= WORK_HOUR_START && hour < WORK_HOUR_END;
}

// --------------------------------------------------------------------------
// WiFi
// --------------------------------------------------------------------------

static bool connectWiFi() {
  Serial.printf("Connecting to %s ", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start > WIFI_TIMEOUT_MS) {
      Serial.println(" timeout!");
      return false;
    }
    delay(300);
    Serial.print('.');
  }
  Serial.printf(" connected, IP %s, RSSI %d dBm\n",
                WiFi.localIP().toString().c_str(), WiFi.RSSI());
  return true;
}

// --------------------------------------------------------------------------
// Time (NTP)
// --------------------------------------------------------------------------

// Syncs system time and fills `outNow`. Returns false on timeout.
static bool syncTime(struct tm &outNow) {
  configTzTime(POSIX_TZ, NTP_SERVER1, NTP_SERVER2);
  Serial.print("Syncing time");

  unsigned long start = millis();
  while (millis() - start < NTP_SYNC_TIMEOUT_MS) {
    if (getLocalTime(&outNow, 200)) {
      Serial.println(" ok");
      return true;
    }
    Serial.print('.');
  }
  Serial.println(" timeout (proceeding without accurate clock)");
  return false;
}

// --------------------------------------------------------------------------
// HTTP fetch
// --------------------------------------------------------------------------

// Fetches the /data payload into `payload`. Returns HTTP status, or a
// negative value on transport error.
static int fetchData(String &payload) {
  HTTPClient http;
  String url = String("http://") + SERVER_HOST + ":" + String(SERVER_PORT) + SERVER_PATH;
  Serial.printf("GET %s\n", url.c_str());

  if (!http.begin(url)) {
    Serial.println("http.begin() failed");
    return -1;
  }
  http.setTimeout(10000);
  int code = http.GET();
  if (code == HTTP_CODE_OK) {
    payload = http.getString();
  }
  http.end();
  return code;
}

// --------------------------------------------------------------------------
// Printing
// --------------------------------------------------------------------------

static void printHeader(const struct tm &now, bool timeValid) {
  char ts[32];
  if (timeValid) {
    strftime(ts, sizeof(ts), "%Y-%m-%d %H:%M:%S", &now);
  } else {
    strncpy(ts, "time-unsynced", sizeof(ts));
  }
  Serial.println();
  Serial.printf("=== %s  RSSI: %d dBm ===\n", ts, WiFi.RSSI());
}

static void printEvents(JsonArrayConst events) {
  Serial.println();
  Serial.println("--- CALENDAR ---");
  if (events.size() == 0) {
    Serial.println("  (no events in window)");
    return;
  }

  String currentSection = "";
  for (JsonObjectConst ev : events) {
    String date = ev["date"] | "";
    if (date != currentSection) {
      currentSection = date;
      Serial.println(date.length() ? date : String("(undated)"));
    }

    bool allDay = ev["allDay"] | false;
    String title = ev["title"] | "(no title)";
    String loc = ev["location"] | "";

    String timeCol;
    if (allDay) {
      timeCol = "[ALL DAY]    ";
    } else {
      String start = ev["start"] | "";
      String end = ev["end"] | "";
      timeCol = start + " - " + end;
    }

    Serial.print("  ");
    Serial.print(col(timeCol, 15));
    Serial.print(col(title, 28));
    if (loc.length()) {
      Serial.print("[");
      Serial.print(loc);
      Serial.print("]");
    }
    Serial.println();
  }
}

static void printTasks(JsonArrayConst tasks) {
  Serial.println();
  Serial.println("--- TASKS ---");
  if (tasks.size() == 0) {
    Serial.println("  (no tasks)");
    return;
  }

  for (JsonObjectConst t : tasks) {
    bool overdue = t["overdue"] | false;
    String due = t["due"] | "";
    String title = t["title"] | "(untitled)";
    String list = t["list"] | "";

    String tag;
    if (overdue) {
      tag = "[OVERDUE]";
    } else if (due.length()) {
      tag = "[" + due + "]";
    } else {
      tag = "[ ]";
    }

    Serial.print("  ");
    Serial.print(col(tag, 14));  // wide enough for "[OVERDUE]" and "[Wed 18 Jun]"
    Serial.print(col(title, 32));
    if (list.length()) {
      Serial.print("(");
      Serial.print(list);
      Serial.print(")");
    }
    Serial.println();
  }
}

// --------------------------------------------------------------------------
// Deep sleep
// --------------------------------------------------------------------------

static void goToSleep(int sleepMinutes) {
#ifdef DEBUG_NO_SLEEP
  (void)sleepMinutes;  // unused in debug mode
  Serial.printf("\n[DEBUG] staying awake, re-fetch in %d s...\n", DEBUG_DELAY_SECONDS);
  Serial.flush();
  delay((unsigned long)DEBUG_DELAY_SECONDS * 1000UL);
  // Returns to caller; in debug mode the work runs from loop() instead.
#else
  Serial.printf("\nNext fetch in %d min. Sleeping...\n", sleepMinutes);
  Serial.flush();
  uint64_t us = (uint64_t)sleepMinutes * 60ULL * 1000000ULL;
  esp_sleep_enable_timer_wakeup(us);
  esp_deep_sleep_start();  // does not return
#endif
}

// --------------------------------------------------------------------------
// Main
// --------------------------------------------------------------------------

// One full work cycle: connect, sync time, fetch, parse, print, then sleep
// (or, in DEBUG_NO_SLEEP mode, delay and return so loop() can run it again).
static void runCycle() {
  // 1. WiFi
  if (!connectWiFi()) {
    goToSleep(SLEEP_MINUTES);
    return;
  }

  // 2. Time (used for the serial header and the work-hours sleep decision)
  struct tm now;
  bool timeValid = syncTime(now);

  // 3. Fetch
  String payload;
  int code = fetchData(payload);
  if (code != HTTP_CODE_OK) {
    if (code < 0) {
      Serial.println("Server unreachable.");
    } else {
      Serial.printf("HTTP error %d\n", code);
    }
    WiFi.disconnect(true);
    goToSleep(SLEEP_MINUTES);
    return;
  }

  // 4. Parse
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, payload);
  if (err) {
    Serial.printf("JSON parse error: %s\n", err.c_str());
    WiFi.disconnect(true);
    goToSleep(SLEEP_MINUTES);
    return;
  }

  // 5. Print
  printHeader(now, timeValid);
  const char *updated = doc["updated"] | "";
  if (strlen(updated)) {
    Serial.printf("(server data updated: %s)\n", updated);
  }
  printEvents(doc["events"].as<JsonArrayConst>());
  printTasks(doc["tasks"].as<JsonArrayConst>());

  // 6. Decide sleep duration based on local time, then sleep.
  WiFi.disconnect(true);
  int sleepMinutes = SLEEP_MINUTES;
  if (timeValid && !isWorkHours(now.tm_hour)) {
    sleepMinutes = SLEEP_MINUTES_OFFHOURS;
  }
  goToSleep(sleepMinutes);
}

void setup() {
  Serial.begin(115200);
  delay(200);  // let USB CDC settle after wake

  runCycle();
  // In normal mode runCycle() ends in deep sleep and never returns here.
  // In DEBUG_NO_SLEEP mode it returns, and loop() drives subsequent cycles.
}

void loop() {
#ifdef DEBUG_NO_SLEEP
  runCycle();  // re-fetch on each pass; goToSleep() inserts the delay
#else
  // Never reached: runCycle() always ends in deep sleep.
#endif
}
