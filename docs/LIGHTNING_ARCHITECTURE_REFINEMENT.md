# MRW Lightning Subsystem — Architecture Refinement

**Status:** Design refinement — no implementation yet.

**Principle:** Lightning follows the MRW pattern: **generators → shared JSON products → dashboards / sites**. It is a shared subsystem, not a Master Dashboard feature.

**Scope:** Architecture and data flow only. No code, no UI assumptions.

**See also:** [LIGHTNING_ARCHITECTURE_CLARIFICATION.md](LIGHTNING_ARCHITECTURE_CLARIFICATION.md) — UTC time standard, strike identity/provenance, Model A (pi-wx as publisher), canonical vs derived separation. The clarification supersedes this document on those points.

---

## 1. Canonical Strike Model Concept

All lightning sources produce different formats. The MRW lightning system converts every source into a single **canonical strike record** internally. Consumers never see raw source data; they consume normalized products.

### 1.1 What a Normalized Strike Record Must Contain

A canonical strike record is the atomic unit of lightning data. It must support five use cases: realtime processing, map display, strike alerts, storm clustering, and archive replay.

#### Identity and Time

- **Timestamp** — When the strike occurred. Must be precise (sub-second if available) and timezone-aware (ISO 8601, America/New_York). Required for: ordering strikes chronologically, filtering by time window, computing strike rate, age-based fading on maps, and replay synchronization.
- **Source identifier** — Which ingestion path produced this record (e.g. `nex_realtime`, `nex_archive`, `flashgate`, `nxutil`). Optional but useful for debugging and understanding data lineage.

#### Location (Sensor-Relative)

- **Distance (miles)** — Range from the detector. LD-350 reports 0–300 mi. Required for: proximity alerts ("strikes within 10 mi"), distance-based filtering, and validation (reject out-of-range).
- **Bearing (degrees)** — Azimuth from detector, 0–360. Required for: computing lat/lon, directional storm tracking, and bearing-based clustering.

#### Location (Geographic)

- **Latitude, longitude** — Computed from distance + bearing + sensor location. Required for: map display (any projection), GeoJSON output, spatial queries, and overlay rendering. Single-station geometry has inherent uncertainty; we store the computed point as the best estimate.

#### Provenance and Debugging

- **Raw payload** — Original source values (e.g. raw distance, raw bearing, raw timestamp bytes) preserved for reprocessing, calibration, and format validation. Optional in published products; essential in internal pipeline.

#### Optional Enrichments (Source-Dependent)

- **Strike type** — Cloud-to-ground (CG) vs intra-cloud (IC) if NexStorm provides it. LD-350 can classify; not all sources include this. Useful for: filtering, display styling, and storm analysis.
- **Polarity** — Positive/negative if available. NexStorm full version may provide; Lite may not. Useful for advanced analysis; not required for core products.

### 1.2 What the Model Explicitly Does Not Include

- **Storm cell assignment** — Cell membership is derived by clustering, not stored on the strike. Cells are a separate product.
- **Alert state** — Whether a strike triggered an alert is computed at alert-evaluation time, not stored on the strike.
- **Display metadata** — Opacity, color, size are computed by the consumer from timestamp (age) and config. Not part of the canonical record.

### 1.3 Why This Model Works Across Use Cases

| Use Case | Fields Used | Rationale |
|----------|-------------|-----------|
| **Realtime processing** | Timestamp, distance, bearing, lat, lon | Enables immediate filtering, windowing, and product generation. Source ID helps trace pipeline issues. |
| **Map display** | Lat, lon, timestamp | Geographic placement; timestamp drives age-based styling (client-side or precomputed in overlay frames). |
| **Strike alerts** | Timestamp, distance (or lat/lon), bearing | Proximity rules (distance < N mi); rate rules (count per time window). Timestamp for recency. |
| **Storm clustering** | Lat, lon, timestamp | Spatial and temporal clustering (e.g. DBSCAN, time-windowed) to form cells. No cell ID on strike; cells are derived. |
| **Archive replay** | Timestamp, lat, lon, distance, bearing | Replay is time-ordered strike playback. Same format as realtime; consumers need not distinguish. |

The canonical model is **minimal and complete**: it has everything needed for downstream products and nothing that belongs in a derived layer.

---

## 2. Ingestion Pipeline Concept

