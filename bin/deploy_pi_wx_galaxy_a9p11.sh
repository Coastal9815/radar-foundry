#!/usr/bin/env bash
# Deploy Galaxy A9+ dashboard files from repo to pi-wx ~/dashboard/ui/
set -euo pipefail
cd "$(dirname "$0")/.."
PI_WX="${PI_WX:-pi-wx}"
SRC="pi-wx-dashboard/galaxy-a9p11"
DEST="${PI_WX}:~/dashboard/ui/"

for f in galaxyA9p11.html a9p_header.js a9p_rain_accum.js a9p_rain.js a9p_threat.js a9p_tide.js; do
  test -f "$SRC/$f" || { echo "Missing $SRC/$f" >&2; exit 1; }
done

echo "Deploying $SRC -> $DEST ..."
rsync -avz \
  "$SRC/galaxyA9p11.html" \
  "$SRC/a9p_header.js" \
  "$SRC/a9p_rain_accum.js" \
  "$SRC/a9p_rain.js" \
  "$SRC/a9p_threat.js" \
  "$SRC/a9p_tide.js" \
  "$DEST"

echo "Verifying HTTP ..."
code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "http://192.168.2.174/ui/galaxyA9p11.html" || echo "000")
if [[ "$code" != "200" ]]; then
  echo "ERROR: galaxyA9p11.html returned HTTP $code (expected 200)" >&2
  exit 1
fi
echo "OK: HTTP 200"
