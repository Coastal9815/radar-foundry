# MRW Lightning System — Architecture Inventory

**Purpose:** Inventory for adding Xweather API as a second source alongside NexStorm/Boltek. No existing products are to be deleted or broken.

---

## 1. Current Lightning System Overview

### Major Components

| Component | Role |
|-----------|------|
| **Lightning-PC** (192.168.2.223) | Windows host: LD-350 (USB) → NexStorm → .nex archive; runs nxutil |
| **wx-core** (weather-core) | Runs `lightning_nex_tail.py`; pulls CSV via SSH, writes ndjson, runs geo generators |
| **wx-i9** (192.168.2.2:8080) | Serves lightning products via `serve_frames.py` |

### Ingestion Flow

```
Lightning-PC
  LD-350 (USB) → NexStorm → .nex archive
  nxutil -extract -i YYYYMMDD -f ALL -o nex_tail.csv -validate
       ↓ (SSH/SCP pull every 3–5 s)
wx-core: lightning_nex_tail.py
  parse_csv_row() → to_canonical() → append lightning_rt.ndjson
  compute_lightning_recent() → lightning_recent.json
  Geo thread (every 3s): generate_lightning_points*.py, generate_lightning_summary.py
       ↓ (SCP push)
Lightning-PC: lightning_rt.ndjson, lightning_recent.json, lightning_status.json
wx-i9 serve_root: lightning_points*.geojson, lightning_summary.json, lightning_range_rings.geojson
```

### Processing Flow

1. **Ingest:** `lightning_nex_tail.py` polls Lightning-PC, pulls `nex_tail.csv`, parses nxutil CSV format.
2. **Canonical:** `to_canonical()` converts to MRW strike record; appends to `lightning_rt.ndjson`.
3. **Products:** Geo thread runs every 3s:
   - `generate_lightning_points.py` → `lightning_points.geojson` (v1)
   - `generate_lightning_points_v2.py` → `lightning_points_v2.geojson` (v2, production)
   - `generate_lightning_summary.py` → `lightning_summary.json`
4. **Range rings:** `generate_lightning_range_rings.py` (run by sync_to_wx_i9, not tail).
5. **Deploy:** SCP to wx-i9 serve_root; serve_frames serves at :8080.

### Outputs/Products

| Product | Path | Consumers |
|---------|------|------------|
| lightning_points.geojson | serve_root | lightning-mapbox (legacy) |
| lightning_points_v2.geojson | serve_root | lightning-full-view, local-lightning (production) |
| lightning_range_rings.geojson | serve_root | lightning-full-view, local-lightning |
| lightning_summary.json | serve_root | Dashboards, alert engine, website |
| lightning_recent.json | Lightning-PC, scratch | generate_lightning_summary |
| lightning_rt.ndjson | scratch, Lightning-PC | All generators |

---

## 2. Current Files and Paths

### Scripts

| Script | Path | Purpose |
|--------|------|---------|
| lightning_nex_tail.py | bin/ | Main pipeline: poll nxutil, ndjson, geo generators |
| generate_lightning_points.py | bin/ | GeoJSON v1 (500 mi, 15 min) |
| generate_lightning_points_v2.py | bin/ | GeoJSON v2 (age buckets, close 30 min) |
| generate_lightning_summary.py | bin/ | lightning_summary.json |
| generate_lightning_range_rings.py | bin/ | Range rings 25–500 mi |
| lightning_inspect_nex.py | bin/ | .nex format inspection |
| run_lightning_nex_tail.sh | bin/ | launchd entry point |
| revert_lightning_v2_to_baseline.sh | bin/ | Revert full-view to baseline |
| sync_to_wx_i9.sh | bin/ | Generates points/rings, SCPs to wx-i9 |
| setup_serve_root.sh | bin/ | Placeholders for lightning_*.geojson, lightning_summary.json |
| serve_frames.py | bin/ | Serves lightning endpoints (no-cache) |
| watchdog_all.sh | bin/ | Lightning staleness check (5 min) |
| flashgate_relay.py | scripts/lightning/windows/ | NexStorm shared-memory relay (Windows) |
| flashgate_relay.go | scripts/lightning/windows/ | Go version of relay |
| deploy_to_lightning_pc.sh | scripts/lightning/windows/ | Deploy to C:/MRW/lightning/ |

