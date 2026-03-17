# MRW Lightning Platform — Architecture Plan

**Status:** Planning only — no implementation yet.

**Principle:** Lightning is a **shared MRW subsystem**, not a Master Dashboard feature. All MRW products (dashboards, players, sites, alerts, animations) consume the same truth-layer outputs.

**Architecture goal:**
```
LD-350 / NexStorm / extraction / MRW lightning processor
    → shared lightning data products
    → dashboards / sites / alerts / animations
```

---

## 1. Source Inputs

### 1.1 LD-350 (Hardware)

- **Boltek LD-350**: Single-station lightning detector, ~300 mile range
- **Connection**: USB to Windows PC
- **Output**: NMEA-like sentences over USB (`$WIMLI,<dist>,<bearing>*<checksum>`)
- **Role**: Raw strike acquisition; NexStorm is the software that receives and processes this data

### 1.2 NexStorm Realtime Data Options

| Option | Description | Latency | Notes |
|--------|--------------|---------|-------|
| **FlashGate IPC** | Windows shared-memory IPC; strike and storm data sent live to external apps (e.g. StormVue) | Near real-time | Full NexStorm feature; C++ demo + source (`nxipc_src.zip`) available from Astrogenic. **Verify:** Does NexStorm Lite include FlashGate? |
| **Tail .nex file** | Pull latest bytes from daily `YYYYMMDD.nex` on Lightning-PC; incremental read | 1–2 min (pull interval) | Simpler; no Windows bridge. Append-only format supports tail reads. |
| **NexStorm file export** | Timed file copy, FTP upload of screenshots/TRAC reports | Minutes | Not strike-level data; report/screenshot only. |

**Recommendation:** Evaluate FlashGate for lowest latency; fall back to tail-.nex for simplicity if FlashGate is unavailable or too complex to bridge.

### 1.3 NexStorm Archive (.nex) Options

