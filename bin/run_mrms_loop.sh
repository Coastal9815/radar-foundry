#!/usr/bin/env bash
# Run MRMS pipeline: incremental (1 newest frame) or full rebuild. Publishes to wx-i9.
# Incremental: ~1-2 min, near real-time like NEXRAD. Full: ~20-30 min (cold start only).
# Only runs on wx-core (weather-core). Requires SSH to wx-i9.
# Uses lock file to prevent overlap (launchd can fire while previous run still in progress).
set -e
cd "$(dirname "$0")/.."
[[ $(hostname) == wx-core ]] || exit 0

MRMS_RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
MRMS_START_EPOCH=$(date +%s)
LOCKFILE="/tmp/mrms_loop.lock"
if [[ -f "$LOCKFILE" ]]; then
  pid=$(cat "$LOCKFILE" 2>/dev/null)
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) MRMS already running (pid=$pid), skipping" >> /tmp/mrms_loop_launchd.log
    exit 0
  fi
fi
echo $$ > "$LOCKFILE"
trap 'ec=$?; dur=$(($(date +%s)-MRMS_START_EPOCH)); rm -f "$LOCKFILE"; echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) MRMS exit=$ec" >> /tmp/mrms_loop_launchd.log; echo "MRMS_TIMING|ts_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)|run_id=$MRMS_RUN_ID|duration_sec=$dur|exit_code=$ec" >> /tmp/mrms_loop_launchd.log; exit $ec' EXIT

REMOTE_BASE="/home/scott/wx-data/served/radar_local_mrms"
export MRMS_RUN_ID
PYTHON="$(cd "$(dirname "$0")/.." && pwd)/.venv/bin/python"
# caffeinate -s: prevent system sleep during run (Mac Studio can sleep overnight, breaking launchd)
# -t 1500: max 25 min; if python hangs, caffeinate won't block forever
export PYTHONUNBUFFERED=1
caffeinate -s -t 1500 "$PYTHON" bin/update_mrms_loop.py \
  --frames 36 \
  --cadence-min 10 \
  --keep 200 \
  --remote-base "$REMOTE_BASE" \
  --remote-host wx-i9 \
  --remote-user scott
