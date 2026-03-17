#!/usr/bin/env bash
# Pull radar-foundry from weather-core (wx-core) to local machine.
# Run from Office Mac (or any machine that can ssh to wx-core).
# Usage: ./bin/sync_from_wx_core.sh
# Creates/updates ~/wx/radar-foundry/ locally.
set -e
SOURCE="${SOURCE:-wx-core:~/wx/radar-foundry}"
DEST="${DEST:-$HOME/wx/radar-foundry}"
mkdir -p "$DEST"
echo "Pulling from $SOURCE to $DEST ..."
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
  --exclude 'serve_cache' --exclude 'scratch' --exclude 'raw_level2' --exclude 'raw' \
  --exclude 'logs' --exclude 'logs_level2' --exclude 'work' \
  "$SOURCE/" "$DEST/"
echo "Done. Local copy at $DEST"