### JSON/GeoJSON Outputs

| File | Path(s) | Format |
|------|---------|--------|
| lightning_rt.ndjson | scratch/lightning_nex/, C:/MRW/lightning/ | NDJSON (canonical strikes) |
| lightning_status.json | scratch/lightning_nex/, C:/MRW/lightning/ | JSON (pipeline health) |
| lightning_recent.json | scratch/lightning_nex/, C:/MRW/lightning/ | JSON (15-min summary) |
| lightning_points.geojson | serve_root/ | GeoJSON v1 |
| lightning_points_v2.geojson | serve_root/ | GeoJSON v2 |
| lightning_range_rings.geojson | serve_root/, C:/MRW/lightning/ | GeoJSON |
| lightning_summary.json | serve_root/ | JSON (operational intelligence) |

### Map/App Files

| Player | Path | Data |
|--------|------|------|
| lightning-full-view | player/lightning-full-view/ | lightning_points_v2, lightning_range_rings |
| local-lightning | player/local-lightning/ | Same |
| lightning-full-view-baseline | player/lightning-full-view-baseline/ | Same |
| lightning-mapbox | player/lightning-mapbox/ | lightning_points.geojson |

### Dashboards/Pages

- **Master MRW:** `player/master-mrw/` — references lightning in spec but no direct lightning module found.
- **Lightning players** are standalone map UIs, not embedded in master-mrw.

### APIs/Endpoints (serve_frames.py, wx-i9:8080)

| Path | Content |
|------|---------|
| /lightning_points.geojson | GeoJSON |
| /lightning_points_v2.geojson | GeoJSON |
| /lightning_range_rings.geojson | GeoJSON |
| /player/lightning-mapbox/ | HTML |
| /player/lightning-full-view/ | HTML |
| /player/local-lightning/ | HTML |

*(lightning_summary.json is in serve_root but not explicitly routed; served as static file.)*

### Config Files

| File | Purpose |
|------|---------|
| conf/launchd/com.mrw.lightning_nex_tail.plist | launchd: RunAtLoad, KeepAlive |
| scripts/lightning/windows/relay_config.example.json | FlashGate relay config |
| .cursor/rules/lightning-hardening.mdc | Retries, atomic writes, watchdog |
| .cursor/rules/lightning-rules.mdc | Constants, API schema |
| .cursor/rules/lightning-v2-locked.mdc | V2 map lock |

---

## 3. Current Data Schemas

### lightning_rt.ndjson (canonical strike) — **Source-specific fields**

| Field | Type | Source-agnostic? | Notes |
|-------|------|------------------|-------|
| strike_id | string | ✓ | SHA256[:32] of ts\|bearing\|dist\|sensor |
| timestamp_utc | ISO8601 | ✓ | |
| sensor_id | string | ✓ | "MRW" |
| source | string | NexStorm | "nex_archive" |
| raw_bearing_deg | number | ✓ | |
| raw_distance_km | number | ✓ | |
| trac_bearing_deg | number | NexStorm | Same as raw for NexStorm |
| trac_distance_km | number | NexStorm | Corrected distance |
| strike_type | "CG" \| "IC" | ✓ | |
| polarity | string | NexStorm | positive/negative |
| is_noise | bool | NexStorm | |
| ingested_at_utc | ISO8601 | ✓ | |
| raw_payload | string | NexStorm | nxutil CSV row |

**Consumers use:** `timestamp_utc`, `raw_distance_km` or `trac_distance_km`, `raw_bearing_deg` or `trac_bearing_deg`, `strike_type`.

### lightning_points_v2.geojson (Feature properties) — **Source-agnostic**

| Field | Type | Notes |
|-------|------|-------|
| timestamp_utc | ISO8601 | |
| strike_type | "CG" \| "IC" | |
| distance_km | number | From center |
| bearing_deg | number | 0–360 |
| age_seconds | number | |
| age_bucket | string | bolt, prominent, medium, low, faint |
| render_type | string | cg, ic, bolt |
| symbol | string | Same |
| icon_size | number | |
| icon_opacity | number | |

**Geometry:** Point `[lon, lat]` — computed from bearing/distance via `bearing_dist_to_lonlat()`.

### lightning_summary.json — **Source-agnostic**

