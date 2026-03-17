#!/usr/bin/env bash
# Run GOES satellite pipeline ON wx-i9. Writes directly to served dir.
# Use cron: */5 * * * * /home/scott/wx/radar-foundry/bin/run_goes_on_wx_i9.sh
set -e
cd "$(dirname "$0")/.."
LOG="/tmp/goes_loop_wxi9.log"
LOCKFILE="/tmp/goes_loop_wxi9.lock"
LOCK_MAX_AGE=720  # 12 min

# Log rotation (keep last 500 lines)
[[ -f "$LOG" ]] && [[ $(wc -l < "$LOG" 2>/dev/null) -gt 500 ]] && tail -400 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"

acquire_lock() {
  if [[ -f "$LOCKFILE" ]]; then
    pid=$(cat "$LOCKFILE" 2>/dev/null)
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      age=$(($(date +%s) - $(stat -c %Y "$LOCKFILE" 2>/dev/null || echo 0)))
      if [[ $age -lt $LOCK_MAX_AGE ]]; then
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) GOES already running (pid=$pid), skipping" >> "$LOG"
        return 1
      fi
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Stale lock (${age}s), removing" >> "$LOG"
    fi
    rm -f "$LOCKFILE"
  fi
  echo $$ > "$LOCKFILE"
  return 0
}

acquire_lock || exit 0
trap 'rm -f "$LOCKFILE"' EXIT

PYTHON="$(pwd)/.venv-wxi9/bin/python"
SERVED="$HOME/wx-data/served/radar_local_satellite"

# Disk check: skip if partition > 90% full (avoid write failures)
DISK_PCT=$(df -P "$SERVED" 2>/dev/null | awk 'NR==2 {gsub(/%/,""); print $5}')
if [[ -n "$DISK_PCT" ]] && [[ "$DISK_PCT" -ge 90 ]]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) SKIP: disk ${DISK_PCT}% full" >> "$LOG"
  exit 1
fi

# Optional: --ir-only (~2 min) or --vis-only (~7 min). Default: both (~8 min)
EXTRA_ARGS=("$@")

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) GOES run starting ${EXTRA_ARGS[*]}" >> "$LOG"
if LOCAL_SATELLITE_DIR="$SERVED" PYTHON="$PYTHON" "$PYTHON" bin/update_goes_loop.py \
  --newest \
  --local-only \
  --frames 72 \
  --cadence-min 5 \
  --keep 100 \
  "${EXTRA_ARGS[@]}" 2>> "$LOG"; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) GOES run done" >> "$LOG"
else
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) GOES run FAILED (exit $?)" >> "$LOG"
  exit 1
fi
