#!/usr/bin/env python3
"""FlashGate IPC-1 relay for MRW lightning ingestion.

Reads NexStorm FlashGate shared memory, parses strike/heartbeat/noise records,
outputs canonical MRW strike NDJSON and health JSON.

Source: NexStorm manual Appendix C (FlashGate IPC-1).
Run on Lightning-PC (Windows) with NexStorm running.

Usage:
  python flashgate_relay.py [--config CONFIG] [--output-dir DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Windows API via ctypes
if sys.platform != "win32":
    print("Error: FlashGate relay requires Windows.", file=sys.stderr)
    sys.exit(1)

import ctypes
from ctypes import wintypes

kernel32 = ctypes.windll.kernel32  # type: ignore

# Constants
FILE_MAP_READ = 0x0004
PAGE_READONLY = 0x02
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
SEMAPHORE_MODIFY_STATE = 0x0002
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x00000102
INFINITE = 0xFFFFFFFF
ERROR_FILE_NOT_FOUND = 2
ERROR_ACCESS_DENIED = 5

# Shared memory size (string[1024])
SHMEM_SIZE = 1024

# Default config (NexStorm Appendix C)
DEFAULT_SHMEM_NAME = "NXFGIPC_SHMEM_0822931589443_238731_GATE0"
DEFAULT_READER_SEM = "Reader Semaphore"
DEFAULT_WRITER_SEM = "Writer Semaphore"
POLL_MS = 15
SENSOR_ID = "MRW"

# Timezone for NexStorm local time (America/New_York)
# Use UTC offset; EDT=-4, EST=-5. Relay uses UTC output.
try:
    import zoneinfo
    LOCAL_TZ = zoneinfo.ZoneInfo("America/New_York")
except ImportError:
    # Python < 3.9 fallback: assume EST -5
    LOCAL_TZ = timezone(timedelta(hours=-5))

# --- Windows API setup ---
kernel32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.OpenFileMappingW.restype = wintypes.HANDLE

kernel32.MapViewOfFile.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t
]
kernel32.MapViewOfFile.restype = ctypes.c_void_p

kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
kernel32.UnmapViewOfFile.restype = wintypes.BOOL

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

kernel32.OpenSemaphoreW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.OpenSemaphoreW.restype = wintypes.HANDLE

kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD

kernel32.ReleaseSemaphore.argtypes = [wintypes.HANDLE, wintypes.LONG, ctypes.POINTER(wintypes.LONG)]
kernel32.ReleaseSemaphore.restype = wintypes.BOOL

kernel32.GetLastError.restype = wintypes.DWORD


def parse_flashgate_line(line: str) -> tuple[dict | None, str | None]:
    """Parse FlashGate comma-separated line. Returns (fields_dict, error)."""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 15:
        return None, f"expected 15 fields, got {len(parts)}"
    try:
        return {
            "count": int(parts[0]),
            "year": int(parts[1]),
            "month": int(parts[2]),
            "day": int(parts[3]),
            "timestamp_secs": int(parts[4]) if parts[4] else 0,
            "trac_bearing": float(parts[5]) if parts[5] else -1,
            "trac_distance": float(parts[6]) if parts[6] else -1,
            "raw_bearing": float(parts[7]) if parts[7] else -1,
            "raw_distance": float(parts[8]) if parts[8] else -1,
            "trac_x": float(parts[9]) if parts[9] else 0,
            "trac_y": float(parts[10]) if parts[10] else 0,
            "correlated": int(parts[11]) if parts[11] else 0,
            "reserved": parts[12],
            "strike_type": int(parts[13]) if parts[13] else 0,
            "strike_polarity": int(parts[14]) if parts[14] else 0,
        }, None
    except (ValueError, IndexError) as e:
        return None, str(e)


def is_noise(f: dict) -> bool:
    """Signal is noise if any bearing or distance has value -1."""
    return (
        f.get("trac_bearing") == -1 or f.get("trac_distance") == -1
        or f.get("raw_bearing") == -1 or f.get("raw_distance") == -1
    )


def is_heartbeat(f: dict) -> bool:
    """Heartbeat: any param (except timestamp_secs, RAWbearing) = -9."""
    exclude = {"timestamp_secs", "raw_bearing"}
    for k, v in f.items():
        if k in exclude:
            continue
        if isinstance(v, (int, float)) and v == -9:
            return True
    return False


def timestamp_to_utc(f: dict) -> str:
    """Build UTC ISO 8601 from year, month, day, timestamp_secs."""
    y, m, d = f["year"], f["month"], f["day"]
    secs = f["timestamp_secs"]
    # If timestamp_secs looks like Unix epoch (> 1e9), use directly
    if secs > 1e9:
        return datetime.fromtimestamp(secs, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    # Else: seconds since midnight local
    if secs >= 86400:
        secs = secs % 86400
    dt_local = datetime(y, m, d, tzinfo=LOCAL_TZ) + timedelta(seconds=secs)
    return dt_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def make_strike_id(ts_utc: str, raw_bearing: float, raw_distance: float, sensor_id: str) -> str:
    """Deterministic strike ID for deduplication."""
    key = f"{ts_utc}|{raw_bearing}|{raw_distance}|{sensor_id}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def to_canonical_strike(f: dict, raw_line: str, ingested_at: str, sensor_id: str) -> dict:
    """Convert FlashGate fields to canonical MRW strike record."""
    ts_utc = timestamp_to_utc(f)
    raw_b = f.get("raw_bearing", -1)
    raw_d = f.get("raw_distance", -1)
    return {
        "strike_id": make_strike_id(ts_utc, raw_b, raw_d, sensor_id),
        "timestamp_utc": ts_utc,
        "sensor_id": sensor_id,
        "source": "flashgate_ipc1",
        "source_seq": f.get("count", 0),
        "raw_bearing_deg": raw_b if raw_b >= 0 else None,
        "raw_distance_km": raw_d if raw_d >= 0 else None,
        "trac_bearing_deg": f.get("trac_bearing") if f.get("trac_bearing") >= 0 else None,
        "trac_distance_km": f.get("trac_distance") if f.get("trac_distance") >= 0 else None,
        "x_raw": f.get("trac_x"),
        "y_raw": f.get("trac_y"),
        "is_correlated": bool(f.get("correlated", 0)),
        "strike_type": "CG" if f.get("strike_type", 0) == 0 else "IC",
        "polarity": "positive" if f.get("strike_polarity", 0) == 0 else "negative",
        "is_noise": is_noise(f),
        "ingested_at_utc": ingested_at,
        "raw_payload": raw_line.strip(),
    }


def to_health(
    relay_running: bool,
    heartbeat_at: str | None,
    last_msg_at: str | None,
    last_strike_at: str | None,
    total_msg: int,
    total_strike: int,
    total_noise: int,
    total_heartbeat: int,
    antenna_rot: float | None,
    last_error: str | None,
) -> dict:
    return {
        "relay_running": relay_running,
        "source_heartbeat_seen_at_utc": heartbeat_at,
        "last_message_at_utc": last_msg_at,
        "last_strike_at_utc": last_strike_at,
        "total_messages": total_msg,
        "total_strikes": total_strike,
        "total_noise": total_noise,
        "total_heartbeats": total_heartbeat,
        "antenna_rotation_deg_last": antenna_rot,
        "last_error": last_error,
    }


def run_relay(
    shmem_name: str,
    reader_sem: str,
    writer_sem: str,
    output_dir: Path,
    sensor_id: str,
    emit_noise: bool,
) -> None:
    """Main relay loop."""
    h_map = kernel32.OpenFileMappingW(FILE_MAP_READ, False, shmem_name)
    if not h_map or h_map == INVALID_HANDLE_VALUE:
        err = kernel32.GetLastError()
        raise RuntimeError(f"OpenFileMapping failed: {err}. Is NexStorm running? Shared memory: {shmem_name}")

    h_reader = kernel32.OpenSemaphoreW(SYNCHRONIZE | SEMAPHORE_MODIFY_STATE, False, reader_sem)
    h_writer = kernel32.OpenSemaphoreW(SYNCHRONIZE | SEMAPHORE_MODIFY_STATE, False, writer_sem)
    if not h_reader or h_reader == INVALID_HANDLE_VALUE:
        kernel32.CloseHandle(h_map)
        raise RuntimeError(f"OpenSemaphore Reader failed. Name: {reader_sem}")
    if not h_writer or h_writer == INVALID_HANDLE_VALUE:
        kernel32.CloseHandle(h_reader)
        kernel32.CloseHandle(h_map)
        raise RuntimeError(f"OpenSemaphore Writer failed. Name: {writer_sem}")

    ptr = kernel32.MapViewOfFile(h_map, FILE_MAP_READ, 0, 0, SHMEM_SIZE)
    if not ptr:
        kernel32.CloseHandle(h_writer)
        kernel32.CloseHandle(h_reader)
        kernel32.CloseHandle(h_map)
        raise RuntimeError("MapViewOfFile failed")

    output_dir.mkdir(parents=True, exist_ok=True)
    rt_path = output_dir / "lightning_rt.ndjson"
    status_path = output_dir / "lightning_status.json"
    noise_path = output_dir / "lightning_noise.ndjson" if emit_noise else None

    total_msg = total_strike = total_noise = total_heartbeat = 0
    last_strike_at = last_msg_at = heartbeat_at = None
    antenna_rot = None
    last_error = None

    try:
        while True:
            wait_ret = kernel32.WaitForSingleObject(h_reader, POLL_MS)
            if wait_ret == WAIT_TIMEOUT:
                # Update health on timeout
                health = to_health(
                    True, heartbeat_at, last_msg_at, last_strike_at,
                    total_msg, total_strike, total_noise, total_heartbeat,
                    antenna_rot, last_error,
                )
                status_path.write_text(json.dumps(health, indent=2), encoding="utf-8")
                continue
            if wait_ret != WAIT_OBJECT_0:
                last_error = f"WaitForSingleObject returned {wait_ret}"
                continue

            total_msg += 1
            last_msg_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            ingested_at = last_msg_at

            raw_bytes = ctypes.string_at(ptr, SHMEM_SIZE)
            raw_line = raw_bytes.decode("utf-8", errors="replace").rstrip("\x00")
            kernel32.ReleaseSemaphore(h_writer, 1, None)

            if not raw_line.strip():
                continue

            f, err = parse_flashgate_line(raw_line)
            if err:
                last_error = err
                continue

            if is_heartbeat(f):
                total_heartbeat += 1
                heartbeat_at = ingested_at
                antenna_rot = f.get("raw_bearing")
                continue

            if is_noise(f):
                total_noise += 1
                if emit_noise and noise_path:
                    rec = to_canonical_strike(f, raw_line, ingested_at, sensor_id)
                    with open(noise_path, "a", encoding="utf-8") as nf:
                        nf.write(json.dumps(rec) + "\n")
                continue

            total_strike += 1
            last_strike_at = ingested_at
            rec = to_canonical_strike(f, raw_line, ingested_at, sensor_id)
            with open(rt_path, "a", encoding="utf-8") as rf:
                rf.write(json.dumps(rec) + "\n")

            health = to_health(
                True, heartbeat_at, last_msg_at, last_strike_at,
                total_msg, total_strike, total_noise, total_heartbeat,
                antenna_rot, last_error,
            )
            status_path.write_text(json.dumps(health, indent=2), encoding="utf-8")

    except KeyboardInterrupt:
        pass
    finally:
        kernel32.UnmapViewOfFile(ptr)
        kernel32.CloseHandle(h_writer)
        kernel32.CloseHandle(h_reader)
        kernel32.CloseHandle(h_map)
        health = to_health(
            False, heartbeat_at, last_msg_at, last_strike_at,
            total_msg, total_strike, total_noise, total_heartbeat,
            antenna_rot, last_error,
        )
        status_path.write_text(json.dumps(health, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="FlashGate IPC-1 relay for MRW lightning")
    ap.add_argument("--config", help="JSON config file (optional)")
    ap.add_argument("--output-dir", default=r"C:\MRW\lightning", help="Output directory")
    ap.add_argument("--shmem", default=DEFAULT_SHMEM_NAME, help="Shared memory name")
    ap.add_argument("--reader-sem", default=DEFAULT_READER_SEM, help="Reader semaphore name")
    ap.add_argument("--writer-sem", default=DEFAULT_WRITER_SEM, help="Writer semaphore name")
    ap.add_argument("--sensor-id", default=SENSOR_ID, help="Sensor ID")
    ap.add_argument("--noise", action="store_true", help="Emit lightning_noise.ndjson")
    args = ap.parse_args()

    if args.config and Path(args.config).exists():
        cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
        output_dir = Path(cfg.get("output_dir", args.output_dir))
        shmem = cfg.get("shmem_name", args.shmem)
        reader_sem = cfg.get("reader_semaphore", args.reader_sem)
        writer_sem = cfg.get("writer_semaphore", args.writer_sem)
        sensor_id = cfg.get("sensor_id", args.sensor_id)
        emit_noise = cfg.get("emit_noise", args.noise)
    else:
        output_dir = Path(args.output_dir)
        shmem = args.shmem
        reader_sem = args.reader_sem
        writer_sem = args.writer_sem
        sensor_id = args.sensor_id
        emit_noise = args.noise

    try:
        run_relay(shmem, reader_sem, writer_sem, output_dir, sensor_id, emit_noise)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
