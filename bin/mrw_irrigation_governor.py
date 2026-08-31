#!/usr/bin/env python3
"""MRW local irrigation governor — Rachio's weather brain, powered by pi-wx.

Evaluates yard conditions (rain, wind, freeze, NWS) and drives:
  - input_boolean.mrw_watering_veto
  - input_text.mrw_watering_reason
  - sensor.mrw_rain_* / temp / hold flags
  - optional Rachio rain-delay switch via HA service call

Credentials: ~/.mrw/homeassistant.env (HA_URL, HA_TOKEN)
Config: ~/.mrw/irrigation.json (thresholds + optional Rachio entity)

Smart-home owns notify/UI; weather owns when to veto watering.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

MRW_DIR = Path.home() / ".mrw"
HA_ENV = MRW_DIR / "homeassistant.env"
CONFIG_PATH = MRW_DIR / "irrigation.json"
STATE_PATH = MRW_DIR / "irrigation_governor_state.json"
PI_WX_BASE = os.environ.get("PI_WX_BASE", "http://192.168.2.174/data")
NWS_ZONE_ALERTS = "https://api.weather.gov/alerts/active?zone=GAZ119"
NWS_SKIDAWAY_LAT = 31.919
NWS_SKIDAWAY_LON = -81.076
NWS_SKIDAWAY_FORECAST_FALLBACK = (
    "https://api.weather.gov/gridpoints/CHS/48,34/forecast"
)
LOCAL_TZ = ZoneInfo("America/New_York")
USER_AGENT = "MRW-Irrigation-Governor/1.0 (moonriverweather.com)"

DEFAULT_CONFIG = {
    "enabled": True,
    "rain_rate_inhr": 0.02,
    "rain_60m_in": 0.1,
    "rain_24h_in": 0.5,
    "rain_yesterday_in": 0.5,
    "rain_today_skip_next_in": 2.0,
    "freeze_temp_f": 32,
    "wind_gust_mph": 20,
    "wind_gust_clear_mph": 17,
    "rain_soak_hours": 12,
    "rachio_auto_delay": False,
    "rachio_rain_delay_entity": "",
    "rachio_delay_hours": 24,
    "nws_forecast_enabled": True,
    "nws_forecast_pop_pct": 60,
    "nws_forecast_lat": NWS_SKIDAWAY_LAT,
    "nws_forecast_lon": NWS_SKIDAWAY_LON,
    "nws_forecast_url": "",
    "railway_sync": True,
    "irrigation_api_url": os.environ.get(
        "IRRIGATION_API_URL",
        "https://mrw-irrigation-api-production.up.railway.app",
    ),
    "irrigation_api_secret": os.environ.get("IRRIGATION_API_SECRET", ""),
}


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_json_atomic(path: Path, data: dict) -> None:
    MRW_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.rename(path)


def load_ha_config() -> tuple[str, str]:
    if HA_ENV.is_file():
        vals: dict[str, str] = {}
        for line in HA_ENV.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
        url = vals.get("HA_URL", "").rstrip("/")
        token = vals.get("HA_TOKEN", "")
        if url and token:
            return url, token
    raise SystemExit(f"Missing HA_URL/HA_TOKEN in {HA_ENV}")


def ha_request(url: str, token: str, method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    req = urllib.request.Request(f"{url}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else None


def fetch_json_url(url: str, timeout: int = 12) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return {}


def nws_tor_svr() -> tuple[bool, bool]:
    req = urllib.request.Request(NWS_ZONE_ALERTS, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False, False
    tor = svr = False
    for feat in data.get("features") or []:
        event = (feat.get("properties") or {}).get("event") or ""
        if event == "Tornado Warning":
            tor = True
        elif event == "Severe Thunderstorm Warning":
            svr = True
    return tor, svr


def nws_forecast_url(cfg: dict) -> str:
    cached = (cfg.get("nws_forecast_url") or "").strip()
    if cached:
        return cached
    lat = float(cfg.get("nws_forecast_lat", NWS_SKIDAWAY_LAT))
    lon = float(cfg.get("nws_forecast_lon", NWS_SKIDAWAY_LON))
    points = fetch_json_url(f"https://api.weather.gov/points/{lat},{lon}")
    url = (points.get("properties") or {}).get("forecast") or ""
    return url or NWS_SKIDAWAY_FORECAST_FALLBACK


def nws_forecast_today_pop(cfg: dict) -> tuple[int | None, list[str]]:
    """Max PoP today (America/New_York) and period labels with PoP above threshold."""
    if not cfg.get("nws_forecast_enabled", True):
        return None, []
    data = fetch_json_url(nws_forecast_url(cfg))
    periods = (data.get("properties") or {}).get("periods") or []
    if not periods:
        return None, []
    today = datetime.now(LOCAL_TZ).date()
    threshold = int(cfg.get("nws_forecast_pop_pct", 60))
    max_pop: int | None = None
    high_periods: list[str] = []
    for period in periods:
        start = datetime.fromisoformat(period["startTime"].replace("Z", "+00:00")).astimezone(LOCAL_TZ)
        end = datetime.fromisoformat(period["endTime"].replace("Z", "+00:00")).astimezone(LOCAL_TZ)
        if start.date() != today and end.date() != today and not (start.date() < today < end.date()):
            continue
        pop = (period.get("probabilityOfPrecipitation") or {}).get("value")
        if pop is None:
            continue
        pop_i = int(pop)
        max_pop = pop_i if max_pop is None else max(max_pop, pop_i)
        if pop_i > threshold:
            name = period.get("name") or "Today"
            high_periods.append(f"{name} {pop_i}%")
    return max_pop, high_periods


def gather_metrics(cfg: dict) -> dict:
    rain = fetch_json_url(f"{PI_WX_BASE}/rain.json")
    now = fetch_json_url(f"{PI_WX_BASE}/now.json")
    wind = fetch_json_url(f"{PI_WX_BASE}/wind.json")
    r = rain.get("rain") or {}
    n = now.get("now") if isinstance(now.get("now"), dict) else now
    w = wind.get("wind") or {}
    gust = w.get("max_gust_10m_mph")
    if gust is None:
        gust = w.get("gust_mph")
    tor, svr = nws_tor_svr()
    nws_pop_today, nws_high_periods = nws_forecast_today_pop(cfg)
    return {
        "rain_rate_inhr": float(r.get("rate_inhr") or 0),
        "rain_today_in": float(r.get("today_in") or 0),
        "rain_60m_in": float(r.get("last_60m_in") or 0),
        "rain_24h_in": float(r.get("last_24h_in") or 0),
        "is_raining": bool(r.get("is_raining")),
        "temp_f": float(n.get("temp_f")) if n.get("temp_f") is not None else None,
        "wind_gust_mph": float(gust) if gust is not None else None,
        "nws_tor": tor,
        "nws_svr": svr,
        "nws_pop_today_max": nws_pop_today,
        "nws_pop_high_periods": nws_high_periods,
    }


def update_daily_rain_state(metrics: dict, state: dict) -> dict:
    """Track Eastern calendar-day rain totals; finalize yesterday on date rollover."""
    today = datetime.now(LOCAL_TZ).date().isoformat()
    today_rain = metrics["rain_today_in"]
    last_date = state.get("last_snapshot_date")

    if last_date and last_date != today:
        prev_snapshot = state.get("today_rain_snapshot")
        if prev_snapshot is not None:
            state["yesterday_rain_in"] = float(prev_snapshot)

    state["today_rain_snapshot"] = today_rain
    state["last_snapshot_date"] = today
    return state


def evaluate_holds(metrics: dict, cfg: dict, state: dict) -> tuple[bool, list[str], dict]:
    now = datetime.now(timezone.utc)
    now_ts = int(now.timestamp())
    holds: list[str] = []
    rain_active = (
        metrics["is_raining"]
        or metrics["rain_rate_inhr"] >= cfg["rain_rate_inhr"]
        or metrics["rain_60m_in"] >= cfg["rain_60m_in"]
        or metrics["rain_24h_in"] >= cfg["rain_24h_in"]
    )

    soak_until = state.get("soak_until_ts")
    if rain_active:
        state["soak_until_ts"] = None
        if metrics["rain_rate_inhr"] >= cfg["rain_rate_inhr"] or metrics["is_raining"]:
            holds.append(f"Raining ({metrics['rain_rate_inhr']:.3f} in/hr)")
        if metrics["rain_60m_in"] >= cfg["rain_60m_in"]:
            holds.append(f"Rain last hour ({metrics['rain_60m_in']:.2f}\")")
        if metrics["rain_24h_in"] >= cfg["rain_24h_in"]:
            holds.append(f"Rain 24h ({metrics['rain_24h_in']:.2f}\")")
    else:
        if state.get("last_rain_active"):
            soak_h = int(cfg.get("rain_soak_hours", 12))
            state["soak_until_ts"] = now_ts + soak_h * 3600
        if soak_until and now_ts < int(soak_until):
            remaining_h = max(1, (int(soak_until) - now_ts) // 3600)
            holds.append(f"Post-rain soak (~{remaining_h}h left)")

    state["last_rain_active"] = rain_active

    temp = metrics.get("temp_f")
    if temp is not None and temp < cfg["freeze_temp_f"]:
        holds.append(f"Freeze ({temp:.0f}°F)")

    gust = metrics.get("wind_gust_mph")
    wind_hold = bool(state.get("wind_hold"))
    wind_on = float(cfg["wind_gust_mph"])
    wind_off = float(cfg.get("wind_gust_clear_mph", wind_on - 3))
    if wind_off >= wind_on:
        wind_off = wind_on - 3
    if wind_hold:
        if gust is None or gust < wind_off:
            state["wind_hold"] = False
        else:
            holds.append(f"Wind gust ({gust:.0f} mph)")
    elif gust is not None and gust >= wind_on:
        state["wind_hold"] = True
        holds.append(f"Wind gust ({gust:.0f} mph)")

    if metrics["nws_tor"]:
        holds.append("Tornado Warning (NWS)")
    elif metrics["nws_svr"]:
        holds.append("Severe T-Storm Warning (NWS)")

    pop_threshold = int(cfg.get("nws_forecast_pop_pct", 60))
    high_periods = metrics.get("nws_pop_high_periods") or []
    if high_periods:
        holds.append(f"NWS forecast rain >{pop_threshold}% today ({', '.join(high_periods)})")

    yesterday_in = state.get("yesterday_rain_in")
    if yesterday_in is not None and yesterday_in >= cfg["rain_yesterday_in"]:
        holds.append(f"Rain yesterday ({yesterday_in:.2f}\")")

    return bool(holds), holds, state


def load_irrigation_api_secret(cfg: dict) -> str:
    secret = (cfg.get("irrigation_api_secret") or os.environ.get("IRRIGATION_API_SECRET") or "").strip()
    if secret:
        return secret
    extra = load_json(CONFIG_PATH)
    return (extra.get("irrigation_api_secret") or "").strip()


def sync_to_railway(cfg: dict, veto: bool, holds: list[str], reason: str, metrics: dict, state: dict) -> None:
    if not cfg.get("railway_sync", True):
        return
    secret = load_irrigation_api_secret(cfg)
    if not secret:
        print("railway_sync skipped: no irrigation_api_secret", flush=True)
        return
    base = (cfg.get("irrigation_api_url") or "").rstrip("/")
    if not base:
        return
    payload = {
        "veto": veto,
        "reasons": holds,
        "reason": reason,
        "metrics": metrics,
        "state": {
            k: v
            for k, v in {
                "soakUntilTs": state.get("soak_until_ts"),
                "lastRainActive": state.get("last_rain_active"),
                "yesterdayRainIn": state.get("yesterday_rain_in"),
                "todayRainSnapshot": state.get("today_rain_snapshot"),
                "lastSnapshotDate": state.get("last_snapshot_date"),
                "windHold": state.get("wind_hold"),
            }.items()
            if v is not None
        },
    }

    data = json.dumps(payload).encode()
    headers = {
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(f"{base}/governor/sync", data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.status >= 300:
                print(f"railway_sync failed: HTTP {resp.status}", flush=True)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"railway_sync error: {e}", flush=True)


def publish_entities(
    url: str,
    token: str,
    veto: bool,
    reason: str,
    holds: list[str],
    metrics: dict,
    cfg: dict,
    state: dict,
) -> None:
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    mirror_veto_to_ha = not cfg.get("railway_sync", True)
    if mirror_veto_to_ha:
        # Reason before veto — HA hold alert reads reason when veto flips ON.
        ha_request(
            url,
            token,
            "POST",
            "/api/states/input_text.mrw_watering_reason",
            {
                "state": (reason[:255] if reason else ""),
                "attributes": {
                    "friendly_name": "MRW Watering Reason",
                    "source": "mrw_irrigation_governor",
                    "updated_utc": updated,
                },
            },
        )
        ha_request(
            url,
            token,
            "POST",
            "/api/states/input_boolean.mrw_watering_veto",
            {
                "state": "on" if veto else "off",
                "attributes": {
                    "friendly_name": "MRW Watering Veto",
                    "icon": "mdi:sprinkler-variant",
                    "source": "mrw_irrigation_governor",
                    "updated_utc": updated,
                },
            },
        )

    def sensor(entity: str, value, attrs: dict) -> None:
        ha_request(url, token, "POST", f"/api/states/{entity}", {"state": str(value), "attributes": attrs})

    sensor(
        "sensor.mrw_rain_today_in",
        f"{metrics['rain_today_in']:.2f}",
        {
            "friendly_name": "MRW Rain Today",
            "unit_of_measurement": "in",
            "device_class": "precipitation",
            "state_class": "total_increasing",
            "source": "pi-wx",
            "updated_utc": updated,
        },
    )
    sensor(
        "sensor.mrw_rain_24h_in",
        f"{metrics['rain_24h_in']:.2f}",
        {
            "friendly_name": "MRW Rain 24h",
            "unit_of_measurement": "in",
            "device_class": "precipitation",
            "state_class": "measurement",
            "source": "pi-wx",
            "updated_utc": updated,
        },
    )
    yesterday_in = state.get("yesterday_rain_in")
    if yesterday_in is not None:
        sensor(
            "sensor.mrw_rain_yesterday_in",
            f"{yesterday_in:.2f}",
            {
                "friendly_name": "MRW Rain Yesterday",
                "unit_of_measurement": "in",
                "device_class": "precipitation",
                "state_class": "measurement",
                "source": "pi-wx",
                "updated_utc": updated,
            },
        )
    sensor(
        "sensor.mrw_rain_60m_in",
        f"{metrics['rain_60m_in']:.2f}",
        {
            "friendly_name": "MRW Rain 60m",
            "unit_of_measurement": "in",
            "device_class": "precipitation",
            "state_class": "measurement",
            "source": "pi-wx",
            "updated_utc": updated,
        },
    )
    if metrics.get("temp_f") is not None:
        sensor(
            "sensor.mrw_temp_outdoor_f",
            f"{metrics['temp_f']:.1f}",
            {
                "friendly_name": "MRW Outdoor Temp",
                "unit_of_measurement": "°F",
                "device_class": "temperature",
                "state_class": "measurement",
                "source": "pi-wx",
                "updated_utc": updated,
            },
        )

    sensor(
        "binary_sensor.mrw_is_raining",
        "on" if metrics["is_raining"] or metrics["rain_rate_inhr"] >= 0.01 else "off",
        {
            "friendly_name": "MRW Is Raining",
            "device_class": "moisture",
            "source": "pi-wx",
            "updated_utc": updated,
        },
    )
    sensor(
        "binary_sensor.mrw_watering_hold_active",
        "on" if veto else "off",
        {
            "friendly_name": "MRW Watering Hold Active",
            "device_class": "safety",
            "hold_reasons": holds,
            "source": "mrw_irrigation_governor",
            "updated_utc": updated,
        },
    )
    pop_max = metrics.get("nws_pop_today_max")
    if pop_max is not None:
        sensor(
            "sensor.mrw_nws_pop_today_max",
            str(pop_max),
            {
                "friendly_name": "MRW NWS PoP Today Max",
                "unit_of_measurement": "%",
                "icon": "mdi:weather-pouring",
                "state_class": "measurement",
                "high_periods": metrics.get("nws_pop_high_periods") or [],
                "source": "nws_skidaway_forecast",
                "updated_utc": updated,
            },
        )
        threshold = int(cfg.get("nws_forecast_pop_pct", 60))
        high = metrics.get("nws_pop_high_periods") or []
        sensor(
            "binary_sensor.mrw_nws_rain_likely_today",
            "on" if high else "off",
            {
                "friendly_name": "MRW NWS Rain Likely Today",
                "device_class": "moisture",
                "pop_threshold_pct": threshold,
                "high_periods": high,
                "source": "nws_skidaway_forecast",
                "updated_utc": updated,
            },
        )


def maybe_rachio_delay(
    url: str,
    token: str,
    cfg: dict,
    prev_veto: bool,
    veto: bool,
    state: dict,
) -> None:
    if not cfg.get("rachio_auto_delay"):
        return
    entity = (cfg.get("rachio_rain_delay_entity") or "").strip()
    if not entity:
        return
    if veto and not prev_veto:
        ha_request(url, token, "POST", "/api/services/switch/turn_on", {"entity_id": entity})
        state["rachio_delay_by_mrw"] = True
    elif not veto and prev_veto and state.get("rachio_delay_by_mrw"):
        ha_request(url, token, "POST", "/api/services/switch/turn_off", {"entity_id": entity})
        state["rachio_delay_by_mrw"] = False


def run_once(dry_run: bool = False) -> int:
    cfg = {**DEFAULT_CONFIG, **load_json(CONFIG_PATH)}
    if not cfg.get("enabled", True):
        print("irrigation governor disabled in config", flush=True)
        return 0

    metrics = gather_metrics(cfg)
    state = load_json(STATE_PATH)
    state = update_daily_rain_state(metrics, state)
    prev_veto = state.get("veto") is True
    veto, holds, state = evaluate_holds(metrics, cfg, state)
    reason = " · ".join(holds) if holds else "All clear — watering allowed"

    result = {
        "veto": veto,
        "reason": reason,
        "holds": holds,
        "metrics": metrics,
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if dry_run:
        print(json.dumps(result, indent=2))
        return 0

    url, token = load_ha_config()
    sync_to_railway(cfg, veto, holds, reason, metrics, state)
    publish_entities(url, token, veto, reason, holds, metrics, cfg, state)
    maybe_rachio_delay(url, token, cfg, prev_veto, veto, state)
    state["veto"] = veto
    state["reason"] = reason
    save_json_atomic(STATE_PATH, state)

    action = "hold" if veto else "clear"
    if veto != prev_veto:
        action = "veto_on" if veto else "veto_off"
    print(f"irrigation {action} veto={veto} reason={reason!r}", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="MRW irrigation governor for Rachio")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=60)
    args = ap.parse_args()
    if not args.loop:
        return run_once(dry_run=args.dry_run)
    import time

    while True:
        try:
            run_once()
        except Exception as e:
            print(f"error: {e}", file=sys.stderr, flush=True)
        time.sleep(max(15, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
