# LD-350 Lightning Detector — Integration Plan

**Status:** Planning (install in 3–4 days)

## Hardware Summary

- **Boltek LD-350**: Single-station lightning detector, ~300 mile range
- **Connection**: USB to computer
- **Output**: NMEA-like sentences over USB

## Data Format (from manual)

**Strike sentence:** `$WIMLI,<corrected_dist>,<uncorrected_dist>,<bearing> *<checksum>\r\n`

| Field | Range | Notes |
|-------|-------|-------|
| corrected_dist | 0–300 miles | Use this for display |
| uncorrected_dist | 0–300 miles | Raw |
| bearing | 000.0–359.9° | Degrees from north, clockwise |

**Other sentences:** `$WIMLN` (noise), `$WIMSU` (status, strike rate, alarms)

## Geometry

Single-station: we get **distance + bearing**. To plot on a map:

1. **Detector location** (lat, lon) — e.g. MRW home: 31.919, -81.076
2. **Strike location** = point at distance D miles, bearing B° from detector
3. Use haversine / destination-point formula to compute (lat, lon)

## Architecture Options

### A. Windows + NexStorm (shipped software)

- LD-350 → USB → Windows PC running NexStorm
- NexStorm may export data (check if it has API, file output, or network stream)
- Our backend would consume that export

### B. Custom USB reader (Boltek Programmers Toolkit)

- LD350_DLL.zip from Boltek — Windows DLL with example code
- Custom Windows service reads USB, writes strikes to file/HTTP/WebSocket
- Our backend consumes

### C. Serial bridge (if LD-350 exposes serial)

- Some USB devices appear as serial ports
- Python `pyserial` could read on Linux/Mac if driver exists
- LD-350 drivers are Windows-focused; Mac/Linux support unclear

### D. Middleware on weather hardware

- If LD-350 connects to a Windows machine in the setup:
  - That machine runs a small service that parses $WIMLI
  - Converts to GeoJSON points
  - Serves `/lightning.json` or WebSocket to our players

## Data Flow (proposed)

```
LD-350 (USB) → Reader process (parse $WIMLI)
                    ↓
              Strike (distance, bearing, timestamp)
                    ↓
              Convert to (lat, lon) using detector location
                    ↓
              Append to rolling buffer (e.g. last 30–60 min)
                    ↓
              serve_root/lightning.json or HTTP endpoint
                    ↓
              Players fetch, add as point layer on map
```

## Display

- **Points** on Mapbox (circle or symbol layer)
- **Retention**: last N minutes (e.g. 30–60), then fade or remove
- **Styling**: e.g. yellow/white dots, maybe size by recency
- **Overlay**: on KCLX, KJAX, MRMS players

## Boltek LD350_DLL Toolkit (in review_this/LD350_DLL)

**Windows-only** — DLL uses `__declspec(dllexport)`, requires Windows + USB driver.

### API (from LD350.h)

| Function | Purpose |
|----------|---------|
| `LD350_Open()` | Open USB connection — call first |
| `LD350_MessageReady()` | True if strike/status message waiting |
| `LD350_GetMessageData(msg)` | Get message string (e.g. `$WIMLI,45,45,182.3*7A`) |
| `LD350_KeepAlive()` | **Must call at least once per second** or LD-350 stops sending |
| `LD350_Close()` | Close connection |

### Strike parsing (from dlltestDlg.cpp)

`$WIMLI,<corrected_dist>,<uncorrected_dist>,<bearing>*<checksum>`

- `distance` = corrected distance, miles (0–300)
- `direction` = bearing, degrees (0–359.9)

### Example loop

```cpp
LD350_Open();
while (running) {
  if (LD350_MessageReady()) {
    LD350_MessageDataType msg;
    LD350_GetMessageData(&msg);
    // Parse msg.message for $WIMLI,...
  }
  LD350_KeepAlive();  // at least every 1 sec
  Sleep(100);
}
LD350_Close();
```

**Implication**: Reader must run on **Windows** (machine with LD-350 USB). That machine would parse strikes, convert to lat/lon, and serve JSON/HTTP to our players.

## Open Questions

1. **Which machine** will the LD-350 USB connect to? Must be Windows for DLL. (Pi/weather-core are Mac/Linux — no DLL support.)
2. **Detector location**: Confirm lat/lon (MRW home or install site)
3. **Network**: Can the Windows machine reach wx-i9 or our players? (Serve lightning.json, or push to a shared location)

## Files to Add (when ready)

- `bin/ld350_reader.py` — parse $WIMLI, convert to GeoJSON, write buffer
- `conf/lightning.json` — detector location, retention config
- `serve_root/lightning.json` — rolling strike GeoJSON (or similar)
- Player changes: add lightning point layer

## References

- [Boltek LD-350 Downloads](https://www.boltek.com/downloads/ld-350/)
- [LD-350 User Manual](https://www.boltek.com/LD-350%20User%20Manual%20-%2012172018.pdf)
- [Manualslib — USB Messages](https://www.manualslib.com/manual/1505787/Boltek-Ld-350.html?page=24)
