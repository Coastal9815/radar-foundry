#!/usr/bin/env python3
"""Celestial API: sunrise, sunset, day length, moonrise, moonset, next season.
Server-side only. No external APIs. Uses astral + skyfield.
Single endpoint /api/celestial/summary."""
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

MRW_LAT = 31.91918481533656
MRW_LON = -81.07604504861318
MRW_TZ = "America/New_York"


def _fmt_time(dt):
    """Format datetime as local time string (e.g. 7:23am, 6:45pm)."""
    if dt is None:
        return None
    h = dt.hour
    m = dt.minute
    ap = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d}{ap}"


def _moon_phase_skyfield():
    """Get moon phase from skyfield (degrees 0-360). Returns phase name."""
    try:
        from skyfield import almanac
        from skyfield.api import load

        ts = load.timescale()
        eph = load("de421.bsp")
        now = datetime.now(ZoneInfo(MRW_TZ))
        t = ts.utc(now.year, now.month, now.day, now.hour, now.minute)
        phase_deg = almanac.moon_phase(eph, t).degrees
        # 0=New, 90=First Q, 180=Full, 270=Last Q. Boundaries at quarter points.
        if phase_deg >= 337.5 or phase_deg < 22.5:
            return "New"
        if phase_deg < 67.5:
            return "Waxing Crescent"
        if phase_deg < 112.5:
            return "First Quarter"
        if phase_deg < 157.5:
            return "Waxing Gibbous"
        if phase_deg < 202.5:
            return "Full"
        if phase_deg < 270:
            return "Waning Gibbous"
        if phase_deg < 315:
            return "Last Quarter"
        return "Waning Crescent"
    except Exception:
        return None


def _fmt_day_length(seconds):
    """Format seconds as HH:MM (e.g. 12:34)."""
    if seconds is None or not (0 <= seconds < 86400 * 2):
        return None
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}:{m:02d}"


def _next_season_start():
    """Find next equinox or solstice using skyfield. Returns local datetime string."""
    try:
        from skyfield import almanac
        from skyfield.api import load

        ts = load.timescale()
        eph = load("de421.bsp")
        now_local = datetime.now(ZoneInfo(MRW_TZ))
        now_utc = now_local.astimezone(ZoneInfo("UTC"))
        t0 = ts.utc(now_utc.year, now_utc.month, now_utc.day, now_utc.hour, now_utc.minute)
        t1 = ts.utc(now_utc.year + 2, 1, 1)  # search up to 2 years ahead

        t, y = almanac.find_discrete(t0, t1, almanac.seasons(eph))
        if len(t) == 0:
            return None
        # First event strictly after t0
        for i, ti in enumerate(t):
            if ti > t0:
                break
        else:
            return None
        first_t = t[i]
        yi = y[i]
        dt_utc = first_t.utc_datetime()
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=ZoneInfo("UTC"))
        dt_local = dt_utc.astimezone(ZoneInfo(MRW_TZ))
        name = almanac.SEASON_EVENTS[yi]
        return f"{name} {dt_local.strftime('%b %d, %Y %I:%M%p')}".replace(" 0", " ")
    except Exception:
        return None


def fetch_summary():
    """Compute celestial summary for MRW station. Returns normalized JSON."""
    try:
        from astral import LocationInfo
        from astral.location import Location

        loc_info = LocationInfo(
            "MRW",
            "GA",
            MRW_TZ,
            MRW_LAT,
            MRW_LON,
        )
        loc = Location(loc_info)
        today = date.today()

        sunrise = loc.sunrise(today, local=True)
        sunset = loc.sunset(today, local=True)
        day_start, day_end = loc.daylight(today, local=True)
        day_length_sec = (day_end - day_start).total_seconds() if day_start and day_end else None
        moonrise = loc.moonrise(today, local=True)
        moonset = loc.moonset(today, local=True)
        phase = _moon_phase_skyfield()
        next_season = _next_season_start()

        return {
            "sunrise": _fmt_time(sunrise) or "--",
            "sunset": _fmt_time(sunset) or "--",
            "day_length": _fmt_day_length(day_length_sec) or "--",
            "moonrise": _fmt_time(moonrise) or "--",
            "moonset": _fmt_time(moonset) or "--",
            "phase": phase or "--",
            "next_season_start": next_season or "--",
        }
    except Exception as e:
        return {
            "sunrise": "--",
            "sunset": "--",
            "day_length": "--",
            "moonrise": "--",
            "moonset": "--",
            "phase": "--",
            "next_season_start": "--",
        }


if __name__ == "__main__":
    print(json.dumps(fetch_summary(), indent=2))
