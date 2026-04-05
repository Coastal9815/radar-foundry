#!/usr/bin/env bash
# Deploy radar-foundry from Office Mac to wx-core (code + config only).
# Excludes serve_root, out/, scratch — wx-core is source of truth for generated products.
#
# Usage: ./bin/deploy_radar_foundry_to_wx_core.sh
# Override: WX_CORE=wx-core SRC=~/wx/radar-foundry
set -e
cd "$(dirname "$0")/.."
WX_CORE="${WX_CORE:-wx-core}"
DEST="${DEST:-$WX_CORE:~/wx/radar-foundry}"
echo "Deploying to $DEST ..."
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
  --exclude 'serve_cache' --exclude 'scratch' --exclude 'raw_level2' --exclude 'raw' \
  --exclude 'serve_root' --exclude 'out' \
  --exclude 'logs' --exclude 'logs_level2' --exclude 'work' \
  . "$DEST/"
echo "Done. Pipelines on wx-core will use updated code on next run."
