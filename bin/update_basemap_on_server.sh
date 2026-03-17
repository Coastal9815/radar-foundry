#!/bin/bash
# Regenerate basemap on weather-core (where serve_frames runs).
# Run from anywhere - SSHs to weather-core to run make_basemap_grid.
# Usage: ./bin/update_basemap_on_server.sh
# Or if already on weather-core: cd ~/wx/radar-foundry && .venv/bin/python bin/make_basemap_grid.py --conf conf

set -e
HOST="${1:-weather-core}"
PROJECT="/Users/scott/wx/radar-foundry"

if [[ $(hostname) == wx-core ]]; then
  echo "Running locally on weather-core..."
  cd "$PROJECT" || exit 1
  .venv/bin/python bin/make_basemap_grid.py --conf conf
  echo "Done. Hard-refresh the player (Cmd+Shift+R) to see the new basemap."
else
  echo "SSHing to $HOST to regenerate basemap..."
  ssh "$HOST" "cd $PROJECT && .venv/bin/python bin/make_basemap_grid.py --conf conf"
  echo "Done. Hard-refresh the player (Cmd+Shift+R) to see the new basemap."
fi
