#!/usr/bin/env bash
# Xweather lightning loop on wx-i9: fetch has HTTPS; write GeoJSON into local serve_root.
# Credentials: ~/.mrw/xweather.env (same as weather-core).
# systemd: conf/systemd/user/mrw-lightning-xweather-fetch.service
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f "$HOME/.mrw/xweather.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$HOME/.mrw/xweather.env"
  set +a
fi
export MRW_LIGHTNING_PUBLISH_LOCAL=1
exec .venv/bin/python bin/lightning_xweather_fetch.py --loop --interval 10 --radius 100 --post-generate
