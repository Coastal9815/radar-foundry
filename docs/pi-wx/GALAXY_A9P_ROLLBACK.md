# Galaxy A9+ dashboard — rollback (pre–Master-standard metrics)

The bundle in `pi-wx-dashboard/galaxy-a9p11/` was aligned with the Master MRW Dashboard and moonriverweather.com metrics in March 2025. If you need the **previous, two-month stable behavior**, use one of the options below.

## Git tag (canonical)

- **Tag:** `galaxy-a9p11-stable-pre-standard-2025-03-24`  
- **Restore files into your working tree** (from repo root):

```bash
git fetch origin tag galaxy-a9p11-stable-pre-standard-2025-03-24 2>/dev/null || true
git checkout galaxy-a9p11-stable-pre-standard-2025-03-24 -- pi-wx-dashboard/galaxy-a9p11/
```

- **Deploy to pi-wx:**

```bash
./bin/deploy_pi_wx_galaxy_a9p11.sh
```

Commit or stash local changes before `git checkout … -- path` if Git refuses to overwrite files.

## What changed after that tag

- Days-since-rain uses `rain.json` + `now.json` (Master `rain-current.js` rules), not only `computed_rt.rain_days_since_stop`.
- Month/year “% normal” uses `rain_norms.json` + prorated expected-to-date (Master `rain-accumulation.js`), not `climatology.json` fractions alone.
- Wind tile: GUST shows **mph**; direction sub-lines match Master; max-day time uses **12-hour am/pm**.
- Temps: heat index / wind chill / THSW use Master priorities, one-decimal display, formula fallback, and optional alert coloring.
- Humidity tile: dew **one decimal** + Master dew/UV color tiers; solar is **not** colored by Galaxy-only thresholds.
- Air PM: prefers **`/api/air/summary`** then `https://api.moonriverweather.com/api/air/summary`, then falls back to **`/data/air.json`**, with Master AQI-style class breakpoints.

## Push the rollback tag to remotes

After the tag was created locally, ensure backups exist on your Git host:

```bash
git push origin galaxy-a9p11-stable-pre-standard-2025-03-24
```
