#!/usr/bin/env python3
"""Fetch MRMS frames from S3, render per region (6 crops), publish. Each region gets full-res overlay.

Option B (NWS-style):
  - Ingest every new file from S3 (no 10-min filter). Pool = last 200 images per region.
  - Loop = 36 frames, one per 10-min slot. For each slot: most recent at or before slot time.
  - Run every 1 min. ~1-2 min per new frame.
"""
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONF_DIR = PROJECT_ROOT / "conf"
PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"


def run(cmd, env=None, timeout=300):
    r = subprocess.run(cmd, text=True, capture_output=True, env=env, timeout=timeout)
    if r.returncode != 0:
        print(r.stdout, end="")
        print(r.stderr, end="", file=sys.stderr)
        raise SystemExit(r.returncode)
    return r


def _render_region(args, region, grib_path, frame_name, scratch, base_dir, i):
    """Render one region. Returns (rid, ok, msg). Used by parallel render stage."""
    rid = region["id"]
    if args.local_only:
        png_path = base_dir / rid / frame_name
    else:
        (scratch / rid).mkdir(parents=True, exist_ok=True)
        png_path = scratch / rid / frame_name
    bounds_out = scratch / f"{rid}_bounds.json" if i == 0 else None
    render_cmd = [str(PYTHON), str(PROJECT_ROOT / "bin" / "render_mrms_frame.py"),
                 str(grib_path), "--output", str(png_path), "--region", rid]
    if bounds_out:
        render_cmd.extend(["--bounds-json", str(bounds_out)])
    try:
        r = subprocess.run(render_cmd, text=True, capture_output=True, timeout=120)
        if r.returncode != 0:
            return (rid, False, (r.stderr or r.stdout or "render failed").strip()[:200])
        return (rid, True, "")
    except subprocess.TimeoutExpired:
        return (rid, False, "timeout")
    except Exception as e:
        return (rid, False, str(e))


def _rsync_region(rid, src, remote_user, remote_host, remote_path, timeout=180):
    """Rsync one region to remote. Returns (rid, ok, msg). Used by parallel rsync stage."""
    if not src.exists():
        return (rid, True, "")
    try:
        r = subprocess.run(
            ["rsync", "-az", "--timeout=120", f"{src}/",
             f"{remote_user}@{remote_host}:{remote_path}/{rid}/"],
            text=True, capture_output=True, timeout=timeout,
        )
        if r.returncode != 0:
            return (rid, False, (r.stderr or r.stdout or "rsync failed").strip()[:200])
        return (rid, True, "")
    except subprocess.TimeoutExpired:
        return (rid, False, "timeout")
    except Exception as e:
        return (rid, False, str(e))


def _post_publish_region(args, region, base_dir, scratch, remote_path, product):
    """Post-publish one region: trim pool, slot select, manifest, SCP. Returns (rid, ok, msg)."""
    rid = region["id"]
    try:
        if args.local_only:
            region_dir = base_dir / rid
            pool = sorted([p.name for p in region_dir.glob("*.png")])
            if len(pool) > args.keep:
                for f in pool[: len(pool) - args.keep]:
                    (region_dir / f).unlink(missing_ok=True)
                pool = sorted([p.name for p in region_dir.glob("*.png")])
        else:
            trim_cmd = ["ssh", f"{args.remote_user}@{args.remote_host}", f"""
cd {remote_path}/{rid}
ls -1 *.png 2>/dev/null | sort > /tmp/mrms_frames.txt || true
count=$(wc -l < /tmp/mrms_frames.txt | tr -d ' ')
if [ "$count" -gt {args.keep} ]; then
  head -n $((count-{args.keep})) /tmp/mrms_frames.txt | xargs -I {{}} rm -f {{}}
fi
rm -f /tmp/mrms_frames.txt
"""]
            r = subprocess.run(trim_cmd, text=True, capture_output=True, timeout=30)
            if r.returncode != 0:
                return (rid, False, (r.stderr or r.stdout or "trim failed").strip()[:200])
            ls_cmd = ["ssh", f"{args.remote_user}@{args.remote_host}",
                      f"ls -1 {remote_path}/{rid}/*.png 2>/dev/null | xargs -I {{}} basename {{}} | sort"]
            r = subprocess.run(ls_cmd, text=True, capture_output=True, timeout=30)
            if r.returncode != 0:
                return (rid, False, (r.stderr or r.stdout or "ls failed").strip()[:200])
            pool = [n.strip() for n in r.stdout.strip().split("\n") if n.strip().endswith(".png")]

        loop_frames = slot_select_loop(pool, args.frames, args.cadence_min)
        manifest = {
            "site": "mrms",
            "region": rid,
            "product": product,
            "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "latest_frame": loop_frames[-1] if loop_frames else "",
            "frame_count": len(loop_frames),
            "frames": loop_frames,
        }
        manifest_json = json.dumps(manifest, indent=2)

        if args.local_only:
            (base_dir / rid / "manifest.json").write_text(manifest_json)
        else:
            manifest_tmp = scratch / f"{rid}_manifest.json"
            manifest_tmp.write_text(manifest_json)
            r = subprocess.run(
                ["scp", str(manifest_tmp),
                 f"{args.remote_user}@{args.remote_host}:{remote_path}/{rid}/manifest.json"],
                text=True, capture_output=True, timeout=10,
            )
            if r.returncode != 0:
                return (rid, False, (r.stderr or r.stdout or "scp manifest failed").strip()[:200])

        bounds_tmp = scratch / f"{rid}_bounds.json"
        if bounds_tmp.exists():
            if args.local_only:
                shutil.copy2(bounds_tmp, base_dir / rid / "mrms_bounds.json")
            else:
                r = subprocess.run(
                    ["scp", str(bounds_tmp),
                     f"{args.remote_user}@{args.remote_host}:{remote_path}/{rid}/mrms_bounds.json"],
                    text=True, capture_output=True, timeout=10,
                )
                if r.returncode != 0:
                    return (rid, False, (r.stderr or r.stdout or "scp bounds failed").strip()[:200])

        return (rid, True, "")
    except subprocess.TimeoutExpired:
        return (rid, False, "timeout")
    except Exception as e:
        return (rid, False, str(e))


