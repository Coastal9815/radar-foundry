#!/usr/bin/env python3
import os, subprocess, sys, json
from datetime import datetime, timezone, timedelta

import boto3
from botocore import UNSIGNED
from botocore.client import Config as ClientConfig

BUCKET = "unidata-nexrad-level2"  # archive bucket (no auth)
S3_BASE = "https://unidata-nexrad-level2.s3.amazonaws.com"

def utcnow():
    return datetime.now(timezone.utc)

def list_keys(s3, prefix: str, max_keys=2000):
    token = None
    out = []
    while True:
        kw = dict(Bucket=BUCKET, Prefix=prefix, MaxKeys=1000)
        if token: kw["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kw)
        out.extend(resp.get("Contents", []))
        if not resp.get("IsTruncated"):
            return out
        token = resp.get("NextContinuationToken")
        if len(out) >= max_keys:
            return out

def pick_latest(s3, site: str, day_utc: datetime):
    y = day_utc.strftime("%Y")
    m = day_utc.strftime("%m")
    d = day_utc.strftime("%d")
    prefix = f"{y}/{m}/{d}/{site}/"
    objs = list_keys(s3, prefix)
    if not objs:
        return None, prefix
    objs = [o for o in objs if not o["Key"].endswith("_MDM")]
    if not objs:
        return None, prefix
    objs.sort(key=lambda o: o["LastModified"])
    return objs[-1], prefix

def main():
    list_only = "--list-only" in sys.argv
    if list_only:
        sys.argv = [a for a in sys.argv if a != "--list-only"]
    site = (sys.argv[1] if len(sys.argv) > 1 else "KCLX").upper()

    config = ClientConfig(signature_version=UNSIGNED, connect_timeout=15, read_timeout=120)
    s3 = boto3.client("s3", region_name="us-east-1", config=config)

    today = utcnow()
    obj, prefix = pick_latest(s3, site, today)
    if obj is None:
        obj, prefix = pick_latest(s3, site, today - timedelta(days=1))
    if obj is None:
        raise SystemExit(f"No Level II objects found for {site} (tried {prefix} and previous day).")

    key = obj["Key"]
    lm = obj["LastModified"].astimezone(timezone.utc).isoformat()
    size = obj["Size"]

    scratch_base = os.environ.get("WX_SCRATCH_BASE")
    if scratch_base:
        out_dir = os.path.join(scratch_base, "raw_level2_live")
        log_dir = os.path.join(scratch_base, "logs_level2")
    else:
        base = os.path.join(os.path.expanduser("~"), "wx", "radar-foundry")
        out_dir = os.path.join(base, "raw_level2")
        log_dir = os.path.join(base, "logs_level2")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    ts = utcnow().strftime("%Y%m%dT%H%M%SZ")
    fname = os.path.basename(key)
    out_path = os.path.join(out_dir, f"{site}_{fname}")
    meta_path = os.path.join(log_dir, f"{site}_latest_{ts}.json")
    url = f"{S3_BASE}/{key}"

    meta = {
        "site": site,
        "bucket": BUCKET,
        "prefix": prefix,
        "key": key,
        "last_modified_utc": lm,
        "size_bytes": size,
        "out_path": out_path,
        "url": url,
    }

    if list_only:
        print(json.dumps(meta, indent=2))
        return

    r = subprocess.run(
        ["/bin/bash", os.path.join(os.path.dirname(__file__), "curl_download.sh"), url, out_path],
        capture_output=False, timeout=200
    )
    if r.returncode != 0:
        raise SystemExit(r.returncode)

    meta["downloaded_utc"] = utcnow().isoformat()
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(json.dumps(meta, indent=2))

if __name__ == "__main__":
    main()
