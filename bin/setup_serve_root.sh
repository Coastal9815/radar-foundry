#!/usr/bin/env bash
# Create serve_root with symlinks so serve_frames can serve players + radar + basemaps.
# Run from project root or with PROJECT_ROOT set.
#
# Modes:
#   Local (weather-core): RADAR_DIR=/Volumes/WX_SCRATCH/mrw/radar (default)
#   Remote (wx-i9): SERVED_RADAR_BASE=$HOME/wx-data/served — symlinks KCLX/KJAX to radar_local_*/frames
#
# IMPORTANT: On wx-i9 (Linux), you MUST set SERVED_RADAR_BASE. Do NOT use local mode —
# /Volumes/ paths do not exist on Linux and symlinks will be broken.
set -e
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
ROOT="$PROJECT_ROOT/serve_root"
mkdir -p "$ROOT/basemaps"

# Radar symlinks: local (WX_SCRATCH) or remote (wx-i9 served dirs)
if [ -n "$SERVED_RADAR_BASE" ]; then
  # wx-i9: frames at $HOME/wx-data/served/radar_local_KCLX/frames etc.
  # Validate targets exist before creating symlinks (prevents broken Mac-path symlinks on Linux)
  for sub in "radar_local_KCLX/frames" "radar_local_KJAX/frames" "radar_local_mrms" "radar_local_satellite"; do
    if [ ! -e "$SERVED_RADAR_BASE/$sub" ]; then
      echo "ERROR: Target does not exist: $SERVED_RADAR_BASE/$sub" >&2
      echo "On wx-i9, run: mkdir -p ~/wx-data/served/radar_local_{KCLX,KJAX}/frames ~/wx-data/served/radar_local_{mrms,satellite}/ir ~/wx-data/served/radar_local_satellite/vis" >&2
      exit 1
    fi
  done
  ln -sf "$SERVED_RADAR_BASE/radar_local_KCLX/frames" "$ROOT/KCLX"
  ln -sf "$SERVED_RADAR_BASE/radar_local_KJAX/frames" "$ROOT/KJAX"
  ln -sf "$SERVED_RADAR_BASE/radar_local_mrms" "$ROOT/mrms"
  ln -sf "$SERVED_RADAR_BASE/radar_local_satellite" "$ROOT/satellite"
  [ -f "$PROJECT_ROOT/conf/satellite_config.json" ] && cp "$PROJECT_ROOT/conf/satellite_config.json" "$SERVED_RADAR_BASE/radar_local_satellite/config.json"
  echo "serve_root: remote mode (SERVED_RADAR_BASE=$SERVED_RADAR_BASE)"