def frame_name_to_dt(name: str):
    """Parse YYYYMMDDTHHMMSSZ.png to datetime."""
    ts = name.replace(".png", "").replace("T", "").replace("Z", "")[:14]
    return datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def slot_select_loop(pool: list[str], num_slots: int = 36, cadence_min: int = 10) -> list[str]:
    """From pool of frame names, pick best for each 10-min slot. Each file used at most once. Returns frame names (oldest first)."""
    if not pool:
        return []
    sorted_pool = sorted(pool, key=lambda n: frame_name_to_dt(n))
    latest_dt = frame_name_to_dt(sorted_pool[-1])
    slot_min = (latest_dt.minute // cadence_min) * cadence_min
    anchor = latest_dt.replace(minute=slot_min, second=0, microsecond=0)

    slots = [anchor - timedelta(minutes=i * cadence_min) for i in range(num_slots - 1, -1, -1)]
    used = set()
    result = []
    for slot_dt in slots:
        best = None
        for name in sorted_pool:
            if name in used:
                continue
            dt = frame_name_to_dt(name)
            if dt <= slot_dt:
                best = name
            else:
                break
        if best:
            used.add(best)
            result.append(best)
    return sorted(result, key=lambda n: frame_name_to_dt(n))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=36, help="Loop size (slots). Pool can be larger.")
    ap.add_argument("--cadence-min", type=int, default=10)
    ap.add_argument("--keep", type=int, default=200, help="Pool size: keep last N images per region")
    ap.add_argument("--full", action="store_true", help="Full rebuild for cold start (~20-30 min)")
    ap.add_argument("--local-only", action="store_true")
    ap.add_argument("--local-frames-dir", help="Parent dir when --local-only (e.g. out/mrms)")
    ap.add_argument("--remote-base", help="e.g. /home/scott/wx-data/served/radar_local_mrms")
    ap.add_argument("--remote-host", default="wx-i9")
    ap.add_argument("--remote-user", default="scott")
    ap.add_argument("--scratch-dir", default=None, help="Temp dir for GRIB downloads")
    ap.add_argument("--render-workers", type=int, default=3, help="Parallel workers for region render (default 3)")
    ap.add_argument("--rsync-workers", type=int, default=3, help="Parallel workers for rsync publish (default 3)")
    ap.add_argument("--post-publish-workers", type=int, default=3, help="Parallel workers for per-region post-publish (default 3)")
    args = ap.parse_args()

    if args.remote_host == "192.168.2.2":
        args.remote_host = "wx-i9"

    cfg = json.loads((CONF_DIR / "mrms_regions.json").read_text())
    product = cfg.get("product", "MergedReflectivityQCComposite_00.50")
    regions = [r for r in cfg["regions"] if "bounds" in r]
    if not regions:
        print("No regions with bounds in mrms_regions.json", file=sys.stderr)
        sys.exit(1)

    if args.local_only:
        base_dir = Path(args.local_frames_dir or str(PROJECT_ROOT / "out" / "mrms")).expanduser().resolve()
        base_dir.mkdir(parents=True, exist_ok=True)
        for r in regions:
            (base_dir / r["id"]).mkdir(parents=True, exist_ok=True)
    else:
        base_dir = None
        if not args.remote_base:
            print("--remote-base required when not --local-only", file=sys.stderr)
            sys.exit(1)
        remote_path = args.remote_base.rstrip("/")
        run(["ssh", f"{args.remote_user}@{args.remote_host}",
             "mkdir -p " + " ".join(f"{remote_path}/{r['id']}" for r in regions)], timeout=10)

    scratch = Path(args.scratch_dir or tempfile.mkdtemp(prefix="mrms_"))
    scratch.mkdir(parents=True, exist_ok=True)

    fetch_out = scratch / "fetch_mrms.json"
    remote_path = args.remote_base.rstrip("/") if not args.local_only else None
    first_region = regions[0]["id"]

    # Check pool size for cold start
    if args.local_only:
        pool_files = sorted([p.name for p in (base_dir / first_region).glob("*.png")])
    else:
        r = run(["ssh", f"{args.remote_user}@{args.remote_host}",
                 f"ls -1 {remote_path}/{first_region}/*.png 2>/dev/null | xargs -I {{}} basename {{}} | sort || true"], timeout=10)
        pool_files = [n.strip() for n in r.stdout.strip().split("\n") if n.strip().endswith(".png")]

    frame_list = []
    if len(pool_files) < 12 or args.full:
        # Cold start or full rebuild: fetch 36 slots to bootstrap
        if args.full:
            print("mrms: full rebuild, fetching 36 slots", flush=True)
        else:
            print("mrms: cold start (<12 frames), fetching 36 slots", flush=True)
        run([str(PYTHON), str(PROJECT_ROOT / "bin" / "fetch_mrms.py"),
             "--frames", str(args.frames), "--cadence-min", str(args.cadence_min),
             "--output", str(fetch_out)])
        fetch_data = json.loads(fetch_out.read_text())
        frame_list = fetch_data.get("frames", [])
    else:
        # Incremental: get newest file (no slot filter). Skip if we have it.
        run([str(PYTHON), str(PROJECT_ROOT / "bin" / "fetch_mrms.py"),
             "--newest", "--output", str(fetch_out)])
        fetch_data = json.loads(fetch_out.read_text())
        frames = fetch_data.get("frames", [])
        if frames:
            newest = frames[0]
            frame_name = f"{newest['ts_raw'][:8]}T{newest['ts_raw'][9:15]}Z.png"
            if frame_name in pool_files:
                print(f"mrms: already have {frame_name}, skip", flush=True)
                for p in scratch.iterdir():
                    if p.is_dir():
                        shutil.rmtree(p)
                    else:
                        p.unlink(missing_ok=True)
                if scratch != Path(args.scratch_dir or "").expanduser():
                    try:
                        scratch.rmdir()
                    except OSError:
                        pass
                sys.exit(0)
            else:
                frame_list = [newest]
                print(f"mrms: adding {frame_name}", flush=True)

    env = os.environ.copy()
    rendered = []

    for i, frame in enumerate(frame_list):
        url = frame["url"]
        ts_raw = frame["ts_raw"]
        frame_name = f"{ts_raw[:8]}T{ts_raw[9:15]}Z.png"
        print(f"frame {i+1}/{len(frame_list)} {frame_name}", flush=True)

        grib_path = scratch / f"{ts_raw}.grib2"
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                raw = gzip.decompress(resp.read())
            grib_path.write_bytes(raw)
        except Exception as e:
            print(f"Download failed {ts_raw}: {e}", file=sys.stderr)
            continue

        with ThreadPoolExecutor(max_workers=args.render_workers) as ex:
            futs = {
                ex.submit(_render_region, args, region, grib_path, frame_name, scratch, base_dir, i): region
                for region in regions
            }
            for fut in as_completed(futs):
                rid, ok, msg = fut.result()
                if not ok:
                    print(f"Render failed {rid}: {msg}", file=sys.stderr)
                    sys.exit(1)

        rendered.append(frame_name)
        grib_path.unlink(missing_ok=True)

    # Batch publish: 6 rsyncs instead of 216 SCPs (saves ~5-10 min of SSH overhead)
    if not args.local_only and rendered:
        with ThreadPoolExecutor(max_workers=args.rsync_workers) as ex:
            futs = {
                ex.submit(_rsync_region, r["id"], scratch / r["id"],
                          args.remote_user, args.remote_host, remote_path): r["id"]
                for r in regions
            }
            for fut in as_completed(futs):
                rid, ok, msg = fut.result()
                if not ok:
                    print(f"Rsync failed {rid}: {msg}", file=sys.stderr)
                    sys.exit(1)

    with ThreadPoolExecutor(max_workers=args.post_publish_workers) as ex:
        futs = {
            ex.submit(_post_publish_region, args, region, base_dir, scratch, remote_path, product): region["id"]
            for region in regions
        }
        for fut in as_completed(futs):
            rid, ok, msg = fut.result()
            if not ok:
                print(f"Post-publish failed {rid}: {msg}", file=sys.stderr)
                sys.exit(1)

    for p in scratch.iterdir():
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink(missing_ok=True)
    if scratch != Path(args.scratch_dir or "").expanduser():
        try:
            scratch.rmdir()
        except OSError:
            pass

    print(f"mrms updated: {len(rendered)} frames × {len(regions)} regions = {len(rendered) * len(regions)} PNGs")
    if rendered:
        print(f"latest={rendered[-1]}")
        run_id = os.environ.get("MRMS_RUN_ID", "")
        if run_id:
            latest_name = rendered[-1]
            source_ts = latest_name.replace(".png", "")
            source_dt = frame_name_to_dt(latest_name)
            publish_dt = datetime.now(timezone.utc)
            latency_sec = int((publish_dt - source_dt).total_seconds())
            print(f"MRMS_FRESHNESS|ts_utc={publish_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}|run_id={run_id}|source_ts={source_ts}|freshness_latency_sec={latency_sec}", flush=True)


if __name__ == "__main__":
    main()
