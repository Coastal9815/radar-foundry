# MRW Lightning — Phase 1 Implementation Plan

**Status:** Plan only — no implementation yet.

**Phase 1 goal:** Establish the first working MRW lightning ingestion path and normalized strike pipeline.

**Prerequisite:** [Phase 0 Discovery](LIGHTNING_PHASE0_DISCOVERY_PLAN.md) must complete successfully. Do not implement the parser until all Phase 0 Go/No-Go criteria are satisfied.

**Architecture (approved):**
- Lightning-PC = acquisition only
- wx-core = primary lightning engine
- wx-i9 = rendering support if needed
- pi-wx = final JSON/API publisher

**Concepts (approved):** UTC timestamps, deterministic strike identity/provenance, canonical strike separate from derived products.

---

## 1. First Ingestion Path

### Recommendation: NexStorm Archive .nex Parsing (Full-File)

**Chosen path:** Pull daily `YYYYMMDD.nex` from Lightning-PC via scp; parse the full file; emit canonical strikes. Start with full-file parsing. Incremental tailing can be added once the parser is validated.

### Why This Is the Best Starting Path

| Option | Pros | Cons | Verdict |
|-------|------|------|---------|
| **.nex archive parsing** | Most evidence (16-byte records, append-only, header ~512). lightning_inspect_nex.py exists. No new infrastructure. scp already works. Full-file parse is simplest to validate. | Field layout still unknown; must determine via nxutil CSV or reverse-engineering. | **Best start** — foundation for everything else. |
| **Incremental .nex tailing** | Same parser as archive; lower latency. | Requires working parser first. Adds offset-tracking, day-rollover logic. | Phase 1.1 or Phase 2 — build after full-file works. |
| **FlashGate IPC** | Lowest latency. | NexStorm Lite may not support. Requires Windows relay, shared-memory protocol. High uncertainty. | Defer until .nex path is proven. |
| **nxutil export** | Produces human-readable CSV; validates format. | Windows-only. Lightning-PC is read-only (we don't run scripts there). Manual process: copy .nex to Windows dev box, run nxutil, scp CSV. Not a production ingest path. | Use for **format discovery** only — run once to infer 16-byte layout; then build .nex parser. |

**Rationale:** The .nex format has the strongest evidence from Phase 1 discovery. We can validate our parser by comparing output to nxutil CSV (if we obtain a sample). Full-file parsing is the minimal viable path: pull, parse, emit. Incremental tailing is an extension of the same parser. FlashGate and nxutil are either uncertain or not production paths for Phase 1.

**Flow:** Lightning-PC (.nex) → scp → wx-core → parse full file → canonical strikes → outputs.

---

## 2. Phase 1 Deliverables

### 2.1 Raw Ingestion

- Script that pulls .nex from Lightning-PC (reuse/adapt lightning_inspect_nex.py pull logic).
- Parser that reads 16-byte records from offset 512 (or determined header size).
- Emit raw/minimal records (timestamp, distance, bearing — as interpreted from bytes).
- Handle: missing file, empty file, partial records at end.

### 2.2 Canonical Strike Normalization

- Apply full canonical schema: timestamp (UTC), distance_mi, bearing_deg, lat, lon, strike_id, source, source_ref, ingested_at, raw.
- Compute strike_id from `(timestamp_utc, distance_mi, bearing_deg, sensor_id)`.
- Compute lat/lon from distance + bearing + sensor location (conf/basemap_geometry.json).
- Set source = `nex_archive`; source_ref = `{filename}@{offset}`.
- Preserve raw payload (original bytes or interpreted values) for reprocessing.

### 2.3 First Saved Output Products

- **lightning_strikes.jsonl** — One canonical strike per line (NDJSON). Full output of a parse run.
- **lightning_rt.json** — Prototype rolling buffer: last N strikes (e.g. 100) or last N minutes (e.g. 15). Array of canonical strikes, most recent last. Includes source metadata (sensor_lat, sensor_lon, generated_at_utc).

### 2.4 First Validation/Debug Outputs

- **lightning_parse_debug.json** — First N raw records with hex dump, interpreted fields, parse errors. For format validation.
- **lightning_validation_report.json** — Record count, timestamp range, distance/bearing stats, geo bounds. For sanity checks.
- Optional: **lightning_nxutil_compare.json** — If we have nxutil CSV for same file: row-by-row comparison, mismatch count. For parser validation.

---

## 3. File/Runtime Layout

### 3.1 Machine Responsibilities

| Machine | Phase 1 Role |
|---------|--------------|
| **Lightning-PC** | .nex files in place. No MRW code. Read-only pull only. |
| **wx-core** | Runs ingestion script. Pulls .nex, parses, normalizes, writes outputs. Syncs products to pi-wx. |
| **wx-i9** | Unused in Phase 1 (no overlay frames yet). |
| **pi-wx** | Receives lightning_rt.json (and optionally lightning_strikes.jsonl) from wx-core. Hosts in `/home/scott/dashboard/data/`. Served via existing HTTP/API. |

### 3.2 Directory Layout on wx-core

```
~/wx/radar-foundry/                    # Project root (or equivalent)
├── bin/
│   ├── lightning_inspect_nex.py      # Existing; format discovery
│   └── lightning_ingest.py           # NEW: Phase 1 ingest + normalize
├── conf/
│   ├── basemap_geometry.json         # Sensor lat/lon (center_lat, center_lon)
│   └── lightning.json                # NEW (optional): ingest config (paths, header size, etc.)
├── scratch/
│   └── lightning_nex/                # Existing
│       ├── YYYYMMDD.nex              # Pulled .nex (current or dated)
│       └── samples/                  # Timestamped snapshots (optional)
├── data/
│   └── lightning/                    # NEW: lightning output dir on wx-core
│       ├── lightning_strikes.jsonl    # Full strike output (NDJSON)
│       ├── lightning_rt.json          # Rolling buffer product
│       ├── lightning_parse_debug.json # Debug output
│       └── lightning_validation_report.json
└── docs/
    └── LIGHTNING_PHASE1_IMPLEMENTATION_PLAN.md
```

**Note:** `data/lightning/` may live under a machine-specific path (e.g. `~/wx-data/lightning/` on wx-core) if project uses separate data volumes. The plan assumes a `data/lightning/` dir under or alongside the project.

### 3.3 Raw Source Files

- **Lightning-PC:** .nex files remain in `C:\Program Files (x86)\Astrogenic\NexStormLite\` (or actual install path). Never modified.
- **wx-core scratch:** Pulled .nex in `scratch/lightning_nex/`. Can be overwritten on next pull (today's file) or retained for samples. No long-term retention required for Phase 1.

### 3.4 Normalized Data Location

- **wx-core:** `data/lightning/` — lightning_strikes.jsonl, lightning_rt.json, debug/validation files. This is the processing output.
- **pi-wx:** `/home/scott/dashboard/data/` — lightning_rt.json (and optionally lightning_strikes.jsonl if we publish it). Synced from wx-core. Matches existing pattern (air.json, now.json, etc.).

### 3.5 Sync to pi-wx

- wx-core runs: `rsync` or `scp` of `lightning_rt.json` (and any other published products) to `pi-wx:/home/scott/dashboard/data/`.
- Sync can be part of the ingest script (run after successful parse) or a separate cron/launchd step. Phase 1 should include this sync so pi-wx has the first product.

---

## 4. First MRW Outputs for Phase 1

### 4.1 lightning_strikes.jsonl (NDJSON)

**Purpose:** Full output of a parse run. One canonical strike per line. Used for validation, debugging, and as input to downstream products.

**Format:** Each line is a JSON object:
- timestamp (UTC, ISO 8601)
- distance_mi, bearing_deg
- lat, lon
- strike_id
- source (`nex_archive`)
- source_ref (`YYYYMMDD.nex@offset`)
- ingested_at (UTC)
- raw (optional; original values or hex)

**Location:** wx-core `data/lightning/lightning_strikes.jsonl`. Optionally synced to pi-wx if we expose it via API.

### 4.2 lightning_rt.json (Prototype)

**Purpose:** Rolling buffer product. First consumable lightning product for dashboards/sites.

**Format:**
```json
{
  "meta": {
    "sensor_lat": 31.919173,
    "sensor_lon": -81.075938,
    "source": "LD350",
    "generated_at_utc": "2026-03-14T19:00:00.000Z",
    "strike_count": 42
  },
  "strikes": [
    { "timestamp": "...", "distance_mi": 7.2, "bearing_deg": 182, "lat": 31.85, "lon": -81.02, "strike_id": "...", ... }
  ]
}
```

**Content:** Last N strikes (e.g. 100) or last N minutes (e.g. 15), most recent last. Phase 1 can use "last N strikes" for simplicity.

**Location:** wx-core `data/lightning/lightning_rt.json`; synced to pi-wx `dashboard/data/lightning_rt.json`.

### 4.3 lightning_parse_debug.json

**Purpose:** Debug output for format validation. First M records with raw bytes and interpreted fields.

**Format:** Array of objects: `{ "offset": 512, "hex": "...", "parsed": {...}, "error": null }`. Include parse errors for records that fail.

**Location:** wx-core `data/lightning/lightning_parse_debug.json`. Not synced to pi-wx.

### 4.4 lightning_validation_report.json

**Purpose:** Sanity checks. Record count, timestamp range, distance/bearing min/max, lat/lon bounds.

**Format:**
```json
{
  "source_file": "20260314.nex",
  "parsed_at_utc": "...",
  "record_count": 12980,
  "expected_records": 12980,
  "timestamp_min": "...",
  "timestamp_max": "...",
  "distance_mi_range": [0.5, 287.3],
  "bearing_deg_range": [12.1, 358.9],
  "lat_lon_bounds": { "min_lat": 30.2, "max_lat": 33.1, "min_lon": -82.5, "max_lon": -79.2 },
  "parse_errors": 0
}
```

**Location:** wx-core `data/lightning/lightning_validation_report.json`. Not synced to pi-wx.

---

## 5. Validation Plan

### 5.1 Parsing Correctness

- **Record count:** `(file_size - header_size) / 16` should equal number of parsed records. Remainder should be 0 (or handle +4 trailing bytes if observed).
- **Monotonic timestamps:** Within a single file, timestamps should be non-decreasing. Flag if not.
- **Value ranges:** distance_mi in [0, 300]; bearing_deg in [0, 360). Reject or flag out-of-range.
- **nxutil comparison:** If we obtain nxutil CSV for the same .nex file: parse CSV, compare our strikes to nxutil rows by timestamp (or order). Report matches, mismatches, and delta for distance/bearing. This is the gold-standard validation.

### 5.2 Bearing/Distance to Lat/Lon Conversion

- **Known tests:**
  - distance=0, bearing=any → point at sensor (lat, lon) = (sensor_lat, sensor_lon).
  - distance=X mi, bearing=90° → point X miles east of sensor. Verify lon delta ≈ X/69.0 (miles per degree longitude at this latitude).
  - distance=X mi, bearing=0° → point X miles north. Verify lat delta ≈ X/69.0.
- **Haversine round-trip:** Compute lat/lon from distance+bearing; compute distance+bearing from lat/lon; compare. Should match within floating-point tolerance.
- **Spot-check:** Pick a few strikes from a real storm, plot on map, verify they land in plausible locations (over water, land, etc.).

### 5.3 Archive vs Realtime Path (Later)

- When we add incremental tailing: process the same file twice — once full-file (archive), once incremental (simulate by parsing in two chunks). Overlapping region should produce identical strikes (same strike_id). Deduplication test.
- Phase 1 does not implement incremental; this validation is for Phase 1.1 or Phase 2.

---

## 6. Questions/Unknowns Before Implementing

### 6.1 Format (Must Answer)

| Question | How to Answer | Blocker? |
|----------|---------------|----------|
| **16-byte record field layout** — Which bytes are timestamp, distance, bearing? | Run nxutil on a sample .nex (copy to Windows, run nxutil, inspect CSV columns). Or reverse-engineer from byte patterns (e.g. 8-byte doubles for distance/bearing). | **Yes** — cannot parse without this. |
| **Timestamp format** — Unix epoch? Windows FILETIME? Seconds since midnight? | Infer from nxutil CSV; or test known strike time against byte values. | **Yes** |
| **Endianness** — Little-endian or big-endian? | Assume little-endian (Windows); verify with nxutil or known values. | **Yes** |
| **Header size** — 512 or 516 bytes? Trailing bytes? | Phase 1 discovery suggests 512. Verify with `(size - header) % 16 == 0`. | Minor |

### 6.2 Infrastructure (Should Answer)

| Question | How to Answer | Blocker? |
|----------|---------------|----------|
| **Exact .nex file path on Lightning-PC** | SSH to Lightning-PC, list `C:\Program Files (x86)\Astrogenic\NexStormLite\` (or check NexStorm config). lightning_inspect_nex.py uses this path. | **Yes** — pull will fail if wrong. |
| **NexStorm Lite vs Full install path** | Lite may use different dir. Verify path exists and contains YYYYMMDD.nex. | **Yes** |
| **Day rollover** — When does NexStorm create new file? | Midnight local? UTC? Observe file creation time. Phase 1 can ignore (single-day only). | No for Phase 1 |

### 6.3 Optional (Can Defer)

| Question | How to Answer | Blocker? |
|----------|---------------|----------|
| **nxutil availability** | Download from Astrogenic; run on Windows with sample .nex. | No — parser can be built without it; nxutil validates. |
| **Strike type (CG/IC) in .nex** | Inspect nxutil CSV or byte layout. | No — optional field. |
| **pi-wx sync mechanism** | Use rsync/scp from wx-core. Same as other product syncs. | No |

### 6.4 Pre-Implementation Checklist

**Phase 0 must complete first.** See [LIGHTNING_PHASE0_DISCOVERY_PLAN.md](LIGHTNING_PHASE0_DISCOVERY_PLAN.md) for full discovery tasks and Go/No-Go criteria.

Before writing lightning_ingest.py, Phase 0 must deliver:

1. [ ] .nex path confirmed and pull verified.
2. [ ] nxutil CSV obtained; 16-byte layout documented.
3. [ ] Timestamp encoding, endianness, distance/bearing fields determined.
4. [ ] Cross-check: at least one CSV row validated against raw bytes.
5. [ ] Sensor location in conf/basemap_geometry.json confirmed.

---

## 7. Phase 1 Success Criteria

- [ ] Pull .nex from Lightning-PC to wx-core scratch.
- [ ] Parse 16-byte records; emit canonical strikes with full schema.
- [ ] lightning_strikes.jsonl contains valid NDJSON; record count matches expected.
- [ ] lightning_rt.json contains last N strikes; valid JSON; synced to pi-wx.
- [ ] lightning_validation_report.json shows no parse errors; value ranges plausible.
- [ ] Geo conversion: at least one known test passes (distance=0, bearing=90, etc.).
- [ ] Optional: nxutil comparison shows high match rate (if nxutil CSV obtained).

---

## 8. References

- [LIGHTNING_ARCHITECTURE_CLARIFICATION.md](LIGHTNING_ARCHITECTURE_CLARIFICATION.md) — UTC, strike identity, Model A, canonical vs derived
- [LIGHTNING_ARCHITECTURE_REFINEMENT.md](LIGHTNING_ARCHITECTURE_REFINEMENT.md) — Canonical model, products
- [lightning_pipeline_plan.md](lightning_pipeline_plan.md) — .nex format discovery, Phase 1 results
- [pi-wx-weather-inventory.md](pi-wx-weather-inventory.md) — pi-wx data path
- `conf/basemap_geometry.json` — Sensor coordinates
- `bin/lightning_inspect_nex.py` — Pull and inspect logic

---

*Document created 2026-03-14. Phase 1 implementation plan only — no code yet.*
