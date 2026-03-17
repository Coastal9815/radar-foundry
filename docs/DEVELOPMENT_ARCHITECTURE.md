# MRW Development Architecture

**Local-first development on Office Mac.** Runtime remains on wx-core, wx-i9, pi-wx.

---

## 1. Overview

| Layer | Location | Role |
|-------|----------|------|
| **Development** | Office Mac | Edit radar-foundry and moonriverweather-public locally; single multi-root workspace |
| **Runtime: pipelines** | wx-core (weather-core) | launchd jobs, pollers, fetch/render/publish |
| **Runtime: serving** | wx-i9 | serve_frames, HTTP 8080, radar frames, players |
| **Runtime: station** | pi-wx | WeeWX, live weather data |

---

## 2. Development Machine (Office Mac)

**Paths:**

| Project | Path |
|---------|------|
| radar-foundry | `~/wx/radar-foundry` |
| moonriverweather-public | `/Volumes/Pierce_Archive/Weather Projects/moonriverweather-public` |

**Workspace:** Open `mrw-multi.code-workspace` to work on both projects in one Cursor window.

**Workflow:**
1. Edit code locally on the Office Mac.
2. When ready to deploy: run deploy helpers to sync to wx-core and/or wx-i9.
3. No Remote-SSH required for development.

---

## 3. Runtime Machines (unchanged)

| Host | Role |
|------|------|
| **wx-core** (weather-core) | Fetches NEXRAD/MRMS/GOES, lightning; renders frames; publishes to wx-i9; launchd jobs |
| **wx-i9** (192.168.2.2) | Serves HTTP 8080; frames, players, GeoJSON |
| **pi-wx** (192.168.2.174) | WeeWX, station data; wx-i9 proxies /pi-wx-data/* |

---

## 4. Deploy / Sync Flow

```
Office Mac (development)
    │
    ├── seed_radar_foundry_from_wx_core.sh   ← initial pull from wx-core
    │
    ├── deploy_radar_foundry_to_wx_core.sh  ← push code to wx-core (pipelines)
    │
    └── deploy_wx_core_to_wx_i9.sh           ← run sync_to_wx_i9 ON wx-core (pushes to wx-i9)
         (or: deploy_radar_foundry_to_wx_i9.sh for code-only push from Mac)
```

**When to use:**
- **Seed:** One-time or occasional pull from wx-core to get latest code/data layout.
- **Deploy to wx-core:** After editing code; needed before pipelines use new logic.
- **Deploy to wx-i9:** After player/config changes; sync_to_wx_i9 is best run from wx-core (has lightning ndjson for geo generators).

---

## 5. Script Categories

See `docs/DEVELOPMENT_IMPLEMENTATION_PLAN.md` for full script categorization.
