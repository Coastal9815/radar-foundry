# pi-wx Weather Data Inventory

**Full inventory of weather-related data, scripts, and services on pi-wx (192.168.2.174).**  
Generated from live exploration.

---

## 1. Architecture Overview

| Component | Role |
|-----------|------|
| **WeeWX** | Live sensor ingest, SQLite archive (`/var/lib/weewx/weewx.sdb`), Belchertown/WDC web UI |
| **Davis WLL** | Weather Link Live at 192.168.1.122 — primary sensor API |
| **Dashboard** | Custom `gen_*.sh` scripts in `/home/scott/dashboard/bin/` — produce JSON for MRW |
| **HTTP** | Nginx serves `/data/*` → symlinked to `/home/scott/dashboard/data/` |
| **AirLink (WeeWX)** | Davis AirLink at `192.168.1.167`; `user.airlink` injects PM into loop/archive. Timeout / poll tuning and `airlink.py` patch: **`docs/pi-wx/AIRLINK_WEEWX_PATCH.md`**, patch file **`patches/pi-wx/weewx-airlink-poll-interval.patch`**. |

**Data flow:** WLL → gen_now.sh → now.json → gen_wind.sh, gen_extremes.sh, gen_computed_rt.sh → wind.json, extremes.json, computed_rt.json. Extremes also sync from WeeWX archive via `sync_weewx_wind_gust_extremes.py`.

---

## 2. Data Files (`/home/scott/dashboard/data/`)

| File | Source | Description |
|------|--------|-------------|
| **now.json** | gen_now.sh ← WLL API | Current conditions: temp, humidity, dewpoint, wind, pressure, rain rate, solar, UV |
| **wind.json** | gen_wind.sh ← now.json + wind_hist.jsonl | speed_mph, gust_mph, dir_deg, **gust_dir_deg**, avg_2m_mph, avg_10m_mph, **avg_10m_dir_deg**, max_gust_10m_mph, **max_gust_10m_dir_deg** |
| **extremes.json** | gen_extremes.sh ← truth_layer_state + sync_weewx | Day/month/ytd hi/lo for temp, pressure, wind, rain rate, UV, solar, heat index, THSW, wind chill, apparent temp. **wind_gust_mph.day.hi_dir_deg** etc. |
| **extremes_alltime.json** | gen_extremes_alltime.sh ← WeeWX archive | All-time records from weewx.sdb |
| **computed_rt.json** | gen_computed_rt.sh ← now + wind | Heat index, THSW, wind chill, apparent temp |
| **rain.json** | gen_rain.sh | today_in, storm_in, rate_inhr, month_in, year_in, etc. |
| **rain_norms.json** | gen_climatology.sh | Monthly/yearly norms for rain accumulation |
| **climatology.json** | gen_climatology.sh | Climatology for rain-accumulation module |
| **air.json** | gen_air.sh ← AirLink 192.168.1.167 | PM2.5, PM10, nowcast |
| **astro.json** | gen_astro.sh | Sunrise/sunset, moon phase (root-owned) |
| **tide.json** | gen_tide.sh | Tide events (root-owned) |
| **status.json** | gen_status.sh | System status |
| **status_rt.json** | gen_status_rt.sh | Real-time status |
| **forecast72.json** | gen_nws_forecast72.sh | NWS forecast |
| **forecast72_hourly.json** | gen_nws_forecast_hourly72.sh | Hourly forecast |
| **nws_points.json** | gen_nws_points.sh | NWS grid points |
| **alerts.json** | gen_nws_alerts.sh | NWS alerts |
| **threat_strip.json** | gen_threat_strip.sh | Threat strip |
| **threat_windows.json** | gen_threat_windows.sh | Threat windows |
| **history_daily.json** | mrw-gen-history-daily | Daily history |
| **history_monthly.json** | mrw-gen-history-monthly | Monthly history |
| **lightning_rt.json** | gen_lightning_fake.sh | Lightning (placeholder) |

---

## 3. Wind & Extremes — Field Mapping

### wind.json (from gen_wind.sh)

```json
{
  "wind": {
    "speed_mph": 18,
    "gust_mph": 26,
    "dir_deg": 321,
    "gust_dir_deg": 321,
    "avg_2m_mph": 17.29,
    "avg_10m_mph": 17.47,
    "avg_10m_dir_deg": 312,
    "max_gust_10m_mph": 26,
    "max_gust_10m_dir_deg": 315
  }
}
```

- **AVG 10 direction:** `avg_10m_dir_deg` ✓ (circular mean over last 10 min)
- **GUST direction:** `gust_dir_deg` ✓ (dir when current gust recorded; same packet as gust)
- **MAX 10 direction:** `max_gust_10m_dir_deg` ✓ (dir when max gust in 10m window occurred)
- **MAX DAY:** From extremes.json (see below)

### extremes.json (from gen_extremes.sh + sync_weewx_wind_gust_extremes.py)

