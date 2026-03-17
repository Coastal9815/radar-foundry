# FlashGate IPC-1 Relay — Lightning-PC

Windows-side relay that reads NexStorm FlashGate IPC-1 shared memory and outputs MRW canonical strike records.

**Run on Lightning-PC (192.168.2.223) with NexStorm running.**

**No Python on Lightning-PC.** Use the Go build (`flashgate_relay.exe`). Build on wx-core; copy exe to Lightning-PC.

---

## Requirements

- **Windows** (Lightning-PC)
- **flashgate_relay.exe** (built from Go; no Python or runtime needed)
- **NexStorm** running with FlashGate IPC-1 enabled at `C:\Astrogenic\NexStorm`

---

## Quick Start

1. Build on wx-core: `cd scripts/lightning/windows && GOOS=windows GOARCH=amd64 go build -o flashgate_relay.exe .`
2. Copy `flashgate_relay.exe` to `C:\MRW\lightning\` on Lightning-PC.
3. Ensure NexStorm is running.
4. On Lightning-PC, run:

```cmd
cd C:\MRW\lightning
.\flashgate_relay.exe --output-dir C:\MRW\lightning
```

4. Strikes append to `C:\MRW\lightning\lightning_rt.ndjson`.
5. Relay health overwrites `C:\MRW\lightning\lightning_status.json`.
6. Stop with Ctrl+C.

---

## Output Files (Lightning-PC) — LOCKED

| File | Path | Mode |
|------|------|------|
| lightning_rt.ndjson | `C:\MRW\lightning\lightning_rt.ndjson` | Append-only NDJSON; one JSON object per line; never overwritten |
| lightning_status.json | `C:\MRW\lightning\lightning_status.json` | Overwrite-in-place; current relay health |
| lightning_noise.ndjson | `C:\MRW\lightning\lightning_noise.ndjson` | Append-only; only if `--noise` enabled |

**Base path:** `C:\MRW\lightning\`

Create the directory if it doesn't exist; the relay creates it automatically.

---

## Command-Line Options

```
python flashgate_relay.py [options]

  --output-dir DIR     Output directory (default: C:\MRW\lightning)
  --config FILE        JSON config file (overrides other options)
  --shmem NAME         Shared memory name (default from Appendix C)
  --reader-sem NAME    Reader semaphore name
  --writer-sem NAME    Writer semaphore name
  --sensor-id ID       Sensor ID (default: MRW)
  --noise              Emit lightning_noise.ndjson for noise records
```

---

## Config File

Create `C:\MRW\lightning\relay_config.json`:

```json
{
  "output_dir": "C:\\MRW\\lightning",
  "shmem_name": "NXFGIPC_SHMEM_0822931589443_238731_GATE0",
  "reader_semaphore": "Reader Semaphore",
  "writer_semaphore": "Writer Semaphore",
  "sensor_id": "MRW",
  "emit_noise": false
}
```

Run with: `python flashgate_relay.py --config C:\MRW\lightning\relay_config.json`

---

## Shared Memory Name

The default name `NXFGIPC_SHMEM_0822931589443_238731_GATE0` is from NexStorm Appendix C. Your NexStorm install may use a different name. Check the NexStorm manual or config. Override with `--shmem` or config.

---

## Run as Background Service (Optional)

To run continuously:

1. **Task Scheduler:** Create a task that runs `python flashgate_relay.py` at logon, runs whether user is logged on or not.
2. **NSSM / WinSW:** Wrap as a Windows service.
3. **Manual:** Run in a persistent terminal or `start /B python flashgate_relay.py`.

---

## Environment Checks

Before running:

1. **Python:** `python --version` → 3.8 or higher.
2. **NexStorm:** Running and connected to LD-350.
3. **FlashGate:** Enabled in NexStorm (see manual).
4. **Output dir:** Writable (e.g. `C:\MRW\lightning`). Create if needed: `mkdir C:\MRW\lightning`.

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| OpenFileMapping failed | NexStorm not running, or wrong shmem name | Start NexStorm; check `--shmem` |
| OpenSemaphore failed | Wrong semaphore names | Check Appendix C; try `--reader-sem` / `--writer-sem` |
| No strikes in output | No lightning, or heartbeat/noise only | Check lightning_status.json for total_strikes; wait for activity |
| Permission denied on output | Output dir not writable | Use a writable path (e.g. user home) |

---

## Next Steps (wx-core)

wx-core pulls `lightning_rt.ndjson` and `lightning_status.json` from Lightning-PC (scp/rsync) and publishes to pi-wx. That sync is separate from this relay.
