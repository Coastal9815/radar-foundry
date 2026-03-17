#!/usr/bin/env bash
# GOES satellite watchdog — runs on wx-i9. Self-healing: if frames are stale, run update.
# Cron: */10 * * * * /home/scott/wx/radar-foundry/bin/goes_watchdog_wxi9.sh
set -e
cd "$(dirname "$0")/.."
LOG="/tmp/goes_watchdog_wxi9.log"
SERVED="$HOME/wx-data/served/radar_local_satellite"
STALE_MIN=12   # If latest IR frame older than this, trigger run
STUCK_MIN=25   # Kill update_goes_loop if running longer than this (vis ~7 min + S3 slowness)

# Log rotation
[[ -f "$LOG" ]] && [[ $(wc -l < "$LOG" 2>/dev/null) -gt 500 ]] && tail -400 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
[[ -f /tmp/goes_cron.log ]] && [[ $(wc -l < /tmp/goes_cron.log 2>/dev/null) -gt 1000 ]] && tail -800 /tmp/goes_cron.log > /tmp/goes_cron.log.tmp && mv /tmp/goes_cron.log.tmp /tmp/goes_cron.log

# Disk check: if > 90% full, aggressive trim before run
DISK_PCT=$(df -P "$SERVED" 2>/dev/null | awk 'NR==2 {gsub(/%/,""); print $5}')
if [[ -n "$DISK_PCT" ]] && [[ "$DISK_PCT" -ge 90 ]]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) DISK ${DISK_PCT}% full, trimming to 50 frames" >> "$LOG"
  for dir in ir vis; do
    count=$(ls -1 "$SERVED/$dir"/*.png 2>/dev/null | wc -l)
    if [[ $count -gt 50 ]]; then
      ls -1 "$SERVED/$dir"/*.png 2>/dev/null | head -n $((count - 50)) | xargs -r rm -f
    fi
  done
fi

# Latest frame mtime (IR as primary indicator)
latest_ts=0
newest=$(ls -t "$SERVED/ir"/*.png 2>/dev/null | head -1)
[[ -n "$newest" ]] && [[ -f "$newest" ]] && latest_ts=$(stat -c %Y "$newest" 2>/dev/null)

now=$(date +%s)
if [[ $latest_ts -gt 0 ]]; then
  age_min=$(( (now - latest_ts) / 60 ))
else
  age_min=999
fi

# Kill stuck update_goes_loop and its children (render_goes_frame)
for pid in $(pgrep -f "update_goes_loop.py" 2>/dev/null); do
  elapsed=$(ps -o etimes= -p "$pid" 2>/dev/null | tr -d ' ')
  [[ -z "$elapsed" ]] && continue
  run_min=$(( elapsed / 60 ))
  if [[ $run_min -ge $STUCK_MIN ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) KILL STUCK: update_goes_loop pid=$pid (${run_min} min)" >> "$LOG"
    pkill -9 -P "$pid" 2>/dev/null
    kill -9 "$pid" 2>/dev/null
    rm -f /tmp/goes_loop_wxi9.lock
  fi
done
# Also kill orphaned render_goes_frame > STUCK_MIN
for pid in $(pgrep -f "render_goes_frame.py" 2>/dev/null); do
  elapsed=$(ps -o etimes= -p "$pid" 2>/dev/null | tr -d ' ')
  [[ -z "$elapsed" ]] && continue
  run_min=$(( elapsed / 60 ))
  if [[ $run_min -ge $STUCK_MIN ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) KILL STUCK: render_goes_frame pid=$pid (${run_min} min)" >> "$LOG"
    kill -9 "$pid" 2>/dev/null
    rm -f /tmp/goes_loop_wxi9.lock
  fi
done

if [[ $age_min -ge $STALE_MIN ]]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) STALE: latest frame ${age_min} min old, triggering run" >> "$LOG"
  rm -f /tmp/goes_loop_wxi9.lock
  ./bin/run_goes_on_wx_i9.sh >> /tmp/goes_cron.log 2>&1
else
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ok (latest ${age_min} min)" >> "$LOG"
fi
