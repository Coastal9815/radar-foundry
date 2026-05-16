Moon River Weather (MRW) System

## Four-Machine Architecture (DO NOT WASTE HORSEPOWER)

We have 4 machines. Use all of them. Do not leave compute idle.

| Machine | IP | Role |
|---------|-----|------|
| **weather-core** | 192.168.1.220 | Mac Studio — primary compute: fetch, render, publish |
| **wx-i9** | 192.168.2.2 | Intel i9 — serve_frames (HTTP), receive frames, future compute |
| **pi-wx** | 192.168.2.174 | Raspberry Pi — WeeWX, weather data |
| **WX-Display** | 192.168.0.185 | Beelink — displays master-mrw dashboard (loads from wx-i9:8080) |
| **Office Mac** | — | Cursor runs here; edits via SSH to remotes |

**Principle:** Distribute work across weather-core, wx-i9, and pi-wx. Consider which machine has headroom when adding ingest or products.

---

**Agent execution:** The agent runs commands via SSH from the office Mac:
- `ssh weather-core "cmd"` (192.168.1.220) — Mac Studio
- `ssh wx-i9 "cmd"` (192.168.2.2) — Intel i9
- `ssh pi-wx "cmd"` (192.168.2.174) — Raspberry Pi
- `rsync` to sync files to any remote

Requires: ~/.ssh/config and known_hosts. See docs/agent_multi_machine_setup.md.

---

## Pipeline Flow

weather-core: fetch → render (parallel) → publish to wx-i9
wx-i9: receive frames → serve_frames → clients hit wx-i9:8080
**wx-i9 → pi-wx:** serve_frames proxies /pi-wx-data/* to pi-wx (192.168.2.174) for wind, tide, conditions. **wx-i9 must always reach pi-wx.** Verify: `ssh wx-i9 "curl -s -o /dev/null -w '%{http_code}' http://192.168.2.174/data/wind.json"`

Radar pipeline order:
fetch_latest_level2.py → render_level2_nn_rgba.py → publish_radar_frame.py → update_radar_loop.py

**Scheduler:** Use radar_loop_coordinator (bin/run_radar_coordinator.sh) via launchd. Runs KCLX and KJAX in parallel. Config: conf/radar_sites.json (remote_base, remote_host, remote_user).

---

## Paths

Output frames: ~/wx/radar-foundry/out
Scratch data: ~/wx-scratch/radar-foundry (or project scratch per mrw_storage)
Remote (wx-i9): /home/scott/wx-data/served/radar_local_{KCLX,KJAX}/frames

---

## Goal

Generate radar frames every 2 minutes for radar loop playback. Leverage all available hardware.