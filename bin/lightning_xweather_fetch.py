#!/usr/bin/env python3
"""Fetch lightning from Xweather API, normalize to MRW schema, append to lightning_xweather_rt.ndjson.

Environment variables (required):
  XWEATHER_CLIENT_ID     Xweather API client ID
  XWEATHER_CLIENT_SECRET Xweather API client secret

Run command:
  XWEATHER_CLIENT_ID=your_id XWEATHER_CLIENT_SECRET=your_secret \\
    .venv/bin/python bin/lightning_xweather_fetch.py

Loop mode (continuous polling):
  ... bin/lightning_xweather_fetch.py --loop [--interval 10] [--status-every 6]

Safe to run repeatedly: dedupes by source_id or timestamp+lat+lon+type.
Output: scratch/lightning_xweather/lightning_xweather_rt.ndjson

---
Docs assumptions (Xweather Weather API, verified 2025-03):
  https://www.xweather.com/docs/weather-api/endpoints/lightning
  https://www.xweather.com/docs/weather-api/actions/closest
  https://www.xweather.com/docs/weather-api/getting-started/authentication
  https://www.xweather.com/docs/weather-api/getting-started/rate-limiting

1. Endpoint: https://data.api.xweather.com/lightning/closest?p={lat},{lon}
2. Auth: client_id and client_secret as query params (required)
3. Params: limit (required for >1 result), radius (optional, max 100km standard)
4. Location: p=lat,lon query param (e.g. p=31.919173,-81.075938) per places/closest pattern
5. Pagination: skip param for next 1000 strikes (standard plan)
6. Response fields:
   - timestamp: ob.dateTimeISO (ISO 8601) or ob.timestamp (unix)
   - latitude: loc.lat
   - longitude: loc.long (note: "long" not "lon")
   - strike type: ob.pulse.type ("cg"|"ic")
   - polarity: derived from ob.pulse.peakamp (sign); null if peakamp absent
   - amplitude: ob.pulse.peakamp (amperes, includes polarity)
   - unique id: id
7. Rate limits: 10x access multiplier; X-RateLimit-* headers; 429 on exceed
8. Standard limits: 5 min data, max 1000/query, max 100km radius, no within
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from pyproj import Geod

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "scratch" / "lightning_xweather"
OUTPUT_FILE = OUTPUT_DIR / "lightning_xweather_rt.ndjson"

# MRW station (Moon River / Savannah)
CENTER_LAT = 31.919173
CENTER_LON = -81.075938

XWEATHER_BASE = "https://data.api.xweather.com/lightning"


def _geod():
    return Geod(ellps="WGS84")


def lonlat_to_bearing_distance(
    lon0: float, lat0: float, lon1: float, lat1: float
) -> tuple[float, float]:
    """Compute forward azimuth (bearing) in degrees and distance in km from (lon0,lat0) to (lon1,lat1)."""
    g = _geod()
    fwd_az, _, dist_m = g.inv(lon0, lat0, lon1, lat1)
    bearing = (fwd_az + 360) % 360
    dist_km = dist_m / 1000.0
    return bearing, dist_km


def _parse_iso(ts: str) -> str:
    """Normalize ISO timestamp to UTC Z format for consistency."""
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
        polarity = None  # not in API when peakamp absent
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
    """Key for deduplication: source_id if available, else timestamp+lat+lon+type."""
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


def count_records_and_timestamps(path: Path) -> tuple[int, str | None, str | None]:
    """Return (total_records, oldest_timestamp, newest_timestamp)."""
    if not path.exists():
        return 0, None, None
    count = 0
    oldest: str | None = None
    newest: str | None = None
    for line in path.read_text().strip().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            count += 1
            ts = rec.get("timestamp_utc")
            if ts:
                if oldest is None or ts < oldest:
                    oldest = ts
                if newest is None or ts > newest:
                    newest = ts
        except json.JSONDecodeError:
            continue
    return count, oldest, newest


def _https_get_code_body(url: str, timeout: float = 30) -> tuple[int, str]:
    """GET URL over HTTPS. Prefer urllib; on OS-level connect failure, retry via curl -4 (IPv4 only).

    weather-core occasionally hits macOS Errno 49 (EADDRNOTAVAIL) from urllib's default stack;
    curl -4 reliably uses IPv4 to data.api.xweather.com.
    """
    headers = {"Accept": "application/json", "User-Agent": "mrw-lightning-xweather/1"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode() if e.fp else "")
    except OSError:
        pass
    tout = str(max(1, int(timeout)))
    hdr_f = bod_f = None
    try:
        h = tempfile.NamedTemporaryFile(delete=False, suffix=".hdr")
        b = tempfile.NamedTemporaryFile(delete=False, suffix=".body")
        hdr_f, bod_f = h.name, b.name
        h.close()
        b.close()
        curl = subprocess.run(
            [
                "curl",
                "-4",
                "-sS",
                "--max-time",
                tout,
                "-D",
                hdr_f,
                "-o",
                bod_f,
                "-H",
                "Accept: application/json",
                url,
            ],
            capture_output=True,
            text=True,
        )
        if curl.returncode != 0 or not Path(hdr_f).exists():
            raise OSError(curl.stderr.strip() or "curl -4 failed") from None
        hdr_text = Path(hdr_f).read_text(encoding="utf-8", errors="replace")
        status_line = hdr_text.splitlines()[0] if hdr_text else ""
        parts = status_line.split()
        code = int(parts[1]) if len(parts) > 2 else 0
        body = Path(bod_f).read_text(encoding="utf-8", errors="replace")
        return code, body
    finally:
        for pth in (hdr_f, bod_f):
            if pth:
                try:
                    Path(pth).unlink(missing_ok=True)
                except OSError:
                    pass


def _extract_strikes_from_response(data: object) -> list[dict]:
    """Extract strike list from API response (handles raw array or wrapper)."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "error" in data and data.get("error"):
            raise RuntimeError(data.get("error", {}).get("description", str(data["error"])))
        resp = data.get("response")
        if isinstance(resp, list):
            return resp
        if isinstance(resp, dict):
            body = resp.get("body")
            if isinstance(body, list):
                return body
            if isinstance(body, dict):
                return [body]
    return []