```json
{
  "extremes": {
    "wind_gust_mph": {
      "day": { "hi": 31, "hi_ts": "...", "hi_dir_deg": 295 },
      "month": { "hi": 29, "hi_dir_deg": 257 },
      "ytd": { "hi": 52, "hi_dir_deg": 323 }
    }
  }
}
```

- **MAX DAY direction:** `wind_gust_mph.day.hi_dir_deg` ✓ (from WeeWX archive via sync script)

---

## 4. Standalone vs WeeWX

| Data | Standalone (dashboard scripts) | WeeWX |
|------|--------------------------------|-------|
| **now.json** | ✓ WLL API directly | — |
| **wind.json** | ✓ gen_wind from now + rolling history | — |
| **extremes (day/month/ytd)** | ✓ truth_layer_state (gen_extremes) | sync_weewx enriches wind_gust hi_dir_deg from archive |
| **extremes_alltime** | — | ✓ gen_extremes_alltime reads weewx.sdb |
| **rain** | ✓ gen_rain (WeeWX mrw_rain_today_series + archive) | Mixed |
| **astro** | ✓ gen_astro (ephemeris) | — |
| **tide** | ✓ gen_tide | — |
| **air** | ✓ gen_air (AirLink) | — |

**Summary:** Most MRW JSON is produced by **standalone dashboard scripts**. WeeWX provides:
1. Live sensor data (WeeWX reads WLL; gen_now reads WLL directly — parallel paths)
2. SQLite archive for extremes_alltime and wind_gust hi_dir_deg sync
3. Belchertown/WDC web UI and plots

---

## 5. systemd Timers (Scheduling)

| Timer | Interval | Script |
|-------|----------|--------|
| mrw-gen-now | ~15s | gen_now.sh |
| mrw-gen-wind | ~15s | gen_wind.sh |
| mrw-gen-extremes | ~15s | gen_extremes.sh |
| mrw-gen-computed-rt | ~15s | gen_computed_rt.sh |
| mrw-gen-rain | ~15s | gen_rain.sh |
| mrw-gen-status | ~15s | gen_status.sh |
| mrw-gen-status-rt | ~15s | gen_status_rt.sh |
| mrw-gen-air | ~15s | gen_air.sh |
| mrw-gen-climatology | ~15s | gen_climatology.sh |
| mrw-gen-tide | 10 min | gen_tide.sh |
| mrw-gen-astro | 10 min | gen_astro.sh |
| mrw-gen-extremes-alltime | Daily 03:15 | gen_extremes_alltime.sh |
| mrw-nws-* | Various | NWS forecast/alerts/points |
| mrw-threat-strip | ~15s | gen_threat_strip.sh |
| mrw-rain-snap | 1 min | Rain snapshot |
| mrw-gen-history-daily | 1 min | history_daily |
| mrw-gen-history-monthly | 5 min | history_monthly |

---

## 6. Key Scripts

| Script | Purpose |
|--------|---------|
| **gen_now.sh** | Fetch WLL `/v1/current_conditions`, emit now.json |
| **gen_wind.sh** | Append to wind_hist.jsonl from now, compute avg_2m, avg_10m, avg_10m_dir (circular mean), max_gust_10m |
| **gen_extremes.sh** | Maintain extremes_state.json (truth layer), call sync_weewx_wind_gust_extremes.py, merge extremes_alltime, emit extremes.json |
| **sync_weewx_wind_gust_extremes.py** | Query weewx.sdb for max gust + windGustDir per day/month/ytd, write hi_dir_deg into state |
| **gen_extremes_alltime.sh** | Query weewx.sdb for all-time records, emit extremes_alltime.json |
| **gen_rain.sh** | Rain from WeeWX mrw_rain_today_series + archive |
| **gen_climatology.sh** | Rain norms, climatology |
| **gen_computed_rt.sh** | Heat index, THSW, wind chill, apparent temp from now + wind |
| **gen_air.sh** | AirLink PM2.5/PM10 |
| **gen_astro.sh** | Sunrise/sunset, moon |
| **gen_tide.sh** | Tide events |

---

## 7. HTTP Serving

- **Base URL:** `http://192.168.2.174/`
- **Data path:** `/data/` → serves files from `/home/scott/dashboard/data/` (symlink or alias)
- **wx-i9 proxy:** serve_frames proxies `/pi-wx-data/*` → `http://192.168.2.174/*`
- **MRW dashboard** fetches: `/pi-wx-data/data/now.json`, wind.json, extremes.json, rain.json, etc.

---

## 8. Dashboard Wind Direction Fix

The Master MRW Wind module uses:

- **AVG 10:** `wind.avg_10m_dir_deg` ✓
- **GUST:** `wind.gust_dir_deg` ✓ (dir when current gust recorded)
- **MAX 10:** `wind.max_gust_10m_dir_deg` ✓ (dir when max gust in 10m occurred)
- **MAX DAY:** `extremes.wind_gust_mph.day.hi_dir_deg` ✓
