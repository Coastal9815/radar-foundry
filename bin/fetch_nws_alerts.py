#!/usr/bin/env python3
"""Fetch NWS active SVR, TOR, and localized SWS (thunderstorm/hail/tornado/lightning) for SE region.
Output: { "svr": GeoJSON, "tor": GeoJSON, "tor_watch": GeoJSON, "svr_watch": GeoJSON, "sws": GeoJSON } — polygon features.
Watches use fill (shaded, no border); warnings/SWS use line outline only.
SWS: Special Weather Statements with thunderstorm/hail/tornado/lightning, localized (polygon geometry).
Run periodically (e.g. every 2–5 min). Writes to --output (default: serve_root/alerts.json).
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = "MRW-Radar/1.0 (https://github.com/moonriverwx)"
NWS_BASE = "https://api.weather.gov"

EVENT_SVR = "Severe Thunderstorm Warning"
EVENT_TOR = "Tornado Warning"
EVENT_TOR_WATCH = "Tornado Watch"
EVENT_SVR_WATCH = "Severe Thunderstorm Watch"
EVENT_SWS = "Special Weather Statement"

# SWS must mention at least one of these (case-insensitive)
SWS_KEYWORDS = re.compile(
    r"\b(thunderstorm|hail|tornado|lightning)\b",
    re.I,
)


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def zone_id_from_url(url: str) -> str | None:
    """Extract zone ID from https://api.weather.gov/zones/forecast/GAZ131"""
    m = re.search(r"/zones/(?:forecast|public)/([A-Z0-9]+)$", url)
    return m.group(1) if m else None


def _extract_polygon_coords(geom: dict) -> list:
    """Extract polygon coordinate lists from Polygon, MultiPolygon, or GeometryCollection."""
    t = geom.get("type")
    if t == "Polygon":
        return [geom["coordinates"]]
    if t == "MultiPolygon":
        return list(geom["coordinates"])
    if t == "GeometryCollection":
        out = []
        for g in geom.get("geometries", []):
            out.extend(_extract_polygon_coords(g))
        return out
    return []


def get_zone_geometry(zone_url: str) -> dict | None:
    """Fetch zone GeoJSON and return geometry (Polygon or MultiPolygon)."""
    try:
        data = fetch_json(zone_url)
        geom = data.get("geometry")
        if not geom:
            return None
        coords = _extract_polygon_coords(geom)
        if not coords:
            return None
        return {"type": "MultiPolygon", "coordinates": coords} if len(coords) > 1 else {"type": "Polygon", "coordinates": coords[0]}
    except Exception:
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="SE", help="NWS region or areas: SE, GA,SC,FL")
    ap.add_argument("--output", type=Path, help="Output JSON path")
    ap.add_argument("--test-polygon", action="store_true", help="Add sample Athens GA SVR polygon for local testing")
    ap.add_argument("--serve-root", type=Path, default=PROJECT_ROOT / "serve_root")
    args = ap.parse_args()

    out_path = args.output or (args.serve_root / "alerts.json")
    args.serve_root.mkdir(parents=True, exist_ok=True)

    # NWS area codes: GA, SC, FL cover KCLX/KJAX radar footprint
    areas = args.region.split(",") if "," in args.region else [args.region]
    if args.region == "SE":
        areas = ["GA", "SC", "FL"]

    all_features = []
    for area in areas:
        url = f"{NWS_BASE}/alerts/active/area/{area}"
        try:
            data = fetch_json(url)
            all_features.extend(data.get("features", []))
        except Exception as e:
            print(f"Fetch {area} failed: {e}", file=sys.stderr)

    # Dedupe by alert id
    seen = set()
    features = []
    for f in all_features:
        aid = f.get("id") or f.get("properties", {}).get("@id")
        if aid and aid not in seen:
            seen.add(aid)
            features.append(f)
    svr_features = []
    tor_features = []
    tor_watch_features = []
    svr_watch_features = []
    sws_features = []

    for f in features:
        props = f.get("properties", {})
        event = props.get("event", "")
        desc = props.get("description", "") or ""
        headline = props.get("headline", "") or ""

        geom = f.get("geometry")
        if not geom:
            # Resolve via affectedZones
            zones = props.get("affectedZones", [])
            poly_coords = []
            for zone_url in zones:
                g = get_zone_geometry(zone_url)
                if not g:
                    continue
                if g["type"] == "Polygon":
                    poly_coords.append(g["coordinates"])
                else:
                    poly_coords.extend(g["coordinates"])
            if not poly_coords:
                continue
            geom = {"type": "MultiPolygon", "coordinates": poly_coords} if len(poly_coords) > 1 else {"type": "Polygon", "coordinates": poly_coords[0]}

        feat = {
            "type": "Feature",
            "geometry": geom,
            "properties": {"event": event, "headline": headline, "areaDesc": props.get("areaDesc", "")},
        }

        if event == EVENT_TOR:
            tor_features.append(feat)
        elif event == EVENT_TOR_WATCH:
            tor_watch_features.append(feat)
        elif event == EVENT_SVR_WATCH:
            svr_watch_features.append(feat)
        elif event == EVENT_SVR:
            svr_features.append(feat)
        elif event == EVENT_SWS:
            # Only localized SWS (has polygon) about thunderstorm/hail/tornado/lightning
            if SWS_KEYWORDS.search(desc) or SWS_KEYWORDS.search(headline):
                sws_features.append(feat)

    if args.test_polygon:
        athens = {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[-83.45, 33.98], [-83.35, 33.98], [-83.35, 33.88], [-83.45, 33.88], [-83.45, 33.98]]]},
            "properties": {"event": "Severe Thunderstorm Warning", "areaDesc": "Clarke (Athens) GA [TEST]", "headline": "Test polygon"},
        }
        svr_features.append(athens)

    result = {
        "svr": {"type": "FeatureCollection", "features": svr_features},
        "tor": {"type": "FeatureCollection", "features": tor_features},
        "tor_watch": {"type": "FeatureCollection", "features": tor_watch_features},
        "svr_watch": {"type": "FeatureCollection", "features": svr_watch_features},
        "sws": {"type": "FeatureCollection", "features": sws_features},
    }
    out_path.write_text(json.dumps(result, indent=0))
    print(f"alerts: {len(svr_features)} SVR, {len(tor_features)} TOR, {len(tor_watch_features)} TOR watch, {len(svr_watch_features)} SVR watch, {len(sws_features)} SWS -> {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
