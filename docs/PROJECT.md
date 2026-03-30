# Moon River Weather — Radar Foundry

**Running project documentation.** The agent updates this doc as features and pipelines evolve — not the user.

**Development:** Local-first on Office Mac. Both radar-foundry and moonriverweather-public live locally; open `mrw-multi.code-workspace`. See `docs/DEVELOPMENT_ARCHITECTURE.md`.

---

## 1. Overview

Radar Foundry produces weather radar overlays and serves them via web players. It supports:

- **NEXRAD Level-II** (KCLX, KJAX): Single-site radar loops, basemap-aligned
- **MRMS** (Multi-Radar/Multi-Sensor): CONUS composite reflectivity, Web Mercator, multi-region

**Player URLs (wx-i9):**

| Product | Desktop | Mobile |
|---------|---------|--------|
| KCLX | http://192.168.2.2:8080/player/kclx/ | http://192.168.2.2:8080/player/kclx-mobile/ |
| KJAX | http://192.168.2.2:8080/player/kjax/ | http://192.168.2.2:8080/player/kjax-mobile/ |
| MRMS | http://192.168.2.2:8080/player/mrms/ | http://192.168.2.2:8080/player/mrms-mobile/ |
| Satellite | http://192.168.2.2:8080/player/satellite/ | — |
| Lightning | http://192.168.2.2:8080/player/lightning-mapbox/ | — |
| Full View Lightning Map | http://192.168.2.2:8080/player/lightning-full-view/ | — |
| Local Lightning Map | http://192.168.2.2:8080/player/local-lightning/ | — |

---

## 2. Rules & Conventions

### Agent Executes — User Directs

- **Agent runs everything.** Commands, edits, syncs. No handoffs.
- **Use SSH** when needed: `ssh weather-core`, `ssh wx-i9`, `ssh pi-wx`.
- **Never say "run this"** — run it yourself.
- **If blocked**, report the error and what you tried.

See `.cursor/rules/agent-executes.mdc`.

### Timezone: America/New_York (EST/EDT)

**Source of truth for all MRW weather data is local Eastern time.** Rain accumulation, climatology, and any date-based calculations use `America/New_York` (EST/EDT), not UTC. This applies to: rain-accumulation module, pi-wx gen_climatology.sh, climatology.json, galaxy/iphone displays.

---

## 3. Architecture

### Development vs Runtime

| Layer | Location | Role |
|-------|----------|------|
| **Development** | Office Mac | Edit radar-foundry and moonriverweather-public locally; deploy when ready |
| **Runtime** | wx-core, wx-i9, pi-wx | Pipelines, serving, station data (unchanged) |

### Machines (Runtime)

| Host | Role |
|------|------|
| **weather-core** (wx-core) | Fetches NEXRAD/MRMS/GOES, renders frames, publishes to wx-i9; launchd jobs |
| **wx-i9** (192.168.2.2) | Serves HTTP (port 8080), displays players; 1TB wx-data volume |
| **pi-wx** (192.168.2.174) | WeeWX, live weather data; wx-i9 proxies /pi-wx-data/* |

### Hybrid Strategy (Compute Where You Serve)

- **weather-core**: KCLX, KJAX, MRMS, IR/Visible satellite — fetch, render, publish to wx-i9
- **wx-i9**: Serves frames; IR/Visible produced on weather-core and published.
- **Storage**: wx-i9 has 4TB NVMe; 1TB allocated for wx-data at `/wx-data` (symlinked as `~/wx-data`). ~956 GB free for GEOCOLOR and growth.

### Data Flow

```
NEXRAD S3 / MRMS S3
       ↓
weather-core: fetch → render → publish (rsync/scp)
       ↓
wx-i9: ~/wx-data/served/radar_local_*/frames
       ↓
serve_root symlinks → serve_frames.py (HTTP 8080)
       ↓
