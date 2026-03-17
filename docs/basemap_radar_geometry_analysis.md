# Basemap vs Radar Geometry Analysis

## 1. Basemap authoritative geometry (source of truth)

**File:** `bin/make_basemap_grid.py`

| Property | Value |
|----------|-------|
| **Center (WGS84)** | lat=31.919173, lon=-81.075938 |
| **Center (EPSG:3857 m)** | x≈-9025332.13, y≈3752705.5 |
| **Bounds (EPSG:3857)** | xmin≈-9255332.13, ymin≈3522705.5, xmax≈-8795332.13, ymax≈3982705.5 |
| **Projection** | EPSG:3857 (Web Mercator) |
| **Half extent** | 230 km → 230,000 m |
| **Output size** | 1600 × 1600 px |

**Pixel-to-world mapping:**
- Column i → x_m = xmin + (xmax-xmin)*(i+0.5)/N
- Row j (0=top) → y_m = ymax - (ymax-ymin)*(j+0.5)/N  (top = north)

---

## 2. Radar pipeline geometry (current mismatch)

**File:** `bin/render_level2_nn_rgba.py` (called by `publish_radar_frame.py`)

| Property | Current (wrong) | Issue |
|----------|-----------------|-------|
| **Grid center** | Radar site (lat/lon from radar metadata) | Basemap is centered on user location |
| **Grid extent** | ±230 km in flat Cartesian km from radar | Same half_km but wrong origin |
| **Projection** | Implicit flat Cartesian (km from radar) | Basemap uses EPSG:3857 |
| **Output** | 1600×1600 | Same |

**`nearest_polar_to_cart()` logic:**
- Builds `xi = np.linspace(-half, half, N)` in km (centered on radar)
- `XX, YY` = meshgrid → (0,0) = radar center
- Converts (x_km, y_km) to polar (range, azimuth) and samples
- Output is centered on **radar site**, not basemap center

**Radar center examples:**
- KCLX: 32.65556, -81.04222 (≈82 km NW of basemap center)
- KJAX: 30.48472, -81.66194 (≈160 km SW of basemap center)

---

## 3. Proposed fix

**Principle:** Use basemap extent as the output grid. For each pixel (i,j):
1. Map (i,j) → (x_m, y_m) in EPSG:3857 using basemap bounds
2. Transform (x_m, y_m) → (lat, lon) in WGS84
3. Compute (range_km, azimuth_deg) from radar to (lat, lon)
4. Sample reflectivity at (range_km, azimuth_deg)

**Files to change:**
1. `conf/basemap_geometry.json` — new config (single source of truth)
2. `bin/render_level2_nn_rgba.py` — replace radar-centered grid with basemap-aligned grid

**Optional:** `bin/make_basemap_grid.py` could later read from this config for consistency, but user said "do not change the basemap."
