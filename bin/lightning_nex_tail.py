#!/usr/bin/env python3
"""NexStorm .nex tail pipeline — simplest supported path.

Polls .nex via nxutil on Lightning-PC every 5 seconds. No session tricks, no FlashGate.
Output: lightning_rt.ndjson, lightning_status.json, lightning_recent.json on Lightning-PC.

HARDENED: Retries, atomic writes, timeouts, watchdog-friendly status.
Usage: python bin/lightning_nex_tail.py [--interval 5] [--output-remote]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path

LIGHTNING_PC = "scott@192.168.2.223"
NEXUTIL = "C:/Astrogenic/NexStorm/util/nxutil.exe"
NEX_DIR = "C:/Astrogenic/NexStorm"
REMOTE_OUT = "C:/MRW/lightning"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_SCRATCH = PROJECT_ROOT / "scratch" / "lightning_nex"
SENSOR_ID = "MRW"
SSH_TIMEOUT = 30
SCP_TIMEOUT = 20
MAX_RETRIES = 3
RETRY_DELAY = 2


def run_ssh(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", "-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=10", LIGHTNING_PC, cmd],
        capture_output=True,
        text=True,
        timeout=SSH_TIMEOUT,
    )


def scp_pull(remote: str, local: Path) -> bool:
    for attempt in range(MAX_RETRIES):
        try:
            r = subprocess.run(
                ["scp", "-q", "-o", "ConnectTimeout=5", f"{LIGHTNING_PC}:{remote}", str(local)],
                capture_output=True,
                timeout=SCP_TIMEOUT,
            )
            if r.returncode == 0:
                return True
        except subprocess.TimeoutExpired:
            pass
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)
    return False


def scp_push(local: Path, remote: str) -> bool:
    for attempt in range(MAX_RETRIES):
        try:
            r = subprocess.run(
                ["scp", "-q", "-o", "ConnectTimeout=5", str(local), f"{LIGHTNING_PC}:{remote}"],
                capture_output=True,
                timeout=SCP_TIMEOUT,
            )
            if r.returncode == 0:
                return True
        except subprocess.TimeoutExpired:
            pass
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)
    return False


def _atomic_write(path: Path, content: str) -> None:
    """Write content atomically (temp + rename)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    tmp.rename(path)


def parse_csv_row(row: str) -> dict | None:
    """Parse nxutil CSV: S,B,D,C,T,P,X,Y,K,L."""
    parts = row.strip().split(",")
    if len(parts) < 10:
        return None
    try:
        s = int(parts[0])  # seconds since midnight
        b = float(parts[1])  # bearing
        d = float(parts[2])  # uncorrected distance
        c = float(parts[3])  # corrected distance
        t = int(parts[4])  # 0=CG, 1=IC
        p = int(parts[5])  # 0=pos, 1=neg
        x, y = float(parts[6]), float(parts[7])
        k, l_ = float(parts[8]), float(parts[9])
    except (ValueError, IndexError):
        return None
    return {
        "s": s,
        "bearing": b,
        "dist_uncorr": d,
        "dist_corr": c,
        "type": t,
        "polarity": p,
        "x": x,
        "y": y,
        "k": k,
        "l": l_,
    }


BEARING_TO_DIR = [
    (22.5, "N"), (67.5, "NE"), (112.5, "E"), (157.5, "SE"),
    (202.5, "S"), (247.5, "SW"), (292.5, "W"), (337.5, "NW"), (360.0, "N"),
]


def bearing_to_direction(deg: float) -> str:
    """Convert bearing (0-360) to cardinal direction."""
    deg = deg % 360
    for threshold, label in BEARING_TO_DIR:
        if deg < threshold:
            return label
    return "N"


