#!/bin/bash
# Fix duplicate Xweather poller processes on weather-core.
# Run from office Mac: ./bin/fix_xweather_duplicates.sh
# 1. Syncs updated run script (with lockfile) to weather-core
# 2. Runs the fix on weather-core
set -e
cd "$(dirname "$0")/.."

echo "=== Syncing updated scripts to weather-core ==="
rsync -avz bin/run_lightning_xweather_fetch.sh bin/fix_xweather_duplicates_on_weather_core.sh \
  weather-core:~/wx/radar-foundry/bin/
rsync -avz conf/launchd/com.mrw.lightning_xweather_fetch.plist \
  weather-core:~/Library/LaunchAgents/

echo ""
echo "=== Running fix on weather-core ==="
ssh weather-core "cd ~/wx/radar-foundry && chmod +x bin/fix_xweather_duplicates_on_weather_core.sh && ./bin/fix_xweather_duplicates_on_weather_core.sh"

echo ""
echo "=== Verification (run from your Mac) ==="
echo "ssh weather-core \"pgrep -fl lightning_xweather_fetch; echo '---'; tail -5 /tmp/lightning_xweather_fetch.log; echo '---'; wc -l ~/wx/radar-foundry/scratch/lightning_xweather/lightning_xweather_rt.ndjson 2>/dev/null || echo '0 (file will populate)'\""
