#!/usr/bin/env bash
# Deploy radar-foundry from Office Mac directly to wx-i9 (code-only).
# Use when you only changed player/config and don't need fresh lightning GeoJSON.
# For full sync including geo generators, use deploy_wx_core_to_wx_i9.sh instead.
#
# Run from project root on Office Mac.
# Usage: ./bin/deploy_radar_foundry_to_wx_i9.sh
set -e
cd "$(dirname "$0")/.."
WX_I9="${WX_I9:-wx-i9}"
DEST="${DEST:-$WX_I9:~/wx/radar-foundry}"
echo "Deploying code to $DEST (exclude serve_root) ..."
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '.git' --exclude 'serve_root' \
  . "$DEST/"
echo "Running setup_serve_root on $WX_I9 ..."
ssh "$WX_I9" "cd ~/wx/radar-foundry && SERVED_RADAR_BASE=\$HOME/wx-data/served ./bin/setup_serve_root.sh"
echo "Done. Lightning GeoJSON unchanged (produced by wx-core pipelines)."
