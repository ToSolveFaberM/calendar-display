// config.h - user configuration for the calendar + tasks serial client.
// Edit these values for your network and laptop, then flash.

#pragma once

// ---- WiFi ----
#define WIFI_SSID        "YourNetwork"
#define WIFI_PASS        "YourPassword"
#define WIFI_TIMEOUT_MS  15000UL

// ---- Data server (your laptop) ----
// Prefer the mDNS hostname so it survives DHCP changes. If .local lookups
// fail on your network, set SERVER_HOST to a hardcoded IP like "192.168.1.42".
#define SERVER_HOST      "laptop-name.local"
#define SERVER_PORT      8080
#define SERVER_PATH      "/data"

// ---- Sleep schedule ----
#define SLEEP_MINUTES           5     // normal refresh interval
#define SLEEP_MINUTES_OFFHOURS  30    // outside work hours
#define WORK_HOUR_START         7     // local hour work day begins (inclusive)
#define WORK_HOUR_END           19    // local hour work day ends (exclusive)

// ---- Time / NTP ----
// POSIX TZ string. Brazil (Espirito Santo) is UTC-3 with no DST since 2019.
// Format "<-03>3" means: zone name "-03", offset 3 hours west of UTC.
#define POSIX_TZ    "<-03>3"
#define NTP_SERVER1 "pool.ntp.org"
#define NTP_SERVER2 "time.nist.gov"
#define NTP_SYNC_TIMEOUT_MS 8000UL

// ---- Debug ----
// When DEBUG_NO_SLEEP is defined (e.g. via build_flags -D DEBUG_NO_SLEEP),
// the device stays awake and re-fetches with a plain delay instead of deep
// sleeping. This keeps the USB-CDC serial port connected while iterating.
// Leave it undefined for normal low-power operation.
// #define DEBUG_NO_SLEEP
#define DEBUG_DELAY_SECONDS 30
