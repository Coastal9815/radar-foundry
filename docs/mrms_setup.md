# MRMS Pipeline Setup

> **Stable baseline** (projection-aligned): see [mrms_baseline_stable.md](mrms_baseline_stable.md)

## Overview

MRMS (Multi-Radar/Multi-Sensor) Composite Reflectivity from NOAA S3, rendered to PNG overlays for Mapbox players. NWS-style: ingest every new file, loop shows one per 10-min slot.

- **Source**: `noaa-mrms-pds` S3, CONUS MergedReflectivityQCComposite_00.50
- **Pool**: Last 200 images per region (ingest every new file as NOAA publishes, ~2-3 min)
- **Loop**: 36 frames, one per 10-min slot (:00, :10, :20, etc.). For each slot: most recent at or before slot time.
- **Extent**: Eastern US (lon -98 to -75, lat 24 to 38)
- **Projection**: GRIB2 regular_ll → PNG with lat flip + -0.29° offset for Mapbox alignment

## Scripts

| Script | Purpose |
|--------|---------|
| `bin/fetch_mrms.py` | List S3, pick N frames at cadence. Output JSON. |
| `bin/render_mrms_frame.py` | Render one GRIB2 → PNG (Eastern US, projection-corrected) |
| `bin/update_mrms_loop.py` | Full pipeline: fetch 36, render each, publish, manifest |
| `bin/run_mrms_loop.sh` | Wrapper for launchd (runs on wx-core, publishes to wx-i9) |

## Local Test

```bash
# 2 frames, local output
.venv/bin/python bin/update_mrms_loop.py --local-only --frames 2 --keep 5

# Serve and open player
cd serve_root && python3 -m http.server 8888
# Open http://localhost:8888/player/mrms/
```

## Remote (wx-i9)

```bash
# From weather-core (wx-core)
.venv/bin/python bin/update_mrms_loop.py \
  --remote-base /home/scott/wx-data/served/radar_local_mrms \
  --remote-host wx-i9 --remote-user scott
```

## serve_root (wx-i9)

```bash
SERVED_RADAR_BASE=$HOME/wx-data/served ./bin/setup_serve_root.sh
# Creates symlink: serve_root/mrms -> radar_local_mrms/frames
```

## Scheduler (launchd)

```bash
# Install MRMS loop (every 5 min)
launchctl load ~/wx/radar-foundry/conf/launchd/com.mrw.mrms_loop.plist
```

**Important:** launchd does not run when the Mac is asleep. If wx-core (Mac Studio) sleeps overnight, MRMS will stop updating.

- **Energy Saver (wx-core):** System Settings → Energy Saver → set "Turn display off after" but **disable** "Put hard disks to sleep when possible" and ensure the Mac does not enter full system sleep (or use "Prevent automatic sleeping when the display is off" if available).
- **caffeinate:** The run script uses `caffeinate -s` to prevent system sleep during each run (~10–15 min). This helps avoid sleep mid-run but cannot wake a sleeping Mac.

## Players

- **Desktop**: http://192.168.2.2:8080/player/mrms/
- **Mobile**: http://192.168.2.2:8080/player/mrms-mobile/

Region thumbnails (Eastern US, Florida South, Southeast, etc.) switch map view. Overlay uses fixed Eastern US bounds.
