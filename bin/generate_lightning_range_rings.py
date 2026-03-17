#!/usr/bin/env python3
"""Generate lightning_range_rings.geojson — concentric geodesic circles for the lightning map.

Rings at 25, 50, 100, 150, 200, 250, 300, 350, 400, 450, 500 miles from MRW station. 25 mi ring has color #ef4444 (red).
Uses pyproj Geod for accurate geodesic circles.

Usage:
  python bin/generate_lightning_range_rings.py [--output PATH] [--remote] [--push-lightning-pc]
  --output: write path (default: serve_root/lightning_range_rings.geojson)
  --remote: scp to wx-i9 serve_root
  --push-lightning-pc: scp to Lightning-PC C:\\MRW\\lightning\\
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from pyproj import Geod

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVE_ROOT = PROJECT_ROOT / "serve_root"
# MRW station (basemap_geometry.json)
CENTER_LAT = 31.919173
CENTER_LON = -81.075938
RING_RADIUS_MILES = [25, 50, 100, 150, 200, 250, 300, 350, 400, 450, 500]
MI_TO_M = 1609.344
POINTS_PER_RING = 72  # 5° steps


def geodesic_circle(lon0: float, lat0: float, radius_mi: float) -> list[list[float]]:
    """Return polygon coordinates for a geodesic circle (closed ring)."""
    g = Geod(ellps="WGS84")
    dist_m = radius_mi * MI_TO_M
    coords = []
    for i in range(POINTS_PER_RING + 1):
        bearing = 360.0 * i / POINTS_PER_RING
        lon2, lat2, _ = g.fwd(lon0, lat0, bearing, dist_m)
        coords.append([lon2, lat2])
    return coords


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate lightning_range_rings.geojson")
    ap.add_argument("--output", type=Path, default=SERVE_ROOT / "lightning_range_rings.geojson")
    ap.add_argument("--remote", action="store_true", help="scp to wx-i9")
    ap.add_argument("--push-lightning-pc", action="store_true", help="scp to Lightning-PC")
    args = ap.parse_args()

    features = []
    g = Geod(ellps="WGS84")
    for radius_mi in RING_RADIUS_MILES:
        coords = geodesic_circle(CENTER_LON, CENTER_LAT, radius_mi)
        props = {"radius_miles": radius_mi}
        if radius_mi == 25:
            props["color"] = "#ef4444"
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": props,
        })
        lon_label, lat_label, _ = g.fwd(CENTER_LON, CENTER_LAT, 90, radius_mi * MI_TO_M)
        label_props = {"radius_miles": radius_mi, "label": f"{radius_mi} mi"}
        if radius_mi == 25:
            label_props["color"] = "#ef4444"
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon_label, lat_label]},
            "properties": label_props,
        })

    fc = {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "center": [CENTER_LON, CENTER_LAT],
            "radii_miles": RING_RADIUS_MILES,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(fc, indent=2))

    if args.remote:
        _scp_to_wx_i9(args.output)
    if args.push_lightning_pc:
        _scp_to_lightning_pc(args.output)

    return 0


def _scp_to_wx_i9(local: Path) -> bool:
    remote = "wx-i9:~/wx/radar-foundry/serve_root/lightning_range_rings.geojson"
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


def _scp_to_lightning_pc(local: Path) -> bool:
    remote = "scott@192.168.2.223:C:/MRW/lightning/lightning_range_rings.geojson"
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
