# Xweather Lightning — Production Deployment

## Overview

- **Pipeline**: `bin/lightning_xweather_fetch.py` — polls Xweather API every 10 s, appends to NDJSON, runs GeoJSON generator, pushes to wx-i9
- **Primary**: weather-core — launchd job runs there
- **Output**: `scratch/lightning_xweather/lightning_xweather_rt.ndjson`, `serve_root/lightning_points_xweather_local.geojson` (scp to wx-i9)
- **Player**: http://192.168.2.2:8080/player/hyper-local-x/

## Prerequisites

1. **Xweather API credentials** — create `~/.mrw/xweather.env`:

```bash
mkdir -p ~/.mrw
cat > ~/.mrw/xweather.env << 'EOF'
export XWEATHER_CLIENT_ID="your_client_id"
export XWEATHER_CLIENT_SECRET="your_client_secret"
EOF
chmod 600 ~/.mrw/xweather.env
```

2. **SSH to wx-i9** — the machine running the fetch must have passwordless SSH to wx-i9 for `--remote` scp.

## Deploy (on weather-core)

**Credentials**: Create `~/.mrw/xweather.env` with `XWEATHER_CLIENT_ID` and `XWEATHER_CLIENT_SECRET`.

**SSH**: weather-core must have passwordless SSH to wx-i9 for `--remote` scp.

```bash
cd ~/wx/radar-foundry

# 1. Copy plist to LaunchAgents
cp conf/launchd/com.mrw.lightning_xweather_fetch.plist ~/Library/LaunchAgents/

# 2. Fix plist path if project is not at /Users/scott/wx/radar-foundry
#    Edit ~/Library/LaunchAgents/com.mrw.lightning_xweather_fetch.plist
#    Update ProgramArguments to your actual path

# 3. Load the job
launchctl load ~/Library/LaunchAgents/com.mrw.lightning_xweather_fetch.plist
```

## Verify

```bash
# On weather-core: check job is running
ssh weather-core "launchctl list | grep lightning_xweather"

# On weather-core: check log
ssh weather-core "tail -20 /tmp/lightning_xweather_fetch.log"

# Check GeoJSON on wx-i9
ssh wx-i9 "curl -s http://127.0.0.1:8080/lightning_points_xweather_local.geojson | head -20"
```

## Stop

```bash
launchctl unload ~/Library/LaunchAgents/com.mrw.lightning_xweather_fetch.plist
```

## Fix duplicate pollers

If two `lightning_xweather_fetch.py` processes run (launchd + manual, or double-load), run from office Mac:

```bash
./bin/fix_xweather_duplicates.sh
```

This syncs the lockfile-protected run script, kills both processes, resets the NDJSON archive, and reloads launchd. The run script now uses `/tmp/lightning_xweather_fetch.lock` to prevent duplicates.

## After sync_to_wx_i9

The plist lives in the repo. After `./bin/sync_to_wx_i9.sh`, the updated plist and scripts are on weather-core. If you've already loaded the job, reload after sync:

```bash
ssh weather-core "launchctl unload ~/Library/LaunchAgents/com.mrw.lightning_xweather_fetch.plist; cp ~/wx/radar-foundry/conf/launchd/com.mrw.lightning_xweather_fetch.plist ~/Library/LaunchAgents/; launchctl load ~/Library/LaunchAgents/com.mrw.lightning_xweather_fetch.plist"
```
