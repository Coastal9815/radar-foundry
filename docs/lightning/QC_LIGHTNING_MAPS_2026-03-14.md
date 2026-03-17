# Lightning Maps QC Report — 2026-03-14

**Scope:** local-lightning, lightning-full-view  
**Reference:** `docs/lightning/LIGHTNING_RULES_REFERENCE.md`, `LIGHTNING_FIXED_135.md`, `FULL_VIEW_LIGHTNING_MAP.md`

---

## 1. Constants — PASS

| Constant | Rules | local-lightning | lightning-full-view |
|----------|-------|-----------------|---------------------|
| CENTER | (-81.075938, 31.919173) | ✓ | ✓ |
| CLOSE_RADIUS_MI | 25 | ✓ | ✓ |
| CLOSE_RADIUS_KM | 40.2336 | ✓ (25×1.609344) | ✓ |
| STRIKE_COUNT_RADIUS_MI | 300 (Full View) / 135 (Local) | 135 ✓ | 300 ✓ |
| MAX_RADIUS_MI | 400 (Full View) / 135 (Local) | 135 ✓ | 400 ✓ |

---

## 2. Close Zone Display Logic (25 mi) — PASS

**Both maps use identical `transformFeaturesForFlash()` logic:**

| Age | Symbol | Color | Both maps |
|-----|--------|-------|-----------|
| 0–3 s | Bolt | Red (#b91c1c), jitter flash | ✓ |
| 3 s–5 min | Bolt | Red (#b91c1c), full opacity | ✓ |
| 5–15 min | Circle | Red (#b91c1c) | ✓ |
| 15–30 min | Circle | Yellow (#eab308) | ✓ |
| 30+ min | Gone | — | ✓ |

**Server:** `generate_lightning_points_v2.py` now keeps close strikes 30 min (CLOSE_WINDOW_MINUTES). ✓

---

## 3. Data Box — Differences (Intentional)

### local-lightning
- **Layout:** Two sections with outline boxes
  - Range 0–25 Miles: Close, Now, Close/Minute, Close/4 Hours
  - Range 26–135 Miles: Now, Strikes/Minute, Strikes/12 Hours
- **Size:** 260×326 px
- **Row order:** Close section first, then area section
- **Empty value:** NONE ✓

### lightning-full-view
- **Layout:** Single list, no outline boxes
  - Row 1: Now (300 mi)
  - Row 2: Close (25 mi)
  - Row 3: Now (close timestamp)
  - Row 4: Close/Minute
  - Row 5: Close/4 Hours
  - Row 6: Strikes/Minute
  - Row 7: Strikes/12 Hours
- **Size:** 260×280 px (per FULL_VIEW doc)
- **Empty value:** NONE ✓

### Close alert phases (both)
- Flash 0–5 s: red, flash 5× ✓
- Solid red 5 s–15 min ✓
- Yellow 15–30 min ✓
- NONE 30+ min ✓

---

## 4. Range Rings — INCONSISTENCY

| Map | 25 mi ring | Uses geojson `color`? |
|-----|------------|------------------------|
| **local-lightning** | Red, 2px, 0.8 opacity | ✓ `["coalesce", ["get", "color"], "#ffffff"]` |
| **lightning-full-view** | White, 1px, 0.4 opacity | ✗ Hardcoded `#ffffff` |

**Issue:** lightning-full-view ignores `lightning_range_rings.geojson` `color` property. The 25 mi ring in the geojson has `"color": "#ef4444"` but full-view renders all rings white.

**Recommendation:** Update lightning-full-view to use `["coalesce", ["get", "color"], "#ffffff"]` for line-color and text-color so the 25 mi ring appears red, matching local-lightning.

---

## 5. Non-Close Strike Logic — PASS

Both use same circle layer with:
- CG: #facc15, IC: #38bdf8
- 5-min fade: age_seconds ≥ 300 → opacity 0.2 ✓
- New-strike flash: 2 s bolt (FLASH_DURATION_MS) ✓

---

## 6. Map Behavior — PASS

| Property | local-lightning | lightning-full-view |
|----------|-----------------|---------------------|
| Zoom/pan | Disabled, fixed 135 mi | Zoom 6–14, pan restricted |
| Domain | 135 mi E–W | 400 mi |
| Station marker | Green star #22c55e | ✓ |
| Poll interval | 2500 ms | ✓ |
| Refresh on load | 2 s delay | ✓ |

---

## 7. Assets — PASS

- `station-star.svg`, `lightning-bolt.svg` present in both player dirs ✓
- `cg-square.svg`, `ic-x.svg` present but not used (circle layer used instead) ✓

---

## 8. LIGHTNING_RULES_REFERENCE.md — Minor Update Needed

- **Section 5 Filter rules:** Says "Window: 15 min" — should note "Close zone (≤25 mi): 30 min; non-close: 15 min"
- **Row 3 label:** Doc says "@" — both maps use "Now" for the close timestamp row. "@" may mean "at" (time). No change required if "Now" is the intended label.

---

## 9. Summary

| Item | Status |
|------|--------|
| Constants | ✓ |
| Close zone display (0–30 min) | ✓ |
| Data box logic | ✓ |
| Non-close logic | ✓ |
| Map behavior | ✓ |
| Assets | ✓ |
| **lightning-full-view range rings** | ⚠ Use geojson color for 25 mi red ring |
| **LIGHTNING_RULES_REFERENCE** | ⚠ Update filter rules for close 30 min |

---

## 10. Fixes Applied

1. **lightning-full-view:** Updated range rings to use `["coalesce", ["get", "color"], "#ffffff"]` for line-color and text-color; line-width 2, line-opacity 0.8 (matches local-lightning).
2. **LIGHTNING_RULES_REFERENCE.md:** Updated Section 5 filter rules: "15 min (non-close); 30 min (close zone ≤25 mi)".
