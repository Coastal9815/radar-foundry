#!/usr/bin/env python3
"""Render one GOES ABI L1b netCDF to PNG in Web Mercator for Mapbox.
Channel 2 = Visible (reflectance), Channel 13 = IR (brightness temperature)."""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONF_DIR = PROJECT_ROOT / "conf"


def _rad_to_bt(rad, fk1, fk2, bc1):
    """Convert ABI radiance to brightness temperature (K)."""
    import numpy as np
    return fk2 / (np.log(fk1 / np.maximum(rad, 1e-10) + 1)) - bc1


def _rad_to_refl(rad, esun, esd):
    """Convert ABI radiance to reflectance (0-1). Satpy formula: R = rad * pi * esd^2 / esun."""
    import numpy as np
    factor = np.pi * esd * esd / esun
    return rad * np.float64(factor)


def render_goes_to_png(
    nc_path: Path,
    png_path: Path,
    bounds: dict,
    channel: int,
    width_px: int = 4096,
    bounds_path: Path | None = None,
) -> dict:
    """Render GOES ABI netCDF to PNG in Web Mercator."""
    import numpy as np
    import xarray as xr
    from pyproj import CRS, Transformer
    from scipy.interpolate import griddata

    ds = xr.open_dataset(str(nc_path))

    # Geostationary projection from file
    proj = ds.goes_imager_projection
    h = float(proj.perspective_point_height)
    a = float(proj.semi_major_axis)
    b = float(proj.semi_minor_axis)
    lon0 = float(proj.longitude_of_projection_origin)
    lat0 = float(proj.latitude_of_projection_origin)

    geos = CRS.from_dict({
        "proj": "geos",
        "h": h, "a": a, "b": b,
        "lon_0": lon0, "lat_0": lat0,
        "sweep": "x",
    })
    wgs84 = CRS.from_epsg(4326)
    to_wgs = Transformer.from_crs(geos, wgs84, always_xy=True)

    # ABI x,y in radians; geos projection expects meters: x_m = x_rad * h
    x_m = ds.x.values.astype(np.float64) * h
    y_m = ds.y.values.astype(np.float64) * h
    xx, yy = np.meshgrid(x_m, y_m)
    lon_raw, lat_raw = to_wgs.transform(xx.ravel(), yy.ravel())
    lon_raw = np.array(lon_raw).reshape(xx.shape)
    lat_raw = np.array(lat_raw).reshape(yy.shape)

    rad = ds.Rad.values.astype(np.float64)
    if channel == 13:
        fk1 = float(ds.planck_fk1)
        fk2 = float(ds.planck_fk2)
        bc1 = float(ds.planck_bc1)
        data = _rad_to_bt(rad, fk1, fk2, bc1)
    else:
        esun = float(ds.esun)
        esd = float(ds.earth_sun_distance_anomaly_in_AU)
        data = _rad_to_refl(rad, esun, esd)
        data = np.clip(data, 0, 1.2)
        # sqrt brightens dark regions (Geo2Grid style) for better contrast
        data = np.sqrt(np.maximum(data, 0))

    # Output grid in Web Mercator
    min_lon = float(bounds["min_lon"])
    max_lon = float(bounds["max_lon"])
    min_lat = float(bounds["min_lat"])
    max_lat = float(bounds["max_lat"])

    to_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    xmin, ymin = to_3857.transform(min_lon, min_lat)
    xmax, ymax = to_3857.transform(max_lon, max_lat)
    w_m = xmax - xmin
    h_m = ymax - ymin
    height_px = max(1, int(width_px * h_m / w_m))

    ii = np.arange(width_px, dtype=np.float64) + 0.5
    jj = np.arange(height_px, dtype=np.float64) + 0.5
    x_m = xmin + w_m * ii / width_px
    y_m = ymax - h_m * jj / height_px
    XX_m, YY_m = np.meshgrid(x_m, y_m)
    to_4326 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    lon_pts, lat_pts = to_4326.transform(XX_m.ravel(), YY_m.ravel())
    lon_pts = np.array(lon_pts).reshape(XX_m.shape)
    lat_pts = np.array(lat_pts).reshape(XX_m.shape)

    lons = np.asarray(lon_raw)
    lats = np.asarray(lat_raw)
    lons = np.where(lons > 180, lons - 360, lons)

    from scipy.interpolate import griddata
    pts_src = np.column_stack([lons.ravel(), lats.ravel()])
    vals_src = data.ravel()
    valid = np.isfinite(vals_src)
    pts_src = pts_src[valid]
    vals_src = vals_src[valid]
    pts_dst = np.column_stack([lon_pts.ravel(), lat_pts.ravel()])
    sampled = griddata(pts_src, vals_src, pts_dst, method="nearest", fill_value=np.nan)
    sampled = sampled.reshape(lon_pts.shape)

    if channel == 13:
        # IR: apply transfer function
        tf_path = CONF_DIR / "satellite_ir_transfer.json"
        tf = json.loads(tf_path.read_text())
        bp = np.array([e["K"] for e in tf["transfer_function"]], dtype=np.float64)
        rgba_arr = np.array([e["rgba"] for e in tf["transfer_function"]], dtype=np.float64)
        out = np.zeros((height_px, width_px, 4), dtype=np.uint8)
        valid_mask = np.isfinite(sampled)
        z = np.clip(sampled, bp[0], bp[-1])
        z[~valid_mask] = bp[0]
        for c in range(4):
            out[..., c] = np.clip(np.interp(z, bp, rgba_arr[:, c]), 0, 255).astype(np.uint8)
        out[..., 3][~valid_mask] = 0
        from PIL import Image
        img = Image.fromarray(out, mode="RGBA")
        img.save(str(png_path))
    else:
        # Visible: gray RGBA. Low reflectance (dark land/ocean) -> transparent so basemap shows through (like IR).
        # Clouds (high reflectance) -> white, opaque.
        from PIL import Image
        valid_mask = np.isfinite(sampled)
        gray = np.clip(sampled, 0, 1)
        g8 = (gray * 255).astype(np.uint8)
        out = np.zeros((height_px, width_px, 4), dtype=np.uint8)
        out[..., 0] = g8
        out[..., 1] = g8
        out[..., 2] = g8
        # Alpha: transparent for land/ocean (refl < 0.25), full for clouds (refl > 0.45), ramp in between
        alpha = np.where(gray < 0.25, 0, np.where(gray > 0.45, 255, (gray - 0.25) / 0.2 * 255))
        out[..., 3] = np.where(valid_mask, np.clip(alpha, 0, 255).astype(np.uint8), 0)
        img = Image.fromarray(out, mode="RGBA")
        img.save(str(png_path))

    coords = [[min_lon, min_lat], [max_lon, min_lat], [max_lon, max_lat], [min_lon, max_lat]]
    if bounds_path:
        bounds_path.write_text(json.dumps({"coordinates": coords, "extent": [min_lon, max_lon, min_lat, max_lat]}, indent=2))
    ds.close()
    return {"coordinates": coords}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("nc_path", help="Path to GOES ABI L1b netCDF")
    ap.add_argument("--output", "-o", required=True)
    ap.add_argument("--channel", "-c", type=int, required=True, help="2=visible, 13=IR")
    ap.add_argument("--config", default=str(CONF_DIR / "satellite_config.json"))
    ap.add_argument("--bounds-json", help="Output bounds JSON path")
    ap.add_argument("--width", type=int, default=4096)
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text())
    bounds = cfg["bounds"]
    width_px = args.width or cfg.get("width_px", 4096)

    nc_path = Path(args.nc_path)
    if not nc_path.exists():
        print(f"File not found: {nc_path}", file=sys.stderr)
        sys.exit(1)

    render_goes_to_png(
        nc_path,
        Path(args.output),
        bounds,
        args.channel,
        width_px=width_px,
        bounds_path=Path(args.bounds_json) if args.bounds_json else None,
    )
    print(f"Rendered: {args.output}")


if __name__ == "__main__":
    main()
