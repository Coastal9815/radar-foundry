#!/bin/bash
# Run Xweather lightning fetch loop. Used by launchd.
# Credentials: create ~/.mrw/xweather.env with:
#   export XWEATHER_CLIENT_ID="your_id"
#   export XWEATHER_CLIENT_SECRET="your_secret"
# Uses lock file to prevent duplicate instances (launchd + manual, or double-load).
LOCKFILE="/tmp/lightning_xweather_fetch.lock"
LOCK_MAX_AGE=120  # 2 min; if lock older and PID dead, assume stale

acquire_lock() {
  if [[ -f "$LOCKFILE" ]]; then
    pid=$(cat "$LOCKFILE" 2>/dev/null)
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Xweather fetch already running (pid=$pid), exiting" >> /tmp/lightning_xweather_fetch.log
      exit 0
    fi
    age=$(($(date +%s) - $(stat -f %m "$LOCKFILE" 2>/dev/null || echo 0)))
    if [[ $age -lt $LOCK_MAX_AGE ]]; then
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Stale lock (${age}s), removing" >> /tmp/lightning_xweather_fetch.log
    fi
    rm -f "$LOCKFILE"
  fi
  echo $$ > "$LOCKFILE"
}

[ -f ~/.mrw/xweather.env ] && . ~/.mrw/xweather.env

cd "$(dirname "$0")/.."
acquire_lock
trap 'rm -f "$LOCKFILE"' EXIT

if [ -x .venv/bin/python ]; then
  exec .venv/bin/python bin/lightning_xweather_fetch.py --loop --interval 10 --radius 100 --post-generate
else
  exec python3 bin/lightning_xweather_fetch.py --loop --interval 10 --radius 100 --post-generate
fi
