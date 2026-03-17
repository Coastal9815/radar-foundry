#!/bin/bash
# Unified watchdog: monitors all MRW processes, detects hangs, repairs.
# Runs on wx-core every 5 min. Checks:
#   1. Manifest freshness (KCLX, KJAX, MRMS)
#   2. Stuck processes (running longer than expected)
#   3. serve_frames health on wx-i9 (HTTP + restart via SSH)
#   4. Kills stuck processes; kicks immediate re-run; log rotation
[[ $(hostname) == wx-core ]] || exit 0

LOG=/tmp/mrw_watchdog.log
PROJECT=/Users/scott/wx/radar-foundry
CONF="$PROJECT/conf/radar_sites.json"
BASE_URL="http://192.168.2.2:8080"
WX_I9="scott@wx-i9"

# Staleness thresholds (minutes)
STALE_NEXRAD=10   # KCLX/KJAX: 2-min cadence
STALE_MRMS=30     # MRMS: 10-min incremental; full rebuild ~25 min — must exceed to avoid killing legitimate rebuild
STALE_SATELLITE=15  # IR/Vis: 5-min cadence; GOES runs on wx-i9
STALE_LIGHTNING=5  # lightning_nex_tail: 5-s cadence; 5 min = stuck or Lightning-PC unreachable

# Max process runtime (minutes) - kill if exceeded
MAX_MRMS_MIN=35       # incremental: ~1-2 min; full rebuild (cold start): ~25 min
MAX_COORDINATOR_MIN=10 # radar_loop_coordinator: ~2-3 min; 10 min = truly stuck

# Log rotation: keep last 2000 lines
[[ -f "$LOG" ]] && [[ $(wc -l < "$LOG") -gt 2000 ]] && tail -1500 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) watchdog start" >> "$LOG"

action=0

# --- 1. Kill stuck processes (running too long) ---
for pattern in "update_mrms_loop" "radar_loop_coordinator" "lightning_nex_tail"; do
  max_min=$MAX_MRMS_MIN
  [[ "$pattern" == "radar_loop_coordinator" ]] && max_min=$MAX_COORDINATOR_MIN
  [[ "$pattern" == "lightning_nex_tail" ]] && max_min=15  # 15 min = stuck (Lightning-PC down, etc.)
  pids=$(pgrep -f "$pattern" 2>/dev/null)
  for pid in $pids; do
    elapsed=$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ')
    [[ -z "$elapsed" ]] && continue
    # Parse elapsed: DD-HH:MM:SS or HH:MM:SS or MM:SS or SS
    days=0
    if [[ "$elapsed" =~ ^([0-9]+)- ]]; then
      days=${BASH_REMATCH[1]}; elapsed="${elapsed#*-}"
    fi
    parts=($(echo "$elapsed" | tr ':' '\n'))
    n=${#parts[@]}
    if [[ $n -eq 1 ]]; then s=${parts[0]}; m=0; h=0
    elif [[ $n -eq 2 ]]; then m=${parts[0]}; s=${parts[1]}; h=0
    else h=${parts[0]}; m=${parts[1]}; s=${parts[2]}; fi
    total_min=$(( days*24*60 + 10#${h:-0}*60 + 10#${m:-0} + 10#${s:-0}/60 ))
    if [[ $total_min -ge $max_min ]]; then
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) KILL STUCK: $pattern pid=$pid (${total_min} min)" >> "$LOG"
      kill -9 "$pid" 2>/dev/null
      action=1
    fi
  done
done

# --- 2. Check manifest freshness ---
# Returns 0 if stale or unreachable (trigger recovery), 1 if fresh
check_manifest() {
  local url="$1" name="$2" stale_min="$3"
  latest=$(curl -s -m 5 "$url" 2>/dev/null | python3 -c "
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
" 2>/dev/null)
  if [[ -z "$latest" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $name: no manifest" >> "$LOG"
    return 0
  fi
  now=$(date +%s)
  age_min=$(( (now - latest) / 60 ))
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $name latest ${age_min} min old" >> "$LOG"
  [[ $age_min -ge $stale_min ]]
}

stale=0

# NEXRAD
sites="KCLX KJAX"
[[ -f "$CONF" ]] && sites=$(python3 -c "import json; print(' '.join(json.load(open('$CONF')).get('sites',['KCLX','KJAX'])))" 2>/dev/null) || true
for site in $sites; do
  check_manifest "$BASE_URL/$site/manifest.json" "$site" "$STALE_NEXRAD" && stale=1
done

# MRMS (eastern_us as proxy)
check_manifest "$BASE_URL/mrms/eastern_us/manifest.json" "mrms" "$STALE_MRMS" && stale=1

# Satellite IR (runs on wx-i9 via cron)
check_manifest "$BASE_URL/satellite/ir/manifest.json" "satellite" "$STALE_SATELLITE" && stale=1

# Lightning (runs on wx-core; 5-s cadence)
LIGHTNING_STATUS="$PROJECT/scratch/lightning_nex/lightning_status.json"
LIGHTNING_AGE_MIN=""
if [[ -f "$LIGHTNING_STATUS" ]]; then
  lightning_ts=$(python3 -c "
import json,sys
from datetime import datetime, timezone
try:
    d=json.load(open('$LIGHTNING_STATUS'))
    s=d.get('last_success_at_utc') or d.get('last_message_at_utc','')
    if not s: sys.exit(1)
    dt=datetime.fromisoformat(s.replace('Z','+00:00'))
    print(int(dt.timestamp()))
except: sys.exit(1)
" 2>/dev/null)
  if [[ -n "$lightning_ts" ]]; then
    LIGHTNING_AGE_MIN=$(( ($(date +%s) - lightning_ts) / 60 ))
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) lightning status ${LIGHTNING_AGE_MIN} min old" >> "$LOG"
    [[ $LIGHTNING_AGE_MIN -ge $STALE_LIGHTNING ]] && stale=1
  else
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) lightning: no status" >> "$LOG"
    stale=1
  fi
fi

# --- 3. Check serve_frames (wx-i9) ---
code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 "$BASE_URL/player/kclx/" 2>/dev/null)
piwx_code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 "$BASE_URL/pi-wx-data/data/wind.json" 2>/dev/null)
if [[ "$piwx_code" != "200" ]]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) pi-wx proxy: FAILED (HTTP $piwx_code) — wx-i9 cannot reach pi-wx; wind/tide/conditions will not update" >> "$LOG"
fi
if [[ ! "$code" =~ ^[23][0-9][0-9]$ ]]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) serve_frames: health FAILED (HTTP $code) - restarting via SSH" >> "$LOG"
  ssh -o ConnectTimeout=10 -o BatchMode=yes "$WX_I9" '
    if systemctl is-active --quiet mrw-serve-frames 2>/dev/null; then
      sudo -n systemctl restart mrw-serve-frames 2>/dev/null || systemctl restart mrw-serve-frames 2>/dev/null
    else
      pkill -f "serve_frames.py" 2>/dev/null
      sleep 2
      cd ~/wx/radar-foundry
      nohup python3 bin/serve_frames.py >> /tmp/serve_frames.log 2>&1 &
    fi
  ' 2>> "$LOG" && echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) serve_frames: restart sent" >> "$LOG" || echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) serve_frames: SSH failed" >> "$LOG"
  action=1
