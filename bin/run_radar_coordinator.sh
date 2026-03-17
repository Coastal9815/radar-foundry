#!/bin/bash
# Run radar_loop_coordinator: KCLX + KJAX in parallel, publish to wx-i9.
# MUST run on weather-core (wx-core) only. Replace separate KCLX/KJAX launchd jobs with this.
[[ $(hostname) == wx-core ]] || exit 0

export HOME=/Users/scott
export PATH=/Users/scott/wx/radar-foundry/.venv/bin:/usr/local/bin:/usr/bin:/bin
export WX_SCRATCH_BASE=/Users/scott/wx/radar-foundry/scratch

cd /Users/scott/wx/radar-foundry || exit 1

echo "RUN_COORD_START $(/bin/date)" >> /tmp/radar_coordinator_launchd.log
/Users/scott/wx/radar-foundry/.venv/bin/python ./bin/radar_loop_coordinator.py >> /tmp/radar_coordinator_launchd.log 2>&1
rc=$?
echo "RUN_COORD_END rc=$rc $(/bin/date)" >> /tmp/radar_coordinator_launchd.log
exit $rc
