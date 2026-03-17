#!/usr/bin/env bash
# Seed or refresh radar-foundry from wx-core onto the Office Mac.
# Run from Office Mac. Creates/updates ~/wx/radar-foundry locally.
#
# Usage: ./bin/seed_radar_foundry_from_wx_core.sh
# Override: SOURCE=wx-core:~/wx/radar-foundry DEST=~/wx/radar-foundry
set -e
cd "$(dirname "$0")/.."
SOURCE="${SOURCE:-wx-core:~/wx/radar-foundry}"
DEST="${DEST:-$HOME/wx/radar-foundry}"
mkdir -p "$DEST"
echo "Pulling from $SOURCE to $DEST ..."
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
  --exclude 'serve_cache' --exclude 'scratch' --exclude 'raw_level2' --exclude 'raw' \
  --exclude 'logs' --exclude 'logs_level2' --exclude 'work' \
  "$SOURCE/" "$DEST/"
echo "Done. Local copy at $DEST"
echo "If needed: cd $DEST && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
