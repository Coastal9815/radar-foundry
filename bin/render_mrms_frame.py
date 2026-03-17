#!/usr/bin/env python3
"""Render one MRMS GRIB2 file to PNG in Web Mercator for Mapbox alignment."""
import gzip
import json
import sys
from pathlib import Path


DEFAULT_WIDTH_PX = 2048


def render_grib_to_png(grib_path: Path, png_path: Path, bounds: dict, bounds_path: Path | None = None, width_px: int = DEFAULT_WIDTH_PX) -> dict:
    """
    Render GRIB2 to PNG in Web Mercator projection.
    Samples MRMS onto an EPSG:3857 grid so the output aligns with Mapbox.
    """
    import numpy as np
    import xarray as xr
    from metpy.plots import ctables
    from pyproj import Transformer
    from scipy.interpolate import RegularGridInterpolator
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = xr.load_dataarray(str(grib_path), engine="cfgrib")
    data = data.where(data > 0, np.nan)

    lons_raw = np.asarray(data.longitude.values)
    lats_raw = np.asarray(data.latitude.values)
    values_raw = np.asarray(data.values)

    # MRMS uses 0-360 lon; convert to -180..180 for interpolation
    lons = np.where(lons_raw > 180, lons_raw - 360, lons_raw)
    # GRIB row 0 = north; flip so lats descending (north first) for image row 0 = top
    if lats_raw[0] < lats_raw[-1]:
        lats_raw = lats_raw[::-1]
        values_raw = np.flipud(values_raw)
    lats = lats_raw

    b = bounds
    min_lon, max_lon = float(b["min_lon"]), float(b["max_lon"])
    min_lat, max_lat = float(b["min_lat"]), float(b["max_lat"])

    # Bounds in Web Mercator (EPSG:3857)
    to_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    to_4326 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

    xmin, ymin = to_3857.transform(min_lon, min_lat)
    xmax, ymax = to_3857.transform(max_lon, max_lat)

    # Output grid: width_px wide, height proportional to Web Mercator aspect
    w_m = xmax - xmin
    h_m = ymax - ymin
    height_px = max(1, int(width_px * h_m / w_m))

    # Pixel centers: row 0 = top (north) = ymax
    ii = np.arange(width_px, dtype=np.float64) + 0.5
    jj = np.arange(height_px, dtype=np.float64) + 0.5
    x_m = xmin + w_m * ii / width_px
    y_m = ymax - h_m * jj / height_px  # j=0 -> ymax
    XX_m, YY_m = np.meshgrid(x_m, y_m)

    lon_pts, lat_pts = to_4326.transform(XX_m.ravel(), YY_m.ravel())
    lon_pts = np.array(lon_pts).reshape(XX_m.shape)
    lat_pts = np.array(lat_pts).reshape(XX_m.shape)

    # Sample MRMS at (lon, lat) - nearest neighbor
    interp = RegularGridInterpolator(
        (lons, lats),
        values_raw.T,  # (lon, lat) for RegularGridInterpolator
        method="nearest",
        bounds_error=False,
        fill_value=np.nan,
    )
    pts = np.column_stack([lon_pts.ravel(), lat_pts.ravel()])
    sampled = interp(pts).reshape(lon_pts.shape)

    # Apply colormap
    ref_norm, ref_cmap = ctables.registry.get_with_steps("NWSReflectivity", 5, 5)
    # First 3 levels (5–20 dBZ) more transparent so light echo doesn't obscure map
    from matplotlib.colors import ListedColormap
    colors = np.array(ref_cmap.colors)
    if colors.shape[1] == 3:
        colors = np.column_stack([colors, np.ones(len(colors))])
    colors = colors.copy()
    colors[:3, 3] = 0.25
    ref_cmap = ListedColormap(colors)
    fig, ax = plt.subplots(figsize=(width_px / 150, height_px / 150), dpi=150)
    ax.imshow(sampled, extent=[0, width_px, height_px, 0], cmap=ref_cmap, norm=ref_norm, interpolation="nearest")
    ax.axis("off")
    fig.patch.set_facecolor("none")
    ax.patch.set_facecolor("none")
    fig.savefig(str(png_path), bbox_inches="tight", pad_inches=0, dpi=150, transparent=True)
    plt.close(fig)

    # Mapbox corners in lon/lat: [SW, SE, NE, NW] - no offset needed (Web Mercator)
    coords = [
        [min_lon, min_lat],
        [max_lon, min_lat],
        [max_lon, max_lat],
        [min_lon, max_lat],
    ]
    extent_adj = [min_lon, max_lon, min_lat, max_lat]

    if bounds_path:
        bounds_path.write_text(json.dumps({"coordinates": coords, "extent": extent_adj}, indent=2))

    return {"extent_adj": extent_adj, "coordinates": coords}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("grib_path", help="Path to .grib2 or .grib2.gz file")
    ap.add_argument("--output", "-o", required=True, help="Output PNG path")
    ap.add_argument("--region", "-r", required=True, help="Region id from mrms_regions.json")
    ap.add_argument("--bounds-json", help="Output mrms_bounds.json path")
    args = ap.parse_args()

    conf_path = Path(__file__).resolve().parent.parent / "conf" / "mrms_regions.json"
    cfg = json.loads(conf_path.read_text())
    region = next((r for r in cfg["regions"] if r["id"] == args.region), None)
    if not region or "bounds" not in region:
        raise SystemExit(f"Region {args.region!r} not found or has no bounds in {conf_path}")
    bounds = region["bounds"]
    width_px = int(region.get("width_px", DEFAULT_WIDTH_PX))

    grib_path = Path(args.grib_path)
    if not grib_path.exists():
        print(f"File not found: {grib_path}", file=sys.stderr)
        sys.exit(1)

    raw = grib_path.read_bytes()
    if grib_path.suffix == ".gz" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)

    tmp = grib_path.with_suffix(".grib2") if ".gz" in grib_path.name else grib_path
    if tmp == grib_path:
        tmp = Path(str(grib_path) + ".tmp")
    tmp.write_bytes(raw)

    try:
        render_grib_to_png(
            tmp,
            Path(args.output),
            bounds,
            Path(args.bounds_json) if args.bounds_json else None,
            width_px=width_px,
        )
    finally:
        if tmp != grib_path and tmp.exists():
            tmp.unlink(missing_ok=True)

    print(f"Rendered: {args.output}")


if __name__ == "__main__":
    main()
