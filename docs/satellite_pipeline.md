# Satellite IR Pipeline — End-to-End

## Flow

```
S3 (noaa-goes19) → fetch_goes.py → netCDF URL
     ↓
urllib download → scratch/ir_{ts}.nc
     ↓
render_goes_frame.py reads conf/satellite_ir_transfer.json
     ↓
BT data → np.interp(bp, rgba) → RGBA PNG
     ↓
rsync scratch/ir/*.png → wx-i9:~/wx-data/served/radar_local_satellite/ir/
     ↓
manifest.json built from pool (slot_select picks best per 5-min slot), scp to remote
     ↓
serve_frames (wx-i9:8080) serves serve_root/satellite → radar_local_satellite
     ↓
Player fetches manifest, loads PNG with ?v=Date.now()
```

## Key Paths

| Step | Local (weather-core / dev) | Remote (wx-i9) |
|------|---------------------------|----------------|
| Transfer function | `conf/satellite_ir_transfer.json` | (same, synced) |
| Rendered PNG | `scratch/ir/` (temp) | `~/wx-data/served/radar_local_satellite/ir/` |
| Manifest | `scratch/ir_manifest.json` (temp) | `~/wx-data/served/radar_local_satellite/ir/manifest.json` |
| Serve root | — | `~/wx/radar-foundry/serve_root/satellite` → `radar_local_satellite` |

## Incremental Fetch (process whatever NOAA sends)

Incremental runs fetch all frames from the last 6 hours (`--recent-minutes 360`), filter out any already in the pool, process the rest. If the latest pool frame is >4h old (e.g. after overnight sleep), the window extends to 12h to fill gaps. This captures frames at any timestamp (e.g. 18:41, 18:43, 18:47) instead of only those exactly on 5-min boundaries. `slot_select_loop` then picks the best frame per 5-min slot from the full pool for the manifest.

## Schedule (wx-i9 — bulletproof)

**Primary:** IR every 5 min (`--ir-only`, ~2 min). Visible at :01,:11,:21,:31,:41,:51 (`--vis-only`, ~7 min). Staggered so they never contend for the lock. Log: `/tmp/goes_loop_wxi9.log`.

**Watchdog:** Cron every 10 min + systemd timer (backup if cron fails). If latest IR frame > 12 min old, clears lock and runs update. Kills stuck processes > 25 min. If disk > 90%, trims to 50 frames. Log: `/tmp/goes_watchdog_wxi9.log`. Install systemd: `./bin/setup_goes_systemd_wxi9.sh`.

**wx-core watchdog:** `watchdog_all.sh` checks satellite manifest freshness. If stale > 15 min, SSHs to wx-i9, kills stuck processes, clears lock, kicks update.

**Lock:** 12-min timeout. Stale lock is removed so next run can proceed.

**Disk:** Run script skips if partition > 90% full. Watchdog trims to 50 frames if disk > 90%.

## Run Update (single IR frame)

```bash
# From project root (weather-core or dev machine)
.venv/bin/python bin/update_goes_loop.py --newest --ir-only \
  --remote-base /home/scott/wx-data/served/radar_local_satellite --remote-host wx-i9
```

**Uses:** `conf/satellite_ir_transfer.json` from the machine where the command runs. Fetches newest frame, renders, rsyncs to wx-i9. Manifest is rebuilt from full pool (72 slots). **Do not use** `--frames 1` — it truncates the manifest to 1 frame.

## Cache / "Nothing Changed"

1. **Browser cache** — PNGs and manifest were cached. `serve_frames` now sends `Cache-Control: no-cache, must-revalidate` for `/satellite/`. **Hard refresh:** Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows).

2. **serve_frames restart** — After syncing `serve_frames.py`, restart on wx-i9:
   ```bash
   ssh wx-i9 "sudo systemctl restart mrw-serve-frames"
   ```

3. **Verify PNG content** — PNG on wx-i9 should have ~71% transparent pixels (260–300 K) when transfer function has 260+ transparent:
   ```bash
   scp wx-i9:~/wx-data/served/radar_local_satellite/ir/20260311T131617Z.png /tmp/check.png
   .venv/bin/python -c "
   from PIL import Image
   import numpy as np
   a = np.array(Image.open('/tmp/check.png').convert('RGBA'))[:,:,3]
   print('Transparent:', np.sum(a==0), '/', a.size, '=', 100*np.sum(a==0)/a.size, '%')
   "
   ```

## Default View (center / zoom)

Edit `conf/satellite_config.json`:

```json
"center": [-85, 34],
"zoom": 4.2
```

- **center**: `[longitude, latitude]` — map center on load
- **zoom**: Mapbox zoom level (higher = closer)

The player fetches `/satellite/config.json` (copied from this config on sync/setup). URL params override: `?center=-82,31&zoom=5`.

## Transfer Function

- **200–255 K:** Standard gray (clouds visible)
- **260–300 K:** Transparent (land/ocean — basemap shows through)
- **180 K:** No data (transparent)

Edit `conf/satellite_ir_transfer.json`, then re-run update_goes_loop to render a new frame.
