# Master MRW Dashboard — Project Spec

**Status:** Skeleton built — `player/master-mrw/index.html`

**Target:** LAN-only dashboard for 32" 4K monitor (3840×2160), served by Windows Beelink mini PC.

---

## Overview

A modular, configurable Master MRW Dashboard that combines:
- **Local realtime data** (Davis/pi-wx) — same sources as galaxy14/iphone
- **Embedded radar products** — Nexrad, regional radar, lightning, etc. from radar-foundry
- **Live conditions/threat bar** — full-width top bar with intelligent, priority-ordered alerts

---

## 1. Conditions/Threat Bar (Top)

- **Full bar** across the top
- **Dynamic** — priority-ordered alerts
- **Display modes:**
  - **Active alerts:** Scroll OR cycle through alerts every few seconds (TBD which feels better)
  - **Quiet mode:** Show current 2-day NWS forecast + predicted days till rain
- **Priority order:** To be defined (e.g., NWS warnings > watches > advisories; local: lightning > high heat > high wind > …)
- **Sources:** NWS alerts, locally generated (lightning, high heat index, high wind, etc.)

---

## 2. Layout & Modules

- **Configurable** — insert/remove modules, reconfigure layout by desire
- **Module count:** TBD — build initial page, review on 32" monitor, iterate
- **Radar/Satellite:** Larger tiles
- **Modular design** — add/remove/reorder as we build more products

---

## 3. Data Sources

- **Local JSON:** pi-wx `http://192.168.2.174/data/` (now.json, computed_rt, extremes, wind, rain, air, tide, astro, threat_strip, threat_windows, etc.)
- **Radar products:** TBD — use best available (radar-foundry publish path)
- **NWS:** threat_strip, threat_windows, forecast72, forecast72_hourly

---

## 4. Technical Approach

- **Module registry** — each module = config (id, data source, refresh interval, render)
- **Config-driven layout** — JSON/JS config for modules, order, size, refresh; edit config, no code changes for layout
- **Tech stack:** Vanilla JS + HTML + CSS (keep it simple)
- **4K typography:** Use clamp() or viewport units for scaling

---

## 5. Open Items (When We Return)

- [ ] Threat bar: scroll vs cycle timing
- [ ] Final priority order for alerts
- [ ] Radar product URLs and embed format
- [ ] Initial module set and grid layout
- [ ] Theme (dark vs light for 4K always-on)

---

*Captured 2025-03-06. Resume when ready.*
