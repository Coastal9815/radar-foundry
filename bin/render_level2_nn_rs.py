#!/usr/bin/env python3
import argparse, math, subprocess
from pathlib import Path
import numpy as np
import pyart
from scipy import ndimage as ndi
from osgeo import gdal, osr

def mercator_xy_m(lat_deg, lon_deg):
    R = 6378137.0
    x = math.radians(lon_deg) * R
    y = math.log(math.tan(math.pi/4.0 + math.radians(lat_deg)/2.0)) * R
    return x, y

def write_geotiff_3857(out_tif: Path, data: np.ndarray, bbox):
    N = data.shape[0]
    xmin, ymin, xmax, ymax = bbox
    px_w = (xmax - xmin) / N
    px_h = (ymax - ymin) / N
    gt = (xmin, px_w, 0.0, ymax, 0.0, -px_h)

    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(str(out_tif), N, N, 1, gdal.GDT_Float32, options=["COMPRESS=DEFLATE","TILED=YES"])
    ds.SetGeoTransform(gt)

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(3857)
    ds.SetProjection(srs.ExportToWkt())

    band = ds.GetRasterBand(1)
    band.SetNoDataValue(-9999.0)
    band.WriteArray(np.flipud(data).astype(np.float32))
    ds.FlushCache()
    ds = None

def despeckle_nan(img: np.ndarray, min_pixels: int = 10) -> np.ndarray:
    """
    Remove tiny isolated echo clusters by connected-component size.
    Keeps organized precip, removes speckle.
    """
    mask = np.isfinite(img)
    if not mask.any():
        return img

    structure = np.ones((3,3), dtype=np.uint8)  # 8-connected
    labels, n = ndi.label(mask, structure=structure)
    if n == 0:
        return img

    sizes = np.bincount(labels.ravel())
    # labels==0 is background
    remove = sizes < min_pixels
    remove[0] = False

    out = img.copy()
    out[remove[labels]] = -9999.0
    return out

def nearest_polar_to_cart(radar, field="reflectivity", sweep=0, N=1600, half_km=230.0, min_cluster_px=10):
    # Azimuth (deg) for sweep rays
    s0 = int(radar.sweep_start_ray_index["data"][sweep])
    s1 = int(radar.sweep_end_ray_index["data"][sweep]) + 1
    az = radar.azimuth["data"][s0:s1].astype(np.float32)

    # Range gates (km)
    r_km = (radar.range["data"].astype(np.float32) / 1000.0)

    # Reflectivity for sweep
    data = radar.get_field(sweep, field)
    if np.ma.isMaskedArray(data):
        data = data.filled(-9999.0)
    data = data.astype(np.float32)

    # Cartesian grid (km)
    half = float(half_km)
    xi = np.linspace(-half, half, N, dtype=np.float32)
    yi = np.linspace(-half, half, N, dtype=np.float32)
    XX, YY = np.meshgrid(xi, yi)

    RR = np.sqrt(XX**2 + YY**2)
    AA = np.arctan2(XX, YY)
    AA_deg = (np.rad2deg(AA) + 360.0) % 360.0

    # nearest azimuth ray
    az_sorted_idx = np.argsort(az)
    az_sorted = az[az_sorted_idx]
    pos = np.searchsorted(az_sorted, AA_deg, side="left")
    pos = np.clip(pos, 0, len(az_sorted)-1)
    pos2 = np.clip(pos-1, 0, len(az_sorted)-1)
    choose = np.where(np.abs(az_sorted[pos] - AA_deg) < np.abs(az_sorted[pos2] - AA_deg), pos, pos2)
    ray_idx = az_sorted_idx[choose]

    # nearest range gate
    gate_idx = np.searchsorted(r_km, RR, side="left")
    gate_idx = np.clip(gate_idx, 0, len(r_km)-1)

    img = data[ray_idx, gate_idx]

    # outside radius -> transparent
    img[RR > half] = -9999.0

    # RadarScope-like threshold
    img[img < 5.0] = -9999.0

    # Despeckle (remove clusters < min_cluster_px)
    img = despeckle_nan(img, min_pixels=min_cluster_px)

    return img

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--site", default="RADAR")
    ap.add_argument("--N", type=int, default=1600)
    ap.add_argument("--half_km", type=float, default=230.0)
    ap.add_argument("--sweep", type=int, default=0)
    ap.add_argument("--min_cluster_px", type=int, default=10)
    args = ap.parse_args()

    f = Path(args.file).expanduser().resolve()
    radar = pyart.io.read_nexrad_archive(str(f))

    img = nearest_polar_to_cart(
        radar,
        field="reflectivity",
        sweep=args.sweep,
        N=args.N,
        half_km=args.half_km,
        min_cluster_px=args.min_cluster_px
    )

    lat = float(radar.latitude["data"][0])
    lon = float(radar.longitude["data"][0])
    x0, y0 = mercator_xy_m(lat, lon)
    half_m = args.half_km * 1000.0
    bbox = [x0-half_m, y0-half_m, x0+half_m, y0+half_m]

    base = Path.home()/"wx/radar-foundry"
    work = base/"work"
    out  = base/"out"
    conf = base/"conf"
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    tif  = work/f"{args.site}_L2_nn_{args.N}.tif"
    rgba = work/f"{args.site}_L2_nn_{args.N}_rgba.tif"
    png  = out/f"{args.site}_L2_nn_radarscope_{args.N}.png"

    write_geotiff_3857(tif, img, bbox)

    subprocess.run([
        "gdaldem","color-relief","-of","GTiff","-alpha","-nearest_color_entry",
        str(tif), str(conf/"radarscope_dbz.txt"), str(rgba)
    ], check=True)

    subprocess.run(["gdal_translate","-of","PNG", str(rgba), str(png)], check=True)

    print("saved:", png)
    print("half_km:", args.half_km, "N:", args.N, "sweep:", args.sweep, "min_cluster_px:", args.min_cluster_px)

if __name__ == "__main__":
    main()
