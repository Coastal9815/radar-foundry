#!/usr/bin/env bash
# Fetch NWS SVR/TOR alerts and write alerts.json.
# Local: writes to serve_root/alerts.json
# Remote: scps to wx-i9 serve_root (use --remote)
set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)/serve_root"
PY=".venv/bin/python"
[ -x "$PY" ] || PY=python3

"$PY" bin/fetch_nws_alerts.py --serve-root "$ROOT" 2>/dev/null || true

if [ "$1" = "--remote" ]; then
  scp "$ROOT/alerts.json" "scott@wx-i9:~/wx/radar-foundry/serve_root/alerts.json" 2>/dev/null || true
fi
