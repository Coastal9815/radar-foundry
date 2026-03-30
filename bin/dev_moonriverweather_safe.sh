#!/usr/bin/env bash
# Start moonriverweather-public Next dev only if its port is free or already owned by Next.
# Default port 3010 (package.json). Coastal Care Core API defaults to 3001 — see WEATHER_DEV_PORTS.md.
#
# Usage:
#   RADAR_FOUNDRY_ROOT=... ./bin/dev_moonriverweather_safe.sh
# Or run from radar-foundry after setting MOONRIVERWEATHER_ROOT to your clone path.
# Override port: MOONRIVERWEATHER_DEV_PORT=3020 ./bin/dev_moonriverweather_safe.sh
set -euo pipefail

BIN="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=weather_dev_lib.sh
source "$BIN/weather_dev_lib.sh"

RF_ROOT="$(cd "$BIN/.." && pwd)"
WORKSPACE_ROOT="$(cd "$RF_ROOT/.." && pwd)"

MOON_ROOT="${MOONRIVERWEATHER_ROOT:-$WORKSPACE_ROOT/moonriverweather-public}"
# Keep in sync with moonriverweather-public package.json "dev" -p value.
MOON_DEFAULT_PORT=3010
PORT="${MOONRIVERWEATHER_DEV_PORT:-$MOON_DEFAULT_PORT}"

if [[ ! -f "$MOON_ROOT/package.json" ]]; then
  echo "moonriverweather-public not found at: $MOON_ROOT" >&2
  echo "Set MOONRIVERWEATHER_ROOT to the repo root, or place moonriverweather-public next to radar-foundry." >&2
  exit 1
fi

weather_assert_port_free_or_ours "$PORT" "moonriverweather"

cd "$MOON_ROOT" || exit 1

if [[ "$PORT" != "$MOON_DEFAULT_PORT" ]]; then
  echo "Starting moonriverweather-public: next dev -p ${PORT} --webpack (MOONRIVERWEATHER_DEV_PORT override)" >&2
  exec npx next dev -p "$PORT" --webpack
fi

echo "Starting moonriverweather-public: npm run dev (port ${MOON_DEFAULT_PORT} per package.json)…" >&2
exec npm run dev
