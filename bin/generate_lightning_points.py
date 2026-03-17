#!/usr/bin/env python3
"""Generate lightning_points.geojson from lightning_rt.ndjson for map display.

Reads strikes from local scratch (populated by lightning_nex_tail) or Lightning-PC.
Converts bearing/distance to lat/lon, filters to 500-mile radius, outputs GeoJSON.

Usage:
  python bin/generate_lightning_points.py [--input PATH] [--output PATH] [--remote]
  --input: lightning_rt.ndjson path (default: scratch/lightning_nex/lightning_rt.ndjson)
  --output: write to path (default: serve_root/lightning_points.geojson)
  --remote: scp output to wx-i9 serve_root after writing
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from pyproj import Geod

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_SCRATCH = PROJECT_ROOT / "scratch" / "lightning_nex"
SERVE_ROOT = PROJECT_ROOT / "serve_root"
MAX_RADIUS_MI = 500
MAX_RADIUS_KM = MAX_RADIUS_MI / 0.621371
# MRW station center (basemap_geometry.json)
CENTER_LAT = 31.919173
CENTER_LON = -81.075938
# Most recent N strikes to include (keep lightweight)
MAX_STRIKES = 500
# Only show strikes from last N minutes (prevents stale map)
WINDOW_MINUTES = 15


def _tail_lines(path: Path, n: int = 2000) -> list[str]:
    """Read last n lines efficiently. Essential when ndjson is 2GB+."""
    try:
        r = subprocess.run(
            ["tail", "-n", str(n), str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0:
            return []
        return r.stdout.strip().splitlines() if r.stdout else []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def _parse_ts(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def bearing_dist_to_lonlat(lon0: float, lat0: float, bearing_deg: float, dist_km: float) -> tuple[float, float]:
    """Convert polar (bearing, distance) from station to (lon, lat)."""
    g = Geod(ellps="WGS84")
    lon2, lat2, _ = g.fwd(lon0, lat0, bearing_deg, dist_km * 1000)
    return lon2, lat2


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate lightning_points.geojson for map")
    ap.add_argument("--input", type=Path, default=LOCAL_SCRATCH / "lightning_rt.ndjson")
    ap.add_argument("--output", type=Path, default=SERVE_ROOT / "lightning_points.geojson")
    ap.add_argument("--remote", action="store_true", help="scp output to wx-i9")
    args = ap.parse_args()

    if not args.input.exists():
        empty = {
            "type": "FeatureCollection",
            "features": [],
            "properties": {"center": [CENTER_LON, CENTER_LAT], "max_radius_mi": MAX_RADIUS_MI},
        }
        _atomic_write(args.output, json.dumps(empty, indent=2))
        if args.remote:
            _scp_to_wx_i9(args.output)
        return 0

    lines = _tail_lines(args.input)
    lines = lines[-MAX_STRIKES:] if len(lines) > MAX_STRIKES else lines

    now_utc = datetime.now(timezone.utc)
    max_age_sec = WINDOW_MINUTES * 60

    def render_props(age_sec: float, strike_type: str) -> dict:
        st = strike_type.upper() if strike_type else "CG"
        is_cg = st == "CG"
        if age_sec <= 10:
            return {
                "age_bucket": "bolt",
                "render_type": "bolt",
                "circle_radius": 0,
                "circle_opacity": 0,
                "icon_size": 0.25,
            }
        if age_sec <= 60:
            return {
                "age_bucket": "fresh",
                "render_type": "cg" if is_cg else "ic",
                "circle_radius": 5 if is_cg else 4,
                "circle_opacity": 0.95,
                "icon_size": 0,
            }
        if age_sec <= 300:
            r = 3 if is_cg else 2.5
            o = 0.9 - (age_sec - 60) / 240 * 0.15
            return {
                "age_bucket": "recent",
                "render_type": "cg" if is_cg else "ic",
                "circle_radius": r,
                "circle_opacity": round(o, 2),
                "icon_size": 0,
            }
        if age_sec <= 600:
            r = 2.5 if is_cg else 2
            return {
                "age_bucket": "aging",
                "render_type": "cg" if is_cg else "ic",
                "circle_radius": r,
                "circle_opacity": 0.5,
                "icon_size": 0,
            }
        r = 1.2 if is_cg else 0.8
        o = 0.3
        return {
            "age_bucket": "old",
            "render_type": "cg" if is_cg else "ic",
            "circle_radius": r,
            "circle_opacity": o,
            "icon_size": 0,
        }

    features = []
    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts_str = rec.get("timestamp_utc", "")
        ts = _parse_ts(ts_str)
        if ts is None:
            continue
        age_sec = (now_utc - ts).total_seconds()
        if age_sec < 0 or age_sec > max_age_sec:
            continue
        dist = rec.get("raw_distance_km") or rec.get("trac_distance_km")
        bearing = rec.get("raw_bearing_deg") or rec.get("trac_bearing_deg")
        if dist is None or dist < 0 or bearing is None:
            continue
        if dist > MAX_RADIUS_KM:
            continue
        lon, lat = bearing_dist_to_lonlat(CENTER_LON, CENTER_LAT, float(bearing), float(dist))
        strike_type = rec.get("strike_type", "CG")
        rp = render_props(age_sec, strike_type)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "timestamp_utc": ts_str,
                "strike_type": strike_type,
                "distance_km": round(float(dist), 2),
                "bearing_deg": round(float(bearing), 1),
                "age_seconds": round(age_sec),
                "age_bucket": rp["age_bucket"],
                "render_type": rp["render_type"],
                "circle_radius": rp["circle_radius"],
                "circle_opacity": rp["circle_opacity"],
                "icon_size": rp["icon_size"],
                "sort_key": ts_str,
            },
        })

    features.sort(key=lambda f: f["properties"]["sort_key"], reverse=True)
    # Dedupe by (timestamp_utc, lon, lat), keeping newest of each
    seen: dict[tuple[str, float, float], bool] = {}
    deduped = []
    for f in features:
        coords = f["geometry"]["coordinates"]
        key = (f["properties"]["timestamp_utc"], coords[0], coords[1])
        if key not in seen:
            seen[key] = True
            deduped.append(f)
    features = deduped[:MAX_STRIKES]

    fc = {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "center": [CENTER_LON, CENTER_LAT],
            "max_radius_mi": MAX_RADIUS_MI,
            "window_minutes": WINDOW_MINUTES,
            "count": len(features),
            "computed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        },
    }
    _atomic_write(args.output, json.dumps(fc, indent=2))

    if args.remote:
        _scp_to_wx_i9(args.output)

    return 0


def _atomic_write(path: Path, content: str) -> None:
    """Write content atomically (temp + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    tmp.rename(path)


def _scp_to_wx_i9(local: Path) -> bool:
    """Push lightning_points.geojson to wx-i9 serve_root. Retry up to 3 times."""
    remote = "wx-i9:~/wx/radar-foundry/serve_root/lightning_points.geojson"
    for attempt in range(3):
        try:
            r = subprocess.run(
                ["scp", "-q", "-o", "ConnectTimeout=5", str(local), remote],
                capture_output=True,
                timeout=20,
            )
            if r.returncode == 0:
                return True
        except subprocess.TimeoutExpired:
            pass
        if attempt < 2:
            time.sleep(2)
    return False


if __name__ == "__main__":
    sys.exit(main())
