#!/bin/bash
export WX_SCRATCH_BASE=$HOME/wx-scratch/radar-foundry
cd $HOME/wx/radar-foundry
./bin/update_radar_loop.py --site KJAX --remote-base /wx-data/served/radar_local_kjax/frames
