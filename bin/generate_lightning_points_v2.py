#!/usr/bin/env python3
"""Generate lightning_points_v2.geojson for the v2 lightning map (strike-behavior spec).

Same input as generate_lightning_points.py. Outputs GeoJSON with v2 age buckets:
- 0-10s: bolt (white icon)
- 10-60s: prominent (CG > IC)
- 1-5min: medium
- 5-10min: smaller
- 10-15min: faint
- >15min: excluded (non-close)
- Close zone (≤25 mi): 30 min window (enables client 15–30 min yellow phase)

Usage:
  python bin/generate_lightning_points_v2.py [--input PATH] [--output PATH] [--remote]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pyproj import Geod

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_SCRATCH = PROJECT_ROOT / "scratch" / "lightning_nex"
SERVE_ROOT = PROJECT_ROOT / "serve_root"
MAX_RADIUS_MI = 500
MAX_RADIUS_KM = MAX_RADIUS_MI / 0.621371
CENTER_LAT = 31.919173
CENTER_LON = -81.075938
MAX_STRIKES = 500
WINDOW_MINUTES = 15
CLOSE_RADIUS_MI = 25
CLOSE_RADIUS_KM = CLOSE_RADIUS_MI * 1.609344
CLOSE_RADIUS_KM_EPSILON = 0.02  # Include 25.0 mi when rounded to 40.24 km
CLOSE_WINDOW_MINUTES = 30


# Tail size: enough for 30-min close window + 500 non-close. Avoids loading multi-GB ndjson.
TAIL_LINES = 20000


def _tail_lines(path: Path, n: int = TAIL_LINES) -> list[str]:
    """Read last n lines efficiently. Essential when ndjson is 2GB+."""
    try:
        r = subprocess.run(
            ["tail", "-n", str(n), str(path)],
            capture_output=True,
            text=True,
            timeout=60,
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
    g = Geod(ellps="WGS84")
    lon2, lat2, _ = g.fwd(lon0, lat0, bearing_deg, dist_km * 1000)
    return lon2, lat2


def render_props_v2(age_sec: float, strike_type: str) -> dict:
    """V2: CG=square, IC=X. NexStorm-style clarity. New fade curve."""
    st = strike_type.upper() if strike_type else "CG"
    is_cg = st == "CG"
    if age_sec <= 10:
        return {"age_bucket": "bolt", "render_type": "bolt", "symbol": "bolt", "icon_size": 0.25, "icon_opacity": 1.0}
    if age_sec <= 60:
        return {
            "age_bucket": "prominent",
            "render_type": "cg" if is_cg else "ic",
            "symbol": "cg" if is_cg else "ic",
            "icon_size": 0.32 if is_cg else 0.28,
            "icon_opacity": 1.0,
        }
    if age_sec <= 180:
        return {
            "age_bucket": "medium",
            "render_type": "cg" if is_cg else "ic",
            "symbol": "cg" if is_cg else "ic",
            "icon_size": 0.27 if is_cg else 0.24,
            "icon_opacity": 0.85,
        }
    if age_sec <= 360:
        return {
            "age_bucket": "low",
            "render_type": "cg" if is_cg else "ic",
            "symbol": "cg" if is_cg else "ic",
            "icon_size": 0.23 if is_cg else 0.21,
            "icon_opacity": 0.7,
        }
    if age_sec <= 600:
        return {
            "age_bucket": "smaller",
            "render_type": "cg" if is_cg else "ic",
            "symbol": "cg" if is_cg else "ic",
            "icon_size": 0.2 if is_cg else 0.18,
            "icon_opacity": 0.55,
        }
    return {
        "age_bucket": "faint",
        "render_type": "cg" if is_cg else "ic",
        "symbol": "cg" if is_cg else "ic",
        "icon_size": 0.17 if is_cg else 0.15,
        "icon_opacity": 0.4,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate lightning_points_v2.geojson for v2 map")
    ap.add_argument("--input", type=Path, default=LOCAL_SCRATCH / "lightning_rt.ndjson")
    ap.add_argument("--output", type=Path, default=SERVE_ROOT / "lightning_points_v2.geojson")
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
    now_utc = datetime.now(timezone.utc)
    max_age_sec = WINDOW_MINUTES * 60
    close_max_age_sec = CLOSE_WINDOW_MINUTES * 60

    # Close strikes: scan entire file so they are never pushed out by the 500 cap
    close_features: list[dict] = []
    non_close_lines: list[str] = []
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
        dist = rec.get("raw_distance_km") or rec.get("trac_distance_km")
        is_close = dist is not None and float(dist) <= CLOSE_RADIUS_KM + CLOSE_RADIUS_KM_EPSILON
        if is_close and 0 <= age_sec <= close_max_age_sec:
            dist = dist if dist is not None else rec.get("raw_distance_km") or rec.get("trac_distance_km")
            bearing = rec.get("raw_bearing_deg") or rec.get("trac_bearing_deg")
            if dist is not None and dist >= 0 and bearing is not None and float(dist) <= MAX_RADIUS_KM:
                lon, lat = bearing_dist_to_lonlat(CENTER_LON, CENTER_LAT, float(bearing), float(dist))
                strike_type = rec.get("strike_type", "CG")
                rp = render_props_v2(age_sec, strike_type)
                close_features.append({
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
                        "symbol": rp["symbol"],
                        "icon_size": rp["icon_size"],
                        "icon_opacity": rp["icon_opacity"],
                        "sort_key": ts_str,
                    },
                })
        else:
            non_close_lines.append(line)

    # Non-close: last MAX_STRIKES lines only (original behavior)
    tail = non_close_lines[-MAX_STRIKES:] if len(non_close_lines) > MAX_STRIKES else non_close_lines

    features: list[dict] = list(close_features)
    for line in tail:
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
        if float(dist) > MAX_RADIUS_KM or float(dist) <= CLOSE_RADIUS_KM + CLOSE_RADIUS_KM_EPSILON:
            continue
        lon, lat = bearing_dist_to_lonlat(CENTER_LON, CENTER_LAT, float(bearing), float(dist))
        strike_type = rec.get("strike_type", "CG")
        rp = render_props_v2(age_sec, strike_type)
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
                "symbol": rp["symbol"],
                "icon_size": rp["icon_size"],
                "icon_opacity": rp["icon_opacity"],
                "sort_key": ts_str,
            },
        })

    # Newest first so they render on top
    features.sort(key=lambda f: f["properties"]["sort_key"], reverse=True)
    # Dedupe by (timestamp_utc, lon, lat); preserve all close strikes, cap non-close
    seen: dict[tuple[str, float, float], bool] = {}
    close_out: list[dict] = []
    non_close_out: list[dict] = []
    for f in features:
        coords = f["geometry"]["coordinates"]
        key = (f["properties"]["timestamp_utc"], coords[0], coords[1])
        if key in seen:
            continue
        seen[key] = True
        if f["properties"]["distance_km"] <= CLOSE_RADIUS_KM + CLOSE_RADIUS_KM_EPSILON:
            close_out.append(f)
        else:
            non_close_out.append(f)
    features = close_out + non_close_out[: MAX_STRIKES - len(close_out)]

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
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    tmp.rename(path)


def _scp_to_wx_i9(local: Path) -> bool:
    remote = "wx-i9:~/wx/radar-foundry/serve_root/lightning_points_v2.geojson"
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
