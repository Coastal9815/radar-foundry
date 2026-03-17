#!/usr/bin/env python3
"""Backfill radar frames: fetch last N scans per site and publish to wx-i9.
Run on weather-core. Usage: ./bin/backfill_radar_frames.py [--count 72] [--site KCLX] [--site KJAX]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.client import Config as ClientConfig

BUCKET = "unidata-nexrad-level2"
S3_BASE = "https://unidata-nexrad-level2.s3.amazonaws.com"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def list_recent_scans(s3, site: str, day_utc: datetime):
    y, m, d = day_utc.strftime("%Y"), day_utc.strftime("%m"), day_utc.strftime("%d")
    prefix = f"{y}/{m}/{d}/{site}/"
    objs = []
    token = None
    while True:
        kw = dict(Bucket=BUCKET, Prefix=prefix, MaxKeys=1000)
        if token:
            kw["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kw)
        objs.extend([o for o in resp.get("Contents", []) if not o["Key"].endswith("_MDM")])
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    objs.sort(key=lambda o: o["LastModified"])
    return objs


def run(cmd, env=None, timeout=300):
    r = subprocess.run(cmd, text=True, capture_output=True, env=env, timeout=timeout, cwd=PROJECT_ROOT)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=72, help="Frames per site")
    ap.add_argument("--site", action="append", default=[], help="Site(s), default KCLX KJAX")
    ap.add_argument("--remote-base", default="/home/scott/wx-data/served")
    ap.add_argument("--remote-host", default="wx-i9")
    ap.add_argument("--remote-user", default="scott")
    args = ap.parse_args()
    sites = args.site if args.site else ["KCLX", "KJAX"]

    scratch_base = Path(os.environ.get("WX_SCRATCH_BASE", str(PROJECT_ROOT / "scratch")))
    raw_dir = scratch_base / "raw_level2_live"
    raw_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["WX_SCRATCH_BASE"] = str(scratch_base)

    config = ClientConfig(signature_version=UNSIGNED, connect_timeout=15, read_timeout=120)
    s3 = boto3.client("s3", region_name="us-east-1", config=config)

    today = datetime.now(timezone.utc)
    py = sys.executable

    for site in sites:
        print(f"[{site}] listing scans...", flush=True)
        objs = list_recent_scans(s3, site, today)
        if not objs:
            objs = list_recent_scans(s3, site, today - timedelta(days=1))
        if not objs:
            print(f"[{site}] no scans found", flush=True)
            continue
        to_fetch = objs[-args.count:]
        print(f"[{site}] backfilling {len(to_fetch)} frames...", flush=True)

        for i, obj in enumerate(to_fetch):
            key = obj["Key"]
            lm = obj["LastModified"].astimezone(timezone.utc)
            lm_str = lm.strftime("%Y-%m-%dT%H:%M:%S+00:00")
            fname = key.split("/")[-1]
            out_path = raw_dir / f"{site}_{fname}"
            url = f"{S3_BASE}/{key}"

            if not out_path.exists():
                r = subprocess.run(["curl", "-sSf", "-o", str(out_path), "--max-time", "180", url], capture_output=True)
                if r.returncode != 0 or not out_path.exists():
                    print(f"[{site}] skip {fname} (download failed)", flush=True)
                    continue

            meta = {
                "site": site,
                "out_path": str(out_path),
                "last_modified_utc": lm_str,
            }
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(meta, f, indent=2)
                meta_path = f.name

            ok = run([py, str(PROJECT_ROOT / "bin" / "update_radar_loop.py"),
                     "--site", site,
                     "--remote-base", f"{args.remote_base}/radar_local_{site}/frames",
                     "--remote-host", args.remote_host,
                     "--remote-user", args.remote_user,
                     "--fetch-meta", meta_path],
                    env=env, timeout=180)
            Path(meta_path).unlink(missing_ok=True)
            if not ok:
                print(f"[{site}] skip {fname} (publish failed)", flush=True)
                continue

            if (i + 1) % 12 == 0:
                print(f"[{site}] {i + 1}/{len(to_fetch)}", flush=True)

        print(f"[{site}] done {len(to_fetch)} frames", flush=True)


if __name__ == "__main__":
    main()
