# Master MRW Dashboard — LAYOUT LOCKED

**Do not change layout dimensions without explicit approval.**

**Layout rule:** Every element uses explicit X/Y coordinates (`position: absolute` with `top`/`left`/`right` in px). No flexbox, no `margin-left: auto`, no wraps for positioning.

## Screen
- **3839 × 2160 px**

## Usable Space (excludes Conditions bar)
- **Edges:** left=20, right=3819, top=124, bottom=2140
- **Dimensions:** 3799 × 2016 px

## Section Dimensions

### Left section (8 boxes, 2×4)
- **Width:** 1420 px (700 + 20 + 700)
- **Height:** 2016 px
- **Box size:** 700 × 489 px each
- **Gap:** 20 px between boxes

### Middle section
- **Width:** 1089 px
- **Wind:** 1089 × 744 px
- **Tide:** 1089 × 744 px
- **Bottom box:** 1089 × 488 px
- **Gap:** 20 px between boxes

### Right section (Radar, Region)
- **Width:** 1250 px
- **Each:** 1250 × 998 px
- **Gap:** 20 px between them

## Radar tile (KCLX Mapbox)
- **Tile:** 1250 × 998 px
- **Embed:** Full kclx-mapbox player via iframe
- **URL params:** viewport=0.38 (zoom); frameLimit=36; autoplay=1 — defaults to Play, 36-frame loop on load

## Rain (Current) module — LOCKED

**Do not change without explicit approval.**

- **Module file:** `player/master-mrw/modules/rain-current.js`
- **Slot:** Box 3 (SLOTS[2]); move via SLOTS[i]
- **Tile:** 700 × 489 px; explicit X/Y for all elements
- **Labels:** left 16px; bottom-aligned (Rain Today 405, Rain Rate 275, Storm Rain 155, Days Since 23). **DO NOT move the labels.**
- **Values:** left 404px, right 186px; top -1, 129; bottom 155, 22; text-align right
- **" (inch):** inline after digits (rainUnitInch 52px, vertical-align top); Rain Today, Storm Rain
- **in/hr:** right 16px, top 144px; stacked (in over hr)
- **Fonts:** labels 44px, values 95px, units 36px
- **Data:** rain.json, now.json via pi-wx proxy. today_in, rate_inhr, storm_in; days since: 0 if today_in > 0.001 else from storm_last_end_at

## Rain Accumulation module
- **Module file:** `player/master-mrw/modules/rain-accumulation.js`
- **Slot:** Box 4 (SLOTS[3])
- **Tile:** 700 × 489 px
- **Layout:** Two columns (Month | Year): label, value 00.00", % of Norm:, 100%; bottom: Deficit This Year, 13.56"
- **Data:** rain.json (month_in, year_in); rain_norms.json (month_norm_in[], year_norm_in) from pi-wx. Methodology: Monthly % = actual ÷ expected_month_to_date [(norm/days)×days_elapsed]; Year % = actual ÷ expected_year_to_date [sum full months + partial current]; Deficit = actual − expected.
- **Timezone:** Source of truth is America/New_York (EST/EDT). All dates use local Eastern time.
- **Bottom row:** Left: Year Deficit/Excess (label + value). Right: Drought Status bar (US Drought Monitor, Chatham County GA). Deficit label: "Year Excess" if ≥0.01", else "Year Deficit". Drought data: /drought-data/chatham.json (proxied USDM API), updates weekly Thursday.

## Air Quality module — LOCKED

**Do not change without explicit approval.**

- **Module file:** `player/master-mrw/modules/air-quality.js`
- **Slot:** Box 5 (SLOTS[4])
- **Tile:** 700 × 489 px
- **Layout:** Six cells in 2×3 grid. PM2.5, PM10 (Davis Air Link), Ozone (AirNow), Smoke (HRRR), Saharan Dust, Pollen.
- **Missing data:** Always show `--` for any metric without data. Never use "Data Unavailable" (it covers up other metrics).
- **Data:** /api/air/summary (PM from pi-wx, ozone from AirNow, smoke from HRRR, dust from CAMS, pollen from NAB). Requires conf/air_api_keys.json. Refresh every 60 s.

## Celestial module — LOCKED

**Do not change without explicit approval.**

- **Module file:** `player/master-mrw/modules/celestial.js`
- **Slot:** Box 6 (SLOTS[5]); move via SLOTS[i]
- **Tile:** 700 × 489 px; explicit X/Y for all elements
- **Row 1 (top 9px):** Sunrise left 24 right 478 | Sunset left 256 right 256 center | Length left 478 right 24 right-align
- **Row 2 (top 161px):** Moonrise left 24 right 478 | Moonset left 256 right 256 center | Phase left 478 right 24 right-align
- **Row 3 (top 318px):** Next Season left 24 right 24 (full width)
- **Fonts:** labels 36px weight 700; values 52px weight 700; Phase and Next Season values weight 500
- **Data:** /api/celestial/summary (astral sun/moon, skyfield phase+seasons; MRW 31.92°N -81.08°W, America/New_York). Refresh every 5 min.
- **Metrics:** sunrise, sunset, day_length (HH:MM), moonrise, moonset, phase (8 phases via skyfield), next_season_start. Missing → `--`.

