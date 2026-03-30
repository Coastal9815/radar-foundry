#!/usr/bin/env bash
# Plain-language snapshot of MRW local dev ports (this Mac).
# Usage: from anywhere —  ./bin/weather_dev_status.sh   (run inside radar-foundry, or pass no args)
set -euo pipefail

BIN="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=weather_dev_lib.sh
source "$BIN/weather_dev_lib.sh"

RF_ROOT="$(cd "$BIN/.." && pwd)"
MOON_PORT="${MOONRIVERWEATHER_DEV_PORT:-3001}"
SERVE_PORT=8080

echo "Moon River Weather — local port snapshot (this Mac)"
echo ""
echo "Repo (radar-foundry): $RF_ROOT"
echo "moonriverweather dev port: ${MOON_PORT} (override with MOONRIVERWEATHER_DEV_PORT=; package.json defaults to 3001)"
echo "serve_frames port: ${SERVE_PORT} (see bin/serve_frames.py PORT)"
echo ""

weather_describe_port "MRW serve_frames (radar HTTP + players)" "$SERVE_PORT" "serve_frames"
weather_describe_port "moonriverweather-public (Next dev)" "$MOON_PORT" "moonriverweather"

echo "Conflict note: Coastal Care Core API also defaults to port 3001 (see CCP_Core docs/LOCAL_DEV_PORTS.md)."
echo "Do not run CCP backend and moonriverweather dev on the same port without changing one."
echo ""
echo "Full registry: radar-foundry/docs/local-dev/WEATHER_DEV_PORTS.md"