def parse_ts(ts_str: str) -> datetime | None:
    """Parse ISO UTC timestamp to datetime."""
    try:
        s = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def compute_lightning_recent(
    strikes: list[tuple[datetime, float, float]],
    now_utc: datetime,
    recent_nearest_history: list[float],
) -> tuple[dict, list[float]]:
    """Compute lightning_recent.json from recent strikes. Returns (product, updated_history)."""
    window_15 = now_utc - timedelta(minutes=15)
    window_10 = now_utc - timedelta(minutes=10)
    window_5 = now_utc - timedelta(minutes=5)

    recent = [(t, d, b) for t, d, b in strikes if t >= window_15 and d is not None and d >= 0]
    if not recent:
        product = {
            "last_strike_time_utc": None,
            "nearest_strike_km": None,
            "nearest_strike_miles": None,
            "closest_strike_bearing_deg": None,
            "closest_strike_direction": None,
            "strikes_last_5_min": 0,
            "strikes_last_10_min": 0,
            "strikes_last_15_min": 0,
            "trend": "steady",
            "computed_at_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
        return product, recent_nearest_history

    last_ts = max(t for t, _, _ in recent)
    nearest = min(recent, key=lambda x: x[1])
    nearest_km = nearest[1]
    nearest_mi = round(nearest_km * 0.621371, 2)
    bearing = nearest[2]

    count_5 = sum(1 for t, _, _ in recent if t >= window_5)
    count_10 = sum(1 for t, _, _ in recent if t >= window_10)
    count_15 = len(recent)

    history = recent_nearest_history + [nearest_km]
    if len(history) > 5:
        history = history[-5:]
    trend = "steady"
    if len(history) >= 4:
        recent_avg = sum(history[-2:]) / 2
        older_avg = sum(history[-4:-2]) / 2
        diff_pct = (older_avg - recent_avg) / older_avg if older_avg > 0 else 0
        if diff_pct > 0.1:
            trend = "approaching"
        elif diff_pct < -0.1:
            trend = "departing"

    product = {
        "last_strike_time_utc": last_ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "nearest_strike_km": round(nearest_km, 2),
        "nearest_strike_miles": nearest_mi,
        "closest_strike_bearing_deg": round(bearing, 1),
        "closest_strike_direction": bearing_to_direction(bearing),
        "strikes_last_5_min": count_5,
        "strikes_last_10_min": count_10,
        "strikes_last_15_min": count_15,
        "trend": trend,
        "computed_at_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    }
    return product, history


def load_recent_strikes(rt_path: Path, window_min: int = 15) -> deque:
    """Load last N minutes of strikes from lightning_rt.ndjson for rolling window."""
    out: deque[tuple[datetime, float | None, float]] = deque(maxlen=5000)
    if not rt_path.exists():
        return out
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_min)
    lines = rt_path.read_text().strip().splitlines()
    for line in lines[-2000:]:  # last 2000 lines to bound startup cost
        try:
            rec = json.loads(line)
            ts = parse_ts(rec.get("timestamp_utc", ""))
            dist = rec.get("raw_distance_km") or rec.get("trac_distance_km")
            bearing = rec.get("raw_bearing_deg") or rec.get("trac_bearing_deg") or 0.0
            if ts and ts >= cutoff:
                out.append((ts, dist, bearing))
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def to_canonical(raw: dict, ingested_at: str, date_str: str) -> dict:
    """Convert to MRW canonical strike record."""
    s = raw["s"]
    b, d = raw["bearing"], raw["dist_corr"]
    # s = seconds since midnight local (NexStorm uses station time)
    yr, mo, dy = int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8])
    from datetime import time as dt_time, datetime as dt_dt
    t = dt_time(s // 3600, (s % 3600) // 60, s % 60)
    ts_local = dt_dt.combine(dt_dt(yr, mo, dy).date(), t)
    try:
        from zoneinfo import ZoneInfo
        ts_utc = ts_local.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(ZoneInfo("UTC"))
    except Exception:
        ts_utc = ts_local
    ts_str = ts_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    key = f"{ts_str}|{b}|{d}|{SENSOR_ID}"
    strike_id = hashlib.sha256(key.encode()).hexdigest()[:32]
    return {
        "strike_id": strike_id,
        "timestamp_utc": ts_str,
        "sensor_id": SENSOR_ID,
        "source": "nex_archive",
        "raw_bearing_deg": b,
        "raw_distance_km": d if d >= 0 else None,
        "trac_bearing_deg": b,
        "trac_distance_km": d if d >= 0 else None,
        "strike_type": "IC" if raw["type"] == 1 else "CG",
        "polarity": "negative" if raw["polarity"] == 1 else "positive",
        "is_noise": False,
        "ingested_at_utc": ingested_at,
        "raw_payload": f"{raw['s']},{raw['bearing']},{raw['dist_uncorr']},{raw['dist_corr']},{raw['type']},{raw['polarity']},{raw['x']},{raw['y']},{raw['k']},{raw['l']}",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="NexStorm .nex tail pipeline")
    ap.add_argument("--interval", type=int, default=5, help="Poll interval seconds")
    ap.add_argument("--output-remote", action="store_true", help="Push outputs to Lightning-PC")
    args = ap.parse_args()

    LOCAL_SCRATCH.mkdir(parents=True, exist_ok=True)
    rt_path = LOCAL_SCRATCH / "lightning_rt.ndjson"
    status_path = LOCAL_SCRATCH / "lightning_status.json"
    recent_path = LOCAL_SCRATCH / "lightning_recent.json"
    csv_local = LOCAL_SCRATCH / "nex_tail.csv"

    last_count = 0
    total_strikes = 0
    last_strike_at: str | None = None
    last_error: str | None = None
    recent_strikes: deque[tuple[datetime, float | None, float]] = load_recent_strikes(rt_path)
    recent_nearest_history: list[float] = []
    range_rings_pushed = False

    print("lightning_nex_tail: polling every", args.interval, "s. Output:", "remote" if args.output_remote else "local")

    def _run_geo_generators() -> None:
        """Run GeoJSON generators every 3s for near real-time map updates."""
        py = PROJECT_ROOT / ".venv" / "bin" / "python"
        if not py.exists():
            py = Path(sys.executable)
        while True:
            if args.output_remote:
                try:
                    for script in ["generate_lightning_points.py", "generate_lightning_points_v2.py", "generate_lightning_summary.py"]:
                        r = subprocess.run(
                            [str(py), str(PROJECT_ROOT / "bin" / script), "--remote"],
                            cwd=str(PROJECT_ROOT),
                            capture_output=True,
                            text=True,
                            timeout=15,
                        )
                        if r.returncode != 0:
                            print(f"{script} failed: {r.stderr or r.stdout}", flush=True)
                except Exception as e:
                    print(f"geo generator error: {e}", flush=True)
            time.sleep(3)

    if args.output_remote:
        geo_thread = threading.Thread(target=_run_geo_generators, daemon=True)
        geo_thread.start()

    while True:
        try:
            date_str = datetime.now().strftime("%Y%m%d")

            # Ensure output dir exists on Lightning-PC (best-effort)
            try:
                run_ssh(f'if not exist "{REMOTE_OUT}" mkdir "{REMOTE_OUT}"')
            except subprocess.TimeoutExpired:
                pass

            # Run nxutil on Lightning-PC (retry on transient failure)
            r = None
            for attempt in range(MAX_RETRIES):
                try:
                    r = run_ssh(
                        f'cd "{NEX_DIR}" && "{NEXUTIL}" -extract -i {date_str} -f ALL -o "{REMOTE_OUT}/nex_tail.csv" -validate'
                    )
                    break
                except subprocess.TimeoutExpired:
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY)
                    else:
                        raise
            if r and r.returncode != 0:
                last_error = r.stderr or r.stdout or "nxutil failed"
                time.sleep(args.interval)
                continue

            # Pull CSV
            if not scp_pull(f"{REMOTE_OUT}/nex_tail.csv", csv_local):
                last_error = "scp pull failed"
                time.sleep(args.interval)
                continue

            lines = csv_local.read_text().strip().splitlines()
            current_count = len(lines)

            ingested_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

            # Process new rows
            for i in range(last_count, current_count):
                raw = parse_csv_row(lines[i])
                if raw:
                    rec = to_canonical(raw, ingested_at, date_str)
                    with open(rt_path, "a") as f:
                        f.write(json.dumps(rec) + "\n")
                    total_strikes += 1
                    last_strike_at = ingested_at
                    ts = parse_ts(rec["timestamp_utc"])
                    dist = rec.get("raw_distance_km") or rec.get("trac_distance_km")
                    bearing = rec.get("raw_bearing_deg") or rec.get("trac_bearing_deg") or 0.0
                    if ts:
                        recent_strikes.append((ts, dist, bearing))

            # Prune strikes older than 15 min
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
            while recent_strikes and recent_strikes[0][0] < cutoff:
                recent_strikes.popleft()

            # Compute lightning_recent product
            now_utc = datetime.now(timezone.utc)
            recent_product, recent_nearest_history = compute_lightning_recent(
                list(recent_strikes), now_utc, recent_nearest_history
            )
            _atomic_write(recent_path, json.dumps(recent_product, indent=2))

            last_count = current_count
            last_error = None

            status = {
                "relay_running": True,
                "source": "nex_archive_tail",
                "last_message_at_utc": ingested_at,
                "last_success_at_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "last_strike_at_utc": last_strike_at,
                "total_strikes": total_strikes,
                "last_error": last_error,
            }
            _atomic_write(status_path, json.dumps(status, indent=2))

            if args.output_remote:
                scp_push(rt_path, f"{REMOTE_OUT}/lightning_rt.ndjson")
                scp_push(status_path, f"{REMOTE_OUT}/lightning_status.json")
                scp_push(recent_path, f"{REMOTE_OUT}/lightning_recent.json")
                # Push range rings once (static product)
                if not range_rings_pushed:
                    rings_path = PROJECT_ROOT / "serve_root" / "lightning_range_rings.geojson"
                    if rings_path.exists():
                        scp_push(rings_path, f"{REMOTE_OUT}/lightning_range_rings.geojson")
                        range_rings_pushed = True
        except subprocess.TimeoutExpired as e:
            last_error = f"timeout: {e}"
            status = {
                "relay_running": True,
                "last_error": last_error,
                "total_strikes": total_strikes,
            }
            _atomic_write(status_path, json.dumps(status, indent=2))
            if args.output_remote:
                scp_push(status_path, f"{REMOTE_OUT}/lightning_status.json")
        except Exception as e:
            last_error = str(e)
            status = {
                "relay_running": True,
                "last_error": last_error,
                "total_strikes": total_strikes,
            }
            _atomic_write(status_path, json.dumps(status, indent=2))
            if args.output_remote:
                scp_push(status_path, f"{REMOTE_OUT}/lightning_status.json")

        time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    sys.exit(main())