## Region tile (MRMS Eastern US)
- **Tile:** 1250 × 998 px
- **Embed:** MRMS player at `/player/mrms/` via iframe
- **URL params:** region=eastern_us; frameLimit=36; autoplay=1; opacity=42 — Eastern US view, Play, 36-frame loop, 42% opacity on load

---

## Grid
- **Columns:** 1420 | 1089 | 1250 px
- **Rows:** 998 | 998 px
- **Gap:** 20 px
- **Padding:** 20 px

---

## Wind box — LOCKED

**Do not change without explicit approval.**

- **Location:** Inline in `player/master-mrw/index.html` (center section, not a module)
- **Tile:** 1089 × 744 px
- **Compass:** 360×360 viewBox, ring r=150, stroke 12px; tick/tickMajor stroke 2/3px, translateY(6px)
- **Cardinal labels:** lbl 24px weight 900, letter-spacing 2px; N y=6 translateY(10px); S y=366 translateY(-12px); E x=364 y=186 translateX(-11px); W x=-10 y=186 translateX(12px)
- **Needle:** scale(0.7) around tip (180,44); polygon points 180,44 170,96 180,86 190,96
- **Direction:** 35px, weight 800; #w_dir_txt translateY(2px)
- **Speed (center):** 100px, weight 700
- **MPH label:** 20px, weight 800
- **Corner callouts:** AVG 10, GUST, MAX 10, MAX DAY — label 39px weight 900, value 108px weight 900; direction (e.g. N/NW) 28px weight 700 under each value; MAX DAY only: timestamp (12h am/pm) 28px below direction; top inset 26px, bottom inset 52px
- **Data:** wind.json via pi-wx proxy; extremes.json for MAX DAY

---

## Current Temp module — LOCKED

**Do not change without explicit approval.**

- **Module file:** `player/master-mrw/modules/current-temp.js` (self-contained)
- **Move/remove:** Set `SLOTS[i] = "current-temp"` or `null`; module works in any box 1–8; script always loaded
- **Tile:** 700 × 489 px
- **Left content (right edge 480px):**
  - Labels: 36px; main values: 120px; degF: 48px translateY(3px)
  - Temp: label top 9px, value top 48px, left 16px/14px
  - Heat Index: label top 169px, value top 208px, left 16px/14px
  - THSW: label top 329px, value top 362px, left 16px/14px
- **Right zone (left 500px, right 16px):**
  - Hi/Lo clusters: right 145px; HiLo base 40px; labels 30px; values 55px
  - Temp Hi top 40px, Lo 113px; Heat Hi 200px, Lo 273px; THSW Hi 354px, Lo 417px
  - Time of occurrence: right 16px, font 26px, line-height 1
  - Hi times: top 56px, 216px, 370px
  - Lo times: top 144px, 304px, 448px
- **Temp alert colors:** 95+ yellow, 100+ orange, 105+ red; 40↓ lightblue, 32↓ blue
- **Data:** now.json, wind.json, computed_rt.json, extremes.json via pi-wx proxy

---

## Humidity module — LOCKED

**Do not change without explicit approval.**

- **Module file:** `player/master-mrw/modules/humidity.js`
- **Tile:** 700 × 489 px
- **Data:** now.json, extremes.json via pi-wx proxy (/pi-wx-data/data/*)
- **Move/remove:** Set SLOTS[i] = "humidity" or null; module works in any box 1–8; script always loaded

### Upper row (Humidity, Dew Point)
- **Humidity:** label top 9px left 16px; value top 48px left 14px; font 110px; % at top+12px; max-width 336px overflow hidden
- **Dew Point:** label top 9px right 16px; value top 48px right 14px; font 110px; °F translateY(12px); max-width 336px overflow hidden
- **Dew color scale:** 0–64.9 base; 65–69.9 yellow; 70–74.9 orange; 75–79.9 dark orange; 80+ red

### Solar
- **Label:** top 183px left 16px
- **Value:** top 222px left 14px; font 110px; W/m² 24px; max-width 686px overflow hidden
- **Hi extreme:** humHiLo-solar-hi top 269px, left 14px right 133px, text-align right
- **Hi time:** top 298px right 16px

### UV
- **Label:** top 341px left 16px
- **Value:** top 375px left 14px; font 110px; max-width 686px overflow hidden; bottom at 485px
- **Hi extreme:** humHiLo top 418px right 145px
- **Hi time:** top 447px right 16px
- **UV color scale:** 0–3.9 base; 4–5.9 yellow; 6–7.9 orange; 8–10.9 red; 11+ purple

### Font sizes
- Labels: 36px; main values: 110px; Hum % / Dew °F: 36px; Solar W/m²: 24px; Hi label: 35px; Hi values: 55px; times: 32px

---

## Tide box — LOCKED

**Do not change without explicit approval.**

- **Tile:** 1089 × 744 px
- **Clock:** 360×360 viewBox, ring r=152, stroke 12px
- **Needle:** scale(0.7) around tip (180,44)
- **Main height:** 85px, weight 600
- **State (Rising/Falling):** 30px, weight 700
- **Labels (High Tide, Low Tide, Flow, Ebb):** 16px, weight 900
- **Numbers 1–5:** 34px, weight 900; positioned on inside of circle
- **Red markers:** 8×8 at 0° and 180°
- **Callouts:** tlbl 40px weight 700, tval 60px weight 700, tsub 45px weight 700; inset 16px/13px
- **Data:** tide.json via pi-wx proxy; parseLocal for times
