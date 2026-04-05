# MRW operational hardening (wx-core, wx-i9, SSH)

Canonical notes so outages like **2026-04 TCP ephemeral port exhaustion** (symptom: all outbound HTTPS fails, Errno 49) do not sneak back unnoticed.

## Architecture

| Role | Host | Notes |
|------|------|--------|
| **Xweather API → NDJSON → `lightning_points_xweather_local.geojson`** | **wx-core** | `com.mrw.lightning_xweather_fetch` LaunchAgent; `bin/run_lightning_xweather_fetch.sh`; `--post-generate` **scp**s GeoJSON to wx-i9 `serve_root`. |
| **NexStorm .nex pipeline** | **wx-core** | `lightning_nex_tail.py --output-remote`; batched **single scp** for three lightning map products every 8s (not three separate scps). |
| **Radar / serve_frames HTTP** | **wx-i9** | Consumes scp’d products. |
| **Xweather on wx-i9** | **Emergency only** | `mrw-lightning-xweather-fetch.service` — **disabled** by default. Enable only if wx-core cannot use HTTPS for an extended period. |

## What went wrong (2026-04)

1. **~15k+ `TIME_WAIT` sockets** on wx-core, almost all to **wx-i9:22**, from **high-frequency `scp`/`ssh`** (especially **3× scp every 3s** from `lightning_nex_tail` geo loop before the batch fix).
2. macOS ephemeral client ports (~16k) were exhausted → **new TCP connects** returned **EADDRNOTAVAIL** → **urllib/curl/Python HTTPS** all failed → Xweather fetch died → stale GeoJSON → red freshness on maps.

## Defenses in repo

1. **`lightning_nex_tail.py`** — generators run **without** `--remote`; **one** `scp` pushes `lightning_points*.geojson` + `lightning_summary.json`; interval **8s** (not 3s).
2. **`bin/deploy_radar_foundry_to_wx_core.sh`** — **excludes** `serve_root` and `out` so a Mac never overwrites wx-core live artifacts.
3. **`conf/ssh/mrw-multiplex.conf` + `bin/install_ssh_multiplex_mrw.sh`** — **SSH ControlMaster** for wx-i9 and Lightning-PC to reuse TCP sessions.
4. **`bin/watchdog_all.sh`** — every run logs **TIME_WAIT** high-water warnings and **HTTPS probe** failure to `/tmp/mrw_watchdog.log`.
5. **`lightning_xweather_fetch.py`** — **curl -4** fallback if `urllib` hits macOS bind quirks.

## Host protection job (wx-core)

**`com.mrw.host_protect`** (`conf/launchd/com.mrw.host_protect.plist`) runs **`bin/mrw_host_protect.sh`** at boot and **twice daily** (06:02 / 18:02 local). It appends to **`/tmp/mrw_host_protect.log`**:

- `TIME_WAIT` / `FIN_WAIT_2` counts  
- HTTPS probe (same class of failure as the 2026-04 outage)  
- Whether **Xweather** and **`lightning_nex_tail`** LaunchAgents look loaded  
- **`ALERT`** lines when thresholds trip or jobs look wrong  
- **Weekly (Sunday UTC):** re-runs **`install_ssh_multiplex_mrw.sh`** so **`~/.ssh/config.d/mrw-multiplex.conf`** stays aligned with the repo after edits or OS work.

**One-time install / upgrade** on wx-core:

```bash
cd ~/wx/radar-foundry && ./bin/install_host_protect_launchd.sh
```

## Operator checklist

- After changing lightning or deploy scripts: **deploy wx-core** then confirm **`launchctl list | grep xweather`** and **`tail /tmp/lightning_xweather_fetch.log`**.
- Review **`/tmp/mrw_host_protect.log`** and **`/tmp/mrw_watchdog.log`** when anything feels “stuck” or HTTPS-heavy tools fail.
- If HTTPS on wx-core breaks again: **check TIME_WAIT** (`netstat -an -p tcp | grep TIME_WAIT | wc -l`) and **watchdog log**; consider **reboot** after stopping churn; **optional** temporary enable of wx-i9 Xweather unit.
- **Never** run **two** Xweather writers (wx-core LaunchAgent + wx-i9 systemd) at once.