Each source feeds into a **source adapter** that converts raw data into canonical strike records. Adapters are the only place that understands source-specific formats. Downstream processing is source-agnostic.

### 2.1 NexStorm Realtime Data

**Format:** NexStorm may expose realtime strikes via a live API, socket, or file stream. The exact mechanism is TBD (FlashGate vs tail-.nex).

**Adapter behavior:**
- Receive strike events as they occur (or poll at short interval).
- Extract timestamp, distance, bearing from NexStorm's format.
- Compute lat/lon from sensor location.
- Emit canonical strike records to the **strike stream** (internal buffer or queue).
- Preserve raw values in a `raw` field for debugging.

**Flow:** NexStorm → (relay if needed) → MRW realtime adapter → strike stream → product generators.

### 2.2 FlashGate IPC

**Format:** Windows shared memory; NexStorm writes strike and storm data. Protocol defined by Astrogenic demo (nxipc_src.zip).

**Adapter behavior:**
- Run a process that attaches to FlashGate shared memory (Windows-only; likely a small relay on Lightning-PC).
- Parse strike messages from shared memory.
- Map FlashGate fields to canonical model (timestamp, distance, bearing → lat, lon).
- Forward strikes to MRW processor (HTTP POST, WebSocket, or similar).
- The MRW side has a **FlashGate adapter** that receives forwarded strikes and emits canonical records into the strike stream.

**Flow:** NexStorm → FlashGate shared memory → Windows relay → network → MRW FlashGate adapter → strike stream.

**Note:** If NexStorm Lite lacks FlashGate, this path is unavailable. The tail-.nex path becomes the realtime source.

### 2.3 .nex Archive Files

**Format:** Daily `YYYYMMDD.nex`, append-only, fixed 16-byte records, ~512-byte header. Field layout to be determined (via nxutil CSV or reverse-engineering).

**Adapter behavior:**
- **Realtime mode:** Pull file via scp; read from last-known offset; parse new 16-byte records; convert each to canonical strike; append to strike stream. Handle day rollover (new file at midnight).
- **Archive mode:** Pull full file; parse all records; emit canonical strikes. No offset tracking; full-file pass. Output may go to replay storage or backfill products.
- Both modes use the same record parser and geo conversion. Only the read strategy (incremental vs full) differs.

**Flow:** Lightning-PC (.nex) → scp → MRW → .nex adapter (incremental or full) → strike stream or archive storage.

### 2.4 nxutil Export

**Format:** CSV from nxutil.exe. Column layout from Astrogenic; human-readable.

**Adapter behavior:**
- Parse CSV rows.
- Map columns to canonical fields (timestamp, distance, bearing).
- Compute lat/lon.
- Emit canonical strikes. Used for: format validation (compare nxutil output to our .nex parser), one-off backfill, or manual extraction when .nex parser is incomplete.

**Flow:** Lightning-PC or Windows dev box → nxutil → CSV → scp → MRW → nxutil adapter → strike stream or batch output.

**Note:** nxutil runs on Windows only. Lightning-PC is read-only. nxutil is typically used for manual/one-off extraction or format discovery, not as a production ingest path.

### 2.5 Unified Strike Stream

All adapters feed into a **strike stream** — a conceptual buffer of canonical strike records. The stream is consumed by:

- **Product generators** — Build lightning_rt, lightning_recent, lightning_cells, lightning_alerts.
- **Animation pipeline** — Renders overlay frames from strikes in a time window.
- **Archive writer** — Persists strikes for replay (if we store raw strike history).

In practice, the "stream" may be in-memory (realtime) or file-based (archive batch). The key is that all sources produce the same canonical format before any product logic runs.

---

## 3. Product Outputs

Products are generated from the normalized strike model. No product recomputes from raw source data. Products are the shared truth-layer outputs for all MRW consumers.

### 3.1 lightning_rt.json

**Purpose:** Live rolling buffer of the most recent strikes (e.g. last 5–15 minutes).

**Content:** Array of canonical strike records, most recent last. Optionally capped by count or time window.

**Consumers:** Map overlays (live layer), alert evaluation, Master Dashboard live widget, website live map.

**Update cadence:** 1–2 minutes (or faster if FlashGate).

### 3.2 lightning_recent.json

**Purpose:** Time-windowed strikes for display. Multiple windows (5, 30, 60 min) or a single configurable window.

