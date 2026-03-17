#!/usr/bin/env python3
"""List GOES ABI L1b RadC files from S3, pick N frames at 5-min cadence.
Output JSON with URLs and timestamps. Channel filter: C02 (visible), C13 (IR).
"""
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONF_DIR = PROJECT_ROOT / "conf"


def parse_goes_timestamp(fname: str) -> str | None:
    """Extract start time from GOES filename: sYYYYDDDHHMMSS[fff] -> YYYYMMDD-HHMMSS."""
    m = re.search(r"_s(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})", fname)
    if not m:
        return None
    year, doy, hour, minute, sec = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
    try:
        dt = datetime.strptime(f"{year}-{doy}", "%Y-%j")
        return f"{dt.strftime('%Y%m%d')}-{hour}{minute}{sec}"
    except ValueError:
        return None


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=72)
    ap.add_argument("--cadence-min", type=int, default=5)
    ap.add_argument("--channel", type=int, required=True, help="ABI channel: 2=visible, 13=IR")
    ap.add_argument("--bucket", default="noaa-goes19", help="noaa-goes16 or noaa-goes19")
    ap.add_argument("--newest", action="store_true", help="Return only newest file")
    ap.add_argument("--recent-minutes", type=int, default=0, help="Return all frames from last N minutes (0=use frames/cadence)")
    ap.add_argument("--output", help="Write JSON to file")
    args = ap.parse_args()

    channel_str = f"C{args.channel:02d}"
    product = "ABI-L1b-RadC"

    dt = datetime.now(timezone.utc)
    files_by_ts = {}

    for day_offset in (0, -1):
        d = dt + timedelta(days=day_offset)
        year = d.year
        doy = d.strftime("%j")
        prefix = f"{args.bucket}/{product}/{year}/{doy}/"
        try:
            import s3fs
            fs = s3fs.S3FileSystem(anon=True)
            # List all hours for the day
            for hour in range(24):
                hour_prefix = f"{prefix}{hour:02d}/"
                try:
                    raw = fs.ls(hour_prefix)
                    for p in raw:
                        fname = p.split("/")[-1]
                        if channel_str in fname and fname.endswith(".nc"):
                            ts = parse_goes_timestamp(fname)
                            if ts:
                                key = p.replace(f"{args.bucket}/", "")
                                files_by_ts[ts] = key
                except (FileNotFoundError, OSError):
                    continue
        except Exception as e:
            if day_offset == 0:
                print(f"S3 list failed: {e}", file=sys.stderr)
                sys.exit(1)
            continue

    if not files_by_ts:
        print(f"No GOES {channel_str} files found in {args.bucket}", file=sys.stderr)
        sys.exit(1)

    sorted_ts = sorted(files_by_ts.keys())
    latest_ts = sorted_ts[-1]

    if args.newest:
        key = files_by_ts[latest_ts]
        out = {
            "frames": [{"ts_raw": latest_ts, "url": f"https://{args.bucket}.s3.amazonaws.com/{key}"}],
            "channel": args.channel,
            "bucket": args.bucket,
        }
    elif args.recent_minutes > 0:
        # Return all frames from last N minutes (process whatever NOAA sent)
        cutoff = (dt - timedelta(minutes=args.recent_minutes)).strftime("%Y%m%d-%H%M%S")
        recent = [(ts, files_by_ts[ts]) for ts in sorted_ts if ts >= cutoff]
        out = {
            "frames": [{"ts_raw": ts, "url": f"https://{args.bucket}.s3.amazonaws.com/{key}"} for ts, key in recent],
            "channel": args.channel,
            "bucket": args.bucket,
        }
    else:
        # Slot selection: 72 slots at 5-min cadence
        latest_dt = datetime.strptime(latest_ts[:15], "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
        slot_min = (latest_dt.minute // args.cadence_min) * args.cadence_min
        anchor = latest_dt.replace(minute=slot_min, second=0, microsecond=0)

        slots = [anchor - timedelta(minutes=i * args.cadence_min) for i in range(args.frames - 1, -1, -1)]
        used = set()
        result = []
        for slot_dt in slots:
            slot_ts = slot_dt.strftime("%Y%m%d-%H%M%S")
            best = None
            for ts in sorted_ts:
                if ts in used:
                    continue
                if ts <= slot_ts:
                    best = ts
                else:
                    break
            if best:
                used.add(best)
                key = files_by_ts[best]
                result.append({"ts_raw": best, "url": f"https://{args.bucket}.s3.amazonaws.com/{key}"})

        out = {
            "frames": sorted(result, key=lambda x: x["ts_raw"]),
            "channel": args.channel,
            "bucket": args.bucket,
            "cadence_min": args.cadence_min,
        }

    j = json.dumps(out, indent=2)
    if args.output:
        Path(args.output).write_text(j)
    else:
        print(j)


if __name__ == "__main__":
    main()
