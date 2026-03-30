#!/usr/bin/env bash
# Start radar-foundry serve_frames.py only if port 8080 is free or already owned by serve_frames.
# Does not fall back to another port. Does not kill foreign processes.
#
# Usage (from radar-foundry root recommended):
#   ./bin/dev_serve_frames_safe.sh
# Optional: use existing wrapper that waits for WX_SCRATCH:
#   MRW_USE_WRAPPER=1 ./bin/dev_serve_frames_safe.sh
set -euo pipefail

BIN="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=weather_dev_lib.sh
source "$BIN/weather_dev_lib.sh"

RF_ROOT="$(cd "$BIN/.." && pwd)"
PORT=8080
# Must match bin/serve_frames.py (no env override in Python today).

weather_assert_port_free_or_ours "$PORT" "serve_frames"

cd "$RF_ROOT" || exit 1
if [[ -x "$RF_ROOT/.venv/bin/python" ]]; then
  PY="$RF_ROOT/.venv/bin/python"
else
  PY="$(command -v python3)"
fi

echo "Starting serve_frames on port 8080…"
echo "(Requires serve_root or /Volumes/WX_SCRATCH/mrw/radar — see serve_frames.py)"
echo ""

if [[ "${MRW_USE_WRAPPER:-0}" == "1" ]] && [[ -x "$BIN/serve_frames_wrapper.sh" ]]; then
  exec "$BIN/serve_frames_wrapper.sh"
fi

exec "$PY" "$RF_ROOT/bin/serve_frames.py"
