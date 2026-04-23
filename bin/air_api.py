#!/usr/bin/env python3
"""Air quality API: ozone (AirNow), smoke (NOAA HMS + optional HRRR Severe), saharan dust, pollen (Google).
Server-side only; keys never exposed. Single endpoint /api/air/summary."""
import json
import os
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

MRW_LAT = 31.91918481533656
MRW_LON = -81.07604504861318
PI_WX_BASE = "http://192.168.2.174"

HMS_SMOKE_SHAPEFILE_BASE = (
    "https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/Smoke_Polygons/Shapefile"
)

# HRRR MASSDEN (µg/m³) tiers for optional debug endpoint fetch_smoke_hrrr
SMOKE_LEVELS = [(5, "None"), (15, "Light"), (35, "Moderate"), (float("inf"), "Heavy")]
SMOKE_COLORS = {"None": None, "Light": "#eab308", "Moderate": "#f97316", "Heavy": "#ef4444"}
HRRR_BUCKET = "s3://noaa-hrrr-bdp-pds"

# When NOAA HMS density is Heavy, upgrade to Severe if HRRR 8 m smoke tracer exceeds this (µg/m³).
HRRR_SEVERE_WITH_HMS_HEAVY_UGM3 = 80.0

# Dashboard / site: None, Light, Moderate, Heavy, Severe (HMS gives Light/Medium/Heavy; Medium→Moderate)
SMOKE_IMPACT_COLORS = {
    "None": None,
    "Light": "#eab308",
    "Moderate": "#f97316",
    "Heavy": "#ef4444",
    "Severe": "#7f1d1d",
}

_DENSITY_ORDER = {"NONE": 0, "LIGHT": 1, "MODERATE": 2, "MEDIUM": 2, "HEAVY": 3, "THICK": 3}

# Google Pollen API: shorter cache so public site / gen_air stay fresher (was 12 h).
POLLEN_CACHE_SEC = 3 * 3600

# In-memory cache: {key: (expires_at, data)}
_cache = {}


def _point_in_ring(lon, lat, ring):
    """Ray cast; ring is list of (lon, lat)."""
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-30) + xi
        ):
            inside = not inside
        j = i
    return inside


def _shape_hits_point(shp, lon, lat):
    pts = shp.points
    parts = list(shp.parts) + [len(pts)]
    for pi in range(len(parts) - 1):
        ring = pts[parts[pi] : parts[pi + 1]]
        if len(ring) >= 3 and _point_in_ring(lon, lat, ring):
            return True
    return False


def _normalize_hms_density(raw):
    if raw is None:
        return None
    d = str(raw).strip().upper()
    if d in ("LIGHT",):
        return "Light"
    if d in ("MEDIUM", "MODERATE"):
        return "Moderate"
    if d in ("HEAVY", "THICK"):
        return "Heavy"
    return None


def _hms_density_rank(label):
    if not label:
        return 0
    return _DENSITY_ORDER.get(str(label).strip().upper(), 0)


def _level_from_hms_rank(rank):
    if rank <= 0:
        return "None"
    if rank == 1:
        return "Light"
    if rank == 2:
        return "Moderate"
    return "Heavy"


def _hms_shapefile_url(utc_date):
    y = utc_date.year
    m = utc_date.month
    d = utc_date.day
    ymd = f"{y:04d}{m:02d}{d:02d}"
    return f"{HMS_SMOKE_SHAPEFILE_BASE}/{y:04d}/{m:02d}/hms_smoke{ymd}.zip"