def fetch_xweather(
    client_id: str,
    client_secret: str,
    limit: int = 1000,
    radius_km: int | None = None,
) -> list[dict]:
    """Fetch lightning strikes from Xweather closest to MRW center.

    Per docs: limit required for >1 result; radius optional (max 100km standard).
    """
    loc = f"{CENTER_LAT},{CENTER_LON}"
    params = [
        f"p={loc}",
        f"client_id={urllib.parse.quote(client_id)}",
        f"client_secret={urllib.parse.quote(client_secret)}",
        f"limit={limit}",
    ]
    if radius_km is not None:
        params.append(f"radius={radius_km}")
    url = f"{XWEATHER_BASE}/closest?" + "&".join(params)
    code, body = _https_get_code_body(url, timeout=30)
    if code != 200:
        raise urllib.error.HTTPError(
            url,
            code,
            f"HTTP {code}",
            {},
            io.BytesIO(body.encode()),
        )
    data = json.loads(body)
    return _extract_strikes_from_response(data)


def run_probe(client_id: str, client_secret: str) -> int:
    """Probe mode: test max strike retrieval with limit=1000, radius=100."""
    loc = f"{CENTER_LAT},{CENTER_LON}"
    limit = 1000
    radius = 100
    params = [
        f"p={loc}",
        f"client_id={urllib.parse.quote(client_id)}",
        f"client_secret={urllib.parse.quote(client_secret)}",
        f"limit={limit}",
        f"radius={radius}",
    ]
    url = f"{XWEATHER_BASE}/closest?" + "&".join(params)

    print("--- Xweather lightning probe (limit=1000, radius=100km) ---")
    print(f"Request URL: {url}")

    status, body = _https_get_code_body(url, timeout=30)

    print(f"HTTP status: {status}")

    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        print(f"Response parse error: {e}")
        print(f"Raw body (first 500 chars): {body[:500]}")
        return 1

    # In probe, handle error response without raising (report 0 strikes)
    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        desc = err.get("description", str(err)) if isinstance(err, dict) else str(err)
        print(f"API error in response: {desc}")
        strikes = []
    else:
        try:
            strikes = _extract_strikes_from_response(data)
        except RuntimeError as e:
            print(f"Response parse error: {e}")
            return 1

    n = len(strikes)
    print(f"Strikes returned: {n}")

    if 0 < n < limit:
        print(f"Cap detected: API returned {n} strikes (requested {limit})")

    timestamps = []
    has_polarity = 0
    has_amplitude = 0
    has_strike_type = 0
    for s in strikes:
        ob = s.get("ob") or {}
        pulse = ob.get("pulse") or {}
        ts = ob.get("dateTimeISO") or ob.get("dateTimeISOMS") or ""
        if ts:
            timestamps.append(ts)
        if pulse.get("peakamp") is not None:
            has_polarity += 1
            has_amplitude += 1
        if pulse.get("type") is not None:
            has_strike_type += 1

    print(f"Earliest strike: {min(timestamps) if timestamps else '—'}")
    print(f"Latest strike: {max(timestamps) if timestamps else '—'}")
    print(f"Strikes with polarity (peakamp): {has_polarity}")
    print(f"Strikes with amplitude (peakamp): {has_amplitude}")
    print(f"Strikes with strike type: {has_strike_type}")

    print("\nFirst 3 raw strike objects:")
    for i, s in enumerate(strikes[:3]):
        print(f"--- strike {i + 1} ---")
        print(json.dumps(s, indent=2))

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fetch Xweather lightning, normalize, append to NDJSON"
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_FILE,
        help=f"Output NDJSON path (default: {OUTPUT_FILE})",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Max strikes to request from API (default: 1000)",
    )
    ap.add_argument(
        "--radius",
        type=int,
        default=None,
        metavar="KM",
        help="Search radius in km (optional, max 100 standard plan)",
    )
    ap.add_argument(
        "--probe-limit",
        action="store_true",
        help="Probe mode: test max retrieval (limit=1000, radius=100), no NDJSON output",
    )
    ap.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously, one fetch per --interval seconds",
    )
    ap.add_argument(
        "--interval",
        type=int,
        default=10,
        metavar="SEC",
        help="Seconds between polls when --loop (default: 10)",
    )
    ap.add_argument(
        "--status-every",
        type=int,
        default=6,
        metavar="N",
        help="Every N polls also print oldest/newest/total (default: 6)",
    )
    ap.add_argument(
        "--post-generate",
        action="store_true",
        help="After each poll, run generate_lightning_points_xweather_local.py --remote",
    )
    args = ap.parse_args()

    client_id = os.environ.get("XWEATHER_CLIENT_ID", "").strip()
    client_secret = os.environ.get("XWEATHER_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        print(
            "Error: XWEATHER_CLIENT_ID and XWEATHER_CLIENT_SECRET must be set",
            file=sys.stderr,
        )
        return 1

    if args.probe_limit:
        return run_probe(client_id, client_secret)

    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.loop:
        return run_loop(
            client_id=client_id,
            client_secret=client_secret,
            output_path=output_path,
            limit=args.limit,
            radius_km=args.radius,
            interval=args.interval,
            status_every=args.status_every,
            post_generate=args.post_generate,
        )

    # Single run
    seen = load_existing_keys(output_path)

    try:
        raw_strikes = fetch_xweather(
            client_id, client_secret, limit=args.limit, radius_km=args.radius
        )
    except urllib.error.HTTPError as e:
        print(f"Error: Xweather API HTTP {e.code}: {e.reason}", file=sys.stderr)
        if e.code == 401:
            print("Check XWEATHER_CLIENT_ID and XWEATHER_CLIENT_SECRET", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    normalized = []
    for raw in raw_strikes:
        rec = normalize_strike(raw)
        if rec is None:
            continue
        key = dedupe_key(rec)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(rec)

    written = 0
    if normalized:
        with open(output_path, "a") as f:
            for rec in normalized:
                f.write(json.dumps(rec) + "\n")
                written += 1

    timestamps = [r["timestamp_utc"] for r in normalized]
    oldest = min(timestamps) if timestamps else None
    newest = max(timestamps) if timestamps else None

    print(f"Strikes fetched: {len(raw_strikes)}")
    print(f"Strikes written: {written}")
    print(f"Oldest timestamp: {oldest or '—'}")
    print(f"Newest timestamp: {newest or '—'}")
    if written == 0 and len(raw_strikes) > 0:
        print("(All fetched strikes were duplicates)")

    # Run summary: fields not in API when absent
    null_polarity = sum(1 for r in normalized if r.get("polarity") is None)
    if null_polarity:
        print(f"(polarity=null for {null_polarity} strike(s): ob.pulse.peakamp absent)")

    return 0


def run_one_cycle(
    client_id: str,
    client_secret: str,
    output_path: Path,
    seen: set[str],
    limit: int,
    radius_km: int | None,
) -> tuple[int, int]:
    """Fetch, normalize, dedupe, append. Returns (fetched, written)."""
    raw_strikes = fetch_xweather(
        client_id, client_secret, limit=limit, radius_km=radius_km
    )
    normalized = []
    for raw in raw_strikes:
        rec = normalize_strike(raw)
        if rec is None:
            continue
        key = dedupe_key(rec)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(rec)

    written = 0
    if normalized:
        with open(output_path, "a") as f:
            for rec in normalized:
                f.write(json.dumps(rec) + "\n")
                written += 1

    return len(raw_strikes), written


def _run_post_generate() -> None:
    """Run generate_lightning_points_xweather_local.py.

    Default: --remote (scp to wx-i9 serve_root). On wx-i9 set MRW_LIGHTNING_PUBLISH_LOCAL=1
    to write directly into local serve_root (no scp).
    """
    py = PROJECT_ROOT / ".venv" / "bin" / "python"
    script = PROJECT_ROOT / "bin" / "generate_lightning_points_xweather_local.py"
    if not py.exists() or not script.exists():
        return
    publish_local = os.environ.get("MRW_LIGHTNING_PUBLISH_LOCAL", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    cmd: list[str] = [str(py), str(script)]
    if not publish_local:
        cmd.append("--remote")
    try:
        subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            timeout=30,
        )
    except Exception:
        pass


def run_loop(
    client_id: str,
    client_secret: str,
    output_path: Path,
    limit: int,
    radius_km: int | None,
    interval: int,
    status_every: int,
    post_generate: bool = False,
) -> int:
    """Run continuous polling loop."""
    poll_count = 0

    try:
        while True:
            poll_count += 1
            seen = load_existing_keys(output_path)

            try:
                fetched, written = run_one_cycle(
                    client_id, client_secret, output_path, seen, limit, radius_km
                )
            except RuntimeError as e:
                if "No results available" in str(e):
                    fetched, written = 0, 0
                else:
                    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    print(f"[{ts}] Error: {e}, sleeping 15s", file=sys.stderr, flush=True)
                    time.sleep(15)
                    continue
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    print(f"[{ts}] HTTP 429 rate limit, sleeping 60s", flush=True)
                    time.sleep(60)
                    continue
                if e.code == 401:
                    print("Error: Xweather API HTTP 401 Unauthorized", file=sys.stderr)
                    print("Check XWEATHER_CLIENT_ID and XWEATHER_CLIENT_SECRET", file=sys.stderr)
                    return 1
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                print(f"[{ts}] Error: HTTP {e.code} {e.reason}, sleeping 15s", file=sys.stderr, flush=True)
                time.sleep(15)
                continue
            except Exception as e:
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                print(f"[{ts}] Error: {e}, sleeping 15s", file=sys.stderr, flush=True)
                time.sleep(15)
                continue

            total_records, oldest, newest = count_records_and_timestamps(output_path)
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            print(f"[{ts}] fetched={fetched} written={written} total_records={total_records}", flush=True)

            if poll_count % status_every == 0:
                print(f"  oldest_timestamp={oldest or '—'}", flush=True)
                print(f"  newest_timestamp={newest or '—'}", flush=True)
                print(f"  total_unique_records={total_records}", flush=True)

            if post_generate:
                _run_post_generate()

            time.sleep(interval)

    except KeyboardInterrupt:
        print("polling stopped", flush=True)
        return 0


if __name__ == "__main__":
    sys.exit(main())
