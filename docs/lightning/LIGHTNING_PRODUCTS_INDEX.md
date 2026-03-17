# MRW Lightning Products Index

This document lists every machine-readable lightning product produced by the MRW lightning system.

These products power dashboards, maps, radar overlays, and alert systems.

All products follow the MRW architecture rule:

**sensor → normalized product → derived product → consumer**

---

## Core Lightning Stream

### lightning_rt.ndjson

**Purpose:** Canonical real-time strike stream produced from NexStorm extraction.

**Source:** LD-350 → NexStorm → nxutil → lightning pipeline

**Used By:** All downstream lightning products.

---

## System Health Product

### lightning_status.json

**Purpose:** Lightning pipeline health monitoring.

**Used By:**
- MRW system dashboards
- watchdog processes
- system monitoring

**Key Fields:**
- `relay_running`
- `last_message_at_utc`
- `last_success_at_utc`
- `last_strike_at_utc`
- `total_strikes`
- `last_error`

---

## Operational Lightning Summary

### lightning_recent.json

**Purpose:** Operational lightning intelligence summary.

**Used By:**
- dashboards
- lightning maps
- system displays

**Example Fields:**
- `last_strike_time`
- `nearest_strike_distance`
- `nearest_strike_bearing`
- `strikes_last_5_min`
- `strikes_last_10_min`
- `strikes_last_15_min`
- `trend`
- `computed_at_utc`

---

## Mapping Product

### lightning_points_v2.geojson

**Purpose:** Strike position product used by lightning map players.

**Used By:**
- regional lightning map
- dashboard map players
- radar/lightning fusion displays

**Contains:**
- strike coordinates
- strike type
- strike age
- symbol lifecycle behavior

---

## Operational Intelligence Product

### lightning_summary.json

**Purpose:** High-level lightning intelligence product used by dashboards and alert logic.

**Used By:**
- MRW dashboards
- lightning alert engine
- map information panels
- website displays

**Important:** Dashboards, maps, and alert systems must read `lightning_summary.json`. They must NOT compute these metrics themselves. The lightning processing layer is responsible for producing the intelligence products.
