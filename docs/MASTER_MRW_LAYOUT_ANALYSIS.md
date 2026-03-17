# Master MRW Dashboard — Layout Analysis (3840×2160)

## Screen
- **Total:** 3840 × 2160 px (4K)
- **Center X:** 1920 px
- **One third:** 3840 ÷ 3 = 1280 px

---

## User Observation (ground truth)

- Wind needle center is at **1920 px** (dead center of screen)
- Left section is **35–38%** of screen width
- 35% of 3840 = 1344 px  
  38% of 3840 = 1459 px  
  So left area ≈ **1350–1460 px**
- With ~3 boxes wide at ~500 px each: 3 × 500 ≈ 1500 px total

---

## Correct Math (from wind center at 1920)

- Wind box: **780 px** wide
- Wind center: **1920 px**
- Wind left edge: 1920 − 390 = **1530 px**
- **Left area width:** 1530 px (to the left edge of the wind box)

So the space to the left of the wind/tide column is **~1530 px** wide (or ~1508 px inside grid padding).

### Left box dimensions (if 3×3 grid)

- Width: (1530 − 2×22 gap) ÷ 3 ≈ **495 px** per box
- Height: (2013 − 2×22 gap) ÷ 3 ≈ **657 px** per box  
  → Each box ≈ **495 × 657 px**

### Left box dimensions (if 2×5 grid)

- Width: (1530 − 22 gap) ÷ 2 ≈ **754 px** per box
- Height: (2013 − 4×22 gap) ÷ 5 ≈ **385 px** per box  
  → Each box ≈ **754 × 385 px**

---

## CSS vs. Observation

**Current CSS:** `grid-template-columns: 1fr 780px 900px`

That implies:
- Fixed: 780 + 900 + 2×gap ≈ 1723 px
- 1fr = (3840 − padding − 1723) ≈ **2074 px**

So the CSS would give a left column of ~2074 px, not ~1530 px.

**Conclusion:** Either the viewport is not 3840 px, or something else (zoom, browser chrome, etc.) changes the layout. The numbers above are based on your observation that the wind center is at 1920.

---

## Source of Truth

The diagnostic on the page reports actual `getBoundingClientRect()` values. Use those for planning.
