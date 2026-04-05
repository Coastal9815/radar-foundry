#!/usr/bin/env bash
# Sync project to wx-i9 so new players (mrms, etc.) and scripts are available.
# Run from project root. Adjust WX_I9 and DEST if needed.
#
# HARDENING: serve_root is EXCLUDED from rsync. Mac serve_root has KCLX/KJAX symlinks
# to /Volumes/WX_SCRATCH/... which don't exist on Linux. Overwriting would break radar.
# setup_serve_root creates serve_root on wx-i9 with correct symlinks. See .cursor/rules/sync-serve-root-hardening.mdc
set -e
cd "$(dirname "$0")/.."
WX_I9="${WX_I9:-wx-i9}"
DEST="${DEST:-$WX_I9:~/wx/radar-foundry}"
BASE_URL="${SYNC_VERIFY_URL:-http://192.168.2.2:8080}"

echo "Removing bogus player/player on $WX_I9 (if any) ..."
ssh "$WX_I9" "rm -rf \"\$HOME/wx/radar-foundry/player/player\""

echo "Syncing to $DEST (exclude serve_root) ..."
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '.git' --exclude 'serve_root' \
  . "$DEST"/

echo "Generating lightning_range_rings.geojson..."
[ -x .venv/bin/python ] && .venv/bin/python bin/generate_lightning_range_rings.py 2>/dev/null || true

echo "Generating lightning_points.geojson..."
[ -x .venv/bin/python ] && .venv/bin/python bin/generate_lightning_points.py --remote 2>/dev/null || true

echo "Generating lightning_points_v2.geojson..."
[ -x .venv/bin/python ] && .venv/bin/python bin/generate_lightning_points_v2.py --remote 2>/dev/null || true

echo "Generating lightning_points_xweather_local.geojson..."
[ -x .venv/bin/python ] && .venv/bin/python bin/generate_lightning_points_xweather_local.py --remote 2>/dev/null || true

echo "Creating frames dirs and re-running setup_serve_root on $WX_I9 ..."
ssh "$WX_I9" "mkdir -p ~/wx-data/served/radar_local_KCLX/frames ~/wx-data/served/radar_local_KJAX/frames ~/wx-data/served/radar_local_mrms/frames ~/wx-data/served/radar_local_satellite/ir ~/wx-data/served/radar_local_satellite/vis && cd ~/wx/radar-foundry && SERVED_RADAR_BASE=\$HOME/wx-data/served ./bin/setup_serve_root.sh"

[ -f serve_root/lightning_range_rings.geojson ] && scp -q serve_root/lightning_range_rings.geojson "$WX_I9:~/wx/radar-foundry/serve_root/" 2>/dev/null || true
[ -f serve_root/lightning_points.geojson ] && scp -q serve_root/lightning_points.geojson "$WX_I9:~/wx/radar-foundry/serve_root/" 2>/dev/null || true
[ -f serve_root/lightning_points_v2.geojson ] && scp -q serve_root/lightning_points_v2.geojson "$WX_I9:~/wx/radar-foundry/serve_root/" 2>/dev/null || true
[ -f serve_root/lightning_points_xweather_local.geojson ] && scp -q serve_root/lightning_points_xweather_local.geojson "$WX_I9:~/wx/radar-foundry/serve_root/" 2>/dev/null || true

echo "Verifying KCLX/KJAX manifests..."
for site in KCLX KJAX; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "$BASE_URL/$site/manifest.json" 2>/dev/null || echo "000")
  if [ "$code" != "200" ]; then
    echo "ERROR: $site/manifest.json returned HTTP $code (expected 200)" >&2
    exit 1
  fi
done
echo "OK: KCLX and KJAX manifests return 200"

echo "Done. MRMS player: http://192.168.2.2:8080/player/mrms/"
