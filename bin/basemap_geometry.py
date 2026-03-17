"""Basemap geometry: Web Mercator square extent (RadarScope-style)."""
import json
from pathlib import Path
from typing import Tuple

from pyproj import Transformer


def load_basemap_geometry(conf_dir: Path) -> Tuple[float, float, float, float, int]:
    """
    Load basemap geometry. Web Mercator square centered on config lat/lon.
    Returns (xmin, ymin, xmax, ymax, N) in EPSG:3857 m.
    """
    cfg_path = conf_dir / "basemap_geometry.json"
    cfg = json.loads(cfg_path.read_text())
    center_lat = cfg["center_lat"]
    center_lon = cfg["center_lon"]
    half_km = cfg["half_km"]
    N = cfg["N"]

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    x0, y0 = transformer.transform(center_lon, center_lat)
    half_m = half_km * 1000.0
    xmin, ymin = x0 - half_m, y0 - half_m
    xmax, ymax = x0 + half_m, y0 + half_m
    return xmin, ymin, xmax, ymax, N
