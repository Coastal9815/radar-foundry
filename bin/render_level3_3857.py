#!/usr/bin/env python3
"""
Render NEXRAD Level III (e.g., N0B) BIN to a georeferenced EPSG:3857 GeoTIFF + PNG.

Inputs:
  - BIN: Level III file path
Outputs:
  - GeoTIFF (EPSG:3857) in work/
  - PNG in out/

Notes:
  - Uses MetPy Level3File to decode symbology.
  - Uses nearest-azimuth sampling onto an NxN cartesian grid (km space),
    then assigns EPSG:3857 georeferencing by mapping radar center lat/lon to Web Mercator meters.
"""
import argparse, math, pathlib, sys
import numpy as np
from metpy.io import Level3File

from osgeo import gdal, osr

def mercator_xy_m(lat_deg: float, lon_deg: float):
    R = 6378137.0
    x = math.radians(lon_deg) * R
    y = math.log(math.tan(math.pi/4.0 + math.radians(lat_deg)/2.0)) * R
    return x, y

def decode_dbz_from_codes(codes: np.ndarray) -> np.ndarray:
    """
    Conservative mapping used in your history:
      0 => no data
      dBZ = (code - 2)*0.5 - 32
    """
    dbz = codes.astype(np.float32)
    dbz[dbz == 0] = np.nan
    dbz = (dbz - 2.0) * 0.5 - 32.0
    return dbz

def render_level3_bin_to_3857_tif(bin_path: pathlib.Path, out_tif: pathlib.Path, N: int = 900) -> dict:
    f = Level3File(str(bin_path))
    d = f.sym_block[0][0]
    pd = f.prod_desc

    lat = float(pd.lat) / 1000.0
    lon = float(pd.lon) / 1000.0

    gate_scale_km = float(d.get("gate_scale", 1.0))

    radials = d["data"]
    start_az = np.array(d["start_az"], dtype=np.float32)
    end_az   = np.array(d["end_az"], dtype=np.float32)

    nr = len(radials)
    ng = len(radials[0])

    codes = np.zeros((nr, ng), dtype=np.uint8)
    for i, r in enumerate(radials):
        codes[i, :] = np.frombuffer(bytes(r), dtype=np.uint8)

    dbz = decode_dbz_from_codes(codes)

    # azimuth per radial (deg 0..360)
    az = (start_az + end_az) / 2.0

    # range in km
    r_km = (np.arange(ng, dtype=np.float32) * gate_scale_km)
    maxr_km = float(r_km[-1])

    # cartesian grid in km centered on radar
    xi = np.linspace(-maxr_km, maxr_km, N, dtype=np.float32)
    yi = np.linspace(-maxr_km, maxr_km, N, dtype=np.float32)
    XX, YY = np.meshgrid(xi, yi)

    RR = np.sqrt(XX**2 + YY**2)
    AA = np.arctan2(XX, YY)  # note: matches your history
    AA_deg = (np.rad2deg(AA) + 360.0) % 360.0

    # nearest azimuth lookup
    az_sorted_idx = np.argsort(az)
    az_sorted = az[az_sorted_idx]
    pos = np.searchsorted(az_sorted, AA_deg, side="left")
    pos = np.clip(pos, 0, len(az_sorted)-1)
    pos2 = np.clip(pos-1, 0, len(az_sorted)-1)
    choose = np.where(np.abs(az_sorted[pos] - AA_deg) < np.abs(az_sorted[pos2] - AA_deg), pos, pos2)
    radial_idx = az_sorted_idx[choose]

    # gate index from range
    gate_idx = np.clip((RR / gate_scale_km).astype(np.int32), 0, ng-1)

    img = dbz[radial_idx, gate_idx]
    img[RR > maxr_km] = np.nan

    # build georeferencing in EPSG:3857 around radar center
    x0, y0 = mercator_xy_m(lat, lon)
    half_m = maxr_km * 1000.0
    xmin, xmax = x0 - half_m, x0 + half_m
    ymin, ymax = y0 - half_m, y0 + half_m

    px_w = (xmax - xmin) / N
    px_h = (ymax - ymin) / N
    gt = (xmin, px_w, 0.0, ymax, 0.0, -px_h)

    out_tif.parent.mkdir(parents=True, exist_ok=True)
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(str(out_tif), N, N, 1, gdal.GDT_Float32, options=["COMPRESS=DEFLATE","TILED=YES"])
    ds.SetGeoTransform(gt)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(3857)
    ds.SetProjection(srs.ExportToWkt())

    band = ds.GetRasterBand(1)
    band.SetNoDataValue(np.nan)
    band.WriteArray(img.astype(np.float32))
    band.FlushCache()
    ds.FlushCache()
    ds = None

    return {
        "bin": str(bin_path),
        "lat": lat,
        "lon": lon,
        "gate_scale_km": gate_scale_km,
        "nr": nr,
        "ng": ng,
        "maxr_km": maxr_km,
        "N": N,
        "bbox_3857": [xmin, ymin, xmax, ymax],
        "out_tif": str(out_tif),
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", help="Path to Level III .bin file")
    ap.add_argument("--site", default="CLX", help="Site label for output naming (default: CLX)")
    ap.add_argument("--product", default="N0B", help="Product label for output naming (default: N0B)")
    ap.add_argument("--N", type=int, default=900, help="Output grid size NxN (default: 900)")
    ap.add_argument("--out-tif", default=None, help="Override output tif path")
    ap.add_argument("--out-png", default=None, help="Override output png path")
    args = ap.parse_args()

    base = pathlib.Path.home() / "wx" / "radar-foundry"
    work = base / "work"
    out  = base / "out"

    bin_path = pathlib.Path(args.bin).expanduser().resolve()
    if not bin_path.exists():
        raise SystemExit(f"BIN not found: {bin_path}")

    tif_path = pathlib.Path(args.out_tif).expanduser() if args.out_tif else (work / f"{args.site}_{args.product}_3857.tif")
    png_path = pathlib.Path(args.out_png).expanduser() if args.out_png else (out / f"{args.site}_{args.product}_3857.png")

    meta = render_level3_bin_to_3857_tif(bin_path, tif_path, N=args.N)

    # render PNG
    png_path.parent.mkdir(parents=True, exist_ok=True)
    gdal.Translate(str(png_path), str(tif_path), format="PNG")

    meta["out_png"] = str(png_path)
    print("OK")
    for k, v in meta.items():
        print(f"{k}: {v}")

if __name__ == "__main__":
    main()
