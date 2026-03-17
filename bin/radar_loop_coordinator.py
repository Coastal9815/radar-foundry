#!/usr/bin/env python3
"""Coordinator for radar pipeline. Runs multiple sites with controlled concurrency.
Config-driven via conf/radar_sites.json. Replaces separate KCLX/KJAX launchd jobs."""
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONF_DIR = PROJECT_ROOT / "conf"
SITES_CONFIG = CONF_DIR / "radar_sites.json"
LOG_DIR = Path("/tmp")
SCRATCH_BASE = PROJECT_ROOT / "scratch"
PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"


def log(site: str, msg: str):
    ts = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{site}] {msg}"
    print(line, flush=True)
    log_path = LOG_DIR / "radar_coordinator.log"
    try:
        with open(log_path, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def run_site(site: str, timeout_sec: int, remote_base: str | None, remote_config: dict, run_id: str) -> tuple[str, bool, str]:
    """Run full pipeline for one site. Returns (site, success, message)."""
    env = os.environ.copy()
    env["HOME"] = str(Path.home())
    env["WX_SCRATCH_BASE"] = str(SCRATCH_BASE)
    meta_path = LOG_DIR / f"fetch_meta_{site}.json"

    try:
        # 1. Fetch meta
        log(site, "fetch meta")
        r = subprocess.run(
            [str(PYTHON), str(PROJECT_ROOT / "bin" / "fetch_latest_level2.py"), "--list-only", site],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if r.returncode != 0:
            log(site, f"fetch failed: {r.stderr[:200]}")
            return (site, False, "fetch failed")
        meta = json.loads(r.stdout)
        meta_path.write_text(r.stdout)

        # 2. Download
        url = meta["url"]
        out_path = Path(meta["out_path"]).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        log(site, "curl download")
        r = subprocess.run(
            ["curl", "-sSf", "-o", str(out_path), "--max-time", "180", url],
            capture_output=True,
            text=True,
            timeout=200,
        )
        if r.returncode != 0:
            log(site, f"curl failed: {r.stderr[:200]}")
            return (site, False, "download failed")

        # 3. Update loop (render + publish)
        log(site, "publish")
        source_ts = meta.get("last_modified_utc", "")
        update_start = time.time()
        update_args = [str(PYTHON), str(PROJECT_ROOT / "bin" / "update_radar_loop.py"),
                      "--site", site, "--fetch-meta", str(meta_path)]
        if remote_base:
            update_args.extend(["--remote-base", f"{remote_base}/radar_local_{site}/frames"])
            if remote_config.get("remote_host"):
                update_args.extend(["--remote-host", remote_config["remote_host"]])
            if remote_config.get("remote_user"):
                update_args.extend(["--remote-user", remote_config["remote_user"]])
        else:
            update_args.append("--local-only")
        r = subprocess.run(
            update_args,
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        duration_sec = int(time.time() - update_start)
        publish_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if r.returncode != 0:
            log(site, f"publish failed: {r.stderr[:200]}")
            if run_id:
                print(f"RADAR_SITE_TIMING|ts_utc={publish_utc}|run_id={run_id}|site={site}|source_ts={source_ts}|duration_sec={duration_sec}|freshness_latency_sec=|exit_code={r.returncode}|success=fail", flush=True)
            return (site, False, "publish failed")
        # Parse last line for latest frame
        for line in reversed(r.stdout.strip().split("\n")):
            if "latest=" in line:
                log(site, line.strip())
                break
        freshness_sec = ""
        if source_ts:
            try:
                src_dt = datetime.fromisoformat(source_ts.replace("Z", "+00:00"))
                if src_dt.tzinfo is None:
                    src_dt = src_dt.replace(tzinfo=timezone.utc)
                freshness_sec = str(int((datetime.now(timezone.utc) - src_dt).total_seconds()))
            except (ValueError, TypeError):
                pass
        if run_id:
            print(f"RADAR_SITE_TIMING|ts_utc={publish_utc}|run_id={run_id}|site={site}|source_ts={source_ts}|duration_sec={duration_sec}|freshness_latency_sec={freshness_sec}|exit_code=0|success=ok", flush=True)
        return (site, True, "ok")
    except subprocess.TimeoutExpired:
        log(site, "timeout")
        return (site, False, "timeout")
    except Exception as e:
        log(site, f"error: {e}")
        return (site, False, str(e))


def main():
    if os.uname().nodename != "wx-core":
        return 0

    if not SITES_CONFIG.exists():
        log("coord", f"config not found: {SITES_CONFIG}")
        return 1

    cfg = json.loads(SITES_CONFIG.read_text())
    sites = cfg.get("sites", ["KCLX", "KJAX"])
    max_concurrent = int(cfg.get("max_concurrent", 2))
    timeout_sec = int(cfg.get("site_timeout_sec", cfg.get("timeout_sec", 180)))
    stagger_sec = int(cfg.get("stagger_sec", 5))
    remote_base = cfg.get("remote_base")  # When set, publish to wx-i9 instead of local
    remote_config = {k: cfg[k] for k in ("remote_host", "remote_user") if k in cfg}

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    coord_start = time.time()
    log("coord", f"start sites={sites} max_concurrent={max_concurrent} timeout={timeout_sec}s remote={bool(remote_base)}")
    results = []
    with ThreadPoolExecutor(max_workers=max_concurrent) as ex:
        futs = {}
        for i, site in enumerate(sites):
            if i > 0:
                time.sleep(stagger_sec)
            futs[ex.submit(run_site, site, timeout_sec, remote_base, remote_config, run_id)] = site
        for fut in as_completed(futs):
            site, ok, msg = fut.result()
            results.append((site, ok))
            log("coord", f"{site} {'ok' if ok else 'FAIL'}: {msg}")

    failed = [s for s, ok in results if not ok]
    duration_sec = int(time.time() - coord_start)
    ts_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log("coord", f"done ok={len(results)-len(failed)} failed={len(failed)} {failed or ''}")
    print(f"COORD_TIMING|ts_utc={ts_utc}|run_id={run_id}|duration_sec={duration_sec}|ok={len(results)-len(failed)}|failed={len(failed)}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
