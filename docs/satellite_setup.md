# GOES Satellite Product

GOES-19 ABI L1b IR (C13) and Visible (C02) imagery over Mapbox. 72 frames at 5-min cadence (6 hours).

## Extent

- **Bounds:** min_lon -110, max_lon -60, min_lat 18, max_lat 50
- **Coverage:** South of Cuba to Canada, Colorado to Atlantic

## Pipeline

1. **fetch_goes.py** — List S3 `noaa-goes19`; cold start: 72 frames at 5-min slots; incremental: all frames from last 2h (process whatever NOAA sent)
2. **render_goes_frame.py** — netCDF → Web Mercator PNG (IR or Visible)
3. **update_goes_loop.py** — Fetch, render both products, publish to wx-i9
4. **run_goes_loop.sh** — Entry point; lock prevents overlap

## Products

| ID | Channel | Description |
|----|---------|-------------|
| ir | C13 | Infrared (10.3 µm), day/night |
| vis | C02 | Visible (0.64 µm), daytime only |

## Serving

- **Remote:** `radar_local_satellite/ir/`, `radar_local_satellite/vis/` on wx-i9
- **URL:** http://192.168.2.2:8080/player/satellite/
- **Params:** `?product=ir` or `?product=vis`, `?frameLimit=72`, `?opacity=70`, `?autoplay=1`

## Scheduler

- **Cron on wx-i9:** `*/5 * * * *` runs `bin/run_goes_on_wx_i9.sh` — every 5 min. wx-i9 does not sleep.
- **Script:** Writes directly to `~/wx-data/served/radar_local_satellite/{ir,vis}/`. Log: `/tmp/goes_loop_wxi9.log`.

## Visible Calibration

- **Formula:** Satpy-style `R = radiance × π × esd² / esun` (earth_sun_distance_anomaly_in_AU, esun from netCDF)
- **Contrast:** sqrt(reflectance) before display (Geo2Grid style)
- **Output:** RGBA grayscale; alpha=0 for invalid/night pixels

## IR Color Table

Documented like radar dBZ: each brightness temp (K) maps to a color.

- **Config:** `conf/satellite_ir_transfer.json` — transfer_function with K breakpoints and RGBA
- **Colortable:** `conf/satellite_ir_colortable.txt` — K, R, G, B (same format as radarscope_dbz.txt)
- **View:** `out/satellite_ir_colortable.html` — table of all levels with swatch, K, hex, RGB

200 K (cold clouds) = white … 300 K (warm land/ocean) = black. Linear gray_r between.

## Cold Start

First run fetches 72 frames × 2 products = 144 downloads + 144 renders (~60–90 min). Incremental runs fetch all frames from the last 2h, skip any already in pool, process the rest (~2–10 min depending on how many new frames NOAA sent). `slot_select_loop` picks the best frame per 5-min slot from the full pool.

## Recovery (no push overnight)

If launchd on weather-core didn't run (sleep, crash, etc.), push the newest frame quickly:

```bash
.venv/bin/python bin/update_goes_loop.py --newest --ir-only \
  --remote-base /home/scott/wx-data/served/radar_local_satellite --remote-host wx-i9
```

~1 min for 1 frame. Then ensure launchd is loaded on weather-core: `launchctl list | grep goes`
