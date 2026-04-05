#!/usr/bin/env bash
# wx-core (and other MRW Macs): daily TCP/HTTPS/LaunchAgent snapshot + weekly SSH multiplex refresh.
# Scheduled by: conf/launchd/com.mrw.host_protect.plist
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${MRW_HOST_PROTECT_LOG:-/tmp/mrw_host_protect.log}"
MAX_LOG_LINES=800

if [[ -f "$LOG" ]] && [[ $(wc -l < "$LOG" | tr -d ' ') -gt $MAX_LOG_LINES ]]; then
  tail -600 "$LOG" > "${LOG}.tmp"
  mv "${LOG}.tmp" "$LOG"
fi

ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
tw="$(netstat -an -p tcp 2>/dev/null | awk '/TIME_WAIT/{n++} END{print n+0}')"
fw2="$(netstat -an -p tcp 2>/dev/null | awk '/FIN_WAIT_2/{n++} END{print n+0}')"
https="ok"
if ! curl -4 -fsS -o /dev/null -m 12 https://www.apple.com/ 2>/dev/null; then
  https="FAIL"
fi

uid="$(id -u)"
gui="gui/${uid}"

xwf="ok"
if [[ ! -f "$HOME/Library/LaunchAgents/com.mrw.lightning_xweather_fetch.plist" ]]; then
  xwf="MISSING_PLIST"
elif ! launchctl print "${gui}/com.mrw.lightning_xweather_fetch" &>/dev/null; then
  xwf="NOT_IN_DOMAIN"
fi

nexf="ok"
if [[ ! -f "$HOME/Library/LaunchAgents/com.mrw.lightning_nex_tail.plist" ]]; then
  nexf="MISSING_PLIST"
elif ! launchctl print "${gui}/com.mrw.lightning_nex_tail" &>/dev/null; then
  nexf="NOT_IN_DOMAIN"
fi

echo "$ts protect tw=$tw fw2=$fw2 https=$https xweather=$xwf nex_tail=$nexf host=$(hostname -s)" >> "$LOG"

if [[ "$tw" -gt 12000 ]]; then
  echo "$ts ALERT TIME_WAIT=$tw (ephemeral port risk)" >> "$LOG"
fi
if [[ "$https" != "ok" ]]; then
  echo "$ts ALERT HTTPS_PROBE_FAILED" >> "$LOG"
fi
if [[ "$xwf" != "ok" ]] || [[ "$nexf" != "ok" ]]; then
  echo "$ts ALERT lightning_jobs xweather=$xwf nex_tail=$nexf" >> "$LOG"
fi

# Sunday UTC: refresh SSH multiplex config from repo (survives hand-edited ssh, OS upgrades).
dow="$(date -u +%w)"
if [[ "$dow" == "0" ]]; then
  if ! bash "$REPO/bin/install_ssh_multiplex_mrw.sh" >> "$LOG" 2>&1; then
    echo "$ts WARN install_ssh_multiplex_mrw failed" >> "$LOG"
  fi
fi
