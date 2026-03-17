#!/bin/bash
# Runs on wx-i9. Watches wx-core: if wx-core is up but radar is stale,
# triggers wx-core's watchdog via SSH (backup when wx-core's launchd misses a run).
# Logs to /tmp/mrw_watch_wx_core.log
#
# SAFETY: Cooldown + circuit breaker. No one present to disable if it misbehaves.
# - Cooldown: 20 min between triggers.
# - Circuit breaker: After 3 triggers with no recovery, stop. Resets when radar fresh.
# Prerequisite: ssh scott@wx-core must work without password (ssh keys).

LOG=/tmp/mrw_watch_wx_core.log
TRIGGERED_FILE=/tmp/mrw_watch_wx_core_triggered_at
CIRCUIT_BREAKER_FILE=/tmp/mrw_watch_wx_core_trigger_count
COOLDOWN_MIN=20
MAX_TRIGGERS_BEFORE_STOP=3   # Stop after this many triggers with no recovery
WX_CORE="${WX_CORE:-scott@wx-core}"
WX_CORE_PROJECT="${WX_CORE_PROJECT:-/Users/scott/wx/radar-foundry}"  # path on wx-core (Mac)
MANIFEST_URL="${MANIFEST_URL:-http://127.0.0.1:8080}"
STALE_MIN=15   # KCLX/KJAX: 2-min cadence; 15 min = conservative (avoids recovery thrashing)
PING_TIMEOUT=3

# Log rotation
[[ -f "$LOG" ]] && [[ $(wc -l < "$LOG") -gt 500 ]] && tail -400 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) watch_wx_core start" >> "$LOG"

# Circuit breaker: if we've triggered 3 times with no recovery, stop (no one here to fix)
trigger_count=$(cat "$CIRCUIT_BREAKER_FILE" 2>/dev/null)
[[ -z "$trigger_count" ]] && trigger_count=0
[[ "$trigger_count" =~ ^[0-9]+$ ]] || trigger_count=0
if [[ $trigger_count -ge $MAX_TRIGGERS_BEFORE_STOP ]]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) circuit breaker: ${trigger_count} triggers with no recovery — stopping (resets when radar fresh)" >> "$LOG"
  exit 0
fi

# Cooldown: skip if we triggered recently
if [[ -f "$TRIGGERED_FILE" ]]; then
  triggered_at=$(cat "$TRIGGERED_FILE" 2>/dev/null)
  if [[ -n "$triggered_at" ]] && [[ "$triggered_at" =~ ^[0-9]+$ ]]; then
    now=$(date +%s)
    elapsed=$(( (now - triggered_at) / 60 ))
    if [[ $elapsed -lt $COOLDOWN_MIN ]]; then
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) cooldown (${elapsed} min since last trigger, need ${COOLDOWN_MIN})" >> "$LOG"
      exit 0
    fi
  fi
fi

# 1. Can we reach wx-core?
if ! ping -c 1 -W "$PING_TIMEOUT" "${WX_CORE#*@}" &>/dev/null; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) wx-core unreachable (ping failed) — may be asleep or down" >> "$LOG"
  exit 0
fi

# 2. Is our radar manifest stale? (we serve it; wx-core produces it)
latest=$(curl -s -m 5 "$MANIFEST_URL/KCLX/manifest.json" 2>/dev/null | python3 -c "
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
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) KCLX manifest missing or invalid" >> "$LOG"
  if ssh -o ConnectTimeout=10 -o BatchMode=yes "$WX_CORE" "cd $WX_CORE_PROJECT && ./bin/watchdog_all.sh" 2>> "$LOG"; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) triggered wx-core watchdog (no manifest)" >> "$LOG"
    date +%s > "$TRIGGERED_FILE" 2>/dev/null || true
    echo $(( trigger_count + 1 )) > "$CIRCUIT_BREAKER_FILE" 2>/dev/null || true
  else
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) SSH to wx-core failed" >> "$LOG"
  fi
  exit 0
fi

now=$(date +%s)
age_min=$(( (now - latest) / 60 ))

# Radar fresh: reset circuit breaker
if [[ $age_min -lt 5 ]]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ok (radar ${age_min} min old) — circuit breaker reset" >> "$LOG"
  echo 0 > "$CIRCUIT_BREAKER_FILE" 2>/dev/null || true
  exit 0
fi

if [[ $age_min -ge $STALE_MIN ]]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) radar stale (${age_min} min) — triggering wx-core watchdog" >> "$LOG"
  if ssh -o ConnectTimeout=10 -o BatchMode=yes "$WX_CORE" "cd $WX_CORE_PROJECT && ./bin/watchdog_all.sh" 2>> "$LOG"; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) watchdog triggered" >> "$LOG"
    date +%s > "$TRIGGERED_FILE" 2>/dev/null || true
    echo $(( trigger_count + 1 )) > "$CIRCUIT_BREAKER_FILE" 2>/dev/null || true
  else
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) SSH to wx-core failed" >> "$LOG"
  fi
else
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ok (radar ${age_min} min old)" >> "$LOG"
fi
