#!/usr/bin/env python3
"""One-off: fetch latest MRMS, render to PNG with Mapbox-compatible bounds. Run and open test page to verify alignment."""
import gzip
import json
import os
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone

# Eastern US extent for Mapbox overlay (lon, lat)
# Order for Mapbox: SW, SE, NE, NW
EASTERN_US_BOUNDS = {
    "min_lon": -98,
    "max_lon": -75,
    "min_lat": 24,
    "max_lat": 38,
}
# Empirical: overlay was ~20 mi north vs official MRMS viewer. Shift south (~0.29 deg).
LAT_OFFSET_DEG = -0.29

def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(project_root, "out", "mrms_test")
    os.makedirs(out_dir, exist_ok=True)

    # Fetch latest from S3
    region = "CONUS"
    product = "MergedReflectivityQCComposite_00.50"
    datestring = datetime.now(timezone.utc).strftime("%Y%m%d")
    s3_prefix = f"noaa-mrms-pds/{region}/{product}/{datestring}/"

    try:
        import s3fs
        aws = s3fs.S3FileSystem(anon=True)
        files = aws.ls(s3_prefix)
        if not files:
            print("No MRMS files found for today", file=sys.stderr)
            sys.exit(1)
        latest = sorted(files)[-1]
        url = f"https://noaa-mrms-pds.s3.amazonaws.com/{latest.replace('noaa-mrms-pds/', '')}"
        # Extract timestamp from filename: MRMS_..._YYYYMMDD-HHMMSS.grib2.gz
        fname = latest.split("/")[-1]
        ts_raw = fname.replace("MRMS_MergedReflectivityQCComposite_00.50_", "").replace(".grib2.gz", "")
        timestamp_utc = f"{ts_raw[:4]}-{ts_raw[4:6]}-{ts_raw[6:8]} {ts_raw[9:11]}:{ts_raw[11:13]}:{ts_raw[13:15]} UTC"
    except Exception as e:
        print(f"S3 list failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching {url[:80]}...")
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            raw = gzip.decompress(resp.read())
    except Exception as e:
        print(f"Fetch failed: {e}", file=sys.stderr)
        sys.exit(1)

    with tempfile.NamedTemporaryFile(suffix=".grib2", delete=False) as f:
        f.write(raw)
        f.flush()
        grib_path = f.name

    try:
        import xarray as xr
        import numpy as np
        from metpy.plots import ctables
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        data = xr.load_dataarray(grib_path, engine="cfgrib")
        data = data.where(data > 0, np.nan)

        # MRMS GRIB2: 1D latitude (3500), longitude (7000). Longitude is 0-360.
        lons_raw = data.longitude.values  # 0-360
        lats_raw = data.latitude.values

        # Eastern US bounds; convert lon -180..180 to 0-360 for MRMS
        b = EASTERN_US_BOUNDS
        lon_min = b["min_lon"] if b["min_lon"] >= 0 else b["min_lon"] + 360
        lon_max = b["max_lon"] if b["max_lon"] >= 0 else b["max_lon"] + 360

        lon_idx = np.where((lons_raw >= lon_min) & (lons_raw <= lon_max))[0]
        lat_idx = np.where((lats_raw >= b["min_lat"]) & (lats_raw <= b["max_lat"]))[0]

        if len(lon_idx) == 0 or len(lat_idx) == 0:
            print("Could not crop to Eastern US - using full extent", file=sys.stderr)
            data_crop = data
            lons = np.where(lons_raw > 180, lons_raw - 360, lons_raw)
            lats = lats_raw
            extent = [float(lons.min()), float(lons.max()), float(lats.min()), float(lats.max())]
        else:
            data_crop = data.isel(longitude=lon_idx, latitude=lat_idx)
            lons = data_crop.longitude.values
            lats = data_crop.latitude.values
            lons = np.where(lons > 180, lons - 360, lons)
            extent = [float(lons.min()), float(lons.max()), float(lats.min()), float(lats.max())]

        values = data_crop.values
        lats = data_crop.latitude.values

        # MRMS GRIB2 metadata says row 0 = north, but empirical check showed our overlay
        # was shifted north vs official viewer. Flip latitude to match official orientation.
        values = np.flipud(values)
        lats = lats[::-1]  # keep values and lats aligned

        ref_norm, ref_cmap = ctables.registry.get_with_steps("NWSReflectivity", 5, 5)

        fig, ax = plt.subplots(figsize=(12, 10))
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])
        ax.set_aspect("equal")

        # pcolormesh: 1D lons (nlon), lats (nlat) with values (nlat, nlon)
        im = ax.pcolormesh(lons, lats, values, cmap=ref_cmap, norm=ref_norm, shading="auto")

        ax.axis("off")
        fig.patch.set_facecolor("none")
        ax.patch.set_facecolor("none")
        fig.savefig(
            os.path.join(out_dir, "mrms_overlay.png"),
            bbox_inches="tight",
            pad_inches=0,
            dpi=150,
            transparent=True,
        )
        plt.close(fig)

        # Apply latitude offset for Mapbox overlay alignment
        extent_adj = [extent[0], extent[1], extent[2] + LAT_OFFSET_DEG, extent[3] + LAT_OFFSET_DEG]
        # Write bounds for Mapbox (SW, SE, NE, NW)
        coords = [
            [extent_adj[0], extent_adj[2]],  # SW
            [extent_adj[1], extent_adj[2]],  # SE
            [extent_adj[1], extent_adj[3]],  # NE
            [extent_adj[0], extent_adj[3]],  # NW
        ]
        with open(os.path.join(out_dir, "mrms_bounds.json"), "w") as f:
            json.dump({"coordinates": coords, "extent": extent_adj, "timestamp_utc": timestamp_utc}, f, indent=2)

        print(f"Saved {out_dir}/mrms_overlay.png and mrms_bounds.json")
        print("Timestamp:", timestamp_utc)
        print("Extent (adjusted):", extent_adj)

    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        os.unlink(grib_path)

if __name__ == "__main__":
    main()
