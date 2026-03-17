# FlashGate Relay — Assumptions and Environment

## Output Filenames (LOCKED)

| File | Path | Mode |
|------|------|------|
| lightning_rt.ndjson | `C:\MRW\lightning\lightning_rt.ndjson` | Append-only NDJSON; never overwritten |
| lightning_status.json | `C:\MRW\lightning\lightning_status.json` | Overwrite-in-place; relay health |
| lightning_noise.ndjson | `C:\MRW\lightning\lightning_noise.ndjson` | Append-only; only if noise logging enabled |

## Relay Scope (LOCKED — Narrow)

- Read FlashGate shared memory
- Classify: valid strike / heartbeat / noise
- Write valid strikes → lightning_rt.ndjson
- Write relay health → lightning_status.json
- Optionally write noise → lightning_noise.ndjson (if enabled)
- NO lat/lon conversion, NO clustering, NO alerts, NO archive replay, NO overlay generation

## Assumptions

1. **NexStorm Appendix C** — FlashGate IPC-1 format (15 comma-separated fields) is the source of truth.
2. **Shared memory name** — Default `NXFGIPC_SHMEM_0822931589443_238731_GATE0` may vary per install; configurable.
3. **Semaphore names** — "Reader Semaphore" and "Writer Semaphore" as in Appendix C; configurable if different.
4. **Timestamp** — UTC ISO 8601. `timestamp_secs` interpreted as Unix epoch or seconds-since-midnight local.
5. **Strike ID** — Content hash of (timestamp_utc, raw_bearing, raw_distance, sensor_id).
6. **Noise** — Bearing or distance = -1 → noise. Never in lightning_rt.ndjson; only lightning_noise.ndjson if enabled.
7. **Heartbeat** — Any excluded field = -9 → heartbeat. Update health only; never in lightning_rt.ndjson.
8. **Python on Lightning-PC** — Python 3.8+ available. No pywin32 required; ctypes only.

## Environment Checks

Before first run on Lightning-PC:

| Check | Command | Expected |
|-------|---------|----------|
| Python | `python --version` | 3.8+ |
| NexStorm | Process running | NexStorm.exe |
| Output dir | `mkdir C:\MRW\lightning` | Writable |
| FlashGate | NexStorm config | Enabled (see manual) |

## File Locations on Lightning-PC

| Path | Purpose |
|------|---------|
| `C:\MRW\lightning\` | Output directory (create if missing) |
| `C:\MRW\lightning\lightning_rt.ndjson` | Strike stream (append-only) |
| `C:\MRW\lightning\lightning_status.json` | Relay health (overwrite) |
| `C:\MRW\lightning\lightning_noise.ndjson` | Optional noise stream |
| `C:\MRW\lightning\relay_config.json` | Optional config |

Relay script can live anywhere (e.g. cloned radar-foundry repo). Output dir is configurable.