else
  RADAR_DIR="${RADAR_DIR:-/Volumes/WX_SCRATCH/mrw/radar}"
  # Refuse Mac paths on Linux — prevents broken symlinks when serve_root is rsynced from Mac
  if [ "$(uname -s)" = "Linux" ] && [[ "$RADAR_DIR" == /Volumes/* ]]; then
    echo "ERROR: On Linux, RADAR_DIR must not use /Volumes/ (Mac paths). Set SERVED_RADAR_BASE instead:" >&2
    echo "  SERVED_RADAR_BASE=\$HOME/wx-data/served ./bin/setup_serve_root.sh" >&2
    exit 1
  fi
  for sub in "KCLX" "KJAX"; do
    if [ ! -e "$RADAR_DIR/$sub" ]; then
      echo "WARN: $RADAR_DIR/$sub does not exist; symlink may be broken" >&2
    fi
  done
  ln -sf "$RADAR_DIR/KCLX" "$ROOT/KCLX"
  ln -sf "$RADAR_DIR/KJAX" "$ROOT/KJAX"
  [ -d "$PROJECT_ROOT/out/mrms" ] && ln -sf "$PROJECT_ROOT/out/mrms" "$ROOT/mrms" || true
  [ -d "$PROJECT_ROOT/out/satellite" ] && ln -sf "$PROJECT_ROOT/out/satellite" "$ROOT/satellite" || true
  [ -f "$PROJECT_ROOT/conf/satellite_config.json" ] && [ -d "$PROJECT_ROOT/out/satellite" ] && cp "$PROJECT_ROOT/conf/satellite_config.json" "$PROJECT_ROOT/out/satellite/config.json"
fi

# Basemap: generate on weather-core; on wx-i9 use existing or sync from weather-core
if [ -f "$PROJECT_ROOT/.venv/bin/python" ] 2>/dev/null; then
  "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/bin/make_basemap_grid.py" --conf "$PROJECT_ROOT/conf" 2>/dev/null || true
fi
[ -f "$PROJECT_ROOT/out/basemap_MRWcenter_1600.png" ] && ln -sf "$PROJECT_ROOT/out/basemap_MRWcenter_1600.png" "$ROOT/basemaps/basemap_MRWcenter_1600.png"
[ -f "$PROJECT_ROOT/out/basemap_MRWcenter_1600.svg" ] && ln -sf "$PROJECT_ROOT/out/basemap_MRWcenter_1600.svg" "$ROOT/basemaps/basemap_MRWcenter_1600.svg"

ln -sf "$PROJECT_ROOT/player" "$ROOT/player"

# NWS alerts: fetch SVR/TOR/TOR watch/SVR watch/SWS for GA,SC,FL; create alerts.json if Python available
if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
  "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/bin/fetch_nws_alerts.py" --serve-root "$ROOT" 2>/dev/null || true
elif command -v python3 >/dev/null 2>&1; then
  python3 "$PROJECT_ROOT/bin/fetch_nws_alerts.py" --serve-root "$ROOT" 2>/dev/null || true
fi
[ -f "$ROOT/alerts.json" ] || echo '{"svr":{"type":"FeatureCollection","features":[]},"tor":{"type":"FeatureCollection","features":[]},"tor_watch":{"type":"FeatureCollection","features":[]},"svr_watch":{"type":"FeatureCollection","features":[]},"sws":{"type":"FeatureCollection","features":[]}}' > "$ROOT/alerts.json"

# Lightning map: placeholder if not yet generated (lightning_nex_tail on wx-core produces this)
[ -f "$ROOT/lightning_points.geojson" ] || echo '{"type":"FeatureCollection","features":[],"properties":{"center":[-81.075938,31.919173],"max_radius_mi":500}}' > "$ROOT/lightning_points.geojson"
[ -f "$ROOT/lightning_points_v2.geojson" ] || echo '{"type":"FeatureCollection","features":[],"properties":{"center":[-81.075938,31.919173],"max_radius_mi":500}}' > "$ROOT/lightning_points_v2.geojson"
[ -f "$ROOT/lightning_points_xweather_local.geojson" ] || echo '{"type":"FeatureCollection","features":[],"properties":{"center":[-81.075938,31.919173],"max_radius_mi":135,"source":"xweather"}}' > "$ROOT/lightning_points_xweather_local.geojson"
[ -f "$ROOT/lightning_summary.json" ] || echo '{"computed_at_utc":"","last_strike_time_utc":"","nearest_strike":{"distance_mi":0,"bearing_deg":0,"type":"CG","age_sec":0},"nearest_cg":{"distance_mi":0,"bearing_deg":0,"age_sec":0},"nearest_ic":{"distance_mi":0,"bearing_deg":0,"age_sec":0},"counts_by_radius":{"mi_5":0,"mi_10":0,"mi_15":0,"mi_25":0,"mi_50":0,"mi_100":0},"counts_by_type":{"cg_15_min":0,"ic_15_min":0},"counts_by_age":{"sec_0_60":0,"min_1_5":0,"min_5_10":0,"min_10_15":0},"strike_rate":{"per_min_5":0,"per_min_10":0,"per_min_15":0},"trend":"steady","alert_state":{"level":"none","reason":"","active":false},"source_health":{"relay_running":true,"fresh":true}}' > "$ROOT/lightning_summary.json"

echo "serve_root ready at $ROOT"