def fetch_smoke_hms():
    """NOAA HMS smoke polygons: analyst smoke density at MRW. Cache 20 min."""
    cached = _get_cached("smoke_hms", 20 * 60)
    if cached is not None:
        return cached

    try:
        import shapefile
    except ImportError:
        out = {
            "level": None,
            "color": None,
            "source": "NOAA HMS",
            "method": "Hazard Mapping System smoke polygons",
            "error": "pyshp not installed",
        }
        _set_cache("smoke_hms", out, 5 * 60)
        return out

    now = datetime.now(timezone.utc)
    zip_bytes = None
    used_ymd = None
    for day_back in range(7):
        day = now.date() - timedelta(days=day_back)
        url = _hms_shapefile_url(datetime(day.year, day.month, day.day, tzinfo=timezone.utc))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "radar-foundry-air-api/1"})
            with urllib.request.urlopen(req, timeout=45) as r:
                data = r.read()
        except Exception:
            continue
        if len(data) < 3000:
            continue
        zip_bytes = data
        used_ymd = f"{day.year:04d}-{day.month:02d}-{day.day:02d}"
        break

    if not zip_bytes:
        out = {
            "level": None,
            "color": None,
            "source": "NOAA HMS",
            "method": "Hazard Mapping System smoke polygons",
            "error": "No recent HMS smoke shapefile",
        }
        _set_cache("smoke_hms", out, 10 * 60)
        return out

    best_rank = 0
    best_raw = None
    best_meta = None

    try:
        with tempfile.TemporaryDirectory() as tmp:
            zpath = Path(tmp) / "hms.zip"
            zpath.write_bytes(zip_bytes)
            with zipfile.ZipFile(zpath, "r") as zf:
                zf.extractall(tmp)
            shp_files = list(Path(tmp).glob("*.shp"))
            if not shp_files:
                raise ValueError("no shp in zip")
            r = shapefile.Reader(str(shp_files[0]))
            shapes = r.shapes()
            records = r.records()
            for i, shp in enumerate(shapes):
                if not _shape_hits_point(shp, MRW_LON, MRW_LAT):
                    continue
                rec = records[i]
                dens_raw = rec[3] if len(rec) > 3 else None
                norm = _normalize_hms_density(dens_raw)
                rk = _hms_density_rank(norm or dens_raw)
                if rk > best_rank:
                    best_rank = rk
                    best_raw = dens_raw
                    sat = rec[0] if len(rec) > 0 else None
                    t0 = rec[1] if len(rec) > 1 else None
                    t1 = rec[2] if len(rec) > 2 else None
                    best_meta = {"satellite": sat, "start": t0, "end": t1}
    except Exception as e:
        out = {
            "level": None,
            "color": None,
            "source": "NOAA HMS",
            "method": "Hazard Mapping System smoke polygons",
            "error": str(e),
        }
        _set_cache("smoke_hms", out, 10 * 60)
        return out

    lvl = _level_from_hms_rank(best_rank)
    out = {
        "level": lvl,
        "color": SMOKE_IMPACT_COLORS.get(lvl),
        "source": "NOAA HMS",
        "method": "Analyst smoke polygon at station coordinates (GOES/VIIRS HMS)",
        "hms_shapefile_date": used_ymd,
        "hms_density": best_raw,
        "hms_window": best_meta,
    }
    _set_cache("smoke_hms", out, 20 * 60)
    return out


def _hrrr_tracer_ugm3_at_mrw():
    """Sample HRRR MASSDEN 8 m at MRW; cache 45 min. Returns float or None."""
    cached = _get_cached("hrrr_tracer_ugm3", 45 * 60)
    if cached is not None:
        return cached

    import subprocess
    from pathlib import Path as P

    try:
        import numpy as np
        import xarray as xr
    except ImportError:
        _set_cache("hrrr_tracer_ugm3", None, 15 * 60)
        return None

    s3_path = _hrrr_smoke_find_file()
    if not s3_path:
        _set_cache("hrrr_tracer_ugm3", None, 15 * 60)
        return None

    with tempfile.TemporaryDirectory() as tmp:
        local = P(tmp) / s3_path.split("/")[-1]
        try:
            subprocess.run(
                ["aws", "s3", "cp", s3_path, str(local), "--no-sign-request"],
                check=True,
                capture_output=True,
                timeout=300,
            )
            data = _hrrr_smoke_sample(local, s3_path)
        except Exception:
            _set_cache("hrrr_tracer_ugm3", None, 15 * 60)
            return None
        val = float(data["value_ug_m3"])
        _set_cache("hrrr_tracer_ugm3", val, 45 * 60)
        return val


