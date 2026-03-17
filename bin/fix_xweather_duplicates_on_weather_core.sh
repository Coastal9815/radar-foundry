#!/bin/bash
# Fix duplicate Xweather poller processes on weather-core.
# Run from office Mac: ./bin/fix_xweather_duplicates_on_weather_core.sh
# Or: ssh weather-core 'bash -s' < bin/fix_xweather_duplicates_on_weather_core.sh
set -e
cd "$(dirname "$0")/.."
REPO="$(pwd)"

echo "=== 1. Kill all lightning_xweather_fetch processes ==="
pkill -f "lightning_xweather_fetch.py" 2>/dev/null || true
sleep 2
# Ensure none remain
for pid in $(pgrep -f "lightning_xweather_fetch.py" 2>/dev/null); do
  echo "Force-killing pid=$pid"
  kill -9 "$pid" 2>/dev/null || true
done
sleep 1
count=$(pgrep -f "lightning_xweather_fetch.py" 2>/dev/null | wc -l)
[[ "$count" -eq 0 ]] || { echo "ERROR: $count process(es) still running"; exit 1; }
echo "All poller processes stopped."

echo ""
echo "=== 2. Unload launchd job ==="
launchctl unload ~/Library/LaunchAgents/com.mrw.lightning_xweather_fetch.plist 2>/dev/null || true
sleep 1
echo "Launchd job unloaded."

echo ""
echo "=== 3. Remove stale lock if any ==="
rm -f /tmp/lightning_xweather_fetch.lock
echo "Lock cleared."

echo ""
echo "=== 4. Remove NDJSON archive (clean start, no test records) ==="
rm -f "$REPO/scratch/lightning_xweather/lightning_xweather_rt.ndjson"
echo "NDJSON removed."

echo ""
echo "=== 5. Reload launchd job ==="
cp "$REPO/conf/launchd/com.mrw.lightning_xweather_fetch.plist" ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mrw.lightning_xweather_fetch.plist
sleep 3
echo "Launchd job loaded."

echo ""
echo "=== 6. Verify single poller running ==="
pids=$(pgrep -f "lightning_xweather_fetch.py" 2>/dev/null)
n=$(echo "$pids" | grep -c . 2>/dev/null || echo 0)
if [[ "$n" -eq 1 ]]; then
  echo "OK: Exactly 1 poller process (pid=$(echo $pids))"
else
  echo "ERROR: Expected 1 process, found $n"
  ps aux | grep lightning_xweather || true
  exit 1
fi

echo ""
echo "=== 7. Check log ==="
tail -5 /tmp/lightning_xweather_fetch.log 2>/dev/null || echo "(log empty or missing)"

echo ""
echo "=== Done ==="
