#!/usr/bin/env python3
"""Air quality API: ozone (AirNow), smoke (HRRR), saharan dust, pollen (Google).
Server-side only; keys never exposed. Single endpoint /api/air/summary."""
import json
import os
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

MRW_LAT = 31.91918481533656
MRW_LON = -81.07604504861318
PI_WX_BASE = "http://192.168.2.174"

# Smoke concentration (µg/m³) -> level: 0 to <5=None, 5 to <15=Light, 15 to <35=Moderate, 35+=Heavy
SMOKE_LEVELS = [(5, "None"), (15, "Light"), (35, "Moderate"), (float("inf"), "Heavy")]
SMOKE_COLORS = {"None": None, "Light": "#eab308", "Moderate": "#f97316", "Heavy": "#ef4444"}
HRRR_BUCKET = "s3://noaa-hrrr-bdp-pds"

# In-memory cache: {key: (expires_at, data)}
_cache = {}


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
    """Fetch PM2.5 and PM10 from pi-wx air.json."""
    try:
        url = f"{PI_WX_BASE}/data/air.json"
        req = urllib.request.Request(url, headers={"User-Agent": "radar-foundry-air-api/1"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        air = data.get("air", {})
        return {
            "pm25": air.get("pm_2p5_ugm3"),
            "pm10": air.get("pm_10_ugm3"),
        }
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


def fetch_smoke():
    """Fetch near-surface smoke from NOAA HRRR GRIB2. Cache 60 min.
    MASSDEN 8m AGL; kg/m³ -> µg/m³ = *1e9. Classification + color."""
    cached = _get_cached("smoke", 60 * 60)
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
        _set_cache("smoke", result, 5 * 60)  # 5 min for failures so transient issues recover
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
        _set_cache("smoke", result, 5 * 60)  # 5 min for failures
        return result

    import tempfile

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
            _set_cache("smoke", result, 5 * 60)  # 5 min for failures so transient issues recover
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

    _set_cache("smoke", result, 60 * 60)
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
                valid_time = str(vt.item()) if hasattr(vt, "item") and np.asarray(vt).size == 1 else str(vt)
            except (ValueError, TypeError):
                valid_time = str(vt) if vt is not None else None
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


def fetch_pollen():
    """Fetch pollen from Google Pollen API. Combined level + primary type. Cache 12 hours.
    NAB (National Allergy Bureau) has no public API; Google Pollen used as proxy."""
    cached = _get_cached("pollen", 12 * 3600)
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

    # Map category to level; find primary (highest) pollen type
    CAT_TO_LEVEL = {
        "None": "None",
        "Very Low": "Very Low",
        "Low": "Low",
        "Low-Moderate": "Low-Moderate",
        "Moderate": "Moderate",
        "High": "High",
        "Very High": "Very High",
    }
    TYPE_NAMES = {"TREE": "Tree", "GRASS": "Grass", "WEED": "Weed"}

    level = "None"
    primary = None
    best_val = -1

    for daily in (data.get("dailyInfo") or [])[:1]:
        for p in daily.get("pollenTypeInfo", []) or []:
            idx = p.get("indexInfo", {})
            val = idx.get("value")
            cat = idx.get("category") or "None"
            if val is not None and val > best_val:
                best_val = val
                primary = TYPE_NAMES.get(p.get("code", ""), p.get("code", "Unknown"))
                level = CAT_TO_LEVEL.get(cat, cat)
            elif val is not None and best_val < 0:
                level = CAT_TO_LEVEL.get(cat, cat)

    result = {
        "level": level if best_val >= 0 else None,
        "primary": primary,
        "source": "National Allergy Bureau",
    }
    _set_cache("pollen", result, 12 * 3600)
    return result


def fetch_summary():
    """Combined air summary: PM, ozone, smoke, saharan_dust, pollen."""
    pm = _fetch_pi_wx_air()
    ozone = fetch_ozone()
    smoke = fetch_smoke()
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