| Option | Description | Use Case |
|--------|--------------|----------|
| **Daily .nex files** | `YYYYMMDD.nex` in `C:\Program Files (x86)\Astrogenic\NexStormLite\` (or NexStorm install path) | Primary archive source. Append-only, fixed 16-byte records, ~512-byte header. |
| **Pull via SCP** | wx-core (or wx-i9) pulls from Lightning-PC; read-only, no writes to Lightning-PC | Production ingest path. |
| **nxutil extraction** | `nxutil.exe` (v1.1) — Astrogenic CLI; reads .nex, exports to CSV | Format validation, repair, bulk extraction. Windows-only. |

**Known .nex format (Phase 1 discovery):**
- Append-only
- Header ~512 bytes (ASCII "NexStorm Archive File Version 1.2" + binary)
- Fixed 16-byte records
- Field layout (timestamp, distance, bearing, etc.) still to be determined

### 1.4 nxutil Extraction Role

- **What it does**: Command-line archive repair and extract; converts .nex to human-readable CSV
- **Where it runs**: Windows only (included with NexStorm in `util` dir; also downloadable from Astrogenic)
- **MRW use**:
  - **Format discovery**: Run nxutil on a sample .nex (on Lightning-PC or a Windows dev box) to get CSV; reverse-engineer field layout from CSV columns
  - **Bulk extraction**: For historical backfill or one-off exports, run nxutil on Lightning-PC, scp CSV to MRW
  - **Limitation**: Lightning-PC is read-only — we do not run scripts there. nxutil would run only for manual/one-off extraction, or we'd need a Windows machine in the pipeline (not currently planned)

### 1.5 FlashGate IPC Role

- **What it is**: Real-time inter-process communication; NexStorm writes strike and storm-tracking data to Windows shared memory
- **Consumers**: StormVue, or custom C++ app using the demo source
- **MRW use**:
  - **Option A**: Build a small Windows relay on Lightning-PC that reads FlashGate, forwards strikes via HTTP/WebSocket to wx-core or wx-i9
  - **Option B**: If FlashGate is not available in NexStorm Lite, use tail-.nex as the realtime path
- **Unknown**: Whether NexStorm Lite includes FlashGate (full NexStorm does)

---

## 2. Recommended MRW Product Outputs

Truth-layer outputs that all MRW consumers use. No computation in dashboards or players.

### 2.1 Core JSON Products

| Product | Purpose | Update Cadence | Consumers |
|---------|---------|----------------|-----------|
| **lightning_rt.json** | Live rolling buffer of most recent strikes (e.g. last 5–15 min) | Near real-time (1–2 min) | Map overlays, live dashboards, alert evaluation |
| **lightning_recent.json** | Time-windowed strikes for display (5, 30, 60 min windows) | 1–2 min | Map layers, Master Dashboard, players |
| **lightning_cells.json** | Storm cell / TRAC-style clusters (if we implement clustering) | 2–5 min | Map overlays, threat bar, storm tracking |
| **lightning_alerts.json** | Active lightning alerts (e.g. strikes within N mi, rate thresholds) | 1–2 min | Threat bar, Master Dashboard, notifications |
| **lightning_archive_index.json** | Index of available archive days/files for replay | Daily or on demand | Archive UI, replay products |

### 2.2 Map Overlay / Animation Products

| Product | Purpose | Format | Consumers |
|---------|---------|--------|-----------|
| **Lightning overlay frames** | Raster frames (PNG) with strike points, optionally faded by age | Same pattern as radar (frame dir + manifest) | KCLX/KJAX/MRMS Mapbox players, Master Dashboard |
| **Strike GeoJSON** | Vector points for Mapbox circle/symbol layers | GeoJSON FeatureCollection | Players, dashboards (alternative to raster) |

### 2.3 Optional / Future

| Product | Purpose |
|---------|---------|
| **lightning_density.json** | Precomputed density grid for heatmap display |
| **lightning_stats.json** | Strike rate, daily/hourly counts for dashboard widgets |
| **Archive replay manifest** | Per-day manifest for replay mode (similar to radar frame manifests) |

### 2.4 Schema Conventions

- **Strike (normalized)**: `{ timestamp, distance_mi, bearing_deg, lat, lon, raw?, type? }`
- **Source metadata**: `{ source: "LD350", sensor: "MoonRiverWeather", sensor_lat, sensor_lon }` (from `conf/basemap_geometry.json`)
- **ISO 8601** timestamps with timezone (America/New_York)

---

## 3. Realtime vs Archive Architecture

### 3.1 Realtime Ingestion

**Purpose:** Sub-2-minute latency for live displays, alerts, and animations.

**Sources (in order of preference):**
1. **FlashGate IPC** → Windows relay → HTTP/WebSocket push to MRW processor
2. **Tail .nex** → Periodic pull from Lightning-PC; incremental read of new bytes; parse new records

**Outputs from realtime:**
- `lightning_rt.json` — rolling buffer
- `lightning_recent.json` — 5/30/60 min windows
- `lightning_alerts.json` — alert evaluation
- Live overlay frames (if animation pipeline runs on same cadence)

**Characteristics:**
- Append-only tail of today's .nex is sufficient
- No need to re-read entire archive
- Track last-read offset; handle day rollover (switch to new YYYYMMDD.nex)

### 3.2 Archive Extraction

**Purpose:** Historical replay, backfill, analysis, calibration.

**Sources:**
- Full .nex files (past days) pulled from Lightning-PC
- Bulk parse entire file(s)
- Optional: nxutil CSV export for validation or one-off extraction

**Outputs from archive:**
- `lightning_archive_index.json` — which days we have
- Per-day or per-range JSON/GeoJSON for replay
- Backfill into `lightning_recent`-style products for historical views

**Characteristics:**
- Batch processing; not latency-sensitive
- Can run overnight or on-demand
- Enables "replay mode" similar to radar loops

### 3.3 How They Complement Each Other

| Aspect | Realtime | Archive |
|--------|----------|---------|
| **Data source** | Tail of today's .nex, or FlashGate | Full .nex files (any date) |
| **Processing** | Incremental, offset-tracked | Full-file parse |
| **Products** | rt, recent, alerts, live frames | Index, replay datasets |
| **Cadence** | 1–2 min | Daily, on-demand |
| **Use case** | Live dashboards, alerts | Replay, analysis, backfill |

**Unified strike model:** Both paths produce the same normalized strike format. Realtime and archive outputs are interchangeable for consumers.

---

## 4. Machine Responsibilities

| Machine | Role | Rationale |
|---------|------|-----------|
| **Lightning-PC** (192.168.2.223) | Acquisition only. NexStorm + LD-350. Produces .nex. Read-only for MRW. | Windows required for LD-350/NexStorm. No MRW software runs here. |
| **weather-core** (wx-core) | Pull .nex, realtime ingest, archive extraction, animation generation (candidate) | Mac Studio; strong compute. Already runs radar/satellite pipelines. Good for Python ingest. |
| **wx-i9** | Alternative for ingest + animation; publishing; HTTP serve | Ubuntu, 1TB wx-data. Serves all players. Could run lightning processor if we want "compute where you serve." |
| **pi-wx** | Unlikely for lightning | Truth layer for station data; lightning is external source. Could host products if we sync there, but ingest belongs on wx-core or wx-i9. |

### Recommended Assignment

| Responsibility | Machine | Notes |
|----------------|---------|------|
| **Acquisition** | Lightning-PC | NexStorm only; no MRW code |
| **Pull** | wx-core | scp from Lightning-PC; or wx-i9 if preferred |
| **Realtime processing** | wx-core | Incremental ingest, offset tracking, JSON products |
| **Archive extraction** | wx-core | Full .nex parse, backfill, index |
| **Animation generation** | wx-core or wx-i9 | Render overlay frames; same pattern as radar |
| **Publishing** | wx-i9 | Products in serve_root; HTTP 8080. Sync from wx-core if processing there. |

**Flexibility:** Processing can move to wx-i9 if we want to colocate with serve_frames and reduce sync hops. Start with wx-core to match existing radar/satellite pattern.

---

## 5. Product Roadmap

### Phase 1: Raw Ingestion

- Pull .nex from Lightning-PC (scp)
- Incremental read: track offset, handle day rollover
- Parse 16-byte records (field layout from nxutil CSV or reverse-engineering)
- Output: raw or minimally normalized strike stream (internal)
- **Deliverable:** `lightning_ingest.py` running on schedule; validated strike output

### Phase 2: Normalized Strike Model

- Normalize to MRW strike schema (timestamp, distance_mi, bearing_deg, lat, lon)
- Apply sensor location from `conf/basemap_geometry.json`
- Preserve raw values for debugging
- **Deliverable:** Canonical strike format; unit tests for geo conversion

### Phase 3: Live JSON Products

- `lightning_rt.json` — rolling buffer (e.g. last 15 min)
- `lightning_recent.json` — 5/30/60 min windows
- Publish to serve_root (or pi-wx data dir if we adopt that pattern)
- **Deliverable:** Products consumable by any MRW client

### Phase 4: Map Overlays / Animation

- Generate overlay frames (PNG with strike points, age-based opacity)
- Frame manifest for loop playback
- Integrate into KCLX/KJAX/MRMS Mapbox players
- Optional: GeoJSON layer for vector rendering
- **Deliverable:** Lightning layer on radar players; Master Dashboard lightning module

### Phase 5: Alerts

- `lightning_alerts.json` — rules (e.g. strikes within 10 mi, rate > N/min)
- Feed into Master Dashboard threat bar
- **Deliverable:** Lightning alerts in threat bar; configurable thresholds

### Phase 6: Archive / Replay Products

- `lightning_archive_index.json` — available days
- Archive extraction for historical dates
- Replay mode: time-windowed strikes for past days
- **Deliverable:** Archive browser, replay in players or dedicated UI

---

## 6. Risks / Unknowns

### 6.1 NexStorm / Lightning-PC

| Risk | Mitigation |
|------|------------|
| **NexStorm Lite lacks FlashGate** | Use tail-.nex as realtime path; accept 1–2 min latency |
| **.nex file location varies** | Document actual path on Lightning-PC; make configurable |
| **NexStorm version differences** | Test with current install; document version in plan |
| **Day rollover timing** | NexStorm may create new file at midnight local; verify behavior |
| **Partial writes** | Validate record before commit; handle mid-record appends |

### 6.2 Format / Parsing

| Risk | Mitigation |
|------|------------|
| **16-byte record field layout unknown** | Run nxutil on sample; or analyze byte patterns (timestamps, distance 0–300, bearing 0–360) |
| **Endianness** | Assume little-endian (Windows); verify with known values |
| **Timestamp format** | Could be Unix, Windows FILETIME, or custom; infer from nxutil CSV |
| **nxutil not on Lightning-PC** | Copy sample .nex to a Windows dev box; run nxutil there for CSV |

### 6.3 FlashGate IPC

| Risk | Mitigation |
|------|------------|
| **FlashGate requires Full NexStorm** | Confirm with Astrogenic or docs; fall back to tail-.nex |
| **Shared memory API undocumented** | Use nxipc_src.zip demo; reverse-engineer protocol |
| **Windows relay adds complexity** | Defer to Phase 2+; start with tail-.nex |
| **StormVue dependency** | FlashGate is independent; we can build our own consumer |

### 6.4 Operations

| Risk | Mitigation |
|------|------------|
| **Lightning-PC offline** | Graceful degradation; stale data; alerting |
| **.nex stops updating** | Compare mtime/size over interval; alert if stale |
| **SSH/scp failures** | Retry with backoff; log; optional local cache |

---

## 7. References

- [lightning_pipeline_plan.md](lightning_pipeline_plan.md) — Phase 1 discovery, ingest requirements
- [ld350_lightning_plan.md](ld350_lightning_plan.md) — LD-350 hardware, $WIMLI format
- [WXForum: NexStorm Archive Files](https://www.wxforum.net/index.php?topic=691.0)
- [Astrogenic NexStorm](https://astrogenic.com/?p=nexstorm) — FlashGate, nxutil
- [Astrogenic Downloads](https://www.astrogenic.com/?p=downloads) — nxutil, FlashGate source
- `conf/basemap_geometry.json` — MRW sensor coordinates (31.919, -81.076)

---

*Document created 2026-03-14. Architecture only — no implementation.*
