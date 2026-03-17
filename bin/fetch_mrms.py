#!/usr/bin/env python3
"""List MRMS files from S3, pick N frames at cadence_min intervals. Output JSON with URLs and timestamps.

Selection logic: 36 frames = true 6 hours (one per 10 min). For each 10-minute slot, pick the
most recent available file at or before that slot. Never use a file from after the slot.
Ensures distinct images spanning the full 6 hours, matching NWS loop behavior.
"""
import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONF_DIR = PROJECT_ROOT / "conf"


def parse_ts_from_fname(fname: str) -> str | None:
    """Extract YYYYMMDD-HHMMSS from MRMS filename. Returns None if invalid."""
    try:
        s = fname.replace("MRMS_MergedReflectivityQCComposite_00.50_", "").replace(".grib2.gz", "")
        if len(s) != 15 or s[8] != "-":
            return None
        datetime.strptime(s[:8], "%Y%m%d")
        datetime.strptime(s[9:], "%H%M%S")
        return s
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=36, help="Number of frames to select")
    ap.add_argument("--cadence-min", type=int, default=10, help="Minutes between frames")
    ap.add_argument("--newest", action="store_true", help="Return only the single newest file on S3 (no slot alignment)")
    ap.add_argument("--date", help="YYYYMMDD (default: today UTC)")
    ap.add_argument("--config", default=str(CONF_DIR / "mrms_regions.json"), help="MRMS config for product/s3_region")
    ap.add_argument("--output", help="Write JSON to file (default: stdout)")
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text())
    product = cfg.get("product", "MergedReflectivityQCComposite_00.50")
    s3_region = cfg.get("s3_region", "CONUS")

    dt = datetime.now(timezone.utc)
    if args.date:
        dt = datetime.strptime(args.date, "%Y%m%d").replace(tzinfo=timezone.utc)

    # List S3 for today and yesterday (6h loop can span midnight)
    files_by_ts = {}
    for day_offset in (0, -1):
        d = dt + timedelta(days=day_offset)
        datestring = d.strftime("%Y%m%d")
        s3_prefix = f"noaa-mrms-pds/{s3_region}/{product}/{datestring}/"
        try:
            import s3fs
            aws = s3fs.S3FileSystem(anon=True)
            raw_files = aws.ls(s3_prefix)
        except Exception as e:
            if day_offset == 0:
                print(f"S3 list failed: {e}", file=sys.stderr)
                sys.exit(1)
            continue
        for p in raw_files:
            fname = p.split("/")[-1]
            ts = parse_ts_from_fname(fname)
            if ts:
                files_by_ts[ts] = p

    if not files_by_ts:
        print(f"No MRMS files found", file=sys.stderr)
        sys.exit(1)

    sorted_ts = sorted(files_by_ts.keys())
    latest_ts = sorted_ts[-1]

    if args.newest:
        # Return only the single newest file (no slot alignment). Ingest whatever NOAA sends.
        selected = [{
            "ts_raw": latest_ts,
            "ts_iso": f"{latest_ts[:4]}-{latest_ts[4:6]}-{latest_ts[6:8]}T{latest_ts[9:11]}:{latest_ts[11:13]}:{latest_ts[13:15]}Z",
            "s3_path": files_by_ts[latest_ts],
            "url": f"https://noaa-mrms-pds.s3.amazonaws.com/{files_by_ts[latest_ts].replace('noaa-mrms-pds/', '')}",
        }]
    else:
        latest_dt = datetime.strptime(latest_ts, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
        slot_min = (latest_dt.minute // args.cadence_min) * args.cadence_min
        anchor = latest_dt.replace(minute=slot_min, second=0, microsecond=0)

        slots = []
        for i in range(args.frames - 1, -1, -1):
            slot_dt = anchor - timedelta(minutes=i * args.cadence_min)
            slots.append(slot_dt)

        used = set()
        selected = []
        for slot_dt in slots:
            best = None
            for ts in sorted_ts:
                if ts in used:
                    continue
                ts_dt = datetime.strptime(ts, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
                if ts_dt <= slot_dt:
                    best = ts
                else:
                    break
            if best:
                used.add(best)
                selected.append({
                    "ts_raw": best,
                    "ts_iso": f"{best[:4]}-{best[4:6]}-{best[6:8]}T{best[9:11]}:{best[11:13]}:{best[13:15]}Z",
                    "s3_path": files_by_ts[best],
                    "url": f"https://noaa-mrms-pds.s3.amazonaws.com/{files_by_ts[best].replace('noaa-mrms-pds/', '')}",
                })

        selected.sort(key=lambda s: s["ts_raw"])

    result = {
        "date": dt.strftime("%Y%m%d"),
        "product": product,
        "frame_count": len(selected),
        "frames": selected,
    }

    out = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(out)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(out)


if __name__ == "__main__":
    main()