fi

# --- 4. If stale, kill STUCK processes only (not fresh kicks), then kick ---
# Only kill processes running > MIN_KILL_AGE so we don't kill our own recovery kicks
MIN_KILL_AGE_COORD=8   # coordinator: ~2-3 min; 8 min = stuck
MIN_KILL_AGE_MRMS=25   # MRMS incremental: ~1-2 min; full rebuild (cold start): ~25 min

kill_if_stuck() {
  local pattern="$1" min_age="$2"
  for pid in $(pgrep -f "$pattern" 2>/dev/null); do
    elapsed=$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ')
    [[ -z "$elapsed" ]] && continue
    days=0; [[ "$elapsed" =~ ^([0-9]+)- ]] && { days=${BASH_REMATCH[1]}; elapsed="${elapsed#*-}"; }
    parts=($(echo "$elapsed" | tr ':' '\n')); n=${#parts[@]}
    if [[ $n -eq 1 ]]; then s=${parts[0]}; m=0; h=0
    elif [[ $n -eq 2 ]]; then m=${parts[0]}; s=${parts[1]}; h=0
    else h=${parts[0]}; m=${parts[1]}; s=${parts[2]}; fi
    total_min=$(( days*24*60 + 10#${h:-0}*60 + 10#${m:-0} + 10#${s:-0}/60 ))
    if [[ $total_min -ge $min_age ]]; then
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) RECOVERY: killing $pattern pid=$pid (${total_min} min)" >> "$LOG"
      kill -9 "$pid" 2>/dev/null
    fi
  done
}

if [[ $stale -eq 1 ]] || [[ $action -eq 1 ]]; then
  if [[ $stale -eq 1 ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) RECOVERY: killing stuck (coord>${MIN_KILL_AGE_COORD}m, mrms>${MIN_KILL_AGE_MRMS}m)" >> "$LOG"
    # Lightning: kill if status stale; launchd KeepAlive will restart
    if [[ -n "$LIGHTNING_AGE_MIN" ]] && [[ $LIGHTNING_AGE_MIN -ge $STALE_LIGHTNING ]]; then
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) RECOVERY: killing lightning_nex_tail (status ${LIGHTNING_AGE_MIN}m stale)" >> "$LOG"
      pkill -9 -f "lightning_nex_tail" 2>/dev/null
    fi
    pkill -9 -f "publish_radar_frame" 2>/dev/null
    pkill -9 -f "update_radar_loop" 2>/dev/null
    kill_if_stuck "radar_loop_coordinator" "$MIN_KILL_AGE_COORD"
    kill_if_stuck "update_mrms_loop" "$MIN_KILL_AGE_MRMS"
    pkill -9 -f "render_mrms_frame" 2>/dev/null
    pkill -9 -f "fetch_mrms" 2>/dev/null
    # Satellite: kick on wx-i9 (GOES runs there)
    ssh -o ConnectTimeout=10 -o BatchMode=yes "$WX_I9" '
      pkill -9 -f "update_goes_loop" 2>/dev/null
      rm -f /tmp/goes_loop_wxi9.lock
      cd ~/wx/radar-foundry && nohup ./bin/run_goes_on_wx_i9.sh >> /tmp/goes_cron.log 2>&1 &
    ' 2>> "$LOG" && echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) RECOVERY: kicked GOES on wx-i9" >> "$LOG" || true
    sleep 3
    # Only kick if we're not already running (avoid duplicate runs)
    if ! pgrep -f "update_mrms_loop" >/dev/null 2>&1; then
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) RECOVERY: kicking coordinator + MRMS" >> "$LOG"
      cd "$PROJECT" && nohup "$PROJECT/bin/run_radar_coordinator.sh" >> /tmp/radar_coordinator_kick.log 2>&1 &
      nohup "$PROJECT/bin/run_mrms_loop.sh" >> /tmp/mrms_loop_kick.log 2>&1 &
    fi
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) RECOVERY: done" >> "$LOG"
  fi
else
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) watchdog: ok" >> "$LOG"
fi