| Field | Type | Notes |
|-------|------|-------|
| mrw_center | {lat, lon} | |
| computed_at_utc | ISO8601 | |
| last_strike_time_utc | string | |
| nearest_strike | {distance_mi, bearing_deg, type, age_sec} | |
| nearest_cg, nearest_ic | same shape | |
| counts_by_radius | mi_5, mi_10, mi_15, mi_25, mi_50, mi_100 | |
| counts_by_type | cg_15_min, ic_15_min | |
| counts_by_age | sec_0_60, min_1_5, min_5_10, min_10_15 | |
| strike_rate | per_min_5, per_min_10, per_min_15 | |
| trend | steady \| approaching \| departing | |
| alert_state | {level, reason, active} | |
| source_health | {relay_running, fresh} | |

### lightning_recent.json — **Source-agnostic**

| Field | Type | Notes |
|-------|------|-------|
| last_strike_time_utc | string \| null | |
| nearest_strike_km, nearest_strike_miles | number \| null | |
| closest_strike_bearing_deg | number \| null | |
| closest_strike_direction | string \| null | N, NE, E, etc. |
| strikes_last_5_min, _10_min, _15_min | number | |
| trend | string | |
| computed_at_utc | string | |

### Schema Summary

- **Source-agnostic:** lightning_points_v2.geojson properties, lightning_summary.json, lightning_recent.json structure.
- **NexStorm-specific:** lightning_rt.ndjson `source`, `trac_*`, `polarity`, `is_noise`, `raw_payload`; nxutil CSV format.

---

## 4. Reusable Components for Xweather

| Component | Location | Reuse |
|-----------|----------|-------|
| **Map rendering** | player/lightning-full-view, local-lightning | Full HTML/JS; consumes GeoJSON. No changes if feed matches schema. |
| **Strike plotting** | transformFeaturesForFlash(), applyTransformedData() | Uses `timestamp_utc`, `distance_km`, `bearing_deg`, `strike_type`. Source-agnostic. |
| **Bearing/distance → lon/lat** | bearing_dist_to_lonlat() in generate_lightning_points*.py | pyproj Geod; reusable. |
| **Range rings** | generate_lightning_range_rings.py | Pure geometry; no strike input. Reuse unchanged. |
| **Summary logic** | generate_lightning_summary.py | Reads ndjson; needs normalized strike records. Reuse with adapter. |
| **Alert logic** | generate_lightning_summary.py (alert_state), lightning_nex_tail (compute_lightning_recent) | Trend, nearest-strike logic. Reuse with normalized input. |
| **Bearing → cardinal** | bearing_to_direction() in lightning_nex_tail | Reusable. |
| **Constants** | LIGHTNING_RULES_REFERENCE.md, generate_* scripts | CENTER_LAT/LON, CLOSE_RADIUS_KM, etc. Reuse. |
| **GeoJSON generators** | generate_lightning_points_v2.py | Expect ndjson with `timestamp_utc`, `raw_distance_km` or `trac_distance_km`, `raw_bearing_deg` or `trac_bearing_deg`, `strike_type`. Add Xweather→ndjson adapter. |
| **SVG assets** | lightning-bolt.svg, station-star.svg | Reuse. |

---

## 5. NexStorm-Specific Dependencies

| Item | Location | Coupling |
|------|----------|----------|
| **nxutil CSV parser** | parse_csv_row() in lightning_nex_tail | Columns S,B,D,C,T,P,X,Y,K,L |
| **Seconds-since-midnight → UTC** | to_canonical() | Assumes NexStorm local time (America/New_York) |
| **CG/IC encoding** | to_canonical() | type 0=CG, 1=IC |
| **Polarity encoding** | to_canonical() | polarity 0=pos, 1=neg |
| **SSH/SCP to Lightning-PC** | lightning_nex_tail | LIGHTNING_PC, NEXUTIL, NEX_DIR, REMOTE_OUT |
| **nxutil invocation** | lightning_nex_tail | `nxutil -extract -i YYYYMMDD -f ALL -o nex_tail.csv -validate` |
| **Field names** | lightning_rt.ndjson | raw_*, trac_* (NexStorm uses both) |
| **source** | lightning_rt.ndjson | "nex_archive" |
| **File watchers** | None | Polling every 3–5 s via SSH |
| **Input file** | nex_tail.csv | nxutil output on Lightning-PC |

---

