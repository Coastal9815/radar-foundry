#!/bin/bash
# Run this ON THE OFFICE MAC to verify no MRW artifacts that belong on weather-core.
# Usage: ./bin/verify_office_mac_clean.sh
# The office Mac should NOT have: serve_frames running, radar frames, or MRW serving.

if [[ $(hostname) == wx-core ]]; then
  echo "This is weather-core (wx-core). Run this script on the office Mac instead."
  echo "From the office Mac: cd ~/wx/radar-foundry && ./bin/verify_office_mac_clean.sh"
  exit 0
fi

echo "=== Office Mac MRW Verification ==="
echo ""

# 1. Check if serve_frames is running (should NOT be on office Mac)
if pgrep -f "serve_frames.py" > /dev/null; then
  echo "⚠️  serve_frames.py is RUNNING on this machine - should only run on weather-core"
  echo "   Kill with: pkill -f serve_frames.py"
else
  echo "✓ serve_frames.py is not running"
fi

# 2. Check if port 8080 is in use (MRW serves on 8080)
if lsof -ti:8080 > /dev/null 2>&1; then
  echo "⚠️  Port 8080 is in use - something may be serving MRW here"
  lsof -i:8080 | head -5
else
  echo "✓ Port 8080 is not in use"
fi

# 3. Check for radar frames on external drive (office Mac shouldn't be generating these)
RADAR="/Volumes/WX_SCRATCH/mrw/radar"
if [ -d "$RADAR" ]; then
  KCLX_COUNT=$(find "$RADAR/KCLX" -name "*.png" 2>/dev/null | wc -l)
  echo "  $RADAR exists: $KCLX_COUNT KCLX frames"
  echo "  (If office Mac generated these, they're in the wrong place - weather-core should own them)"
else
  echo "✓ $RADAR not mounted (or doesn't exist)"
fi

# 4. Check project out/ for generated basemap (should be generated on weather-core)
OUT_BASEMAP="/Users/scott/wx/radar-foundry/out/basemap_MRWcenter_1600.png"
if [ -f "$OUT_BASEMAP" ]; then
  MTIME=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$OUT_BASEMAP" 2>/dev/null)
  echo "  out/basemap exists, modified: $MTIME"
  echo "  (If generated on office Mac, weather-core has the canonical copy)"
else
  echo "✓ No basemap in out/"
fi

echo ""
echo "=== Summary ==="
echo "Office Mac should: edit files, run Cursor. Nothing else."
echo "Weather-core should: run serve_frames, radar loop, generate basemap & frames."
