# MRW Lightning Products

Lightning products are derived from the strike stream (`lightning_rt.ndjson`) and written to `C:\MRW\lightning\` on Lightning-PC. Computed on wx-core by `bin/lightning_nex_tail.py`; pushed each poll cycle.

**Rules reference:** `docs/lightning/LIGHTNING_RULES_REFERENCE.md` — constants, thresholds, close-zone behavior. Use across dashboards, website, map players.

**Hardening:** Retries (3x SSH/SCP), atomic writes, timeouts, watchdog (5-min staleness → restart). See `.cursor/rules/lightning-hardening.mdc`.

---

## lightning_recent.json

**Path:** `C:\MRW\lightning\lightning_recent.json`

Near real-time intelligence product. Updated every 5 seconds (same as the nex tail poll interval).

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `last_strike_time_utc` | string \| null | ISO 8601 UTC of most recent strike in last 15 min |
| `nearest_strike_km` | number \| null | Distance (km) of closest strike in last 15 min |
| `nearest_strike_miles` | number \| null | Same in miles |
| `closest_strike_bearing_deg` | number \| null | Bearing (0–360°) of closest strike |
| `closest_strike_direction` | string \| null | Cardinal: N, NE, E, SE, S, SW, W, NW |
| `strikes_last_5_min` | number | Count in last 5 min |
| `strikes_last_10_min` | number | Count in last 10 min |
| `strikes_last_15_min` | number | Count in last 15 min |
| `trend` | string | `approaching` \| `departing` \| `steady` |
| `computed_at_utc` | string | ISO 8601 UTC when product was computed |

### Trend Logic

Compares nearest-strike distance over the last 4 evaluations. If recent nearest is >10% closer than older → `approaching`; >10% farther → `departing`; else `steady`.

### Source

- **Input:** `lightning_rt.ndjson` (rolling 15-min window in memory)
- **Compute:** wx-core, `bin/lightning_nex_tail.py`
- **Output:** Pushed to Lightning-PC with `lightning_rt.ndjson` and `lightning_status.json`

---

## lightning_points.geojson

**Path:** `serve_root/lightning_points.geojson` (served at `/lightning_points.geojson` on wx-i9:8080)

**Map product.** GeoJSON FeatureCollection of strike points for map display. Updated every 5 seconds by `lightning_nex_tail` (same cycle as lightning_recent).

### Fields

- **features:** Point geometries with `[lon, lat]` converted from bearing/distance
- **properties:** `timestamp_utc`, `strike_type` (CG/IC), `distance_km`, `bearing_deg`
- **Filter:** Strikes within 500-mile radius from MRW station only
- **Limit:** Most recent 500 strikes

### Source

- **Input:** `scratch/lightning_nex/lightning_rt.ndjson`
- **Generator:** `bin/generate_lightning_points.py`
- **Output:** Pushed to wx-i9 serve_root by lightning_nex_tail
- **Consumer:** `player/lightning-mapbox/` — Mapbox map with lightning overlay

---

## lightning_points_v2.geojson

**Path:** `serve_root/lightning_points_v2.geojson` (served at `/lightning_points_v2.geojson` on wx-i9:8080)

**Map product.** GeoJSON FeatureCollection for Full View Lightning Map. Same input as v1; v2 age buckets. Close-zone behavior (25 mi) applied client-side in player.

### Fields

- **features:** Point geometries `[lon, lat]`
- **properties:** `timestamp_utc`, `strike_type` (CG/IC), `distance_km`, `bearing_deg`, `age_seconds`, `age_bucket`, `render_type`, `symbol`, `icon_size`, `icon_opacity`
- **Filter:** ≤500 km from MRW
- **Window:** 15 min
- **Cap:** 500 strikes

### Close zone (client-side)

Strikes with `distance_km <= 40.2336` (25 mi) use special symbol behavior. See `docs/lightning/LIGHTNING_RULES_REFERENCE.md`.

### Source

- **Input:** `scratch/lightning_nex/lightning_rt.ndjson`
- **Generator:** `bin/generate_lightning_points_v2.py`
- **Output:** Pushed to wx-i9 serve_root by lightning_nex_tail
- **Consumer:** `player/lightning-full-view/` — **PRODUCTION**

---

## lightning_summary.json

**Path:** `serve_root/lightning_summary.json` (served at `/lightning_summary.json` on wx-i9:8080)

**Operational intelligence product.** High-level summary for dashboards, alert engine, website. **Dashboards must read this file; they must NOT compute these metrics themselves.**

**Inputs:** lightning_rt.ndjson, lightning_recent.json, lightning_status.json

**Generator:** `bin/generate_lightning_summary.py` (runs in lightning_nex_tail geo thread)

**Schema:** See `docs/lightning/LIGHTNING_PRODUCTS_INDEX.md`. Fields include: computed_at_utc, last_strike_time_utc, nearest_strike, nearest_cg, nearest_ic, counts_by_radius (5/10/15/25/50/100 mi), counts_by_type, counts_by_age, strike_rate, trend, alert_state, source_health.
