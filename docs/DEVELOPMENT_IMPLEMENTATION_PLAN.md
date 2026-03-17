# MRW Development — Implementation Plan

Local-first development on Office Mac. This doc covers seeding, deploying, and script categories.

---

## 1. Seeding radar-foundry onto the Office Mac

**One-time (or occasional) pull from wx-core:**

```bash
./bin/seed_radar_foundry_from_wx_core.sh
```

Or manually:

```bash
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
  --exclude 'serve_cache' --exclude 'scratch' --exclude 'raw_level2' --exclude 'raw' \
  --exclude 'logs' --exclude 'logs_level2' --exclude 'work' \
  wx-core:~/wx/radar-foundry/ ~/wx/radar-foundry/
```

**After seeding:** Create `.venv` locally if needed: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`

---

## 2. Deploy Flow

### 2.1 Mac → wx-core (code)

After editing code locally:

```bash
./bin/deploy_radar_foundry_to_wx_core.sh
```

Pushes code to wx-core. Pipelines (launchd) will use the updated code on their next run.

### 2.2 wx-core → wx-i9 (code + setup_serve_root)

**Preferred:** Run sync_to_wx_i9 from wx-core (has lightning ndjson for geo generators):

```bash
./bin/deploy_wx_core_to_wx_i9.sh
```

This SSHs to wx-core and runs `./bin/sync_to_wx_i9.sh` there.

**Alternative (code-only from Mac):** If you only changed player/config and don't need fresh lightning GeoJSON:

```bash
./bin/deploy_radar_foundry_to_wx_i9.sh
```

Pushes code from Mac directly to wx-i9 and runs setup_serve_root. Lightning GeoJSON steps may produce empty/stale; production GeoJSON comes from wx-core pipelines.

---

## 3. Script Categories

### 3.1 Safe for local development (run on Mac)

| Script | Purpose |
|--------|---------|
| `sync_from_wx_core.sh` | Pull from wx-core (same as seed) |
| `seed_radar_foundry_from_wx_core.sh` | Wrapper for initial/occasional pull |
| `deploy_radar_foundry_to_wx_core.sh` | Push code to wx-core |
| `deploy_radar_foundry_to_wx_i9.sh` | Push code to wx-i9 from Mac |
| `deploy_wx_core_to_wx_i9.sh` | Run sync_to_wx_i9 on wx-core |
| `backup_restore_point.sh` | Create restore tarball |
| `verify_office_mac_clean.sh` | Verify Mac has no runtime artifacts |
| `fetch_nws_alerts.py` | Fetch alerts (network only) |
| `make_basemap_grid.py` | Generate basemap (if shapefiles present) |
| `basemap_geometry.py` | Geometry helpers |
| `baseline_report.py` | Baseline reporting |
| `lightning_inspect_nex.py` | Inspect .nex (if file available) |

### 3.2 Runtime-only — wx-core

**Do not run on Mac.** These check `hostname == wx-core` and exit elsewhere:

| Script | Purpose |
|--------|---------|
| `run_mrms_loop.sh` | MRMS fetch/render/publish |
| `run_kclx_loop.sh` | KCLX loop |
| `run_kjax_loop.sh` | KJAX loop |
| `run_goes_loop.sh` | GOES satellite loop |
| `run_radar_coordinator.sh` | Radar coordinator |
| `run_lightning_nex_tail.sh` | Lightning NexStorm ingest |
| `run_lightning_xweather_fetch.sh` | Lightning Xweather ingest |
| `run_nws_alerts.sh` | NWS alerts fetch |
| `watchdog_all.sh` | Unified watchdog |
| `watchdog_radar_loops.sh` | Radar watchdog |
| `radar_loop_coordinator.py` | Coordinator entry |
| `lightning_nex_tail.py` | Lightning pipeline |
| `lightning_xweather_fetch.py` | Xweather pipeline |
| `fix_xweather_duplicates_on_weather_core.sh` | Fix duplicates on wx-core |

### 3.3 Runtime-only — wx-i9

| Script | Purpose |
|--------|---------|
| `watchdog_serve_frames.sh` | serve_frames watchdog (cron) |
| `serve_frames.py` | HTTP server (systemd) |
| `setup_serve_root.sh` | With SERVED_RADAR_BASE on wx-i9 |

### 3.4 Deploy/sync helpers (run from Mac, target remote)

| Script | Purpose |
|--------|---------|
| `sync_to_wx_i9.sh` | Full sync to wx-i9; best run from wx-core (geo generators need ndjson) |
| `deploy_radar_foundry_to_wx_i9.sh` | Code-only push from Mac to wx-i9 |
| `deploy_wx_core_to_wx_i9.sh` | SSH to wx-core, run sync_to_wx_i9 there |
| `update_basemap_on_server.sh` | SSH to wx-core, regenerate basemap |
| `fix_xweather_duplicates.sh` | Sync fix script to wx-core, run there |

---

## 4. Assumptions

- Office Mac can SSH to wx-core, wx-i9, pi-wx (key-based).
- radar-foundry on wx-core remains at `~/wx/radar-foundry`.
- wx-i9 receives radar-foundry at `~/wx/radar-foundry`.
- Pierce_Archive is mounted for moonriverweather-public path.
- launchd plists on wx-core are unchanged; they reference `/Users/scott/wx/radar-foundry` on wx-core.
