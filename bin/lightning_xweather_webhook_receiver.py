#!/usr/bin/env python3
"""Minimal webhook receiver for Xweather lightning push data.

Accepts POSTed JSON from Xweather webhooks, normalizes to MRW schema,
appends to scratch/lightning_xweather/lightning_xweather_rt.ndjson.

Docs: https://www.xweather.com/docs/weather-api/reference/webhooks-pushed-data
Payload format: same as lightning API response (single object or array).

Run locally:
  .venv/bin/python bin/lightning_xweather_webhook_receiver.py [--port 8765]

Test with curl:
  curl -X POST http://localhost:8765/lightning \\
    -H "Content-Type: application/json" \\
    -d '[{"id":"test1","loc":{"lat":31.92,"long":-81.08},"ob":{"dateTimeISO":"2025-03-14T12:00:00Z","pulse":{"type":"cg","peakamp":-5000}}}]'

Xweather needs: public HTTPS URL (e.g. https://yourhost/lightning) — contact sales.
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from pyproj import Geod

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = PROJECT_ROOT / "scratch" / "lightning_xweather" / "lightning_xweather_rt.ndjson"

# MRW station (Moon River / Savannah)
CENTER_LAT = 31.919173
CENTER_LON = -81.075938


def _geod():
    return Geod(ellps="WGS84")


def lonlat_to_bearing_distance(
    lon0: float, lat0: float, lon1: float, lat1: float
) -> tuple[float, float]:
    """Compute forward azimuth (bearing) in degrees and distance in km."""
    g = _geod()
    fwd_az, _, dist_m = g.inv(lon0, lat0, lon1, lat1)
    bearing = (fwd_az + 360) % 360
    dist_km = dist_m / 1000.0
    return bearing, dist_km


def _parse_iso(ts: str) -> str:
    """Normalize ISO timestamp to UTC Z format."""
    s = (ts or "").strip()
    if not s:
        return ""
    s = s.replace("+00:00", "Z").replace("+0000", "Z")
    if s and not s.endswith("Z") and "+" not in s:
        s = s + "Z"
    return s


def normalize_strike(raw: dict) -> dict | None:
    """Convert Xweather strike to MRW normalized schema."""
    loc = raw.get("loc") or {}
    ob = raw.get("ob") or {}
    pulse = ob.get("pulse") or {}

    lat = loc.get("lat")
    lon = loc.get("long")
    if lat is None or lon is None:
        return None

    ts_iso = ob.get("dateTimeISO") or ob.get("dateTimeISOMS") or ""
    if not ts_iso:
        return None

    timestamp_utc = _parse_iso(ts_iso)

    strike_type_raw = (pulse.get("type") or "cg").upper()
    strike_type = "CG" if strike_type_raw == "CG" else "IC"

    peakamp = pulse.get("peakamp")
    if peakamp is not None:
        polarity = "negative" if peakamp < 0 else "positive"
        amplitude = peakamp
    else:
        polarity = None
        amplitude = None

    bearing, dist_km = lonlat_to_bearing_distance(CENTER_LON, CENTER_LAT, lon, lat)

    extra = {}
    if raw.get("recTimestamp") is not None:
        extra["recTimestamp"] = raw["recTimestamp"]
    if raw.get("recISO"):
        extra["recISO"] = raw["recISO"]
    if ob.get("age") is not None:
        extra["age_sec"] = ob["age"]
    if pulse:
        extra["pulse"] = {k: v for k, v in pulse.items() if v is not None}
    if raw.get("relativeTo"):
        extra["relativeTo"] = raw["relativeTo"]

    return {
        "timestamp_utc": timestamp_utc,
        "source": "xweather",
        "source_id": raw.get("id"),
        "latitude": lat,
        "longitude": lon,
        "raw_bearing_deg": round(bearing, 2),
        "raw_distance_km": round(dist_km, 2),
        "strike_type": strike_type,
        "polarity": polarity,
        "amplitude": amplitude,
        "extra": extra if extra else None,
    }


def dedupe_key(rec: dict) -> str:
    """Key for deduplication."""
    if rec.get("source_id"):
        return f"id:{rec['source_id']}"
    ts = rec.get("timestamp_utc", "")
    lat = rec.get("latitude")
    lon = rec.get("longitude")
    typ = rec.get("strike_type", "")
    return f"ts:{ts}|{lat}|{lon}|{typ}"


def load_existing_keys(path: Path) -> set[str]:
    """Load dedupe keys from existing NDJSON file."""
    seen: set[str] = set()
    if not path.exists():
        return seen
    for line in path.read_text().strip().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            seen.add(dedupe_key(rec))
        except json.JSONDecodeError:
            continue
    return seen


def _extract_strikes(payload: object) -> list[dict]:
    """Extract strike list from webhook payload (single object, array, or wrapper)."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if "response" in payload:
            resp = payload["response"]
            if isinstance(resp, list):
                return resp
            if isinstance(resp, dict):
                return [resp]
        # Single strike object
        if "loc" in payload and "ob" in payload:
            return [payload]
    return []


class LightningWebhookHandler(BaseHTTPRequestHandler):
    """Handle POST /lightning with Xweather strike JSON."""

    def log_message(self, format: str, *args: object) -> None:
        """Suppress default request logging."""
        pass

    def do_POST(self) -> None:
        if self.path.rstrip("/") in ("/lightning", "/"):
            self._handle_lightning()
        else:
            self._send(404, {"error": "Not found"})

    def _handle_lightning(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            self._send(400, {"error": "Content-Type must be application/json"})
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode()
            payload = json.loads(body) if body else None
        except (json.JSONDecodeError, ValueError) as e:
            self._send(400, {"error": f"Invalid JSON: {e}"})
            return

        strikes_raw = _extract_strikes(payload)
        if not strikes_raw:
            self._send(200, {"accepted": 0, "message": "No strikes in payload"})
            return

        output_path = OUTPUT_FILE
        output_path.parent.mkdir(parents=True, exist_ok=True)
        seen = load_existing_keys(output_path)

        accepted = []
        for raw in strikes_raw:
            if not isinstance(raw, dict):
                continue
            rec = normalize_strike(raw)
            if rec is None:
                continue
            key = dedupe_key(rec)
            if key in seen:
                continue
            seen.add(key)
            accepted.append(rec)

        if accepted:
            with open(output_path, "a") as f:
                for rec in accepted:
                    f.write(json.dumps(rec) + "\n")
            for rec in accepted:
                print(
                    f"accepted strike {rec.get('source_id', '?')} "
                    f"{rec.get('timestamp_utc')} {rec.get('strike_type')} "
                    f"{rec.get('raw_distance_km')}km"
                )

        self._send(201, {"accepted": len(accepted), "total_in_payload": len(strikes_raw)})

    def _send(self, status: int, body: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())


def main() -> int:
    ap = argparse.ArgumentParser(description="Xweather lightning webhook receiver")
    ap.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    ap.add_argument("--host", default="", help="Bind host (default: all interfaces)")
    args = ap.parse_args()

    server = HTTPServer((args.host, args.port), LightningWebhookHandler)
    print(f"Xweather lightning webhook receiver on http://{args.host or '0.0.0.0'}:{args.port}/lightning")
    print("POST JSON to /lightning — Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
