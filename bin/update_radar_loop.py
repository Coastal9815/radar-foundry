#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

def run(cmd, env=None):
    r = subprocess.run(cmd, text=True, capture_output=True, env=env)
    if r.returncode != 0:
        print(r.stdout, end="")
        print(r.stderr, end="", file=sys.stderr)
        raise SystemExit(r.returncode)
    return r

def iso_to_z(dt_str):
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True)
    ap.add_argument("--remote-host", default="wx-i9")
    ap.add_argument("--remote-user", default="scott")
    ap.add_argument("--remote-base", help="Required when not --local-only")
    ap.add_argument("--keep", type=int, default=72)
    ap.add_argument("--scratch-base", default=str(Path.home() / "wx-scratch" / "radar-foundry"))
    ap.add_argument("--local-only", action="store_true", help="Write frames and manifest locally, no scp/ssh")
    ap.add_argument("--local-frames-dir", help="Frames dir when --local-only (default: /Volumes/WX_SCRATCH/mrw/radar/{site})")
    ap.add_argument("--mrw-storage", help="Path to mrw_storage.json dir (optional)")
    ap.add_argument("--fetch-meta", help="Use pre-fetched meta JSON (download done by shell)")
    args = ap.parse_args()
    if args.remote_host == "192.168.2.2":
        args.remote_host = "wx-i9"

    site = args.site.upper()
    scratch_base = Path(args.scratch_base).expanduser()
    raw_dir = scratch_base / "raw_level2_live"
    raw_dir.mkdir(parents=True, exist_ok=True)

    if args.local_only:
        conf_dir = Path(args.mrw_storage or str(Path.home() / "wx" / "radar-foundry" / "conf"))
        storage_cfg = conf_dir / "mrw_storage.json"
        cfg = {}
        if storage_cfg.exists():
            cfg = json.loads(storage_cfg.read_text())
            frames_dir = Path(cfg.get("radar_frames_base", "/Volumes/WX_SCRATCH/mrw/radar")).expanduser().resolve() / site
        else:
            frames_dir = Path(args.local_frames_dir or f"/Volumes/WX_SCRATCH/mrw/radar/{site}").expanduser().resolve()
        frames_dir.mkdir(parents=True, exist_ok=True)
    elif not args.remote_base:
        raise SystemExit("--remote-base required when not --local-only")

    env = os.environ.copy()
    env["WX_SCRATCH_BASE"] = str(scratch_base)

    print(f"[{site}] stage: start", flush=True)
    if args.fetch_meta:
        print(f"[{site}] stage: using fetch-meta", flush=True)
        with open(args.fetch_meta) as f:
            meta = json.load(f)
    else:
        print(f"[{site}] stage: before fetch", flush=True)
        r = subprocess.run(
            [sys.executable, "./bin/fetch_latest_level2.py", site],
            text=True, capture_output=True, env=env, timeout=180
        )
        if r.returncode != 0:
            print(r.stdout, end="")
            print(r.stderr, end="", file=sys.stderr)
            raise SystemExit(r.returncode)
        print(f"[{site}] stage: after fetch", flush=True)
        meta = json.loads(r.stdout)
    level2_file = Path(meta["out_path"]).expanduser().resolve()
    frame_ts = iso_to_z(meta["last_modified_utc"])

    if args.local_only:
        publish_cmd = [
            sys.executable, "./bin/publish_radar_frame.py",
            str(level2_file),
            "--site", site,
            "--local-only",
            "--local-frames-dir", str(frames_dir),
        ]
    else:
        remote_dir = args.remote_base.rstrip("/")
        publish_cmd = [
            sys.executable, "./bin/publish_radar_frame.py",
            str(level2_file),
            "--site", site,
            "--remote-host", args.remote_host,
            "--remote-user", args.remote_user,
            "--remote-dir", remote_dir,
        ]
    print(f"[{site}] stage: before publish", flush=True)
    run(publish_cmd, env=env)
    print(f"[{site}] stage: after publish", flush=True)

    out_png = Path.home() / "wx" / "radar-foundry" / "out" / f"{site}_L2_nn_rgba_1600.png"
    staged = Path.home() / "wx" / "radar-foundry" / "out" / f"{site}_{frame_ts}.png"
    shutil.copy2(out_png, staged)

    if args.local_only:
        print(f"[{site}] stage: local frame copy", flush=True)
        dest_frame = frames_dir / f"{frame_ts}.png"
        shutil.copy2(staged, dest_frame)
        staged.unlink(missing_ok=True)

        print(f"[{site}] stage: local prune", flush=True)
        frames = sorted([p.name for p in frames_dir.glob("*.png") if p.name != f"{site}_L2_nn_rgba_1600.png"])
        if len(frames) > args.keep:
            for f in frames[: len(frames) - args.keep]:
                (frames_dir / f).unlink(missing_ok=True)
        frames = sorted([p.name for p in frames_dir.glob("*.png") if p.name != f"{site}_L2_nn_rgba_1600.png"])

        print(f"[{site}] stage: local manifest", flush=True)
        manifest = {
            "site": site,
            "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "latest_scan_utc": meta["last_modified_utc"],
            "latest_frame": f"{frame_ts}.png",
            "frame_count": len(frames),
            "frames": frames,
        }
        (frames_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    else:
        print(f"[{site}] stage: before scp", flush=True)
        remote_target = f"{args.remote_user}@{args.remote_host}:{remote_dir}/{frame_ts}.png"
        run(["scp", str(staged), remote_target], env=env)
        print(f"[{site}] stage: after scp", flush=True)
        staged.unlink(missing_ok=True)

        print(f"[{site}] stage: before ssh manifest", flush=True)
        ssh_target = f"{args.remote_user}@{args.remote_host}"
        remote_script = f"""
set -e
cd {remote_dir}
ls -1 *.png 2>/dev/null | sort > /tmp/mrw_frames_list.txt || true
count=$(wc -l < /tmp/mrw_frames_list.txt | tr -d ' ')
if [ "$count" -gt {args.keep} ]; then
  head -n $((count-{args.keep})) /tmp/mrw_frames_list.txt | xargs rm -f
fi
python3 - <<'EOF'
import json, os
from pathlib import Path
base = Path("{remote_dir}")
frames = sorted([p.name for p in base.glob("*.png") if p.name != "{site}_L2_nn_rgba_1600.png"])
manifest = {{
  "site": "{site}",
  "generated_utc": "{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
  "latest_scan_utc": "{meta['last_modified_utc']}",
  "latest_frame": "{frame_ts}.png",
  "frame_count": len(frames),
  "frames": frames
}}
(base / "manifest.json").write_text(json.dumps(manifest, indent=2))
EOF
rm -f /tmp/mrw_frames_list.txt
"""
        run(["ssh", ssh_target, remote_script], env=env)
        print(f"[{site}] stage: after ssh manifest", flush=True)

    print(f"updated loop: {site} latest={frame_ts}.png", flush=True)

if __name__ == "__main__":
    main()
