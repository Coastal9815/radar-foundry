# pi-wx dashboard assets (version controlled)

Static HTML/JS served on **pi-wx** (`192.168.2.174`) for LAN phones/tablets (e.g. Samsung Galaxy).

## Galaxy A9+ (`/ui/galaxyA9p11.html`)

| File | Role |
|------|------|
| `galaxy-a9p11/galaxyA9p11.html` | Main shell (grid, wind tile, inline styles) |
| `galaxy-a9p11/a9p_header.js` | Header / chips |
| `galaxy-a9p11/a9p_rain.js` | Rain tile |
| `galaxy-a9p11/a9p_rain_accum.js` | Rain accumulation |
| `galaxy-a9p11/a9p_threat.js` | Threat strip / NWS dots |
| `galaxy-a9p11/a9p_tide.js` | Tide clock |

**Runtime data:** Fetches `/data/*.json` on pi-wx (same generators as MRW). Scripts load from `/ui/*.js` (nginx path → `~/dashboard/ui/`).

## Workflow

1. Edit files under `pi-wx-dashboard/galaxy-a9p11/` in **radar-foundry** (commit to git).
2. Deploy to pi-wx: `bin/deploy_pi_wx_galaxy_a9p11.sh`
3. Spot-check: `curl -sS -o /dev/null -w '%{http_code}\n' http://192.168.2.174/ui/galaxyA9p11.html`

The agent uses this tree as **source of truth**; ad hoc edits on the Pi should be avoided without syncing back here.

## Related

- `docs/pi-wx-weather-inventory.md` — JSON generators and paths on pi-wx
