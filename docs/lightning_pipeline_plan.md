# MRW Lightning Ingest Pipeline — Plan

**Status:** FlashGate primary path implemented; .nex secondary for archive/backfill

## Overview

Add a lightning ingest pipeline to Moon River Weather (MRW) using data from a Boltek LD-350 detector via NexStorm Lite on Lightning-PC.

**Primary path:** FlashGate IPC-1 → Windows relay (scripts/lightning/windows/flashgate_relay.py) → lightning_rt.ndjson, lightning_status.json.

**Secondary path:** .nex archive + nxutil for backfill/replay. Do not reverse-engineer .nex for live pipeline.

---

## Lightning-PC: Strictly Read-Only

| Rule | Meaning |
|------|---------|
| No writes | Never create, modify, or delete files on Lightning-PC |
| No installs | No software installation or updates |
| No background jobs | No scheduled tasks, services, or daemons on Lightning-PC |
| No file modifications | Do not touch NexStorm files or config |
| No changes to NexStorm | Treat NexStorm as a black-box producer |

**Data access:** wx-core pulls via SSH + scp only. Lightning-PC is a read-only data appliance.

---

## Architecture

```
Lightning-PC (192.168.2.223)
   │  NexStorm Lite (unchanged)
   │  Daily .nex archive (YYYYMMDD.nex)
   ↓
wx-core (pull via SSH, all processing local)
   │  bin/lightning_inspect_nex.py  (Phase 1: discovery)
   │  bin/lightning_ingest.py       (Phase 2: ingest)
   ↓
Normalized JSON / GeoJSON
   ↓
serve_root/lightning.json, Mapbox layers, dashboards
```

---

## Phase 1: Format Discovery (Evidence-Based)

**Goal:** Characterize the .nex file format through inspection and comparison. Do not assume structure.

### Phase 1 Discovery Results (2026-03-12)

**Evidence from two timestamped snapshots** (20260312_snap1.nex, 20260312_snap2.nex, ~45s apart):

| Finding | Evidence |
|---------|----------|
| **Append-only** | Common prefix = 2,284,628 bytes; snap2 has exactly 207,680 additional bytes at end. No mid-file differences. |
| **ASCII header extent** | First null at offset 33. ASCII region: `NexStorm Archive File Version 1.2` |
| **Header boundary** | Bytes 0x00–0x1df: ASCII + null padding. Bytes 0x1e0–0x1ff: binary (e.g. `0c 00 00 00`, `14 6b 00 00`, `0a 13 00 00`, `f1 00 00 00`). Natural boundary: 512 bytes (0x200). Header=516 yields exact division for record=16. |
| **Record length** | **16 bytes** is the strongest candidate. Appended 207,680 bytes ÷ 16 = 12,980 records (exact). Also: 32, 64, 80 divide appended region evenly. With header=512, both files show +4 trailing bytes. |
| **Fixed vs variable** | **Fixed-record.** Appended bytes align to 16-byte boundaries. Many records show 8-byte value repeated in both halves (e.g. `e1 c3 12 85 07 8e 58 40` × 2); ~25% of appended records have first 8 bytes == last 8 bytes. |
| **Repeating structures** | 16-byte records; first 8 bytes often look like IEEE 754 double (little-endian). No field interpretation yet. |

**First 512 bytes (hex/ASCII):** See Phase 1 Tooling output or `lightning_inspect_nex.py` on a sample.

**Conclusion:** Fixed-record format, 16-byte records, append-only. Header 512 bytes (or 516 if counting trailing header fields). Parser design can assume 16-byte fixed records; field layout still unknown.

### Discovery Questions (to Answer)

1. **Is the file append-only?** — ✅ Yes (observed).
2. **Are records fixed-length or variable-length?** — ✅ Fixed, 16 bytes (observed).
3. **Is there a header followed by repeating records?** — ✅ Yes; header ~512 bytes.
4. **Are timestamps encoded in a recognizable format?** — TBD (no interpretation yet).
5. **Are distance/bearing fields likely integer or float?** — TBD (8-byte doubles observed; layout unknown).
6. **Are records little-endian or big-endian?** — TBD (multi-byte values present; likely little-endian on Windows).