**Content:** Array of canonical strikes within the requested window(s). May include metadata: window start/end, strike count.

**Consumers:** Map layers (with age-based fading), Master Dashboard, players, website. Clients can choose which window to display.

**Update cadence:** 1–2 minutes.

### 3.3 lightning_cells.json

**Purpose:** Storm cell / cluster data. Derived from strike clustering (spatial + temporal).

**Content:** Array of cell objects. Each cell: centroid (lat, lon), strike count, time range, bounding region or radius. Cell membership is derived; strikes are not stored in the cell, but cell geometry can be used for display.

**Consumers:** Map overlays (cell markers), threat bar ("storm 12 mi NE"), storm tracking displays.

**Update cadence:** 2–5 minutes (clustering has higher cost).

### 3.4 lightning_alerts.json

**Purpose:** Active lightning alerts based on configurable rules (e.g. strikes within N mi, rate > X/min).

**Content:** Array of active alerts. Each: alert type, severity, message, triggered-at, optional geometry (e.g. "strikes within 10 mi").

**Consumers:** Master Dashboard threat bar, website alerts, notification systems.

**Update cadence:** 1–2 minutes (evaluated from lightning_rt or lightning_recent).

### 3.5 lightning_archive_index.json

**Purpose:** Index of available archive data for replay.

**Content:** List of dates (or date ranges) for which we have extracted strike data. May include file paths or product URLs for replay.

**Consumers:** Archive browser, replay UI, backfill tools.

**Update cadence:** Daily or on extraction.

### 3.6 Animation Frame Products

**Purpose:** Raster overlay frames (PNG) for loop playback, matching radar/satellite pattern.

**Content:** Frame directory with PNGs; manifest (frame list with timestamps). Each frame: strike points rendered with age-based opacity over basemap or transparent overlay.

**Consumers:** KCLX/KJAX/MRMS Mapbox players, Master Dashboard embedded player, wall displays.

**Update cadence:** Same as radar loop (e.g. every 2 min for live; on-demand for replay).

### 3.7 GeoJSON Outputs

**Purpose:** Vector strike points for Mapbox circle/symbol layers. Alternative to raster overlays.

**Content:** GeoJSON FeatureCollection. Each feature: Point geometry (lat, lon), properties (timestamp, distance, bearing, age).

**Consumers:** Players that prefer vector layers, website map, custom overlays.

**Update cadence:** 1–2 minutes; can be derived from lightning_recent.

---

## 4. Machine Roles

### 4.1 Lightning-PC (192.168.2.223)

**Role:** Acquisition only. Read-only for MRW.

**Responsibilities:**
- Run NexStorm Lite (or Full) with LD-350 connected via USB.
- Produce daily .nex archive files.
- Optionally: Run FlashGate relay (if we build one) to forward strikes in realtime.

**Does not:** Run MRW ingest code, process data, or publish products. We only pull from it.

### 4.2 wx-core (weather-core, M1 Ultra)

**Role:** Primary compute for lightning pipeline.

**Responsibilities:**
- **Ingestion:** Pull .nex from Lightning-PC via scp. Run incremental (realtime) and full-file (archive) parsers.
- **Processing:** Source adapters, canonical strike model, product generators (lightning_rt, lightning_recent, lightning_cells, lightning_alerts).
- **Animation generation:** Render overlay frames from strike data. Same pattern as radar (render → publish).
- **Publishing:** Write products to local output dir; sync to wx-i9 (or push via rsync/scp).

**Rationale:** wx-core already runs radar, satellite, and NWS pipelines. Colocating lightning keeps the pattern consistent. M1 Ultra has ample compute for clustering and frame rendering.

### 4.3 wx-i9 (192.168.2.2)

**Role:** Serve and publish. Optional processing.

**Responsibilities:**
- **Publishing:** Host lightning products in serve_root. HTTP 8080 via serve_frames. Products are synced from wx-core (or written directly if we run ingest there).
- **Optional processing:** Could run the lightning pipeline if we prefer "compute where you serve" — reduces sync hops. Trade-off: wx-core has more powerful CPU; wx-i9 is closer to clients.

**Rationale:** All players and dashboards load from wx-i9. Lightning products must be served from there. Processing can live on wx-core (recommended) or move to wx-i9 for colocation.

### 4.4 pi-wx (192.168.2.174)

