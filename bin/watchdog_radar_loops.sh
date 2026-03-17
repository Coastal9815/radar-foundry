#!/bin/bash
# Watchdog: ensure radar coordinator is producing fresh frames. Runs every 10 min.
# If any site's latest frame is older than 10 min, kill stuck processes.
# Only runs on wx-core (weather-core).
[[ $(hostname) == wx-core ]] || exit 0

LOG=/tmp/mrw_watchdog.log
STALE_MIN=10
CONF=/Users/scott/wx/radar-foundry/conf/radar_sites.json
BASE_URL="http://192.168.2.2:8080"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) watchdog start" >> "$LOG"

# Get sites from config, default KCLX+KJAX
sites="KCLX KJAX"
[ -f "$CONF" ] && sites=$(python3 -c "import json; print(' '.join(json.load(open('$CONF')).get('sites',['KCLX','KJAX'])))" 2>/dev/null) || true

stale=0
for site in $sites; do
  latest=$(curl -s -m 5 "$BASE_URL/$site/manifest.json" 2>/dev/null | python3 -c "
import json,sys
from datetime import datetime, timezone
try:
    d=json.load(sys.stdin)
    f=d.get('latest_frame','')
    if not f or not f.endswith('.png'): sys.exit(1)
    ts=f.replace('.png','').replace('T','').replace('Z','')
    dt=datetime.strptime(ts[:15],'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
    print(int(dt.timestamp()))
except: sys.exit(1)
" 2>/dev/null) || { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $site: no manifest" >> "$LOG"; stale=1; continue; }
  now=$(date +%s)
  age_min=$(( (now - latest) / 60 ))
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $site latest ${age_min} min old" >> "$LOG"
  [ "$age_min" -ge "$STALE_MIN" ] && stale=1
done

if [ "$stale" -eq 0 ]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) watchdog: ok" >> "$LOG"
  exit 0
fi

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) watchdog: STALE - killing stuck processes" >> "$LOG"
pkill -9 -f "publish_radar_frame" 2>/dev/null
pkill -9 -f "update_radar_loop" 2>/dev/null
pkill -9 -f "radar_loop_coordinator" 2>/dev/null
sleep 3
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) watchdog: triggered recovery" >> "$LOG"
