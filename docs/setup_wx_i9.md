# wx-i9 Setup (Serve + Display)

wx-i9 (192.168.2.2, Linux) receives radar frames from weather-core and serves the players via HTTP.

**Player URLs:** http://192.168.2.2:8080/player/kclx/ · http://192.168.2.2:8080/player/kjax/ · + mapbox variants · **Mobile:** http://192.168.2.2:8080/player/kclx-mobile/ · http://192.168.2.2:8080/player/kjax-mobile/

## 1. One-time setup on wx-i9

### Create frame directories

```bash
ssh 192.168.2.2 "mkdir -p \$HOME/wx-data/served/radar_local_KCLX/frames \$HOME/wx-data/served/radar_local_KJAX/frames"
```

### Clone project and build serve_root

```bash
# On wx-i9
cd /Users/scott  # or wherever
git clone <repo> wx/radar-foundry   # or rsync from weather-core
cd wx/radar-foundry

# Build serve_root (remote mode — symlinks to ~/wx-data/served/radar_local_*/frames)
SERVED_RADAR_BASE=$HOME/wx-data/served ./bin/setup_serve_root.sh
```

**Basemap and player:** Either sync from weather-core or ensure the project has `out/basemap_MRWcenter_1600.png` and `player/`. If basemap is missing, run on weather-core:

```bash
# On weather-core
cd ~/wx/radar-foundry && .venv/bin/python bin/make_basemap_grid.py --conf conf
rsync -a out/basemap_MRWcenter_1600.* wx-i9:~/wx/radar-foundry/out/
```

### Allow port 8080 in firewall (required for LAN access)

If other machines (Office Mac, pi-wx, weather-core) cannot reach the radar URLs, UFW on wx-i9 is likely blocking port 8080. Run on **wx-i9**:

```bash
# On wx-i9 — requires sudo
sudo ufw allow 8080/tcp comment 'MRW radar serve_frames'
sudo ufw status
# If UFW was inactive, enable it: sudo ufw enable
```

### pi-wx connectivity (required for master-mrw wind/tide/conditions)

**wx-i9 must reach pi-wx (192.168.2.174)** — serve_frames proxies /pi-wx-data/* to pi-wx for live weather data. Verify:

```bash
# From wx-i9
curl -s -o /dev/null -w '%{http_code}' http://192.168.2.174/data/wind.json
# Expect: 200
```

If this fails, check: pi-wx is powered on, same subnet (192.168.2.x), no firewall blocking wx-i9 → pi-wx:80.

```bash
# Or run the verify script (from project root)
ssh wx-i9 "~/wx/radar-foundry/bin/verify_pi_wx_reachability.sh"
```

### Run serve_frames (hardened: systemd + watchdog)

**serve_frames** uses a threaded HTTP server with 30s socket timeout so one slow client cannot block others. Run it via systemd for auto-restart on failure, plus a cron watchdog that restarts if the server stops responding.

**1. Install systemd service**

```bash
# On wx-i9 — stop any manually running serve_frames first
pkill -f serve_frames.py

# Adjust path in the .service file if project lives elsewhere
sudo cp ~/wx/radar-foundry/conf/systemd/mrw-serve-frames.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mrw-serve-frames
sudo systemctl start mrw-serve-frames
sudo systemctl status mrw-serve-frames
```

**2. Optional: wx-i9 cron watchdog** — The unified watchdog on wx-core (see §2 below) checks serve_frames via HTTP and restarts via SSH. A local cron is redundant but can be added for belt-and-suspenders:

```bash
# On wx-i9 — run as root (optional)
sudo crontab -e
*/5 * * * * /home/scott/wx/radar-foundry/bin/watchdog_serve_frames.sh
```

**3. Required for unified watchdog: allow scott to restart without password**

```bash
# On wx-i9 — if watchdog runs as scott (user crontab) instead of root
echo 'scott ALL=(ALL) NOPASSWD: /bin/systemctl restart mrw-serve-frames' | sudo tee /etc/sudoers.d/mrw-serve-frames
sudo chmod 440 /etc/sudoers.d/mrw-serve-frames
```

## 2. weather-core: coordinator + watchdog

### Coordinator (every 2 min)

Replace the two launchd jobs (KCLX, KJAX) with one that runs the coordinator:

1. Unload the old jobs:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.mrw.kclx.plist   # if exists
   launchctl unload ~/Library/LaunchAgents/com.mrw.kjax.plist
   ```

2. Copy and load the plist:
   ```bash
   cp ~/wx/radar-foundry/conf/launchd/com.mrw.radar_coordinator.plist ~/Library/LaunchAgents/
   ```

3. Load it:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.mrw.radar_coordinator.plist
   ```

### Unified watchdog (every 5 min)

Monitors KCLX, KJAX, MRMS manifest freshness; kills stuck processes (MRMS >20 min, coordinator >8 min); checks serve_frames health and restarts via SSH if down. **On wx-i9:** ensure `scott` can run `sudo systemctl restart mrw-serve-frames` without password (add to sudoers if needed).

```bash
cp ~/wx/radar-foundry/conf/launchd/com.mrw.watchdog_all.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mrw.watchdog_all.plist
```

### NWS alerts (every 3 min)

SVR/TOR overlays on KCLX/KJAX Mapbox players. Fetches from api.weather.gov, scps alerts.json to wx-i9:

```bash
cp ~/wx/radar-foundry/conf/launchd/com.mrw.nws_alerts.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mrw.nws_alerts.plist
```

## 3. Satellite (IR + Visible)

IR and Visible are produced on **weather-core** and published to wx-i9. Ensure frame dirs exist:

```bash
mkdir -p ~/wx-data/served/radar_local_satellite/ir ~/wx-data/served/radar_local_satellite/vis
```

**Player:** http://192.168.2.2:8080/player/satellite/?product=ir

## 4. Backfill frames (1/1 → 72/72)

The loop accumulates one frame per coordinator run (~2 min). To fill quickly, run on **weather-core**:

```bash
cd ~/wx/radar-foundry
./.venv/bin/python bin/backfill_radar_frames.py --count 72
```

This fetches the last 72 scans per site from NEXRAD and publishes to wx-i9. Takes ~15–30 min depending on network.

## 5. Local-only fallback

To run everything on weather-core (no wx-i9), remove `remote_base` from `conf/radar_sites.json`. The coordinator will use `--local-only` and write to WX_SCRATCH.