**Role:** Unlikely for lightning. Possible product hosting.

**Responsibilities:**
- **Truth layer for station data:** pi-wx runs gen_now, gen_air, gen_climatology, etc. Lightning is an external source; it does not originate on pi-wx.
- **Optional:** If we want lightning products on api.moonriverweather.com, we could sync lightning_rt, lightning_recent to pi-wx data dir and expose via the same API. Not required for LAN dashboards; useful for public website.

**Rationale:** Lightning ingest and processing belong on wx-core or wx-i9. pi-wx could host products only if we adopt a "all MRW products on pi-wx API" pattern. Defer unless needed.

### 4.5 Summary Table

| Responsibility       | Lightning-PC | wx-core | wx-i9 | pi-wx |
|----------------------|--------------|---------|-------|-------|
| Acquisition          | ✓            | —       | —     | —     |
| Pull .nex            | —            | ✓       | —     | —     |
| Ingestion / Adapters | —            | ✓       | opt   | —     |
| Product generation   | —            | ✓       | opt   | —     |
| Animation frames     | —            | ✓       | opt   | —     |
| Publish / HTTP serve | —            | —       | ✓     | opt   |

---

## 5. Implementation Phases

### Phase 1 — Ingestion

**Goal:** Raw data flows from sources into the pipeline.

**Scope:**
- Pull .nex from Lightning-PC (scp).
- Incremental read: track offset, handle day rollover.
- Parse 16-byte records (field layout from nxutil CSV or reverse-engineering).
- Output: internal strike stream (raw or minimally normalized).
- Optional: FlashGate relay + adapter if we validate FlashGate availability.

**Deliverable:** Ingestion running on schedule; validated strike output. No published products yet.

### Phase 2 — Normalization

**Goal:** All sources produce canonical strike records.

**Scope:**
- Implement canonical strike model (timestamp, distance_mi, bearing_deg, lat, lon, raw).
- Apply sensor location from conf/basemap_geometry.json.
- Source adapters for: .nex (realtime + archive), nxutil CSV (validation).
- Unit tests for geo conversion, timestamp handling.
- Preserve raw values for debugging.

**Deliverable:** Canonical format; all adapters emit identical structure. Downstream logic is source-agnostic.

### Phase 3 — Live JSON Products

**Goal:** Shared products consumable by any MRW client.

**Scope:**
- lightning_rt.json — rolling buffer.
- lightning_recent.json — 5/30/60 min windows.
- Publish to serve_root (sync from wx-core to wx-i9).
- Source metadata in products (sensor_lat, sensor_lon, source).

**Deliverable:** Products on wx-i9; Master Dashboard, website, players can consume.

### Phase 4 — Overlays / Animations

**Goal:** Lightning layer on map players and displays.

**Scope:**
- Generate overlay frames (PNG) from strike data; age-based opacity.
- Frame manifest for loop playback.
- Integrate into KCLX/KJAX/MRMS Mapbox players.
- Optional: GeoJSON layer for vector rendering.

**Deliverable:** Lightning visible on radar players; Master Dashboard lightning module.

### Phase 5 — Alerts

**Goal:** Lightning alerts in threat bar and notification systems.

**Scope:**
- lightning_alerts.json — rules (proximity, rate).
- Configurable thresholds (e.g. strikes within 10 mi, rate > 5/min).
- Feed into Master Dashboard threat bar.

**Deliverable:** Alerts displayed; config-driven rules.

### Phase 6 — Archive / Replay

**Goal:** Historical replay and archive browser.

**Scope:**
- lightning_archive_index.json — available days.
- Archive extraction for historical .nex files.
- Replay products: time-windowed strikes for past days.
- Replay mode in players or dedicated UI.

**Deliverable:** Archive browser; replay capability.

---

## 6. References

- [LIGHTNING_ARCHITECTURE_PLAN.md](LIGHTNING_ARCHITECTURE_PLAN.md) — Broader platform plan, sources, risks
- [lightning_pipeline_plan.md](lightning_pipeline_plan.md) — Phase 1 discovery, .nex format
- [ld350_lightning_plan.md](ld350_lightning_plan.md) — LD-350 hardware
- `conf/basemap_geometry.json` — MRW sensor coordinates

---

*Document created 2026-03-14. Architecture refinement only — no implementation.*
