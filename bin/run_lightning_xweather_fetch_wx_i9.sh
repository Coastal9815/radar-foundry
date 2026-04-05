#!/usr/bin/env bash
# FALLBACK ONLY — canonical Xweather loop runs on wx-core (LaunchAgent com.mrw.lightning_xweather_fetch).
# Use this + systemd unit only if wx-core cannot reach HTTPS for an extended period.
# Credentials: ~/.mrw/xweather.env
# systemd: conf/systemd/user/mrw-lightning-xweather-fetch.service (normally disabled)
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