Browser: player/mrms/, player/kclx/, etc.
```

### Key Paths

| Path | Purpose |
|------|---------|
| `conf/` | JSON configs (regions, geometry, sites) |
| `bin/` | Python scripts and shell wrappers |
| `player/` | HTML/JS players (desktop + mobile) |
| `serve_root/` | Symlink tree for HTTP serve |
| `out/` | Generated basemaps, MRMS frames |
| `basemap/src/` | TIGER, Natural Earth shapefiles |
| `docs/pi-wx/` | pi-wx operational notes (WeeWX AirLink patch, etc.) |
| `patches/pi-wx/` | Unified diffs for pi-wx (re-apply after WeeWX extension upgrades) |
| `pi-wx-dashboard/` | Galaxy A9+ LAN phone UI — **`galaxy-a9p11/`**; deploy: `bin/deploy_pi_wx_galaxy_a9p11.sh` → `pi-wx:~/dashboard/ui/` |

---

## 4. How Radars Are Built

### NWS Alert Overlays (KCLX, KJAX, MRMS Mapbox)

- **Severe Thunderstorm Warning (SVR)**: Yellow outline, no fill
- **Tornado Warning (TOR)**: Red outline, no fill
- **Tornado Watch**: Red fill 20% opacity (no border)
- **Severe Thunderstorm Watch**: Yellow fill 20% opacity (no border)
- **Special Weather Statement (SWS)**: Orange outline — only when localized (polygon) and mentions thunderstorm, hail, tornado, or lightning
- **Source**: `bin/fetch_nws_alerts.py` — fetches from api.weather.gov/area/GA,SC,FL (covers JAX, CAE, CHS, ATL offices), resolves zone polygons
- **Output**: `serve_root/alerts.json` — { svr: GeoJSON, tor: GeoJSON, tor_watch, svr_watch, sws }
- **Refresh**: `bin/run_nws_alerts.sh --remote` every 3 min (launchd on weather-core), scps to wx-i9
- **Players**: kclx-mapbox, kjax-mapbox, mrms — fetch /alerts.json, county fill + line layers; refresh every 2 min

### NEXRAD Level-II (KCLX, KJAX)

**Config:** `conf/radar_sites.json` — `sites` must include both `["KCLX", "KJAX"]` for both radars to update.

1. **Fetch**: `bin/fetch_latest_level2.py` — lists S3, picks latest scan per site
2. **Render**: `bin/render_level2_nn_rgba.py` — polar → basemap-aligned Cartesian, RGBA
3. **Publish**: `bin/publish_radar_frame.py` — writes to local or remote frames dir
4. **Coordinator**: `bin/radar_loop_coordinator.py` — runs every 2 min on weather-core, fetches + renders + publishes for all sites

**Geometry**: Uses `conf/basemap_geometry.json` (center, half_km, N). Output 1600×1600 PNG, EPSG:3857.

**Scheduler**: `conf/launchd/com.mrw.radar_coordinator.plist` (every 2 min)

### MRMS Composite Reflectivity

1. **Fetch**: `bin/fetch_mrms.py` — lists S3 `noaa-mrms-pds`, picks N frames at 10 min cadence
2. **Render**: `bin/render_mrms_frame.py` — GRIB2 → Web Mercator PNG per region
3. **Update loop**: `bin/update_mrms_loop.py` — fetch 36, render each region, publish to wx-i9
4. **Wrapper**: `bin/run_mrms_loop.sh` — launchd entry point; lock file prevents overlap

**Regions**: `conf/mrms_regions.json` — eastern_us, florida_south, southeast, florida, georgia, savannah_250. Each has bounds, center, zoom, width_px (4096).

**Projection**: Web Mercator (EPSG:3857) for Mapbox alignment.

**Frame selection**: 36 frames = true 6 hours. For each 10-minute slot (:00, :10, :20, …), `fetch_mrms.py` picks the most recent available file at or before that slot. 6 frames/hour, one every 10 min.

**Freshness rule**: Latest frame target ≤10 min old; watchdog triggers at 15 min. Run every 5 min to minimize lag on top of S3.

**Scheduler**: `conf/launchd/com.mrw.mrms_loop.plist` (every 5 min, RunAtLoad)

### Lightning (NexStorm .nex tail)

- **Source**: Lightning-PC (192.168.2.223) — NexStorm + LD-350, nxutil extracts today's .nex to CSV
- **Pipeline**: `bin/lightning_nex_tail.py` on wx-core — polls every 5 s, pulls CSV, parses new rows, emits canonical NDJSON
- **Outputs** (pushed to `C:\MRW\lightning\`): `lightning_rt.ndjson`, `lightning_status.json`, `lightning_recent.json`
- **lightning_recent.json**: Near real-time intelligence — last_strike_time_utc, nearest_strike_km/miles, closest_strike_bearing_deg/direction, strikes_last_5/10/15_min, trend (approaching/departing/steady). See `docs/lightning/LIGHTNING_PRODUCTS.md`
- **lightning_points.geojson**: Map product — GeoJSON points from bearing/distance, 500-mile radius, served at `/lightning_points.geojson`; player at `/player/lightning-mapbox/` (stable baseline)
- **lightning_points_v2.geojson**: Full View Lightning Map — same input, v2 age buckets, 15 min window, max 500; player at `/player/lightning-full-view/` — **PRODUCTION** (see `docs/lightning/FULL_VIEW_LIGHTNING_MAP.md`). **Rules:** `docs/lightning/LIGHTNING_RULES_REFERENCE.md` — constants, close zone (25 mi), API schema; use across dashboards, website.
- **local-lightning**: Local Lightning Map — no zoom/pan, MRW center, 135 mile radius; player at `/player/local-lightning/` (see `docs/lightning/LIGHTNING_FIXED_135.md`).
- **lightning_summary.json**: Operational intelligence — nearest strike, counts by radius (5/10/15/25/50/100 mi), counts by type/age, strike rate, trend, alert_state. **Dashboards must read this; do not compute metrics client-side.** See `docs/lightning/LIGHTNING_PRODUCTS_INDEX.md`.
- **Scheduler**: `conf/launchd/com.mrw.lightning_nex_tail.plist` (RunAtLoad, KeepAlive)

### Lightning (Xweather API)

- **Source**: Xweather API — REST poll every 10 s
- **Pipeline**: `bin/lightning_xweather_fetch.py` on weather-core — `--loop --interval 10 --post-generate`
- **Output**: `scratch/lightning_xweather/lightning_xweather_rt.ndjson`, `lightning_points_xweather_local.geojson` (pushed to wx-i9)
- **hyper-local-x**: Xweather-only hyper-local map at `/player/hyper-local-x/` (see `docs/lightning/XWEATHER_DEPLOYMENT.md`)
- **Scheduler**: `conf/launchd/com.mrw.lightning_xweather_fetch.plist` (RunAtLoad, KeepAlive)
- **Credentials**: `~/.mrw/xweather.env` (XWEATHER_CLIENT_ID, XWEATHER_CLIENT_SECRET)

---

## 5. How Basemaps Are Built

1. **Config**: `conf/basemap_geometry.json` — center_lat, center_lon, half_km, N (1600)
2. **Script**: `bin/make_basemap_grid.py` — reads config, loads shapefiles, clips to extent, renders PNG + SVG
3. **Sources**: `basemap/src/` — TIGER 2024 (states, counties, roads), Natural Earth (coastline, cities)
4. **Output**: `out/basemap_MRWcenter_1600.png`, `out/basemap_MRWcenter_1600.svg`

**Projection**: EPSG:3857 (Web Mercator). Radar overlays use the same geometry for alignment.

---

## 6. Players

### Desktop (mrms, kclx, kjax)

- Top bar: regions (MRMS) or single site, play/pause, step, speed, frame limit, opacity (MRMS), refresh, fullscreen
- Mapbox GL JS base map + raster overlay
- Frame stamp bottom-right

### Mobile (mrms-mobile, kclx-mobile, kjax-mobile)

- Compact bar: regions, play/step, frame limit, opacity (MRMS)
- Touch-friendly, safe-area insets

### MRMS Features (2026-03-07)

- **Opacity slider**: 30–100%, persisted in localStorage (`mrw_mrms_opacity` / `mrw_mobile_mrms_opacity`)
- **Static thumbnails**: `player/mrms/thumbs/*.png` per region
- **6 regions**: Eastern US, Florida South, Southeast, Florida, Georgia, Savannah 250

### Master MRW Dashboard (2026-03-09)

- **Location**: `player/master-mrw/index.html` — 4K (3839×2160) for WX-Display (Beelink)
- **Layout**: See `docs/MASTER_MRW_LAYOUT_LOCKED.md` — left 8 boxes (700×489), center Wind+Tide, right radar/regional
- **Plug-and-play modules**: Left section uses `SLOTS` config + `MODULES` registry. Any module can go in any of the 8 boxes — set `SLOTS[i]` (i = 0..7) to module id or null. Add new modules to `MODULES`; wire into `SLOTS` to place.
- **Modules implemented**: `current-temp` — current temp, Heat Index/Wind Chill, THSW; daily Hi/Lo with times. `humidity` — Humidity, Dew Point, Solar, UV; Hi + time for Solar/UV; color scales. `rain-current` — LOCKED. Today, Rain Rate, Storm Rain, Days Since Rain; live data: rain.json, now.json via pi-wx proxy. `rain-accumulation` — Monthly to Date, Monthly % of Norm, YTD, Year % of Norm, Yearly Deficit/Excess; rain.json, rain_norms.json; expected-to-date methodology (sum full months + partial current). `celestial` — Sunrise, Sunset, Day Length, Moonrise, Moonset, Next Season; /api/celestial/summary (astral + skyfield, MRW coords). Move/remove: set SLOTS[i] = module id or null.

---

## 7. Deployment

**Development is on Office Mac.** Deploy to runtime when ready.

### Agent runs wx-i9 deploy (same session as the code change)

**Git push alone does not update wx-i9.** The Beelink and browsers load `~/wx/radar-foundry/` on **wx-i9**, not GitHub. When the agent changes anything served from there — especially `player/` (KCLX, MRMS, **`player/master-mrw/`**, etc.) — the agent **runs** a deploy in that same session:

| Situation | Command (from up-to-date repo root) |
|-----------|-------------------------------------|
| **Typical:** Mac has the commit; player / config / `bin/` only | `./bin/deploy_radar_foundry_to_wx_i9.sh` |
| **Full sync:** regenerate lightning GeoJSON and rsync (best from **wx-core** after `git pull`) | `./bin/sync_to_wx_i9.sh` |
| **Mac triggers wx-core’s tree** | `./bin/deploy_wx_core_to_wx_i9.sh` (SSHs to wx-core, runs `sync_to_wx_i9.sh` there) |

Do not end a turn with “merged” or “pushed” for Master MRW / players **without** having deployed to wx-i9 (or report SSH/rsync failure after trying). See `.cursor/rules/agent-executes.mdc`.

**Local Mac dev — port safety (MRW vs CCP_Core, etc.):** `docs/local-dev/WEATHER_DEV_PORTS.md` — `./bin/weather_dev_status.sh`, `./bin/dev_serve_frames_safe.sh`, `./bin/dev_moonriverweather_safe.sh`. Pattern matches `CCP_Core/docs/LOCAL_DEV_PORTS.md`.

| Action | Command |
|--------|---------|
| Seed (pull from wx-core) | `./bin/seed_radar_foundry_from_wx_core.sh` |
| Deploy code to wx-core | `./bin/deploy_radar_foundry_to_wx_core.sh` |
| Deploy to wx-i9 (from wx-core) | `./bin/deploy_wx_core_to_wx_i9.sh` |
| Deploy to wx-i9 (from Mac, code-only) | `./bin/deploy_radar_foundry_to_wx_i9.sh` |

See `docs/DEVELOPMENT_IMPLEMENTATION_PLAN.md`.

### sync_to_wx_i9 (run from wx-core for full sync)

```bash
./bin/sync_to_wx_i9.sh
```

Rsyncs project to wx-i9, runs `setup_serve_root.sh` on remote. **Best run from wx-core** (lightning geo generators need ndjson). Run after any player or config change **that must ship with fresh lightning GeoJSON**; for most Master MRW / player HTML+CSS edits, **`deploy_radar_foundry_to_wx_i9.sh` from the Mac** is enough.

### setup_serve_root.sh

- **Remote mode** (`SERVED_RADAR_BASE`): Symlinks KCLX, KJAX, mrms to `~/wx-data/served/`
- **Local mode**: Symlinks to WX_SCRATCH or `out/mrms`
- Symlinks player, basemaps

**Machine-specific (prevents broken symlinks):**

| Host | Command |
|------|---------|
| **weather-core** (Mac) | `./bin/setup_serve_root.sh` (uses RADAR_DIR default) |
| **wx-i9** (Linux) | `SERVED_RADAR_BASE=$HOME/wx-data/served ./bin/setup_serve_root.sh` |

On wx-i9, **never** run without `SERVED_RADAR_BASE` — `/Volumes/` paths do not exist on Linux. The script now validates targets exist and refuses Mac paths on Linux.

### serve_frames

- `bin/serve_frames.py` — HTTP server on port 8080
- systemd: `conf/systemd/mrw-serve-frames.service`
- **Watchdog (wx-core)**: `bin/watchdog_all.sh` — every 5 min; checks KCLX/KJAX/MRMS manifest freshness; kills stuck processes (MRMS >20 min, coordinator >8 min); checks serve_frames health, restarts via SSH if down; kicks coordinator+MRMS after recovery; log rotation. **Requires** sudoers on wx-i9: `scott NOPASSWD: /bin/systemctl restart mrw-serve-frames`
- **Watchdog (wx-i9)**: `bin/watchdog_serve_frames.sh` (cron every 5 min) — optional; unified watchdog handles serve_frames via SSH

---

## 8. Restore & Backup

### Restore Point

Backups are in `backups/`:

```
backups/radar-foundry-restore-YYYYMMDD-HHMM.tar.gz
```

To restore:

```bash
cd /path/to/restore-dir
tar -xzvf backups/radar-foundry-restore-YYYYMMDD-HHMM.tar.gz
```

Excludes: `.venv`, `.git`, `__pycache__`, `serve_cache`, `scratch`, `raw_level2`, `raw`, `logs`, `work`.

### Creating a New Backup

From project root:

```bash
mkdir -p backups
tar --exclude='.venv' --exclude='.git' --exclude='__pycache__' --exclude='serve_cache' \
    --exclude='scratch' --exclude='raw_level2' --exclude='raw' --exclude='logs' --exclude='work' \
    -czvf backups/radar-foundry-restore-$(date +%Y%m%d-%H%M).tar.gz .
```

Or run: `./bin/backup_restore_point.sh`

---

## 9. Related Docs

| Doc | Purpose |
|-----|---------|
| [DEVELOPMENT_ARCHITECTURE.md](DEVELOPMENT_ARCHITECTURE.md) | Local-first dev on Office Mac; deploy to wx-core/wx-i9 |
| [DEVELOPMENT_IMPLEMENTATION_PLAN.md](DEVELOPMENT_IMPLEMENTATION_PLAN.md) | Seeding, deploy flow, script categories |
| [MRW_PROJECTS.md](MRW_PROJECTS.md) | Multi-root workspace; radar-foundry + moonriverweather-public |
| [ld350_lightning_plan.md](ld350_lightning_plan.md) | LD-350 lightning detector integration — planning (install in 3–4 days) |
| [lightning_pipeline_plan.md](lightning_pipeline_plan.md) | Lightning ingest — FlashGate primary, .nex secondary |
| [lightning/FLASHGATE_RELAY_PLAN.md](lightning/FLASHGATE_RELAY_PLAN.md) | FlashGate relay implementation plan |
| [lightning/FLASHGATE_TROUBLESHOOTING.md](lightning/FLASHGATE_TROUBLESHOOTING.md) | FlashGate relay diagnostics, session IDs, enablement |
| [LIGHTNING_ARCHITECTURE_PLAN.md](LIGHTNING_ARCHITECTURE_PLAN.md) | Lightning platform architecture — sources, products, realtime vs archive, machine roles, roadmap |
| [LIGHTNING_ARCHITECTURE_REFINEMENT.md](LIGHTNING_ARCHITECTURE_REFINEMENT.md) | Lightning refinement — canonical strike model, ingestion pipeline, product outputs, machine roles, phases |
| [LIGHTNING_ARCHITECTURE_CLARIFICATION.md](LIGHTNING_ARCHITECTURE_CLARIFICATION.md) | Lightning clarification — UTC time, strike identity/provenance, Model A (pi-wx publisher), canonical vs derived |
| [LIGHTNING_PHASE0_DISCOVERY_PLAN.md](LIGHTNING_PHASE0_DISCOVERY_PLAN.md) | Lightning Phase 0 — discovery: .nex path, rollover, append-only, nxutil, format layout, Go/No-Go |
| [LIGHTNING_PHASE1_IMPLEMENTATION_PLAN.md](LIGHTNING_PHASE1_IMPLEMENTATION_PLAN.md) | Lightning Phase 1 — .nex full-file ingest, canonical normalization, outputs, validation (blocked until Phase 0) |
| [lightning/LIGHTNING_PRODUCTS.md](lightning/LIGHTNING_PRODUCTS.md) | Lightning products — lightning_recent.json schema, trend logic |
| [mrms_baseline_stable.md](mrms_baseline_stable.md) | MRMS projection baseline, do-not-change params |
| [mrms_setup.md](mrms_setup.md) | MRMS pipeline setup, local/remote |
| [setup_wx_i9.md](setup_wx_i9.md) | wx-i9 one-time setup, systemd, firewall |
| [wx_i9_storage.md](wx_i9_storage.md) | wx-i9 1TB wx-data volume, Hybrid strategy |
| [air_api_setup.md](air_api_setup.md) | Air API: ozone (AirNow), smoke (HRRR), pollen (Google); /api/air/summary |
| [satellite_setup.md](satellite_setup.md) | GOES satellite: IR + Visible, 72 frames at 5 min; /player/satellite/ |
| [basemap_radar_geometry_analysis.md](basemap_radar_geometry_analysis.md) | Basemap vs radar geometry alignment |

---

## 10. Changelog (Running)

*Agent maintains this section on each significant change.*

| Date | Change |
|------|--------|
| 2026-03-30 | Local dev: `docs/local-dev/WEATHER_DEV_PORTS.md` + `bin/weather_dev_status.sh`, `dev_serve_frames_safe.sh`, `dev_moonriverweather_safe.sh` (port safety; CCP_Core 3001 conflict documented) |
| 2026-03-30 | Deployment: agent must run wx-i9 deploy same session as player/master-mrw changes (push ≠ live); §7 table — `deploy_radar_foundry_to_wx_i9.sh` vs `sync_to_wx_i9.sh` |
| 2026-03-16 | Development architecture: local-first on Office Mac; docs/DEVELOPMENT_ARCHITECTURE.md, DEVELOPMENT_IMPLEMENTATION_PLAN.md; seed/deploy helper scripts |
| 2026-03-14 | Lightning: Production deployment — Startup pipeline (NexStorm + relay), SIPC support, retry logic, autologon setup; deploy_to_lightning_pc.sh |
| 2026-03-15 | Lightning hardening: retries (SSH/SCP 3x), atomic writes, timeouts, last_success_at_utc, watchdog integration, ThrottleInterval, .cursor/rules/lightning-hardening.mdc |
| 2026-03-15 | Sync hardening: exclude serve_root from rsync to wx-i9; post-sync verification of KCLX/KJAX manifests; .cursor/rules/sync-serve-root-hardening.mdc |
| 2026-03-15 | Lightning V2: dot size LOCKED — CG 6px, IC 5px; baseline updated |
| 2026-03-16 | Local Lightning Map — no zoom/pan, MRW center, 135 mi radius; /player/local-lightning/ (renamed from lightning-fixed-135) |
| 2026-03-16 | Full View Lightning Map — PRODUCTION LOCKED; zoom 6, minZoom 6, pan restricted to initial viewport (getBounds on idle); data box 260×280; row 3 label Now; docs/lightning/FULL_VIEW_LIGHTNING_MAP.md |
| 2026-03-15 | Full View Lightning Map — PRODUCTION; map behavior (400mi, zoom 7–14, pan/zoom locked), strike behavior (CG/IC 6/5px, 5-min fade), green star station; docs/lightning/FULL_VIEW_LIGHTNING_MAP.md |
| 2026-03-15 | Lightning: dedupe in GeoJSON generators — (timestamp_utc, lon, lat) key; keep newest; both v1 and v2; before 500 cap |
| 2026-03-15 | Lightning: lightning_points.geojson + lightning-mapbox player — Map product from bearing/distance; 500-mile domain; CG/IC styling; serve_root /player/lightning-mapbox/ |
| 2026-03-15 | Lightning: lightning_recent.json — first MRW lightning intelligence product; last_strike, nearest_km/miles, bearing/direction, strikes_last_5/10/15_min, trend; computed in lightning_nex_tail, pushed to C:\MRW\lightning\ |
| 2026-03-14 | Lightning: FlashGate IPC-1 relay (scripts/lightning/windows/) — primary live path; lightning_rt.ndjson, lightning_status.json on Lightning-PC |
| 2026-03-14 | Lightning: LIGHTNING_PHASE0_DISCOVERY_PLAN.md — discovery tasks, nxutil CSV, format layout, Go/No-Go before parser |
| 2026-03-14 | Lightning: LIGHTNING_PHASE1_IMPLEMENTATION_PLAN.md — .nex full-file ingest, lightning_rt.json prototype, validation (blocked until Phase 0) |
| 2026-03-14 | Lightning: LIGHTNING_ARCHITECTURE_CLARIFICATION.md — UTC time, strike_id/provenance, Model A (pi-wx publisher), canonical vs derived |
| 2026-03-14 | Lightning: LIGHTNING_ARCHITECTURE_REFINEMENT.md — canonical strike model, source adapters, product outputs, machine roles, 6-phase implementation |
| 2026-03-14 | Lightning: LIGHTNING_ARCHITECTURE_PLAN.md — shared MRW subsystem, sources (LD-350, NexStorm, nxutil, FlashGate), products, realtime vs archive, 6-phase roadmap |
| 2026-03-12 | Satellite: --newest flag for quick single-frame push (recovery when launchd didn't run overnight) |
| 2026-03-12 | NWS alerts on MRMS player: same county coloring + line outlines as KCLX/KJAX; GA,SC,FL covers JAX, CAE, CHS, ATL |
| 2026-03-12 | NWS alerts: handle GeometryCollection in zone geometry (e.g. Chatham County GAC051); all counties in tor/svr watch now render |
| 2026-03-11 | GEOCOLOR removed; IR production finalized. Satellite player: IR + Visible, produced on weather-core. |
| 2026-03-11 | Hybrid strategy: wx-i9 1TB LVM volume for wx-data (/wx-data, ~/wx-data symlink); docs/wx_i9_storage.md |
| 2026-03-10 | Satellite product: GOES-19 IR + Visible, 72 frames at 5-min cadence; extent Cuba–Canada, Colorado–Atlantic; /player/satellite/ |
| 2026-03-10 | Celestial module LOCKED: sunrise, sunset, day_length, moonrise, moonset, phase, next_season_start; skyfield phase; box 6 |
| 2026-03-10 | Air Quality module LOCKED: missing data → `--` only; never "Data Unavailable"; docs + rule |
| 2026-03-10 | Smoke: failure cache 5 min (was 60) so transient errors recover; success still 60 min |
| 2026-03-10 | Saharan Dust: CAMS duaod550 integration; level None/Light/Moderate/Heavy; serve_frames uses .venv-wxi9 |
| 2026-03-09 | Air Quality: 6 metrics (PM2.5, PM10, Ozone, Smoke, Saharan Dust, Pollen); single /api/air/summary; removed tree/grass/weed pollen |
| 2026-03-08 | MRMS: run every 5 min (was 10); freshness target ≤10 min, watchdog at 15 min; RunAtLoad; lock prevents overlap |
| 2026-03-08 | MRMS colormap: first 3 levels (5–20 dBZ) at alpha 0.25 for transparency; NWSReflectivity otherwise unchanged |
| 2026-03-08 | Unified watchdog (bin/watchdog_all.sh): monitors KCLX/KJAX/MRMS, kills stuck processes (>20 min MRMS, >8 min coordinator), serve_frames health via SSH restart, kick after recovery, log rotation; replaces watchdog_radar |
| 2026-03-07 | LD-350 lightning detector integration plan — docs/ld350_lightning_plan.md |
| 2026-03-07 | NWS Tornado Watch, SVR Watch: shaded fill (red/yellow 20%), no border; county-level via affectedZones |
| 2026-03-07 | NWS SWS: Special Weather Statements (thunderstorm/hail/tornado/lightning, localized) — orange outline on Mapbox players |
| 2026-03-07 | NWS alert overlays: SVR (yellow), TOR (red), SWS (orange) on KCLX/KJAX Mapbox players; fetch_nws_alerts.py fetches from api.weather.gov/area/GA,SC,FL |
| 2026-03-07 | MRMS fetch: true 10-min cadence — one image per 10-min slot, most recent at or before each slot; 36 frames = 6 hours; multi-day S3 listing for midnight span |
| 2026-03-07 | Restore point, PROJECT.md, backup created |
| 2026-03-07 | MRMS opacity slider (desktop + mobile), localStorage persistence |
| 2026-03-07 | MRMS Web Mercator reprojection, 6 regions, static thumbnails |
| 2026-03-07 | Agent-executes rule, sync_to_wx_i9 |
