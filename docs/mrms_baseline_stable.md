# MRMS Baseline — Stable (2026-03-07)

**Mark this state before attempting coverage/quality improvements.**

## What Works

- **Projection**: Radar overlay aligns with Mapbox base map (coastlines, borders).
- **Pipeline**: Fetch from S3 → render per region → publish to wx-i9.
- **Regions**: 6 regions (eastern_us, florida_south, southeast, florida, georgia, savannah_250).
- **Players**: Desktop and mobile at http://192.168.2.2:8080/player/mrms/
- **Freshness**: Run every 5 min; target latest ≤10 min old; watchdog at 15 min.

## Key Parameters (do not change without testing)

| Parameter | Value | Location |
|-----------|-------|----------|
| eastern_us bounds | -98 to -75 lon, 24 to 38 lat | `conf/mrms_regions.json` |
| figsize | (12, 10) | `bin/render_mrms_frame.py` |
| dpi | 150 | `bin/render_mrms_frame.py` |
| LAT_OFFSET_DEG | -0.29 | `bin/render_mrms_frame.py` |
| light echo alpha | 0.25 (first 3 levels, 5–20 dBZ) | `bin/render_mrms_frame.py` |

## Known Limitation

- **eastern_us** radar extent is smaller than the map viewport at zoom 5.49. Map shows more area than radar covers.

## What We Want Next

1. **Full coverage**: Radar image fills the map viewport (no blank margins).
2. **Sharp**: Maintain or improve resolution when expanding extent.
3. **Aligned**: Projection must stay correct on Mapbox.

## What Broke (avoid)

- Expanding bounds without reprojection → projection drifted.
- Variable figsize / pixels_per_degree → projection drifted.
- Likely cause: equirectangular (1° lon = 1° lat) does not match Web Mercator at mid-latitudes.

## Implemented (2026-03-07)

**Eastern US**: Web Mercator reprojection works. Bounds -110 to -62, 22 to 48, width_px 4096.

**Florida South**: Alignment was wrong when bounds were expanded. Reverted to original bounds (-84.82 to -79.53, 26.28 to 31.56), still using Web Mercator render. Needs investigation.

**Opacity slider**: Radar overlay opacity 30–100%, persisted in localStorage. Desktop: `mrw_mrms_opacity`, mobile: `mrw_mobile_mrms_opacity`.
