#!/usr/bin/env bash
# Plain-language snapshot of MRW local dev ports (this Mac).
# Usage: from anywhere —  ./bin/weather_dev_status.sh   (run inside radar-foundry, or pass no args)
set -euo pipefail

BIN="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=weather_dev_lib.sh
source "$BIN/weather_dev_lib.sh"

RF_ROOT="$(cd "$BIN/.." && pwd)"
MOON_PORT="${MOONRIVERWEATHER_DEV_PORT:-3010}"
SERVE_PORT=8080

echo "Moon River Weather — local port snapshot (this Mac)"
echo ""
echo "Repo (radar-foundry): $RF_ROOT"
echo "moonriverweather dev port: ${MOON_PORT} (override MOONRIVERWEATHER_DEV_PORT=; package.json defaults to 3010; CCP_Core API defaults to 3001)"
echo "serve_frames port: ${SERVE_PORT} (see bin/serve_frames.py PORT)"
echo ""

weather_describe_port "MRW serve_frames (radar HTTP + players)" "$SERVE_PORT" "serve_frames"
weather_describe_port "moonriverweather-public (Next dev)" "$MOON_PORT" "moonriverweather"

echo "Port layout: Coastal Care Core API → 3001; moonriverweather Next dev → 3010 (see CCP_Core docs/LOCAL_DEV_PORTS.md and WEATHER_DEV_PORTS.md)."
echo "If you override MRW to 3001 while CCP is running, the safe wrapper will refuse to start."
echo ""
echo "Full registry: radar-foundry/docs/local-dev/WEATHER_DEV_PORTS.md"
