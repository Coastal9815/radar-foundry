# Fixed 135 mi Lightning Map

**Fixed-view lightning map.** No zoom, no pan. MRW center, 135 mile radius.

**Player:** `player/local-lightning/`  
**Data:** `lightning_points_v2.geojson`  
**URL:** `/player/local-lightning/`

## Map behavior

| Property | Value |
|----------|-------|
| **Center** | MRW station (31.919173, -81.075938) |
| **Extent** | 135 miles E–W (fixed); N/S derived from viewport aspect ratio |
| **Zoom/Pan** | Disabled — fixed view only |
| **Initial view** | fitBounds to 135 mi extent |
| **Station marker** | Green star (#22c55e) |
| **Strike count radius** | 135 miles |

## Strike behavior

Same as Full View Lightning Map — CG/IC dots, close-zone (25 mi) red bolt/dot, 5-min fade. See `docs/lightning/FULL_VIEW_LIGHTNING_MAP.md`.
