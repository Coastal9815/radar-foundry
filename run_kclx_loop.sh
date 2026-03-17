#!/bin/bash

export WX_SCRATCH_BASE="$HOME/wx-scratch/radar-foundry"

cd "$HOME/wx/radar-foundry" || exit 1

source "$HOME/wx/radar-foundry/.venv/bin/activate"

./bin/update_radar_loop.py --site KCLX --remote-base /wx-data/served/radar_local_kclx/frames
