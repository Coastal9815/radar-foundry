#!/usr/bin/env python3
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

def run(cmd, timeout=120):
    r = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    if r.returncode != 0:
        print(r.stdout, end="")
        print(r.stderr, end="", file=sys.stderr)
        raise SystemExit(r.returncode)
    return r

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("level2_file")
    ap.add_argument("--site", required=True)
    ap.add_argument("--remote-host", default="wx-i9")
    ap.add_argument("--remote-user", default="scott")
    ap.add_argument("--remote-dir", help="Required when not --local-only")
    ap.add_argument("--local-only", action="store_true", help="Write base PNG locally, no scp")
    ap.add_argument("--local-frames-dir", help="Required when --local-only")
    args = ap.parse_args()
    if args.remote_host == "192.168.2.2":
        args.remote_host = "wx-i9"

    if args.local_only:
        if not args.local_frames_dir:
            raise SystemExit("--local-frames-dir required when --local-only")
    elif not args.remote_dir:
        raise SystemExit("--remote-dir required when not --local-only")

    project_root = Path(__file__).resolve().parent.parent
    level2 = str(Path(args.level2_file).expanduser().resolve())
    out_base = project_root / "out"
    png_name = f"{args.site}_L2_nn_rgba_1600.png"
    local_png = out_base / png_name
    conf_dir = project_root / "conf"

    run([sys.executable, "./bin/render_level2_nn_rgba.py", level2, "--site", args.site, "--conf-dir", str(conf_dir)])

    if not local_png.exists():
        raise SystemExit(f"Expected rendered PNG not found: {local_png}")

    if args.local_only:
        frames_dir = Path(args.local_frames_dir).expanduser().resolve()
        frames_dir.mkdir(parents=True, exist_ok=True)
        dest = frames_dir / png_name
        shutil.copy2(local_png, dest)
        print(f"published: {local_png} -> {dest}")
    else:
        remote = f"{args.remote_user}@{args.remote_host}:{args.remote_dir.rstrip('/')}/"
        run(["scp", str(local_png), remote])
        print(f"published: {local_png} -> {remote}")

if __name__ == "__main__":
    main()
