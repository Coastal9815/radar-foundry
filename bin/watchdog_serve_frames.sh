#!/bin/bash
# Watchdog: ensure serve_frames is responding. If health check fails, restart it.
# Runs on wx-i9 only. Add to root crontab: */5 * * * * /home/scott/wx/radar-foundry/bin/watchdog_serve_frames.sh
[[ $(hostname) == wx-i9 ]] || exit 0

LOG=/tmp/mrw_serve_frames_watchdog.log
PROJECT="${MRW_PROJECT:-$HOME/wx/radar-foundry}"
HEALTH_URL="http://127.0.0.1:8080/player/kclx/"
TIMEOUT=5

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) watchdog start" >> "$LOG"

code=$(curl -s -o /dev/null -w '%{http_code}' -m "$TIMEOUT" "$HEALTH_URL" 2>/dev/null)
if [[ "$code" =~ ^[23][0-9][0-9]$ ]]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) watchdog: ok" >> "$LOG"
  exit 0
fi

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) watchdog: health check FAILED - restarting serve_frames" >> "$LOG"

if systemctl is-active --quiet mrw-serve-frames 2>/dev/null; then
  (id -u | grep -q '^0$') && systemctl restart mrw-serve-frames || sudo systemctl restart mrw-serve-frames
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) watchdog: systemctl restart mrw-serve-frames" >> "$LOG"
else
  pkill -f "serve_frames.py" 2>/dev/null
  sleep 2
  cd "$PROJECT" && nohup python3 bin/serve_frames.py >> /tmp/serve_frames.log 2>&1 &
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) watchdog: pkill + nohup restart" >> "$LOG"
fi
