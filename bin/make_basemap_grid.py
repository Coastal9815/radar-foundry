#!/usr/bin/env python3
"""Generate basemap PNG from conf/basemap_geometry.json (and optional conf/basemap_presets.json)."""
from pathlib import Path
import argparse
import json
import sys

import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bin.basemap_geometry import load_basemap_geometry

def _project_root():
    return Path(__file__).resolve().parent.parent

def load_config(conf_dir: Path):
    cfg_path = conf_dir / "basemap_geometry.json"
    if not cfg_path.exists():
        raise FileNotFoundError(f"Missing {cfg_path}")
    return json.loads(cfg_path.read_text())

def main():
    ap = argparse.ArgumentParser(description="Generate basemap from config")
    ap.add_argument("--conf", type=Path, default=None, help="Config dir (default: conf/)")
    ap.add_argument("--out", type=Path, default=None, help="Output path (default: out/basemap_MRWcenter_{N}.png)")
    ap.add_argument("--format", choices=["png", "svg", "both"], default="both", help="Output format (default: both)")
    args = ap.parse_args()
    root = _project_root()
    conf_dir = args.conf or (root / "conf")
    cfg = load_config(conf_dir)
    out_dir = root / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    center_lat = cfg["center_lat"]
    center_lon = cfg["center_lon"]
    half_km = cfg["half_km"]
    N = cfg["N"]
    out_png = args.out or (out_dir / f"basemap_MRWcenter_{N}.png")
    out_svg = out_dir / f"basemap_MRWcenter_{N}.svg"
    half_m = half_km * 1000
    print("basemap extent: %.0f km (%.0f mi) from center" % (half_km, half_km * 0.621371))

    base = root
    src = base / "basemap" / "src"

    state_shp = list((src / "tiger2024/tl_2024_us_state").glob("*.shp"))[0]
    county_shp = list((src / "tiger2024/tl_2024_us_county").glob("*.shp"))[0]
    roads_shp = list((src / "tiger2024/tl_2024_us_primaryroads").glob("*.shp"))[0]
    coast_shp = list((src / "naturalearth/ne_10m_coastline").glob("*.shp"))[0]
    cities_shp = list((src / "naturalearth/ne_10m_populated_places").glob("*.shp"))[0]

    states = gpd.read_file(state_shp).to_crs(3857)
    counties = gpd.read_file(county_shp).to_crs(3857)
    roads = gpd.read_file(roads_shp).to_crs(3857)
    coast = gpd.read_file(coast_shp).to_crs(3857)
    cities = gpd.read_file(cities_shp).to_crs(3857)

    xmin, ymin, xmax, ymax, N = load_basemap_geometry(conf_dir)
    clip_poly = box(xmin, ymin, xmax, ymax)

    def clip(g):
        return g.clip(clip_poly)

    st = clip(states)
    co = clip(counties)
    rd = clip(roads)
    cs = clip(coast)
    ci = clip(cities)

    dpi = 200
    fig = plt.figure(figsize=(N / dpi, N / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor("black")
    fig.patch.set_facecolor("black")

    cs.plot(ax=ax, color="none", edgecolor=(0.6, 0.6, 0.6, 0.9), linewidth=0.8)
    st.boundary.plot(ax=ax, color=(0.8, 0.8, 0.8, 0.9), linewidth=1)
    co.boundary.plot(ax=ax, color=(0.35, 0.35, 0.35, 0.7), linewidth=0.5)
    interstates = rd[rd["RTTYP"] == "I"]
    others = rd[rd["RTTYP"] != "I"]
    others.plot(ax=ax, color=(0.45, 0.45, 0.45, 0.7), linewidth=0.6)
    interstates.plot(ax=ax, color=(65 / 255, 105 / 255, 225 / 255, 0.9), linewidth=1.4)
    for _, r in ci.iterrows():
        g = r.geometry
        if g is None:
            continue
        ax.text(g.x, g.y, str(r["NAME"]), fontsize=8, color="white", ha="center", va="center")
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal")
    ax.set_axis_off()

    fmt = args.format
    if fmt in ("png", "both"):
        fig.savefig(out_png, facecolor="black", bbox_inches=None, pad_inches=0, dpi=dpi)
        print("saved:", out_png)
    if fmt in ("svg", "both"):
        fig.savefig(out_svg, facecolor="black", bbox_inches=None, pad_inches=0, format="svg", dpi=dpi)
        print("saved:", out_svg)
    plt.close(fig)

if __name__ == "__main__":
    main()