def fetch_smoke_summary():
    """Public smoke line: HMS categories + Severe when HMS Heavy and HRRR tracer is very high."""
    hms = fetch_smoke_hms()
    if hms.get("error"):
        return hms

    lvl = hms.get("level") or "None"
    hrrr_ug = None
    if lvl == "Heavy":
        hrrr_ug = _hrrr_tracer_ugm3_at_mrw()
        if hrrr_ug is not None and hrrr_ug >= HRRR_SEVERE_WITH_HMS_HEAVY_UGM3:
            lvl = "Severe"

    out = dict(hms)
    out["level"] = lvl
    out["color"] = SMOKE_IMPACT_COLORS.get(lvl)
    if hrrr_ug is not None:
        out["hrrr_smoke_tracer_ugm3"] = round(hrrr_ug, 4)
    if lvl == "Severe":
        out["method"] = (
            (hms.get("method") or "")
            + f"; Severe when HMS Heavy and HRRR MASSDEN 8m ≥ {HRRR_SEVERE_WITH_HMS_HEAVY_UGM3:g} µg/m³"
        ).strip()
    return out


def _format_valid_time_for_json(v):
    """Convert cfgrib/xarray valid_time (often int64 ns since Unix epoch) to ISO 8601 UTC."""
    if v is None:
        return None
    try:
        import numpy as np

        if isinstance(v, np.ndarray):
            if v.size == 0:
                return None
            v = v.reshape(-1)[0]
        if hasattr(v, "item"):
            v = v.item()
    except Exception:
        pass
    if isinstance(v, str):
        s = v.strip()
        if s and not s.isdigit():
            return s
    try:
        sec = float(v)
        if sec > 1e15:
            sec /= 1e9
        elif sec > 1e12:
            sec /= 1e6
        if 946684800 <= sec <= 4102444800:
            return datetime.fromtimestamp(sec, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
    except (TypeError, ValueError, OSError):
        pass
    return str(v)


def _load_keys():
    """Load API keys from conf/air_api_keys.json or env vars."""
    keys = {}
    cfg_path = Path(__file__).resolve().parent.parent / "conf" / "air_api_keys.json"
    if cfg_path.exists():
        try:
            keys = json.loads(cfg_path.read_text())
        except Exception:
            pass
    keys.setdefault("airnow_api_key", os.environ.get("AIRNOW_API_KEY", ""))
    keys.setdefault("google_pollen_api_key", os.environ.get("GOOGLE_POLLEN_API_KEY", ""))
    return keys


def _get_cached(key, max_age_sec):
    now = datetime.now(timezone.utc)
    if key in _cache:
        expires, data = _cache[key]
        if now < expires:
            return data
    return None


def _set_cache(key, data, max_age_sec):
    expires = datetime.now(timezone.utc) + timedelta(seconds=max_age_sec)
    _cache[key] = (expires, data)


def _fetch_pi_wx_air():
    """Fetch PM2.5 and PM10 from pi-wx air.json.

    Prefer EPA nowcast (pm_*_nowcast_ugm3) when present — same as moonriverweather.com
    (AirQualityBox uses pm25Nowcast ?? pm25). Falls back to instantaneous *_ugm3.
    """
    try:
        url = f"{PI_WX_BASE}/data/air.json"
        req = urllib.request.Request(url, headers={"User-Agent": "radar-foundry-air-api/1"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        air = data.get("air", {})
        pm25 = air.get("pm_2p5_nowcast_ugm3")
        if pm25 is None:
            pm25 = air.get("pm_2p5_ugm3")
        pm10 = air.get("pm_10_nowcast_ugm3")
        if pm10 is None:
            pm10 = air.get("pm_10_ugm3")
        return {"pm25": pm25, "pm10": pm10}
    except Exception:
        return {"pm25": None, "pm10": None}


def fetch_ozone():
    """Fetch current ozone from AirNow. Cache 15 min."""
    cached = _get_cached("ozone", 15 * 60)
    if cached is not None:
        return cached

    keys = _load_keys()
    api_key = keys.get("airnow_api_key", "").strip()
    if not api_key:
        return {
            "value": None,
            "unit": "ppb",
            "aqi": None,
            "category": None,
            "source": "AirNow",
            "error": "API key not configured",
        }

    url = (
        f"https://www.airnowapi.org/aq/observation/latLong/current/"
        f"?format=application/json&latitude={MRW_LAT}&longitude={MRW_LON}&distance=50&API_KEY={api_key}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "radar-foundry-air-api/1"})
        with urllib.request.urlopen(req, timeout=15) as r:
            obs_list = json.loads(r.read().decode())
    except Exception as e:
        return {
            "value": None,
            "unit": "ppb",
            "aqi": None,
            "category": None,
            "source": "AirNow",
            "error": str(e),
        }

    ozone_obs = None
    for obs in obs_list if isinstance(obs_list, list) else []:
        if obs.get("ParameterName") == "O3":
            ozone_obs = obs
            break

    if not ozone_obs:
        result = {
            "value": None,
            "unit": "ppb",
            "aqi": None,
            "category": None,
            "source": "AirNow",
        }
    else:
        raw = ozone_obs.get("RawConcentration")
        unit = str(ozone_obs.get("UnitCode") or ozone_obs.get("Unit") or "").upper()
        if raw is not None:
            try:
                v = float(raw)
                if unit == "PPM" or unit in ("7", "007"):
                    raw = v * 1000
                elif not unit and 0.001 <= v <= 0.15:
                    raw = v * 1000
            except (TypeError, ValueError):
                pass
        # AirNow latLong/current often returns AQI only, not RawConcentration
        if raw is None:
            aqi_val = ozone_obs.get("AQI")
            if aqi_val is not None:
                try:
                    aqi_val = int(float(aqi_val))
                    # EPA ozone breakpoints (ppb): 0-50->0-54, 51-100->55-70, 101-150->71-85, ...
                    if aqi_val <= 50:
                        raw = round(54 * aqi_val / 50)
                    elif aqi_val <= 100:
                        raw = round(55 + 15 * (aqi_val - 50) / 50)
                    elif aqi_val <= 150:
                        raw = round(71 + 14 * (aqi_val - 100) / 50)
                    else:
                        raw = round(86 + 29 * min(aqi_val - 150, 50) / 50)  # approximate
                except (TypeError, ValueError):
                    pass
        result = {
            "value": raw,
            "unit": "ppb",
            "aqi": ozone_obs.get("AQI"),
            "category": ozone_obs.get("Category", {}).get("Name"),
            "source": "AirNow",
        }

    _set_cache("ozone", result, 15 * 60)
    return result


def _hrrr_smoke_lon_0_360(lon):
    """Convert longitude to 0–360 (HRRR convention)."""
    return lon + 360 if lon < 0 else lon


def _hrrr_smoke_find_file():
    """Try recent cycles; return s3_path or None."""
    import subprocess

    now = datetime.now(timezone.utc)
    for hour_off in range(4):
        t = now - timedelta(hours=hour_off)
        date_str = t.strftime("%Y%m%d")
        hh = t.strftime("%H")
        s3_path = f"{HRRR_BUCKET}/hrrr.{date_str}/conus/hrrr.t{hh}z.wrfsfcf00.grib2"
        r = subprocess.run(
            ["aws", "s3", "ls", s3_path, "--no-sign-request"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode == 0 and "wrfsfcf00.grib2" in (r.stdout or ""):
            return s3_path
    return None


def _hrrr_smoke_parse_valid_time(s3_path):
    """Extract valid time from s3 path: .../hrrr.YYYYMMDD/conus/hrrr.tHHz.wrfsfcf00.grib2."""
    import re

    m = re.search(r"hrrr\.(\d{8})/.*hrrr\.t(\d{2})z", s3_path)
    if m:
        date_str, hh = m.groups()
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}T{hh}:00:00"
    return ""


def _hrrr_smoke_sample(grib_path, s3_path):
    """Open GRIB2 with cfgrib, sample MASSDEN 8m at MRW. Return dict or None."""
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
    lon_t = _hrrr_smoke_lon_0_360(MRW_LON)
    dist = (lats - MRW_LAT) ** 2 + (lons - lon_t) ** 2
    j, i = np.unravel_index(np.argmin(dist), dist.shape)
    val_kg = float(ds[var].isel(y=j, x=i).values)
    val_ug = val_kg * 1e9
    ds.close()
    return {
        "value_ug_m3": val_ug,
        "grid_lat": float(lats[j, i]),
        "grid_lon": float(lons[j, i]),
        "valid_time": _hrrr_smoke_parse_valid_time(s3_path),
        "file": s3_path,
    }


def fetch_smoke_hrrr():
    """Optional: HRRR MASSDEN 8 m smoke tracer (not used for public smoke line)."""
    cached = _get_cached("smoke_hrrr", 60 * 60)
    if cached is not None:
        return cached

    import subprocess
    from pathlib import Path

    try:
        import numpy as np
        import xarray as xr
    except ImportError:
        result = {
            "level": None,
            "color": None,
            "value": None,
            "unit": "µg/m³",
            "source": "NOAA HRRR Smoke",
            "error": "Data unavailable",
        }
        _set_cache("smoke_hrrr", result, 5 * 60)  # 5 min for failures so transient issues recover
        return result

    s3_path = _hrrr_smoke_find_file()
    if not s3_path:
        result = {
            "level": None,
            "color": None,
            "value": None,
            "unit": "µg/m³",
            "source": "NOAA HRRR Smoke",
            "error": "Data unavailable",
        }
        _set_cache("smoke_hrrr", result, 5 * 60)  # 5 min for failures
        return result

    with tempfile.TemporaryDirectory() as tmp:
        fname = s3_path.split("/")[-1]
        local = Path(tmp) / fname
        try:
            subprocess.run(
                ["aws", "s3", "cp", s3_path, str(local), "--no-sign-request"],
                check=True,
                capture_output=True,
                timeout=300,
            )
            data = _hrrr_smoke_sample(local, s3_path)
        except Exception:
            result = {
                "level": None,
                "color": None,
                "value": None,
                "unit": "µg/m³",
                "source": "NOAA HRRR Smoke",
                "error": "Data unavailable",
            }
            _set_cache("smoke_hrrr", result, 5 * 60)  # 5 min for failures so transient issues recover
            return result

        val_ug = data["value_ug_m3"]
        level = "Heavy"
        for threshold, lev in SMOKE_LEVELS:
            if val_ug < threshold:
                level = lev
                break
        color = SMOKE_COLORS.get(level)

        result = {
            "level": level,
            "color": color,
            "value": round(val_ug, 4),
            "unit": "µg/m³",
            "source": "NOAA HRRR Smoke",
            "variable": "MASSDEN 8m AGL",
            "grid_lat": data["grid_lat"],
            "grid_lon": data["grid_lon"],
            "valid_time": data["valid_time"],
            "file": data["file"],
        }
        result["concentration"] = result["value"]

    _set_cache("smoke_hrrr", result, 60 * 60)
    return result


# Dust AOD (duaod550) -> categorical level and color
DUST_LEVELS = [(0.02, "None"), (0.05, "Light"), (0.10, "Moderate"), (float("inf"), "Heavy")]
DUST_COLORS = {"None": None, "Light": "#eab308", "Moderate": "#f97316", "Heavy": "#ef4444"}


def fetch_saharan_dust():
    """Saharan dust from CAMS global atmospheric composition forecasts.
    Variable: duaod550 (dust aerosol optical depth at 550 nm).
    Cache 6 hours. Requires cdsapi, cfgrib, ~/.cdsapirc."""
    cached = _get_cached("saharan_dust", 6 * 3600)
    if cached is not None:
        return cached

    import tempfile

    try:
        import cdsapi
        import xarray as xr
    except ImportError as e:
        result = {
            "level": None,
            "color": None,
            "aod": None,
            "source": "CAMS",
            "variable": "duaod550",
            "valid_time": None,
            "error": f"Dependencies: {e}",
        }
        _set_cache("saharan_dust", result, 6 * 3600)
        return result

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    # Area [north, west, south, east]. CAMS grid is 0.4°; area must be >= one grid cell.
    area = [
        round(MRW_LAT + 1.0, 1),  # north
        round(MRW_LON - 1.0, 1),   # west
        round(MRW_LAT - 1.0, 1),   # south
        round(MRW_LON + 1.0, 1),  # east
    ]

    grib_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".grib", delete=False) as f:
            grib_path = f.name
        client = cdsapi.Client()
        # Try today first; if 00Z not yet available, fall back to yesterday
        for days_back in range(2):
            try_date = (now - timedelta(days=days_back)).strftime("%Y-%m-%d")
            request = {
                "variable": ["dust_aerosol_optical_depth_550nm"],
                "date": [f"{try_date}/{try_date}"],
                "time": ["00:00"],
                "leadtime_hour": ["0"],
                "type": ["forecast"],
                "format": "grib",  # ADS uses "format" not "data_format"
                "area": area,
            }
            try:
                client.retrieve("cams-global-atmospheric-composition-forecasts", request, grib_path)
                break
            except Exception as req_err:
                if days_back == 1:
                    raise req_err
                # Today's 00Z may not be available yet; try yesterday
                continue

        import numpy as np
        import cfgrib
        # CAMS GRIB may have multiple messages; open_datasets returns iterable, take first
        datasets = list(cfgrib.open_datasets(grib_path))
        ds = datasets[0] if datasets else None
        if ds is None:
            raise ValueError("No data in CAMS GRIB file")
        dust_var = ds.get("duaod550")
        if dust_var is None:
            dust_var = list(ds.data_vars)[0]
        mean_val = np.asarray(dust_var.mean().values)
        aod_raw = mean_val.flat[0] if mean_val.size > 0 else np.nan
        aod = float(aod_raw) if np.isfinite(aod_raw) else None
        valid_time = None
        if "valid_time" in ds.coords:
            vt = ds.coords["valid_time"].values
            try:
                valid_time = _format_valid_time_for_json(
                    vt.item() if hasattr(vt, "item") and np.asarray(vt).size == 1 else vt
                )
            except (ValueError, TypeError):
                valid_time = _format_valid_time_for_json(vt)
        ds.close()
        if grib_path and os.path.exists(grib_path):
            try:
                os.unlink(grib_path)
            except Exception:
                pass

        if aod is None:
            level = "None"
        else:
            for threshold, level in DUST_LEVELS:
                if aod < threshold:
                    break

        result = {
            "level": level,
            "color": DUST_COLORS.get(level),
            "aod": round(aod, 4) if aod is not None else None,
            "source": "CAMS",
            "variable": "duaod550",
            "valid_time": valid_time,
        }
    except Exception as e:
        result = {
            "level": None,
            "color": None,
            "aod": None,
            "source": "CAMS",
            "variable": "duaod550",
            "valid_time": None,
            "error": str(e),
        }
        if grib_path and os.path.exists(grib_path):
            try:
                os.unlink(grib_path)
            except Exception:
                pass

    _set_cache("saharan_dust", result, 6 * 3600)
    return result


def _pollen_category_score(category_raw):
    """Map Google Pollen category text to 0–5 (matches UPI). Case-insensitive."""
    c = (category_raw or "").strip().lower().replace("–", "-")
    if not c or c == "none":
        return 0.0
    if "very high" in c:
        return 5.0
    if c == "high" or c.startswith("high "):
        return 4.0
    if "moderate" in c and "low" in c:
        return 2.5
    if "moderate" in c:
        return 3.0
    if "very low" in c:
        return 1.0
    if c == "low" or c.startswith("low "):
        return 2.0
    return 0.0


def _pollen_canonical_level(category_raw):
    """Display labels aligned with AirQualityBox pollenColor() expectations."""
    s = (category_raw or "").strip()
    if not s:
        return "None"
    low = s.lower()
    if "very high" in low:
        return "Very High"
    if low == "high" or low.startswith("high "):
        return "High"
    if "moderate" in low and "low" in low:
        return "Low-Moderate"
    if "moderate" in low:
        return "Moderate"
    if "very low" in low:
        return "Very Low"
    if low == "low" or low.startswith("low "):
        return "Low"
    if low == "none":
        return "None"
    return s[:1].upper() + s[1:] if s else "None"


def fetch_pollen():
    """Fetch pollen from Google Pollen API. Combined level + primary type. Cache POLLEN_CACHE_SEC.
    NAB (National Allergy Bureau) has no public API; Google Pollen used as proxy."""
    cached = _get_cached("pollen", POLLEN_CACHE_SEC)
    if cached is not None:
        return cached

    keys = _load_keys()
    api_key = keys.get("google_pollen_api_key", "").strip()
    if not api_key:
        return {
            "level": None,
            "primary": None,
            "source": "National Allergy Bureau",
            "error": "API key not configured (using Google Pollen proxy)",
        }

    url = (
        f"https://pollen.googleapis.com/v1/forecast:lookup"
        f"?key={api_key}&location.latitude={MRW_LAT}&location.longitude={MRW_LON}&days=1"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "radar-foundry-air-api/1"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
    except Exception as e:
        return {
            "level": None,
            "primary": None,
            "source": "National Allergy Bureau",
            "error": str(e),
        }

    TYPE_NAMES = {"TREE": "Tree", "GRASS": "Grass", "WEED": "Weed"}

    best_score = -1.0
    level = "None"
    primary = None

    for daily in (data.get("dailyInfo") or [])[:1]:
        for p in daily.get("pollenTypeInfo", []) or []:
            idx = p.get("indexInfo") or {}
            if not idx:
                continue
            val = idx.get("value")
            cat_raw = idx.get("category") or "None"
            cat_score = _pollen_category_score(cat_raw)
            if val is not None:
                try:
                    score = max(float(val), cat_score)
                except (TypeError, ValueError):
                    score = cat_score
            else:
                score = cat_score
            if score > best_score:
                best_score = score
                primary = TYPE_NAMES.get(p.get("code", ""), p.get("code", "Unknown"))
                level = _pollen_canonical_level(cat_raw)

    if best_score < 0:
        result = {
            "level": "None",
            "primary": None,
            "source": "National Allergy Bureau",
        }
    else:
        result = {
            "level": level,
            "primary": primary,
            "source": "National Allergy Bureau",
        }
    _set_cache("pollen", result, POLLEN_CACHE_SEC)
    return result


def fetch_summary():
    """Combined air summary: PM, ozone, smoke, saharan_dust, pollen."""
    pm = _fetch_pi_wx_air()
    ozone = fetch_ozone()
    saharan_dust = fetch_saharan_dust()
    pollen = fetch_pollen()

    pm25 = pm.get("pm25")
    pm10 = pm.get("pm10")
    if pm25 is not None:
        try:
            pm25 = float(pm25)
        except (TypeError, ValueError):
            pm25 = None
    if pm10 is not None:
        try:
            pm10 = float(pm10)
        except (TypeError, ValueError):
            pm10 = None

    smoke = fetch_smoke_summary()

    return {
        "location": {"lat": MRW_LAT, "lon": MRW_LON},
        "pm25": pm25,
        "pm10": pm10,
        "ozone": ozone,
        "smoke": smoke,
        "saharan_dust": saharan_dust,
        "pollen": pollen,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
