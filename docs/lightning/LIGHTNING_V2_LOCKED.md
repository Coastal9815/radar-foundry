# Lightning Map V2 — Full View Lightning Map (PRODUCTION)

**See `docs/lightning/FULL_VIEW_LIGHTNING_MAP.md` for full spec.**

**Cross-product rules:** `docs/lightning/LIGHTNING_RULES_REFERENCE.md` — constants, close zone, API schema. Use for dashboards, website, other products.

**Player:** `player/lightning-full-view/`  
**Baseline:** `player/lightning-full-view-baseline/`  
**URL:** `/player/lightning-full-view/`

## Locked Spec (Circle Layer)

| Property | CG | IC |
|----------|----|----|
| **Color** | `#facc15` | `#38bdf8` |
| **Radius** | 6 px | 5 px |
| **Opacity** | 0.9 (<5 min), 0.2 (≥5 min) | same |
| **Stroke width** | 1 px | 1 px |
| **Stroke color** | `#fff` | `#fff` |
| **Stroke opacity** | 1.0 (<5 min), 0.2 (≥5 min) | same |

**5-min fade rule:** At 5 minutes (age_seconds ≥ 300), both fill and stroke switch to 80% transparent (opacity 0.2).

## Bolt Layer

- 0–10s: red bolt icon (fill="#ef4444") with white stroke (stroke="#ffffff", stroke-width="1.5")
- Flash duration: 2s
- 10s+: circle (dot) as above

## Close zone (25 mi)

See `LIGHTNING_RULES_REFERENCE.md`. Red bolt 0–5 min (jitter flash 0–3 s), red dot 5–15 min, yellow dot 15–30 min, gone 30+ min.

## Rules

- No fade curve on dots (fixed 0.9 opacity)
- No stroke-opacity; stroke is full opacity
- Keep deduplication in the generator (timestamp_utc, lon, lat) before 500 cap
