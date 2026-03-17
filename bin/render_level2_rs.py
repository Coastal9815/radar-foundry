#!/usr/bin/env python3
import argparse, math, subprocess
from pathlib import Path
import numpy as np
import pyart
from osgeo import gdal, osr

def mercator_xy_m(lat_deg, lon_deg):
    R = 6378137.0
    x = math.radians(lon_deg) * R
    y = math.log(math.tan(math.pi/4.0 + math.radians(lat_deg)/2.0)) * R
    return x, y

def write_geotiff(out_tif, data, bbox):
    N = data.shape[0]
    xmin, ymin, xmax, ymax = bbox
    px_w = (xmax - xmin) / N
    px_h = (ymax - ymin) / N

    gt = (xmin, px_w, 0.0, ymax, 0.0, -px_h)

    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(str(out_tif), N, N, 1, gdal.GDT_Float32,
                       options=["COMPRESS=DEFLATE","TILED=YES"])

    ds.SetGeoTransform(gt)

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(3857)
    ds.SetProjection(srs.ExportToWkt())

    band = ds.GetRasterBand(1)
    band.WriteArray(np.flipud(data).astype(np.float32))
    band.SetNoDataValue(np.nan)

    ds.FlushCache()
    ds = None

def main():

    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--N", type=int, default=1600)
    ap.add_argument("--half_km", type=float, default=300)
    ap.add_argument("--site", default="RADAR")
    args = ap.parse_args()

    radar = pyart.io.read_nexrad_archive(args.file)

    gf = pyart.filters.GateFilter(radar)
    gf.exclude_transition()
    gf.exclude_invalid("reflectivity")
    gf.exclude_outside("reflectivity", -10, 90)

    half_m = args.half_km * 1000
    N = args.N

    grid = pyart.map.grid_from_radars(
        radar,
        grid_shape=(1, N, N),
        grid_limits=((0,0),(-half_m,half_m),(-half_m,half_m)),
        fields=["reflectivity"],
        gatefilters=gf
    )

    data = grid.fields["reflectivity"]["data"][0]

    if np.ma.isMaskedArray(data):
        data = data.filled(np.nan)

    data[data < 5] = np.nan

    lat = float(radar.latitude["data"][0])
    lon = float(radar.longitude["data"][0])

    x0, y0 = mercator_xy_m(lat, lon)

    bbox = [x0-half_m, y0-half_m, x0+half_m, y0+half_m]

    base = Path.home()/"wx/radar-foundry"
    work = base/"work"
    out  = base/"out"
    conf = base/"conf"

    work.mkdir(parents=True,exist_ok=True)
    out.mkdir(parents=True,exist_ok=True)

    tif = work/f"{args.site}_level2_1600.tif"
    rgba = work/f"{args.site}_rgba.tif"
    png = out/f"{args.site}_level2_radarscope.png"

    write_geotiff(tif, data, bbox)

    subprocess.run([
        "gdaldem","color-relief","-of","GTiff","-alpha","-nearest_color_entry",
        str(tif),
        str(conf/"radarscope_dbz.txt"),
        str(rgba)
    ],check=True)

    subprocess.run([
        "gdal_translate","-of","PNG",str(rgba),str(png)
    ],check=True)

    print("saved:",png)

if __name__ == "__main__":
    main()
