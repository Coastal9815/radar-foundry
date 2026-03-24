# MRW Projects — Multi-Root Workspace

When opened via `mrw-multi.code-workspace`, this workspace includes two related projects. **Both are local on the Office Mac.**

---

## 1. radar-foundry (this project)

**Path:** `~/wx/radar-foundry` (local on Office Mac)

**Focus:** Backend products and LAN dashboards

- **Radar products:** NEXRAD (KCLX, KJAX), MRMS, IR/Visible satellite
- **Lightning products:** NexStorm/Boltek, Xweather (hyper-local-x)
- **Master MRW Dashboard:** `player/master-mrw/` — 32" 4K LAN dashboard
- **Serve:** wx-i9:8080 — frames, GeoJSON, players

**Outputs consumed elsewhere:** GeoJSON, JSON summaries, radar frames, lightning points — used by moonriverweather-public for the public website.

---

## 2. moonriverweather-public

**Path:** `/Volumes/Pierce_Archive/Cursor Weather Projects/moonriverweather-public` (local on Office Mac)

**Focus:** Public website — moonriverweather.com

- New moonriverweather.com
- Consumes data/products from radar-foundry (radar, lightning, station data)
- Station data: pi-wx, api.moonriverweather.com

---

## Relationship

```
radar-foundry (products)     pi-wx (station data)
        ↓                            ↓
   wx-i9:8080              api.moonriverweather.com
        ↓                            ↓
        └──────────┬─────────────────┘
                   ↓
        moonriverweather-public (website)
```

**When working across both:** Changes in radar-foundry that affect the public site (new endpoints, schema, product URLs) should be reflected in moonriverweather-public. Check both codebases when touching shared data flows.

---

## Development Architecture

- **Development:** Office Mac — both projects local, no Remote-SSH.
- **Deploy:** Use `bin/seed_radar_foundry_from_wx_core.sh`, `deploy_radar_foundry_to_wx_core.sh`, `deploy_wx_core_to_wx_i9.sh` as needed.
- See `docs/DEVELOPMENT_ARCHITECTURE.md`.

---

## Rule for moonriverweather-public

When the moonriverweather-public folder is available, add `.cursor/rules/mrw-multi-workspace.mdc` with:

```markdown
---
description: Multi-root workspace; moonriverweather-public consumes radar-foundry products.
alwaysApply: true
---

# MRW Multi-Root Workspace

This project (moonriverweather-public) is the new moonriverweather.com website.

**radar-foundry** (sibling folder) produces:
- Radar products (KCLX, KJAX, MRMS, satellite)
- Lightning products (NexStorm, Xweather)
- Served at wx-i9:8080

**Data sources:** wx-i9:8080, pi-wx, api.moonriverweather.com

When changing how this site consumes radar-foundry products, check radar-foundry for schema, endpoints, and URLs. See `docs/MRW_PROJECTS.md` in radar-foundry.
```
