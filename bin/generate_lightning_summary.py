#!/usr/bin/env python3
"""Generate lightning_summary.json — operational intelligence product.

Reads lightning_rt.ndjson, lightning_recent.json, lightning_status.json.
Outputs lightning_summary.json for dashboards, alert engine, website.

Usage:
  python bin/generate_lightning_summary.py [--input-rt PATH] [--output PATH] [--remote]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_SCRATCH = PROJECT_ROOT / "scratch" / "lightning_nex"
SERVE_ROOT = PROJECT_ROOT / "serve_root"
WX_I9 = "wx-i9"
WINDOW_MINUTES = 15
LIGHTNING_RADIUS_BUCKETS_MI = [5, 10, 15, 25, 50, 100]
KM_PER_MI = 1.609344


def _parse_ts(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    tmp.rename(path)


def _scp_to_wx_i9(local: Path, remote_name: str) -> bool:
    remote = f"{WX_I9}:~/wx/radar-foundry/serve_root/{remote_name}"
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate lightning_summary.json")
    ap.add_argument("--input-rt", type=Path, default=LOCAL_SCRATCH / "lightning_rt.ndjson")
    ap.add_argument("--input-recent", type=Path, default=LOCAL_SCRATCH / "lightning_recent.json")
    ap.add_argument("--input-status", type=Path, default=LOCAL_SCRATCH / "lightning_status.json")
    ap.add_argument("--output", type=Path, default=SERVE_ROOT / "lightning_summary.json")
    ap.add_argument("--remote", action="store_true", help="scp output to wx-i9")
    args = ap.parse_args()

    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(minutes=WINDOW_MINUTES)

    # Default empty product
    product = {
        "mrw_center": {"lat": 31.919117, "lon": -81.075932},
        "data_freshness_sec": 0,
        "computed_at_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "last_strike_time_utc": "",
        "nearest_strike": {"distance_mi": 0, "bearing_deg": 0, "type": "CG", "age_sec": 0},
        "nearest_cg": {"distance_mi": 0, "bearing_deg": 0, "age_sec": 0},
        "nearest_ic": {"distance_mi": 0, "bearing_deg": 0, "age_sec": 0},
        "counts_by_radius": {f"mi_{r}": 0 for r in LIGHTNING_RADIUS_BUCKETS_MI},
        "counts_by_type": {"cg_15_min": 0, "ic_15_min": 0},
        "counts_by_age": {"sec_0_60": 0, "min_1_5": 0, "min_5_10": 0, "min_10_15": 0},
        "strike_rate": {"per_min_5": 0, "per_min_10": 0, "per_min_15": 0},
        "trend": "steady",
        "alert_state": {"level": "none", "reason": "", "active": False},
        "source_health": {"relay_running": True, "fresh": True},
    }

    if not args.input_rt.exists():
        _atomic_write(args.output, json.dumps(product, indent=2))
        if args.remote:
            _scp_to_wx_i9(args.output, "lightning_summary.json")
        return 0

    # Load strikes from lightning_rt.ndjson (last 15 min)
    lines = args.input_rt.read_text().strip().splitlines()
    lines = lines[-2000:] if len(lines) > 2000 else lines

    strikes = []
    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = _parse_ts(rec.get("timestamp_utc", ""))
        if ts is None or ts < cutoff:
            continue
        dist = rec.get("raw_distance_km") or rec.get("trac_distance_km")
        bearing = rec.get("raw_bearing_deg") or rec.get("trac_bearing_deg") or 0.0
        if dist is None or dist < 0:
            continue
        strike_type = rec.get("strike_type", "CG")
        age_sec = (now_utc - ts).total_seconds()
        dist_mi = dist / KM_PER_MI
        strikes.append({
            "ts": ts,
            "dist_km": dist,
            "dist_mi": dist_mi,
            "bearing": bearing,
            "type": strike_type,
            "age_sec": age_sec,
        })

    if not strikes:
        # Load trend from lightning_recent if available
        if args.input_recent.exists():
            try:
                recent = json.loads(args.input_recent.read_text())
                product["trend"] = recent.get("trend", "steady")
                product["last_strike_time_utc"] = recent.get("last_strike_time_utc") or ""
            except (json.JSONDecodeError, OSError):
                pass
        if args.input_status.exists():
            try:
                status = json.loads(args.input_status.read_text())
                product["source_health"]["relay_running"] = status.get("relay_running", True)
                last_ok = status.get("last_success_at_utc")
                if last_ok:
                    last_dt = _parse_ts(last_ok)
                    product["source_health"]["fresh"] = (now_utc - last_dt).total_seconds() < 60 if last_dt else True
                last_msg = status.get("last_message_at_utc")
                if last_msg:
                    last_msg_dt = _parse_ts(last_msg)
                    if last_msg_dt:
                        product["data_freshness_sec"] = int((now_utc - last_msg_dt).total_seconds())
            except (json.JSONDecodeError, OSError):
                pass
        _atomic_write(args.output, json.dumps(product, indent=2))
        if args.remote:
            _scp_to_wx_i9(args.output, "lightning_summary.json")
        return 0

    # Nearest strike (any type)
    nearest = min(strikes, key=lambda s: s["dist_km"])
    product["last_strike_time_utc"] = max(s["ts"] for s in strikes).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    product["nearest_strike"] = {
        "distance_mi": round(nearest["dist_mi"], 2),
        "bearing_deg": round(nearest["bearing"], 1),
        "type": nearest["type"],
        "age_sec": round(nearest["age_sec"]),
    }

    # Nearest CG, nearest IC
    cg_strikes = [s for s in strikes if s["type"] == "CG"]
    ic_strikes = [s for s in strikes if s["type"] == "IC"]
    if cg_strikes:
        nearest_cg = min(cg_strikes, key=lambda s: s["dist_km"])
        product["nearest_cg"] = {
            "distance_mi": round(nearest_cg["dist_mi"], 2),
            "bearing_deg": round(nearest_cg["bearing"], 1),
            "age_sec": round(nearest_cg["age_sec"]),
        }
    if ic_strikes:
        nearest_ic = min(ic_strikes, key=lambda s: s["dist_km"])
        product["nearest_ic"] = {
            "distance_mi": round(nearest_ic["dist_mi"], 2),
            "bearing_deg": round(nearest_ic["bearing"], 1),
            "age_sec": round(nearest_ic["age_sec"]),
        }

    # Counts by radius (mi)
    for r in LIGHTNING_RADIUS_BUCKETS_MI:
        r_km = r * KM_PER_MI
        count = sum(1 for s in strikes if s["dist_km"] <= r_km)
        product["counts_by_radius"][f"mi_{r}"] = count

    # Counts by type
    product["counts_by_type"]["cg_15_min"] = len(cg_strikes)
    product["counts_by_type"]["ic_15_min"] = len(ic_strikes)

    # Counts by age
    product["counts_by_age"]["sec_0_60"] = sum(1 for s in strikes if s["age_sec"] <= 60)
    product["counts_by_age"]["min_1_5"] = sum(1 for s in strikes if 60 < s["age_sec"] <= 300)
    product["counts_by_age"]["min_5_10"] = sum(1 for s in strikes if 300 < s["age_sec"] <= 600)
    product["counts_by_age"]["min_10_15"] = sum(1 for s in strikes if 600 < s["age_sec"] <= 900)

    # Strike rate (per minute)
    window_5 = now_utc - timedelta(minutes=5)
    window_10 = now_utc - timedelta(minutes=10)
    count_5 = sum(1 for s in strikes if s["ts"] >= window_5)
    count_10 = sum(1 for s in strikes if s["ts"] >= window_10)
    count_15 = len(strikes)
    product["strike_rate"]["per_min_5"] = round(count_5 / 5, 2) if count_5 else 0
    product["strike_rate"]["per_min_10"] = round(count_10 / 10, 2) if count_10 else 0
    product["strike_rate"]["per_min_15"] = round(count_15 / 15, 2) if count_15 else 0

    # Trend from lightning_recent
    if args.input_recent.exists():
        try:
            recent = json.loads(args.input_recent.read_text())
            product["trend"] = recent.get("trend", "steady")
        except (json.JSONDecodeError, OSError):
            pass

    # Alert state: CG within thresholds
    nearest_cg_mi = product["nearest_cg"]["distance_mi"] if product["nearest_cg"]["distance_mi"] > 0 else 999
    if nearest_cg_mi <= 5:
        product["alert_state"] = {"level": "danger", "reason": "CG within 5 mi", "active": True}
    elif nearest_cg_mi <= 10:
        product["alert_state"] = {"level": "warning", "reason": "CG within 10 mi", "active": True}
    elif nearest_cg_mi <= 15:
        product["alert_state"] = {"level": "elevated", "reason": "CG within 15 mi", "active": True}
    elif nearest_cg_mi <= 30:
        product["alert_state"] = {"level": "info", "reason": "CG within 30 mi", "active": True}
    else:
        product["alert_state"] = {"level": "none", "reason": "", "active": False}

    # Source health
    if args.input_status.exists():
        try:
            status = json.loads(args.input_status.read_text())
            product["source_health"]["relay_running"] = status.get("relay_running", True)
            last_ok = status.get("last_success_at_utc")
            if last_ok:
                last_dt = _parse_ts(last_ok)
                product["source_health"]["fresh"] = (now_utc - last_dt).total_seconds() < 60 if last_dt else True
            else:
                product["source_health"]["fresh"] = True
            last_msg = status.get("last_message_at_utc")
            if last_msg:
                last_msg_dt = _parse_ts(last_msg)
                if last_msg_dt:
                    product["data_freshness_sec"] = int((now_utc - last_msg_dt).total_seconds())
        except (json.JSONDecodeError, OSError):
            pass

    _atomic_write(args.output, json.dumps(product, indent=2))
    if args.remote:
        _scp_to_wx_i9(args.output, "lightning_summary.json")

    return 0


if __name__ == "__main__":
    sys.exit(main())
