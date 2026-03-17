# Full View Lightning Map — PRODUCTION

**Production product.** Map behavior and strike behavior are LOCKED.

**Cross-product rules:** `docs/lightning/LIGHTNING_RULES_REFERENCE.md` — constants, close zone, API. Use for dashboards, website, other products.

**Player:** `player/lightning-full-view/`  
**Baseline:** `player/lightning-full-view-baseline/`  
**Data:** `lightning_points_v2.geojson`  
**URL:** `/player/lightning-full-view/`

**Baseline locked:** 2026-03-15 — Data box + close strike symbols (25 mi). Close: red bolt 0–5 min (jitter flash 0–3 s), red dot 5–15 min, yellow dot 15–30 min, gone 30+ min. Non-close strikes unchanged.

**Production locked:** 2026-03-16 — Zoom 6, minZoom 6, pan restricted to initial viewport; data box 260×280; row 3 label "Now".

## Revert to baseline

```bash
./bin/revert_lightning_v2_to_baseline.sh
rsync -az player/lightning-full-view/ wx-i9:~/wx/radar-foundry/player/lightning-full-view/
```

---

## Map behavior (LOCKED)

| Property | Value |
|----------|-------|
| **Center** | MRW station (31.919173, -81.075938) |
| **Radius** | 400 miles |
| **Initial zoom** | 6 |
| **Zoom range** | 6–14 (min zoom = 6, cannot zoom out past load) |
| **Pan** | Restricted to initial viewport bounds (maxBounds = getBounds() on idle) |
| **Station marker** | Green star (#22c55e), icon-size 0.35–0.65 |
| **Strike count radius** | 300 miles |

---

## Strike behavior (LOCKED)

### Dots (circle layer)

| Property | CG | IC |
|----------|----|----|
| **Color** | `#facc15` | `#38bdf8` |
| **Radius** | 6 px | 5 px |
| **Opacity** | 0.9 (<5 min), 0.2 (≥5 min) | same |
| **Stroke** | 1 px white, same opacity rule | same |

**5-min fade rule:** At age_seconds ≥ 300, fill and stroke → 80% transparent.

### Bolt layer

- 0–10s: red bolt (#ef4444) with white stroke
- Flash duration: 2s
- 10s+: circle (dot) as above

### Other

- Deduplication: (timestamp_utc, lon, lat) before 500 cap
- 15 min window, max 500 strikes

---

## Labels and text

May be changed without affecting locked behavior.

### Data box (upper right)

| Row | Label | Value |
|-----|-------|-------|
| 1 | Now | CG/IC, Bng (bearing °), distance (mi) |
| 2 | Close | CG/IC Bng distance, or NONE if no strike within 30 min |
| 3 | Now | Strike time (12h) + Since (m:ss), or NONE |
| 4 | Close/Minute | Strikes within 25 mi in rolling 1 min |
| 5 | Close/4 Hours | Strikes within 25 mi in rolling 4 hr |
| 6 | Strikes/Minute | Count in last 60s within 300 mi |
| 7 | Strikes/12 Hours | Unique strikes within 300 mi in rolling 12-hour window |

**Data box size:** 260×280 px, 14px font.

**Close metric (rows 2–4):** Strikes within 25 miles of MRW. When a close strike occurs: flash red 5× in 5 s, solid red 0–15 min, yellow 15–30 min, then NONE. New strike replaces and restarts timer.

### Close strike symbols (25 mi radius)

| Age | Symbol | Color |
|-----|--------|-------|
| 0–3 s | Bolt | Red, jitter flash |
| 3 s–5 min | Bolt | Red (#b91c1c) |
| 5–15 min | Dot | Red (#b91c1c) |
| 15–30 min | Dot | Yellow (#eab308) |
| 30+ min | — | Gone |

**Isolation:** Close logic applies only when `distance_km <= 25 mi`. Strikes outside 25 mi use the original behavior (2s white bolt flash, then CG/IC dots with 5-min fade).

### Verification

| Test | Expected |
|------|----------|
| Close strike (≤25 mi) | Red bolt (jitter 0–3s) → red dot (5–15 min) → yellow dot (15–30 min) → gone |
| Non-close strike (25–400 mi) | White bolt 2s → CG yellow / IC blue dot |
| 5-min fade (non-close) | Dot opacity 0.9 → 0.2 at age ≥5 min |
