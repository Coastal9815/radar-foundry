#!/usr/bin/env bash
# Run GOES satellite pipeline: IR + Visible. Publishes to wx-i9.
# Run every 5 min via launchd. Uses lock with 12-min timeout to prevent stale blocks.
set -e
cd "$(dirname "$0")/.."
[[ $(hostname) == wx-core ]] || [[ $(hostname) == weather-core ]] || exit 0

LOG="/tmp/goes_loop_launchd.log"
LOCKFILE="/tmp/goes_loop.lock"
LOCK_MAX_AGE=720  # 12 min — if lock older, assume stale (run takes ~7 min)

acquire_lock() {
  if [[ -f "$LOCKFILE" ]]; then
    pid=$(cat "$LOCKFILE" 2>/dev/null)
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      # Process running — check age
      age=$(($(date +%s) - $(stat -f %m "$LOCKFILE" 2>/dev/null || echo 0)))
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

REMOTE_BASE="/home/scott/wx-data/served/radar_local_satellite"
PYTHON="$(cd "$(dirname "$0")/.." && pwd)/.venv/bin/python"
export PYTHONUNBUFFERED=1

# --newest: 1 frame per product, ~7 min total. Fits in 12-min window before next launchd.
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) GOES run starting" >> "$LOG"
caffeinate -s -t 3600 "$PYTHON" bin/update_goes_loop.py \
  --newest \
  --frames 72 \
  --cadence-min 5 \
  --keep 100 \
  --remote-base "$REMOTE_BASE" \
  --remote-host wx-i9 \
  --remote-user scott
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) GOES run done" >> "$LOG"
