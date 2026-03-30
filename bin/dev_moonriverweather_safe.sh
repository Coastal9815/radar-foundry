#!/usr/bin/env bash
# Start moonriverweather-public Next dev only if its port is free or already owned by Next.
# Default port 3001 (package.json). CONFLICTS with CCP_Core API default — see WEATHER_DEV_PORTS.md.
#
# Usage:
#   RADAR_FOUNDRY_ROOT=... ./bin/dev_moonriverweather_safe.sh
# Or run from radar-foundry after setting MOONRIVERWEATHER_ROOT to your clone path.
set -euo pipefail

BIN="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=weather_dev_lib.sh
source "$BIN/weather_dev_lib.sh"

RF_ROOT="$(cd "$BIN/.." && pwd)"
WORKSPACE_ROOT="$(cd "$RF_ROOT/.." && pwd)"

MOON_ROOT="${MOONRIVERWEATHER_ROOT:-$WORKSPACE_ROOT/moonriverweather-public}"
PORT="${MOONRIVERWEATHER_DEV_PORT:-3001}"

if [[ ! -f "$MOON_ROOT/package.json" ]]; then
  echo "moonriverweather-public not found at: $MOON_ROOT" >&2
  echo "Set MOONRIVERWEATHER_ROOT to the repo root, or place moonriverweather-public next to radar-foundry." >&2
  exit 1
fi

weather_assert_port_free_or_ours "$PORT" "moonriverweather"

cd "$MOON_ROOT" || exit 1

if [[ "$PORT" != "3001" ]]; then
  echo "Starting moonriverweather-public: next dev -p ${PORT} --webpack (MOONRIVERWEATHER_DEV_PORT override)" >&2
  exec npx next dev -p "$PORT" --webpack
fi

echo "Starting moonriverweather-public: npm run dev (port 3001 per package.json)…" >&2
exec npm run dev
