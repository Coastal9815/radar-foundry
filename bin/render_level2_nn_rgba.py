#!/usr/bin/env python3
"""Render NEXRAD Level II reflectivity to RGBA PNG aligned with basemap geometry."""
import argparse
import json
import sys
from pathlib import Path

# Import shared geometry (run from project root)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bin.basemap_geometry import load_basemap_geometry
import numpy as np
import pyart
from pyproj import Transformer
from pyproj import Geod
from scipy import ndimage as ndi
from PIL import Image, ImageDraw

NODATA = -9999.0


def despeckle(img: np.ndarray, min_pixels: int = 10) -> np.ndarray:
    mask = img != NODATA
    if not mask.any():
        return img
    labels, n = ndi.label(mask, structure=np.ones((3,3), dtype=np.uint8))
    if n == 0:
        return img
    sizes = np.bincount(labels.ravel())
    remove = sizes < min_pixels
    remove[0] = False
    out = img.copy()
    out[remove[labels]] = NODATA
    return out

def nearest_polar_to_basemap(radar, xmin, ymin, xmax, ymax, N, sweep=0, mask_below_dbz=5.0, min_cluster_px=10):
    """
    Sample radar reflectivity onto a grid matching basemap extent (EPSG:3857).
    Pixel (i,j) maps to (x_m, y_m) in Web Mercator; row 0 = top = north.
    """
    s0 = int(radar.sweep_start_ray_index["data"][sweep])
    s1 = int(radar.sweep_end_ray_index["data"][sweep]) + 1
    az = radar.azimuth["data"][s0:s1].astype(np.float32)
    r_km = (radar.range["data"].astype(np.float32) / 1000.0)
    r_max = float(r_km[-1])

    data = radar.get_field(sweep, "reflectivity")
    if np.ma.isMaskedArray(data):
        data = data.filled(NODATA)
    data = data.astype(np.float32)

    lat_r = float(radar.latitude["data"][0])
    lon_r = float(radar.longitude["data"][0])

    to_wgs = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    geod = Geod(ellps="WGS84")

    # Pixel centers: row 0 = top (north) = ymax
    jj = np.arange(N, dtype=np.float32)
    ii = np.arange(N, dtype=np.float32)
    x_m = xmin + (xmax - xmin) * (ii + 0.5) / N
    y_m = ymax - (ymax - ymin) * (jj + 0.5) / N  # j=0 -> ymax
    XX_m, YY_m = np.meshgrid(x_m, y_m)

    lon_flat, lat_flat = to_wgs.transform(XX_m.ravel(), YY_m.ravel())
    lon_pts = np.array(lon_flat).reshape(XX_m.shape)
    lat_pts = np.array(lat_flat).reshape(XX_m.shape)

    lon1 = np.full_like(lon_pts, lon_r)
    lat1 = np.full_like(lat_pts, lat_r)
    az12, _, dist_m = geod.inv(lon1.ravel(), lat1.ravel(), lon_pts.ravel(), lat_pts.ravel())
    az_deg = (np.array(az12).reshape(XX_m.shape) + 360.0) % 360.0
    range_km = np.array(dist_m).reshape(XX_m.shape) / 1000.0

    az_sorted_idx = np.argsort(az)
    az_sorted = az[az_sorted_idx]
    pos = np.searchsorted(az_sorted, az_deg, side="left")
    pos = np.clip(pos, 0, len(az_sorted) - 1)
    pos2 = np.clip(pos - 1, 0, len(az_sorted) - 1)
    choose = np.where(
        np.abs(az_sorted[pos] - az_deg) < np.abs(az_sorted[pos2] - az_deg), pos, pos2
    )
    ray_idx = az_sorted_idx[choose]

    gate_idx = np.searchsorted(r_km, range_km, side="left")
    gate_idx = np.clip(gate_idx, 0, len(r_km) - 1)

    img = data[ray_idx, gate_idx].copy()

    img[range_km > r_max] = NODATA
    img[(img != NODATA) & (img < mask_below_dbz)] = NODATA

    img = despeckle(img, min_pixels=min_cluster_px)
    return img


def apply_transfer_rgba(dbz: np.ndarray, conf_dir: Path) -> np.ndarray:
    """
    Apply RadarScope-style reflectivity transfer function from JSON profile.
    """
    tf_path = conf_dir / "radar_transfer_function.json"
    tf = json.loads(tf_path.read_text())

    bp = np.array(tf["breakpoints"], dtype=np.float32)
    rgba = np.array(tf["colors"], dtype=np.float32)

    out = np.zeros((dbz.shape[0], dbz.shape[1], 4), dtype=np.uint8)

    valid = dbz != NODATA
    if not valid.any():
        return out

    z = dbz.copy()
    z[~valid] = bp[0]

    for c in range(4):
        out[...,c] = np.clip(np.interp(z, bp, rgba[:,c]),0,255).astype(np.uint8)

    out[...,3][~valid] = 0
    return out
def make_grid(size=1600, spacing=100):
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 255))
    draw = ImageDraw.Draw(bg)
    grid = (90, 90, 90, 255)
    for x in range(0, size, spacing):
        draw.line([(x,0),(x,size)], fill=grid, width=1)
    for y in range(0, size, spacing):
        draw.line([(0,y),(size,y)], fill=grid, width=1)
    return bg

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--site", default="RADAR")
    ap.add_argument("--sweep", type=int, default=0)
    ap.add_argument("--mask_below_dbz", type=float, default=5.0)
    ap.add_argument("--min_cluster_px", type=int, default=10)
    project_root = Path(__file__).resolve().parent.parent
    ap.add_argument("--conf-dir", type=Path, default=None, help="Config dir (default: project conf/)")
    args = ap.parse_args()
    conf_dir = args.conf_dir or (project_root / "conf")

    f = Path(args.file).expanduser().resolve()
    radar = pyart.io.read_nexrad_archive(str(f))

    xmin, ymin, xmax, ymax, N = load_basemap_geometry(conf_dir)
    half_km = (xmax - xmin) / 2000.0  # half extent in km
    print("radar extent: %.0f km (%.0f mi) from basemap center" % (half_km, half_km * 0.621371))

    img = nearest_polar_to_basemap(
        radar,
        xmin, ymin, xmax, ymax, N,
        sweep=args.sweep,
        mask_below_dbz=args.mask_below_dbz,
        min_cluster_px=args.min_cluster_px,
    )

    rgba = apply_transfer_rgba(img, conf_dir)
    radar_png = Image.fromarray(rgba, mode="RGBA")

    base = project_root / "out"
    base.mkdir(parents=True, exist_ok=True)

    out_png = base/f"{args.site}_L2_nn_rgba_{N}.png"
    radar_png.save(out_png)

    # grid composite for transparency verification
    grid = make_grid(size=N, spacing=100)
    comp = Image.alpha_composite(grid, radar_png)
    out_grid = base/f"{args.site}_L2_nn_rgba_{N}_on_grid.png"
    comp.save(out_grid)

    print("saved:", out_png)
    print("saved:", out_grid)

if __name__ == "__main__":
    main()
