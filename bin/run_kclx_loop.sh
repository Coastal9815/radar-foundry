#!/bin/bash
# MUST run on weather-core (wx-core) only. Exit silently if on wrong host.
[[ $(hostname) == wx-core ]] || exit 0

export HOME=/Users/scott
export PATH=/Users/scott/wx/radar-foundry/.venv/bin:/usr/local/bin:/usr/bin:/bin
# Use project-local scratch for launchd (wx-scratch may have sandbox restrictions)
export WX_SCRATCH_BASE=/Users/scott/wx/radar-foundry/scratch

cd /Users/scott/wx/radar-foundry || exit 1

LOCK=/tmp/mrw_radar_loop.lock
if [ -f "$LOCK" ] && [ $(($(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || echo 0))) -lt 300 ]; then
  echo "RUN_KCLX_SKIP (locked) $(/bin/date)" >> /tmp/kclx_launchd.log
  exit 0
fi
touch "$LOCK"
trap "rm -f $LOCK" EXIT
echo "RUN_KCLX_START $(/bin/date)" >> /tmp/kclx_launchd.log
HOME=/Users/scott WX_SCRATCH_BASE=/Users/scott/wx/radar-foundry/scratch \
  /Users/scott/wx/radar-foundry/.venv/bin/python ./bin/fetch_latest_level2.py --list-only KCLX > /tmp/fetch_meta_KCLX.json 2>>/tmp/kclx_launchd.log || exit 1
url=$(/Users/scott/wx/radar-foundry/.venv/bin/python -c "import json; print(json.load(open('/tmp/fetch_meta_KCLX.json'))['url'])")
out=$(/Users/scott/wx/radar-foundry/.venv/bin/python -c "import json; print(json.load(open('/tmp/fetch_meta_KCLX.json'))['out_path'])")
mkdir -p "$(dirname "$out")"
/usr/bin/curl -sSf -o "$out" --max-time 180 "$url" 2>>/tmp/kclx_launchd.log || exit 1
HOME=/Users/scott WX_SCRATCH_BASE=/Users/scott/wx/radar-foundry/scratch \
  /Users/scott/wx/radar-foundry/.venv/bin/python ./bin/update_radar_loop.py --site KCLX --local-only --fetch-meta /tmp/fetch_meta_KCLX.json < /dev/null >> /tmp/kclx_launchd.log 2>&1
echo "RUN_KCLX_END rc=$? $(/bin/date)" >> /tmp/kclx_launchd.log
