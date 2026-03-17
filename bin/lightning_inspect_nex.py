#!/usr/bin/env python3
"""Phase 1: NexStorm .nex format discovery — evidence-based, no assumptions.

Usage:
  lightning_inspect_nex.py [file]              Inspect a local .nex file
  lightning_inspect_nex.py --pull [--date YYYYMMDD]
                                            Pull from Lightning-PC (read-only)
  lightning_inspect_nex.py --pull --snapshot   Pull and save timestamped copy
  lightning_inspect_nex.py --diff FILE1 FILE2  Compare two captures; highlight appended bytes
  lightning_inspect_nex.py --diff              Diff two most recent samples for today

Discovery outputs:
  - Raw header bytes (hex + ASCII)
  - Candidate record lengths (what divides (size - header) evenly)
  - Diff of two files: common prefix, appended region, byte-level changes
  - No structured parsing until evidence supports a layout

Lightning-PC is strictly read-only. No writes, installs, or modifications.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Config
LIGHTNING_PC = "scott@192.168.2.223"
NEX_REMOTE = "C:/Program Files (x86)/Astrogenic/NexStormLite"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRATCH_DIR = PROJECT_ROOT / "scratch" / "lightning_nex"
SAMPLES_DIR = SCRATCH_DIR / "samples"

# Candidate header sizes to test (bytes)
HEADER_CANDIDATES = [0, 64, 128, 256, 384, 512, 768, 1024]

# Candidate record lengths to test (bytes)
RECORD_CANDIDATES = [16, 24, 32, 48, 64, 72, 80, 96, 128, 256]


def pull_nex(date_str: str | None = None, snapshot: bool = False) -> Path:
    """Copy .nex from Lightning-PC to local scratch. Read-only on remote."""
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    date = date_str or datetime.now().strftime("%Y%m%d")
    fname = f"{date}.nex"
    remote = f"{NEX_REMOTE}/{fname}"
    local = SCRATCH_DIR / fname
    subprocess.run(
        ["scp", "-q", f"{LIGHTNING_PC}:{remote}", str(local)],
        check=True,
        capture_output=True,
    )
    if snapshot:
        SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap_path = SAMPLES_DIR / f"{date}_{ts}.nex"
        snap_path.write_bytes(local.read_bytes())
        return snap_path
    return local


def show_header(data: bytes, max_display: int = 512) -> None:
    """Show raw header bytes: hex dump and ASCII."""
    n = min(len(data), max_display)
    print("--- Header bytes (hex + ASCII) ---")
    for i in range(0, n, 16):
        chunk = data[i : i + 16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"  {i:04x}: {hex_part:<48}  {ascii_part}")
    if len(data) > max_display:
        print(f"  ... ({len(data) - max_display} more bytes)")
    print()


def find_ascii_header_end(data: bytes) -> int:
    """Find where ASCII header ends (first long run of nulls or binary)."""
    for i in range(min(512, len(data))):
        if data[i] == 0:
            # Check if rest of block is zeros
            j = i
            while j < min(i + 64, len(data)) and data[j] == 0:
                j += 1
            if j - i >= 4:
                return i
    return 0


def candidate_record_lengths(data: bytes) -> list[tuple[int, int, int, int]]:
    """
    For various header sizes, find record lengths that divide (size - header) evenly,
    or leave a small remainder (partial last record).
    Returns [(header_size, record_len, n_records, remainder), ...]
    """
    size = len(data)
    results = []
    for hdr in HEADER_CANDIDATES:
        if hdr >= size:
            continue
        body = size - hdr
        for rec in RECORD_CANDIDATES:
            n, rem = divmod(body, rec)
            if rem == 0 and n > 0:
                results.append((hdr, rec, n, 0))
            elif 0 < rem < rec and n > 0:
                results.append((hdr, rec, n, rem))
    return sorted(results, key=lambda x: (x[2], x[1], x[0]))


def show_candidates(data: bytes) -> None:
    """Show candidate header + record length combinations."""
    print("--- Candidate structure (header + fixed records) ---")
    print("  (header_size, record_len) -> n_records [+ remainder bytes]")
    print("  Showing: exact division first, then smallest remainder (max 15).")
    print()
    candidates = candidate_record_lengths(data)
    # Prefer exact (rem=0), then smallest remainder; limit output
    exact = [(h, r, n, rem) for h, r, n, rem in candidates if rem == 0]
    partial = [(h, r, n, rem) for h, r, n, rem in candidates if rem > 0]
    partial.sort(key=lambda x: (x[3], -x[2]))  # smallest remainder, then most records
    shown = set()
    count = 0
    for hdr, rec, n, rem in exact + partial:
        if count >= 15:
            break
        key = (hdr, rec)
        if key in shown:
            continue
        shown.add(key)
        rem_str = f"  +{rem} trailing" if rem else ""
        print(f"  header={hdr:4d}  record={rec:3d}  ->  {n} records{rem_str}")
        count += 1
    print()


def diff_files(path_a: Path, path_b: Path) -> None:
    """Compare two .nex captures; highlight common prefix and appended region."""
    data_a = path_a.read_bytes()
    data_b = path_b.read_bytes()
    n_a, n_b = len(data_a), len(data_b)

    print(f"--- Diff: {path_a.name} vs {path_b.name} ---")
    print(f"  {path_a.name}: {n_a:,} bytes")
    print(f"  {path_b.name}: {n_b:,} bytes")
    print()

    # Find common prefix
    common = 0
    for i in range(min(n_a, n_b)):
        if data_a[i] != data_b[i]:
            break
        common = i + 1

    print(f"  Common prefix: {common:,} bytes (0x{common:x})")
    print()

    if common == n_a == n_b:
        print("  Files are identical.")
        return

    if common < n_a and common < n_b:
        print("  WARNING: Files differ in middle (not append-only).")
        print(f"  First difference at offset 0x{common:x} ({common})")
        # Show differing region
        show_diff_region(data_a, data_b, common, max_bytes=64)
        return

    # Append-only: A is prefix of B or vice versa
    if n_b > n_a:
        appended = n_b - n_a
        print(f"  Append-only: {path_b.name} has {appended:,} additional bytes at end.")
        print(f"  Appended region: offset 0x{n_a:x} ({n_a}) to 0x{n_b:x} ({n_b})")
        print()
        print("  --- First 64 bytes of appended region ---")
        show_hex(data_b[n_a : n_a + 64], n_a)
    elif n_a > n_b:
        appended = n_a - n_b
        print(f"  Append-only: {path_a.name} has {appended:,} additional bytes at end.")
        print(f"  Appended region: offset 0x{n_b:x} ({n_b}) to 0x{n_a:x} ({n_a})")
        print()
        print("  --- First 64 bytes of appended region ---")
        show_hex(data_a[n_b : n_b + 64], n_b)
    print()


def show_diff_region(a: bytes, b: bytes, off: int, max_bytes: int = 64) -> None:
    """Show byte-level diff at offset."""
    end = min(off + max_bytes, len(a), len(b))
    print(f"  Offset 0x{off:x}:")
    for i in range(off, end, 16):
        chunk_a = a[i : i + 16] if i < len(a) else b""
        chunk_b = b[i : i + 16] if i < len(b) else b""
        hex_a = " ".join(f"{b:02x}" for b in chunk_a)
        hex_b = " ".join(f"{b:02x}" for b in chunk_b)
        mark = " != " if chunk_a != chunk_b else "    "
        print(f"    {i:04x}: {hex_a:<48} {mark} {hex_b}")
    print()


def show_hex(data: bytes, base_offset: int = 0) -> None:
    """Hex dump with offset."""
    for i in range(0, len(data), 16):
        chunk = data[i : i + 16]
        hex_str = " ".join(f"{b:02x}" for b in chunk)
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"    {base_offset + i:04x}: {hex_str:<48}  {ascii_str}")
    print()


def inspect(path: Path) -> None:
    """Full discovery inspection of a .nex file."""
    data = path.read_bytes()
    n = len(data)

    print(f"File: {path}")
    print(f"Size: {n:,} bytes (0x{n:x})")
    print()

    # 1. Header bytes
    show_header(data)

    # 2. ASCII extent
    ascii_end = find_ascii_header_end(data)
    if ascii_end > 0:
        print(f"--- ASCII header extent ---")
        print(f"  First null at offset {ascii_end}; ASCII region: {data[:ascii_end].decode('ascii', errors='replace')!r}")
        print()

    # 3. Candidate structure
    show_candidates(data)

    # 4. Endianness hint (no assumption, just show)
    print("--- Endianness (no assumption) ---")
    print("  Multi-byte values: inspect hex to determine byte order.")
    print("  Common: little-endian (Intel/Windows), big-endian (network).")
    print()

    # 5. Timestamp / numeric format hint
    print("--- Timestamp / numeric format (no assumption) ---")
    print("  Candidates: Unix epoch, seconds-since-midnight, Windows FILETIME, BCD.")
    print("  Distance 0-300 mi, bearing 0-360°: likely int or float.")
    print("  Inspect appended bytes for patterns that increase over time.")
    print()


def get_recent_samples(date: str) -> list[Path]:
    """Return two most recent sample files for date, newest first."""
    pattern = f"{date}_*.nex"
    samples = sorted(SAMPLES_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return samples[:2]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="NexStorm .nex format discovery (read-only, no assumptions)"
    )
    ap.add_argument("--pull", action="store_true", help="scp from Lightning-PC first")
    ap.add_argument("--snapshot", action="store_true", help="with --pull: save timestamped copy to samples/")
    ap.add_argument("--date", help="YYYYMMDD for .nex file (default: today)")
    ap.add_argument("--diff", nargs="*", metavar="FILE", help="Compare two files; or no args to diff two recent samples")
    ap.add_argument("file", nargs="?", help="Local .nex path")
    args = ap.parse_args()

    if args.pull:
        path = pull_nex(args.date, args.snapshot)
        if args.snapshot:
            print(f"Pulled and saved snapshot: {path}\n")
        else:
            print(f"Pulled to {path}\n")
        inspect(path)
        return 0

    if args.diff is not None:
        if len(args.diff) == 0:
            date = args.date or datetime.now().strftime("%Y%m%d")
            samples = get_recent_samples(date)
            if len(samples) < 2:
                print(f"Need 2 samples. Run: --pull --snapshot (twice) to create samples for {date}.", file=sys.stderr)
                return 1
            path_a, path_b = samples[1], samples[0]  # older, newer
        elif len(args.diff) == 2:
            path_a, path_b = Path(args.diff[0]), Path(args.diff[1])
            if not path_a.exists():
                print(f"Error: {path_a} not found", file=sys.stderr)
                return 1
            if not path_b.exists():
                print(f"Error: {path_b} not found", file=sys.stderr)
                return 1
        else:
            print("--diff requires 0 or 2 file arguments", file=sys.stderr)
            return 1
        diff_files(path_a, path_b)
        return 0

    if args.file:
        path = Path(args.file)
    else:
        date = args.date or datetime.now().strftime("%Y%m%d")
        path = SCRATCH_DIR / f"{date}.nex"

    if not path.exists():
        print(f"Error: {path} not found. Use --pull to fetch from Lightning-PC.", file=sys.stderr)
        return 1

    inspect(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
