# FlashGate IPC-1 Relay — Implementation Plan

**Status:** Implemented.

**Source:** NexStorm manual Appendix C (FlashGate IPC-1).

**Primary path:** FlashGate IPC-1 → Windows relay → lightning_rt.ndjson, lightning_status.json.

**Secondary path:** .nex + nxutil (archive/backfill only).

---

## 1. Output Filenames (LOCKED)

| File | Path | Mode |
|------|------|------|
| lightning_rt.ndjson | `C:\MRW\lightning\lightning_rt.ndjson` | Append-only NDJSON; never overwritten |
| lightning_status.json | `C:\MRW\lightning\lightning_status.json` | Overwrite-in-place; current relay health |
| lightning_noise.ndjson | `C:\MRW\lightning\lightning_noise.ndjson` | Append-only; only if noise logging enabled |

---

## 2. Architecture

```
NexStorm (Lightning-PC)
   │  FlashGate IPC-1 shared memory
   │  Semaphores: Reader, Writer
   ↓
flashgate_relay.py (Lightning-PC)
   │  Poll 15ms, parse comma-separated fields
   │  Classify: valid strike / heartbeat / noise
   ↓
lightning_rt.ndjson          (valid strikes only; append)
lightning_status.json        (relay health; overwrite)
lightning_noise.ndjson       (noise only; append; optional)
```

---

## 3. Relay Scope (LOCKED — Narrow)

The relay does **only**:

- Read FlashGate shared memory
- Classify records as valid strike / heartbeat / noise
- Write valid strikes to lightning_rt.ndjson
- Write relay health to lightning_status.json
- Optionally write noise to lightning_noise.ndjson (if noise logging enabled)

The relay does **NOT**:

- NO lat/lon conversion
- NO clustering
- NO alerts
- NO archive replay logic
- NO overlay generation

---

## 4. FlashGate IPC-1 Format (Appendix C)

| # | Field | Notes |
|---|-------|-------|
| 1 | count | Source sequence |
| 2 | year | |
| 3 | month | |
| 4 | day | |
| 5 | timestamp_secs | Seconds (interpret with year/month/day) |
| 6 | TRACbearing | TRAC bearing deg |
| 7 | TRACDistance | TRAC distance |
| 8 | RAWbearing | Raw bearing deg |
| 9 | RAWDistance | Raw distance |
| 10 | TRAC_X | |
| 11 | TRAC_Y | |
| 12 | Correlated strike | 0/1 |
| 13 | Reserved | |
| 14 | StrikeType | 0=CG, 1=IC |
| 15 | StrikePolarity | 0=Pos, 1=Neg |

**Noise:** Any bearing or distance = -1 → noise. Exclude from strike output.

**Heartbeat:** Any param (except timestamp_secs, RAWbearing) = -9 or 0 (unsigned) → heartbeat. RAWbearing = antenna rotation. Do not emit as strike; track for health.

---

## 5. Canonical MRW Live Strike Record

- strike_id
- timestamp_utc (ISO 8601)
- sensor_id
- source = "flashgate_ipc1"
- source_seq (count)
- raw_bearing_deg, raw_distance_km
- trac_bearing_deg, trac_distance_km
- x_raw, y_raw
- is_correlated
- strike_type ("CG" | "IC")
- polarity ("positive" | "negative")
- is_noise
- ingested_at_utc
- raw_payload

---

## 6. Health/Status Structure (lightning_status.json)

- relay_running
- source_heartbeat_seen_at_utc
- last_message_at_utc
- last_strike_at_utc
- total_messages, total_strikes, total_noise, total_heartbeats
- antenna_rotation_deg_last
- last_error

---

## 7. Record Classification Rules

- **Valid strike:** Not heartbeat, not noise → write to lightning_rt.ndjson (append).
- **Heartbeat:** Any excluded field = -9 → update health counters only; do NOT write to lightning_rt.ndjson.
- **Noise:** Any bearing or distance = -1 → do NOT write to lightning_rt.ndjson; only write to lightning_noise.ndjson if noise logging enabled.
