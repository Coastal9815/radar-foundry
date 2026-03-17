#!/usr/bin/env python3
import os, sys, json
from datetime import datetime, timezone, timedelta
import boto3
from botocore import UNSIGNED
from botocore.client import Config as ClientConfig

BUCKET = "unidata-nexrad-level3"

def utcnow():
    return datetime.now(timezone.utc)

def list_all(s3, prefix: str):
    token = None
    out = []
    while True:
        if token:
            resp = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix, ContinuationToken=token)
        else:
            resp = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix)
        out.extend(resp.get("Contents", []))
        if not resp.get("IsTruncated"):
            return out
        token = resp.get("NextContinuationToken")

def pick_latest_for_date(s3, site: str, product: str, day_utc: datetime):
    d = day_utc.strftime("%Y_%m_%d")
    prefix = f"{site}_{product}_{d}"
    objs = list_all(s3, prefix)
    if not objs:
        return None, prefix
    objs.sort(key=lambda o: o["LastModified"])
    return objs[-1], prefix

def main():
    site = (sys.argv[1] if len(sys.argv) > 1 else "CLX").upper()
    product = (sys.argv[2] if len(sys.argv) > 2 else "N0B").upper()

    s3 = boto3.client("s3", config=ClientConfig(signature_version=UNSIGNED))

    today = utcnow()
    obj, prefix = pick_latest_for_date(s3, site, product, today)
    if obj is None:
        obj, prefix = pick_latest_for_date(s3, site, product, today - timedelta(days=1))
    if obj is None:
        raise SystemExit(f"No objects found for {site} {product} using date prefixes (tried {prefix} and previous day).")

    key = obj["Key"]
    lm = obj["LastModified"].astimezone(timezone.utc).isoformat()
    size = obj["Size"]

    base = os.path.join(os.path.expanduser("~"), "wx", "radar-foundry")
    out_dir = os.path.join(base, "raw")
    log_dir = os.path.join(base, "logs")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    ts = utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_path = os.path.join(out_dir, f"{site}_{product}_latest_{ts}.bin")
    meta_path = os.path.join(log_dir, f"{site}_{product}_latest_{ts}.json")

    s3.download_file(BUCKET, key, out_path)

    meta = {
        "site": site,
        "product": product,
        "bucket": BUCKET,
        "date_prefix_used": prefix,
        "key": key,
        "last_modified_utc": lm,
        "size_bytes": size,
        "downloaded_utc": utcnow().isoformat(),
        "out_path": out_path,
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(json.dumps(meta, indent=2))

if __name__ == "__main__":
    main()
