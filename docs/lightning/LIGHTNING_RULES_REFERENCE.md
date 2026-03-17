# MRW Lightning Rules

Version: 1.0
Locked: 2026-03-15
Maintainer: Moon River Weather (MRW)

Purpose:
This document is the single source of truth for all MRW lightning constants, thresholds, visualization rules, and behavioral standards.

All lightning products, dashboards, map players, and alert systems must follow the specifications defined here.

## Version History

| Version | Date | Notes |
|---------|------|-------|
| v1.0 | 2026-03-15 | Initial rules reference created and locked alongside the first operational MRW lightning map. |

---

# Lightning Rules Reference — Cross-Product

**Single source of truth** for lightning constants, thresholds, and behavior. Use this when building dashboards, website widgets, map players, or any product that consumes lightning data.

---

## 1. Constants

| Constant | Value | Unit | Use |
|----------|-------|------|-----|
| **MRW_CENTER_LAT** | 31.919173 | degrees | Station location |
| **MRW_CENTER_LON** | -81.075938 | degrees | Station location |
| **CLOSE_RADIUS_MI** | 25 | miles | Close-strike zone |
| **CLOSE_RADIUS_KM** | 40.2336 | km | 25 × 1.609344 |
| **STRIKE_COUNT_RADIUS_MI** | 300 | miles | Now, Strikes/Min, Strikes/12h |
| **STRIKE_COUNT_RADIUS_KM** | 482.803 | km | 300 × 1.609344 |
| **MAX_RADIUS_MI** | 400 | miles | Map domain |
| **MAX_RADIUS_MI_LEGACY** | 500 | miles | lightning_points.geojson (v1) |

---

## 2. Close Zone (≤25 mi)

### Symbol behavior (map)

| Age | Symbol | Color | Notes |
|-----|--------|-------|-------|
| 0–3 s | Bolt | Red (#b91c1c) | Jitter flash (opacity pulse) |
| 3 s–5 min | Bolt | Red (#b91c1c) | Full opacity |
| 5–15 min | Dot | Red (#b91c1c) | Full opacity |
| 15–30 min | Dot | Yellow (#eab308) | Full opacity |
| 30+ min | — | Gone | Excluded from display |

### Data box alert (rows 2–4)

| Phase | Duration | Display |
|-------|----------|---------|
| Flash | 0–5 s | Red, flash 5× |
| Solid red | 5 s–15 min | Red text |
| Yellow | 15–30 min | Yellow text |
| NONE | 30+ min | Value = NONE |

**New strike:** Replaces existing, restarts timer.

---

## 3. Non-Close Zone (>25 mi)

### Symbol behavior (map)

| Age | Symbol | Color | Opacity |
|-----|--------|-------|---------|
| 0–2 s | Bolt | White (#ffffff) | 1 |
| 2 s–5 min | Dot | CG #facc15 / IC #38bdf8 | 0.9 |
| 5+ min | Dot | Same | 0.2 |

**5-min fade:** At age_seconds ≥ 300, fill and stroke → 0.2 opacity.

---

## 4. Data Box Metrics

| Row | Label | Radius | Window | Value when empty |
|-----|-------|--------|--------|------------------|
| 1 | Now | 300 mi | 15 min | NONE |
| 2 | Close | 25 mi | 30 min | NONE |
| 3 | @ | 25 mi | 30 min | NONE |
| 4 | Close/Minute | 25 mi | 1 min rolling | NONE |
| 5 | Close/4 Hours | 25 mi | 4 hr rolling | NONE |
| 6 | Strikes/Minute | 300 mi | 1 min rolling | NONE |
| 7 | Strikes/12 Hours | 300 mi | 12 hr rolling | NONE |

---

## 5. API: lightning_points_v2.geojson

**URL:** `http://192.168.2.2:8080/lightning_points_v2.geojson`

### Schema

```json
{
  "type": "FeatureCollection",
  "properties": { "computed_at_utc": "ISO8601" },
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Point", "coordinates": [lon, lat] },
      "properties": {
        "timestamp_utc": "ISO8601",
        "strike_type": "CG" | "IC",
        "distance_km": number,
        "bearing_deg": number,
        "age_seconds": number,
        "age_bucket": "bolt" | "prominent" | "medium" | "low" | "faint",
        "render_type": "cg" | "ic" | "bolt",
        "symbol": "cg" | "ic" | "bolt",
        "icon_size": number,
        "icon_opacity": number
      }
    }
  ]
}
```

### Filter rules (generator)

- **Radius:** ≤500 km from MRW
- **Window:** 15 min (non-close); 30 min (close zone ≤25 mi)
- **Cap:** 500 strikes
- **Dedup:** (timestamp_utc, lon, lat)

---

## 6. API: lightning_recent.json

**Path:** `C:\MRW\lightning\lightning_recent.json` (Lightning-PC)

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `last_strike_time_utc` | string \| null | Most recent strike in 15 min |
| `nearest_strike_km` | number \| null | Closest strike distance |
| `nearest_strike_miles` | number \| null | Same in miles |
| `closest_strike_bearing_deg` | number \| null | Bearing 0–360° |
| `closest_strike_direction` | string \| null | N, NE, E, SE, S, SW, W, NW |
| `strikes_last_5_min` | number | Count |
| `strikes_last_10_min` | number | Count |
| `strikes_last_15_min` | number | Count |
| `trend` | string | approaching \| departing \| steady |
| `computed_at_utc` | string | ISO8601 |

---

## 7. Colors (hex)

| Use | Hex |
|-----|-----|
| Close bolt/dot red | #b91c1c |
| Close dot yellow | #eab308 |
| CG (non-close) | #facc15 |
| IC (non-close) | #38bdf8 |
| Station marker | #22c55e |
| Data box background | rgba(235,235,235,0.85) |

---

## 8. Products

| Product | Data | Rules |
|---------|------|-------|
| Full View Lightning Map | lightning_points_v2.geojson | This doc (close + non-close) |
| lightning-mapbox | lightning_points.geojson | Legacy, 500 mi |
| lightning_recent | lightning_recent.json | Intelligence product |
| lightning_summary | lightning_summary.json | Operational intelligence — dashboards must read this |
| Master MRW / Website | lightning_summary.json, lightning_points_v2 | Use constants above |

---

## 9. Implementation notes

- **Close check:** `distance_km <= CLOSE_RADIUS_KM` (40.2336)
- **Age from timestamp:** `Date.now() - new Date(timestamp_utc).getTime()`
- **Miles from km:** `km * 0.621371`