## 6. Recommended Integration Plan

### Add Xweather as Additional Source

1. **New ingestion script:** `bin/lightning_xweather_fetch.py`
   - Calls Xweather API (or webhook/poll).
   - Converts Xweather response → **normalized MRW strike records** (see below).
   - Appends to a **separate** ndjson: `scratch/lightning_xweather/lightning_rt.ndjson` (or merged stream).

2. **Normalized MRW lightning schema** (both sources feed):

   ```json
   {
     "strike_id": "string (unique per strike)",
     "timestamp_utc": "ISO8601",
     "sensor_id": "MRW",
     "source": "nex_archive" | "xweather",
     "raw_bearing_deg": number,
     "raw_distance_km": number,
     "strike_type": "CG" | "IC"
   }
   ```

   Optional: `trac_*` for backward compatibility; generators already accept `raw_*` or `trac_*`.

3. **Merge strategy:**
   - **Option A:** Single `lightning_rt.ndjson` with both sources; generators read all, dedupe by (timestamp_utc, lon, lat).
   - **Option B:** Separate ndjson per source; new `generate_lightning_points_merged.py` reads both and merges.
   - **Recommendation:** Option A — append to same ndjson with `source` field; generators filter/dedupe as needed.

4. **Adapter layer:** Xweather → normalized schema
   - Xweather typically provides lon/lat. Compute `bearing_deg`, `distance_km` from MRW center using `pyproj.Geod.inv()` or equivalent.
   - Map Xweather strike type to CG/IC if available; else default CG.

5. **What stays unchanged:**
   - lightning_nex_tail.py (NexStorm pipeline)
   - generate_lightning_points_v2.py, generate_lightning_summary.py (add optional `--input` for merged ndjson)
   - All map players
   - lightning_range_rings.geojson
   - serve_frames, sync_to_wx_i9

6. **What needs adapter:**
   - Xweather API client → normalized ndjson records
   - Optional: merge script or unified generator input path

---

## 7. Fastest Path to Xweather-Backed Product

### Minimum Changes

1. **Create `bin/lightning_xweather_fetch.py`**
   - Fetch from Xweather API (e.g., strikes within radius of MRW center).
   - For each strike: compute `bearing_deg`, `distance_km` from center (Geod.inv).
   - Emit records matching: `timestamp_utc`, `raw_bearing_deg`, `raw_distance_km`, `strike_type`, `source: "xweather"`.
   - Append to `scratch/lightning_xweather/lightning_rt.ndjson` (or same scratch path with source tag).

2. **Create merged input**
   - `bin/merge_lightning_sources.py` — concatenates nex + xweather ndjson, dedupes by (timestamp_utc, lon, lat), writes `scratch/lightning_nex/lightning_rt_merged.ndjson`.
   - Or: have generators accept `--input` and `--input-xweather`, merge in memory.

3. **Simpler path:** Write Xweather strikes to **same** `lightning_rt.ndjson` with `source: "xweather"`. Generators already read ndjson and use `raw_distance_km` or `trac_distance_km` — ensure Xweather records have `raw_distance_km`, `raw_bearing_deg`. No generator changes.

4. **Run Xweather fetch**
   - Cron or systemd timer every 1–2 min (or per Xweather rate limits).
   - Append to `scratch/lightning_nex/lightning_rt.ndjson` (or dedicated file that merge script combines).

5. **Reuse unchanged:**
   - generate_lightning_points_v2.py (if input has required fields)
   - generate_lightning_summary.py
   - All players, serve_frames, wx-i9 deploy

### Fastest Path Summary

| Step | Action |
|------|--------|
| 1 | Implement `lightning_xweather_fetch.py` that outputs ndjson with `timestamp_utc`, `raw_bearing_deg`, `raw_distance_km`, `strike_type` |
| 2 | Append Xweather strikes to `lightning_rt.ndjson` (or a second file that gets merged before generators run) |
| 3 | Ensure generators read combined stream; they already support the schema |
| 4 | Schedule Xweather fetch (cron/timer) |
| 5 | No player changes; existing maps consume lightning_points_v2.geojson |

**Critical:** Xweather usually gives lon/lat. Use `Geod.inv(lon0, lat0, lon_strike, lat_strike)` to get forward azimuth and distance; convert to `bearing_deg` and `distance_km` for the normalized schema.
