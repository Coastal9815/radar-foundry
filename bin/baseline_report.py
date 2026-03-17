#!/usr/bin/env python3
"""Parse MRMS and coordinator timing logs, compute baseline metrics.
Usage: python3 baseline_report.py [mrms_log] [coord_log] [--since TIMESTAMP]
  If omitted, uses /tmp/mrms_loop_launchd.log and /tmp/radar_coordinator_launchd.log
  --since: only include runs with ts_utc >= TIMESTAMP (ISO format, e.g. 2026-03-08T16:52:21Z)
"""
import sys
from collections import defaultdict

MRMS_LOG = "/tmp/mrms_loop_launchd.log"
COORD_LOG = "/tmp/radar_coordinator_launchd.log"


def _ts_ge(ts: str, cutoff: str) -> bool:
    """True if ts >= cutoff (ISO format, lexicographic compare works)."""
    return ts >= cutoff


def parse_line(line):
    """Parse key=value pairs from log line."""
    if "|" not in line:
        return {}
    parts = line.strip().split("|")
    return dict(p.split("=", 1) for p in parts[1:] if "=" in p)


def stats(vals):
    if not vals:
        return 0, 0.0, 0
    return min(vals), sum(vals) / len(vals), max(vals)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    since_idx = next((i for i, a in enumerate(sys.argv[1:], 1) if a == "--since"), None)
    since = sys.argv[since_idx + 1] if since_idx is not None and since_idx + 1 < len(sys.argv) else None

    mrms_path = args[0] if len(args) > 0 else MRMS_LOG
    coord_path = args[1] if len(args) > 1 else COORD_LOG

    mrms_timing = []
    mrms_freshness_raw = []

    try:
        for line in open(mrms_path):
            if "MRMS_TIMING|" in line:
                d = parse_line(line)
                if d:
                    if since and not _ts_ge(d.get("ts_utc", ""), since):
                        continue
                    mrms_timing.append({
                        "run_id": d.get("run_id", ""),
                        "duration_sec": int(d.get("duration_sec", 0)),
                        "exit_code": int(d.get("exit_code", -1)),
                    })
            elif "MRMS_FRESHNESS|" in line:
                d = parse_line(line)
                if d:
                    if since:
                        if not _ts_ge(d.get("ts_utc", ""), since):
                            continue
                    mrms_freshness_raw.append({
                        "run_id": d.get("run_id", ""),
                        "source_ts": d.get("source_ts", ""),
                        "freshness_latency_sec": int(d.get("freshness_latency_sec", 0)),
                    })
    except FileNotFoundError:
        print(f"MRMS log not found: {mrms_path}", file=sys.stderr)
        mrms_timing = []
        mrms_freshness_raw = []

    filtered_run_ids = {t["run_id"] for t in mrms_timing}
    mrms_freshness = [f for f in mrms_freshness_raw if f["run_id"] in filtered_run_ids]
    mrms_add_run_ids = {f["run_id"] for f in mrms_freshness}

    coord_timing = []
    radar_site = defaultdict(list)

    try:
        for line in open(coord_path):
            if "COORD_TIMING|" in line:
                d = parse_line(line)
                if d:
                    if since and not _ts_ge(d.get("ts_utc", ""), since):
                        continue
                    coord_timing.append({
                        "run_id": d.get("run_id", ""),
                        "duration_sec": int(d.get("duration_sec", 0)),
                        "ok": int(d.get("ok", 0)),
                        "failed": int(d.get("failed", 0)),
                    })
            elif "RADAR_SITE_TIMING|" in line:
                d = parse_line(line)
                if d and d.get("success") == "ok":
                    if since and not _ts_ge(d.get("ts_utc", ""), since):
                        continue
                    site = d.get("site", "")
                    fl = d.get("freshness_latency_sec", "")
                    radar_site[site].append({
                        "duration_sec": int(d.get("duration_sec", 0)),
                        "freshness_latency_sec": int(fl) if fl and str(fl).isdigit() else None,
                    })
    except FileNotFoundError:
        print(f"Coordinator log not found: {coord_path}", file=sys.stderr)
        coord_timing = []

    add_runs = [t for t in mrms_timing if t["run_id"] in mrms_add_run_ids]
    skip_runs = [t for t in mrms_timing if t["run_id"] not in mrms_add_run_ids]
    add_durations = [t["duration_sec"] for t in add_runs]
    freshness_latencies = [f["freshness_latency_sec"] for f in mrms_freshness if f["freshness_latency_sec"] > 0]

    if since:
        print(f"=== CLEAN WINDOW (post-change) ===")
        print(f"start_timestamp: {since}")
        print()

    print("=== MRMS ===")
    print(f"count_runs: {len(mrms_timing)}")
    print(f"count_add_runs: {len(add_runs)}")
    print(f"count_skip_runs: {len(skip_runs)}")
    add_min, add_avg, add_max = stats(add_durations)
    print(f"add_duration_sec: min={add_min} avg={add_avg:.1f} max={add_max}")
    skip_min, skip_avg, skip_max = stats([t["duration_sec"] for t in skip_runs])
    print(f"skip_duration_sec: min={skip_min} avg={skip_avg:.1f} max={skip_max}")
    fl_min, fl_avg, fl_max = stats(freshness_latencies)
    print(f"freshness_latency_sec: min={fl_min} avg={fl_avg:.1f} max={fl_max}")

    # Skip-path optimization comparison (Phase 1)
    SKIP_PREV_OBSERVED_SEC = 49
    if skip_runs and skip_avg > 0:
        improvement = SKIP_PREV_OBSERVED_SEC / skip_avg
        print("\n=== MRMS SKIP OPTIMIZATION (Phase 1) ===")
        print(f"previous_observed_skip_sec: ~{SKIP_PREV_OBSERVED_SEC}")
        print(f"current_skip_sec: min={skip_min} avg={skip_avg:.1f} max={skip_max}")
        print(f"estimated_improvement_factor: {improvement:.1f}x")

    print("\n=== COORDINATOR ===")
    print(f"count_runs: {len(coord_timing)}")
    cd_min, cd_avg, cd_max = stats([t["duration_sec"] for t in coord_timing])
    print(f"duration_sec: min={cd_min} avg={cd_avg:.1f} max={cd_max}")

    for site in sorted(radar_site.keys()):
        vals = radar_site[site]
        print(f"\n=== RADAR {site} ===")
        d_min, d_avg, d_max = stats([v["duration_sec"] for v in vals])
        print(f"duration_sec: min={d_min} avg={d_avg:.1f} max={d_max}")
        fl_vals = [v["freshness_latency_sec"] for v in vals if v["freshness_latency_sec"] is not None]
        fl_min, fl_avg, fl_max = stats(fl_vals)
        print(f"freshness_latency_sec: min={fl_min} avg={fl_avg:.1f} max={fl_max}")


if __name__ == "__main__":
    main()