### Phase 1 Tooling (No Guessing)

| Capability | Purpose |
|------------|---------|
| Show header bytes | Inspect raw header; identify ASCII vs binary regions |
| Show candidate record lengths | Test which lengths divide (file_size - header) evenly |
| Diff two captures | Compare same-day file at T1 vs T2; highlight appended bytes |
| Highlight newly appended region | Identify which bytes changed between pulls |
| Structured parsing | Only after evidence supports a specific layout |

### Safe Workflow

1. **Pull** (read-only): `scp` from Lightning-PC to wx-core scratch
2. **Snapshot** (optional): Save timestamped copy for later diff
3. **Inspect** locally — never modify source
4. **Diff** two snapshots to confirm append-only and locate new data

---

## Phase 2: Ingest Pipeline (Production-Safe)

| Requirement | Implementation |
|-------------|----------------|
| Pull from wx-core only | All ingest scripts run on wx-core |
| Prefer incremental ingest | Track last-read offset; only process new bytes |
| Handle day rollover | Detect YYYYMMDD change; switch to new file |
| Never reread entire archives | Maintain position; append-only format allows tail reads |
| Resilient to partial writes | NexStorm may write mid-record; validate before commit |

---

## Phase 3: Normalization & Output

### Internal Normalized Event Object

```json
{
  "timestamp": "2026-03-12T11:23:52-04:00",
  "distance_mi": 7.17,
  "bearing_deg": 182.3,
  "lat": 31.85,
  "lon": -81.02,
  "raw": { "..." }
}
```

### Output Formats

- **JSON** — Array of normalized events
- **GeoJSON** — FeatureCollection for Mapbox

### Source Metadata (Required)

```json
{
  "source": "LD350",
  "sensor": "MoonRiverWeather",
  "sensor_lat": 31.919117,
  "sensor_lon": -81.075932
}
```

### Preserve Raw Values

Include original source values when possible (e.g. `raw.distance`, `raw.bearing`) for debugging and reprocessing.

---

## Phase 4: Map Preparation

| Requirement | Design |
|-------------|--------|
| Mapbox-ready | GeoJSON FeatureCollection with Point geometry |
| Recent-strike windows | 5 min, 30 min, 60 min (filter by timestamp) |
| Future strike fading / animation | Precise event timestamps; client-side age-based opacity |
| Precise timestamps | ISO 8601 with timezone |

---

## Phase 5: Operations

| Requirement | Implementation |
|-------------|----------------|
| Logging | Structured logs; rotation |
| Detect .nex stops changing | Compare file mtime/size over interval |
| Detect day rollover | New YYYYMMDD.nex appears |
| Detect Lightning-PC access failure | SSH/scp timeout; retry with backoff |
| Unattended 24/7 | No manual intervention; graceful degradation |

---

## MRW Site Coordinates

From `conf/basemap_geometry.json`:
- **sensor_lat:** 31.919117
- **sensor_lon:** -81.075932

---

## Files

| File | Purpose |
|------|---------|
| `docs/lightning_pipeline_plan.md` | This plan |
| `bin/lightning_inspect_nex.py` | Phase 1: format discovery (header, candidates, diff) |
| `conf/lightning.json` | Detector config (future) |
| `scratch/lightning_nex/` | Local .nex samples |
| `scratch/lightning_nex/samples/` | Timestamped snapshots for diff |

---

## References

- [WXForum: NexStorm Archive Files](https://www.wxforum.net/index.php?topic=691.0)
- [LD-350 User Manual](https://www.boltek.com/LD-350%20User%20Manual%20-%2012172018.pdf)
- `docs/ld350_lightning_plan.md`
