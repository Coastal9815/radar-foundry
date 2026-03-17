#!/usr/bin/env python3
"""Fetch GOES ABI frames, render IR and Visible, publish to wx-i9.
72 frames at 5-min cadence. Run every 5 min for near real-time."""
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONF_DIR = PROJECT_ROOT / "conf"
# Use invoking interpreter (e.g. .venv-wxi9 on wx-i9) or PROJECT_ROOT/.venv
_venv_python = PROJECT_ROOT / ".venv" / "bin" / "python"
PYTHON = Path(os.environ.get("PYTHON", str(_venv_python) if _venv_python.exists() else sys.executable))


def frame_name(ts_raw: str) -> str:
    """YYYYMMDD-HHMMSS -> YYYYMMDDTHHMMSSZ.png"""
    return f"{ts_raw[:8]}T{ts_raw[9:15]}Z.png"


def frame_name_to_dt(name: str):
    ts = name.replace(".png", "").replace("T", "").replace("Z", "")[:14]
    return datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def slot_select_loop(pool: list[str], num_slots: int = 72, cadence_min: int = 5) -> list[str]:
    if not pool:
        return []
    sorted_pool = sorted(pool, key=lambda n: frame_name_to_dt(n))
    if num_slots == 1:
        return [sorted_pool[-1]]  # absolute latest
    latest_dt = frame_name_to_dt(sorted_pool[-1])
    slot_min = (latest_dt.minute // cadence_min) * cadence_min
    anchor = latest_dt.replace(minute=slot_min, second=0, microsecond=0)
    slots = [anchor - timedelta(minutes=i * cadence_min) for i in range(num_slots - 1, -1, -1)]
    used = set()
    result = []
    for slot_dt in slots:
        slot_ts = slot_dt.strftime("%Y%m%d-%H%M%S")
        best = None
        for name in sorted_pool:
            if name in used:
                continue
            if frame_name_to_dt(name).strftime("%Y%m%d-%H%M%S") <= slot_ts:
                best = name
            else:
                # No frame at or before slot; use closest future frame (e.g. 15:36 for 15:35 slot)
                if best is None:
                    best = name
                break
        if best:
            used.add(best)
            result.append(best)
    return sorted(result, key=lambda n: frame_name_to_dt(n))


def run(cmd, timeout=300):
    r = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    if r.returncode != 0:
        print(r.stderr or r.stdout, file=sys.stderr)
        raise SystemExit(r.returncode)
    return r


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=72)
    ap.add_argument("--cadence-min", type=int, default=5)
    ap.add_argument("--keep", type=int, default=100)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--newest", action="store_true", help="Fetch only newest frame (quick recovery)")
    ap.add_argument("--local-only", action="store_true")
    ap.add_argument("--ir-only", action="store_true", help="Only fetch/render IR (~2 min)")
    ap.add_argument("--vis-only", action="store_true", help="Only fetch/render Visible (~7 min)")
    ap.add_argument("--remote-base", help="e.g. /home/scott/wx-data/served/radar_local_satellite")
    ap.add_argument("--remote-host", default="wx-i9")
    ap.add_argument("--remote-user", default="scott")
    ap.add_argument("--scratch-dir", default=None)
    args = ap.parse_args()

    if args.remote_host == "192.168.2.2":
        args.remote_host = "wx-i9"

    cfg = json.loads((CONF_DIR / "satellite_config.json").read_text())
    products = [p for p in cfg["products"]]
    if args.ir_only:
        products = [p for p in products if p["id"] == "ir"]
    elif args.vis_only:
        products = [p for p in products if p["id"] == "vis"]
    bucket = cfg.get("bucket", "noaa-goes19")
    channel_map = {p["id"]: p["channel"] for p in products}

    if args.local_only:
        base_dir = Path(os.environ.get("LOCAL_SATELLITE_DIR", str(PROJECT_ROOT / "out" / "satellite")))
        base_dir.mkdir(parents=True, exist_ok=True)
        remote_path = None
        for p in products:
            (base_dir / p["id"]).mkdir(parents=True, exist_ok=True)
    else:
        if not args.remote_base:
            print("--remote-base required when not --local-only", file=sys.stderr)
            sys.exit(1)
        remote_path = args.remote_base.rstrip("/")
        run(["ssh", f"{args.remote_user}@{args.remote_host}",
             "mkdir -p " + " ".join(f"{remote_path}/{p['id']}" for p in products)], timeout=10)

    scratch = Path(args.scratch_dir or tempfile.mkdtemp(prefix="goes_"))
    scratch.mkdir(parents=True, exist_ok=True)

    fetch_out = scratch / "fetch_goes.json"
    rendered = []

    def get_pool(pid):
        if args.local_only:
            return sorted([p.name for p in (base_dir / pid).glob("*.png")])
        r = run(["ssh", f"{args.remote_user}@{args.remote_host}",
                 f"ls -1 {remote_path}/{pid}/*.png 2>/dev/null | xargs -I {{}} basename {{}} | sort || true"], timeout=10)  # noqa: F821
        return [n.strip() for n in r.stdout.strip().split("\n") if n.strip().endswith(".png")]

    first_pool = get_pool(products[0]["id"])
    do_full = args.full or len(first_pool) < 12
    if args.newest:
        print("Quick: fetching newest frame per product", flush=True)
    elif do_full:
        print("Cold start: fetching 72 frames per product", flush=True)
    else:
        # Incremental: if latest pool frame is >4h old, use 12h window to fill gaps (e.g. after sleep)
        recent_min = 360  # normal: 6h window (every 5 min → ~0–2 new frames)
        if first_pool:
            latest_dt = frame_name_to_dt(first_pool[-1])
            gap_min = (datetime.now(timezone.utc) - latest_dt).total_seconds() / 60
            if gap_min > 240:
                recent_min = 720  # 12h when recovering from overnight
                print(f"Incremental: gap {gap_min:.0f} min, fetching last 12h per product", flush=True)
            else:
                print("Incremental: fetching all from last 6h per product", flush=True)
        else:
            print("Incremental: fetching all from last 6h per product", flush=True)

    for prod in products:
        pid = prod["id"]
        channel = prod["channel"]
        print(f"Product {pid} (C{channel:02d})", flush=True)

        # Fetch frames: newest = 1, full = 72 slots, incremental = all from last N min
        fetch_cmd = [str(PYTHON), str(PROJECT_ROOT / "bin" / "fetch_goes.py"),
                    "--channel", str(channel), "--bucket", bucket, "--output", str(fetch_out)]
        if args.newest:
            fetch_cmd.append("--newest")
        elif do_full and args.frames > 1:
            fetch_cmd.extend(["--frames", str(args.frames), "--cadence-min", str(args.cadence_min)])
        else:
            fetch_cmd.extend(["--recent-minutes", str(recent_min)])
        run(fetch_cmd)

        fetch_data = json.loads(fetch_out.read_text())
        frame_list = fetch_data.get("frames", [])
        if not do_full and frame_list:
            pool = get_pool(pid)
            frame_list = [f for f in frame_list if frame_name(f["ts_raw"]) not in pool]
            if not frame_list:
                print(f"  All {len(fetch_data['frames'])} frames already in pool, skip", flush=True)
                continue
        if not frame_list:
            print(f"No frames for {pid}", file=sys.stderr)
            continue

        for i, frame in enumerate(frame_list):
            ts_raw = frame["ts_raw"]
            url = frame["url"]
            fname = frame_name(ts_raw)
            nc_path = scratch / f"{pid}_{ts_raw}.nc"
            png_name = fname

            print(f"  {i+1}/{len(frame_list)} {fname}", flush=True)

            try:
                with urllib.request.urlopen(url, timeout=120) as resp:
                    nc_path.write_bytes(resp.read())
            except Exception as e:
                print(f"  Download failed: {e}", file=sys.stderr)
                continue

            if args.local_only:
                out_path = base_dir / pid / png_name
            else:
                out_path = scratch / pid / png_name
                (scratch / pid).mkdir(parents=True, exist_ok=True)

            run([str(PYTHON), str(PROJECT_ROOT / "bin" / "render_goes_frame.py"),
                 str(nc_path), "-o", str(out_path), "-c", str(channel)], timeout=360)

            rendered.append((pid, png_name))
            nc_path.unlink(missing_ok=True)

    # Publish
    if not args.local_only and rendered:
        for pid in {r[0] for r in rendered}:
            src = scratch / pid
            if src.exists():
                run(["rsync", "-az", "--timeout=120", f"{src}/",
                     f"{args.remote_user}@{args.remote_host}:{remote_path}/{pid}/"], timeout=180)

    # Post-publish: trim, slot select, manifest per product
    for prod in products:
        pid = prod["id"]
        if args.local_only:
            pool = sorted([p.name for p in (base_dir / pid).glob("*.png")])
            if len(pool) > args.keep:
                for f in pool[: len(pool) - args.keep]:
                    (base_dir / pid / f).unlink(missing_ok=True)
                pool = sorted([p.name for p in (base_dir / pid).glob("*.png")])
            manifest_path = base_dir / pid / "manifest.json"
        else:
            r = run(["ssh", f"{args.remote_user}@{args.remote_host}", f"""
cd {remote_path}/{pid}
ls -1 *.png 2>/dev/null | sort > /tmp/goes_frames.txt || true
count=$(wc -l < /tmp/goes_frames.txt | tr -d ' ')
if [ "$count" -gt {args.keep} ]; then
  head -n $((count-{args.keep})) /tmp/goes_frames.txt | xargs -I {{}} rm -f {{}}
fi
ls -1 *.png 2>/dev/null | xargs -I {{}} basename {{}} | sort
"""], timeout=30)
            pool = [n.strip() for n in r.stdout.strip().split("\n") if n.strip().endswith(".png")]
            manifest_tmp = scratch / f"{pid}_manifest.json"
            manifest_path = manifest_tmp

        loop_frames = slot_select_loop(pool, args.frames, args.cadence_min)
        manifest = {
            "product": pid,
            "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "latest_frame": loop_frames[-1] if loop_frames else "",
            "frame_count": len(loop_frames),
            "frames": loop_frames,
        }
        manifest_json = json.dumps(manifest, indent=2)

        if args.local_only:
            manifest_path.write_text(manifest_json)
        else:
            manifest_tmp.write_text(manifest_json)
            run(["scp", str(manifest_tmp),
                 f"{args.remote_user}@{args.remote_host}:{remote_path}/{pid}/manifest.json"], timeout=10)

    # Publish view config (center, zoom, bounds) for satellite player
    if not args.local_only and remote_path:
        cfg_path = CONF_DIR / "satellite_config.json"
        if cfg_path.exists():
            run(["scp", str(cfg_path),
                 f"{args.remote_user}@{args.remote_host}:{remote_path}/config.json"], timeout=10)

    # Cleanup
    for p in scratch.iterdir():
        if p.is_dir():
            import shutil
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)
    try:
        scratch.rmdir()
    except OSError:
        pass

    print(f"Satellite updated: {len(rendered)} frames")


if __name__ == "__main__":
    main()
