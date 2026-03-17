#!/usr/bin/env python3
"""Step 2: Retrieve HRRR smoke GRIB2, sample at MRW location.
Downloads latest CONUS wrfsfcf00, extracts MASSDEN 8m AGL, samples nearest grid point.
Output: printed report + JSON result. No API, no classification, no dashboard integration."""
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

MRW_LAT = 31.91918481533656
MRW_LON = -81.07604504861318
BUCKET = "s3://noaa-hrrr-bdp-pds"


def _lon_0_360(lon):
    """Convert longitude to 0–360 if needed (HRRR uses 0–360)."""
    if lon < 0:
        return lon + 360
    return lon


def _find_latest_file():
    """Try recent cycles; return s3_path or None."""
    now = datetime.now(timezone.utc)
    for hour_off in range(4):
        t = now - timedelta(hours=hour_off)
        date_str = t.strftime("%Y%m%d")
        hh = t.strftime("%H")
        s3_path = f"{BUCKET}/hrrr.{date_str}/conus/hrrr.t{hh}z.wrfsfcf00.grib2"
        r = subprocess.run(
            ["aws", "s3", "ls", s3_path, "--no-sign-request"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode == 0 and "wrfsfcf00.grib2" in (r.stdout or ""):
            return s3_path
    return None


def _download(s3_path, dest_dir):
    """Download GRIB2 file; return local path."""
    fname = s3_path.split("/")[-1]
    local = Path(dest_dir) / fname
    subprocess.run(
        ["aws", "s3", "cp", s3_path, str(local), "--no-sign-request"],
        check=True,
        capture_output=True,
        timeout=300,
    )
    return local


def _parse_valid_time_from_path(s3_path):
    """Extract valid time from s3 path: .../hrrr.YYYYMMDD/conus/hrrr.tHHz.wrfsfcf00.grib2."""
    import re
    m = re.search(r"hrrr\.(\d{8})/.*hrrr\.t(\d{2})z", s3_path)
    if m:
        date_str, hh = m.groups()
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}T{hh}:00:00"
    return ""


def _sample_smoke(grib_path, s3_path=""):
    """Open GRIB2 with cfgrib, sample MASSDEN 8m at MRW. Return dict."""
    import numpy as np
    import xarray as xr

    ds = xr.open_dataset(
        str(grib_path),
        engine="cfgrib",
        decode_times=False,
        backend_kwargs={"filter_by_keys": {"typeOfLevel": "heightAboveGround", "level": 8}},
    )
    var = list(ds.data_vars)[0]
    lats = ds.latitude.values
    lons = ds.longitude.values
    lon_t = _lon_0_360(MRW_LON)
    dist = (lats - MRW_LAT) ** 2 + (lons - lon_t) ** 2
    j, i = np.unravel_index(np.argmin(dist), dist.shape)
    val_kg = float(ds[var].isel(y=j, x=i).values)
    val_ug = val_kg * 1e9
    grid_lat = float(lats[j, i])
    grid_lon = float(lons[j, i])
    valid_str = _parse_valid_time_from_path(s3_path)
    ds.close()
    return {
        "value_kg_m3": val_kg,
        "value_ug_m3": val_ug,
        "grid_lat": grid_lat,
        "grid_lon": grid_lon,
        "valid_time": valid_str,
    }


def main():
    s3_path = _find_latest_file()
    if not s3_path:
        print("ERROR: No recent HRRR wrfsfcf00 file found.", file=sys.stderr)
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp:
        local_path = _download(s3_path, tmp)
        try:
            data = _sample_smoke(local_path, s3_path)
        except Exception as e:
            print(f"ERROR: Failed to sample: {e}", file=sys.stderr)
            sys.exit(1)

    # Report
    print("=" * 60)
    print("HRRR Smoke — MRW Point Sample")
    print("=" * 60)
    print(f"Source file:     {s3_path}")
    print(f"Native value:    {data['value_kg_m3']:.6e} kg/m³")
    print(f"Converted:       {data['value_ug_m3']:.4f} µg/m³")
    print(f"Nearest grid:    lat={data['grid_lat']:.4f}, lon={data['grid_lon']:.4f}")
    print(f"Valid time:      {data['valid_time']}")
    print("=" * 60)

    # JSON result
    result = {
        "smoke": {
            "value": round(data["value_ug_m3"], 4),
            "unit": "µg/m³",
            "source": "NOAA HRRR Smoke",
            "variable": "MASSDEN 8m AGL",
            "grid_lat": data["grid_lat"],
            "grid_lon": data["grid_lon"],
            "valid_time": data["valid_time"],
            "file": s3_path,
        }
    }
    out_path = Path(__file__).resolve().parent.parent / "out" / "hrrr_smoke_sample.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nJSON saved: {out_path}")


if __name__ == "__main__":
    main()
