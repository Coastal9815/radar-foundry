# Local development — port registry (Moon River Weather)

**Scope:** repos in the MRW workspace (**radar-foundry**, **moonriverweather-public**) — static pages and LAN dashboards are usually opened **from wx-i9**; this doc is for **Mac local dev** when you run HTTP servers here.

**Rule:** If a port is busy, **do not kill the listener** until you know what it is. Another project (**Coastal Care Core**, Docker, etc.) may own it. Use **`./bin/weather_dev_status.sh`** from **radar-foundry**.

**Pattern:** Modeled after **`CCP_Core/docs/LOCAL_DEV_PORTS.md`** — fixed ports, `lsof` checks, heuristics for “ours” vs “foreign”, **no silent port fallback**.

---

## Port registry

| Service | Port | Fixed? | Purpose | Where defined | Safe start |
|--------|------|--------|---------|----------------|------------|
| **MRW serve_frames** (local) | **8080** | Yes (`PORT = 8080` in code) | Radar frames + players (`/player/...`), proxies `/pi-wx-data/`, `/api/air/summary`, `/api/celestial/summary` when air/celestial keys exist | `radar-foundry/bin/serve_frames.py` | `./bin/dev_serve_frames_safe.sh` |
| **moonriverweather-public** (Next dev) | **3001** | Yes in `package.json` | Public site dev server | `moonriverweather-public/package.json` → `next dev -p 3001` | `./bin/dev_moonriverweather_safe.sh` or `npm run dev:safe` from moon repo |
| **moonriverweather-public** (`next start`) | **3000** (Next default) | Default if `-p` not passed | Production-mode local test | Next.js default | *No wrapper yet* — if you use `next start`, check **3000** with `weather_dev_status.sh` (add 3000 to script if needed) |

### Not separate local servers (no extra ports in-repo)

These are **not** started as their own Mac dev processes from this workspace:

- **Master MRW Dashboard HTML** — static; usually loaded from **http://192.168.2.2:8080/player/master-mrw/** (wx-i9) or from local **serve_frames** on **8080**.
- **Galaxy A9+** — static UI on **pi-wx** (`~/dashboard/ui/`), not a typical Mac dev server.
- **air_api.py** — invoked **inside** `serve_frames.py` for `/api/air/summary` on the **same** port (**8080**), not a second listener.
- **Data collectors / radar loops** (`run_kclx_loop.sh`, `run_mrms_loop.sh`, etc.) — batch/worker processes; **no** fixed dev port in-repo for Mac (production uses **wx-core** / **wx-i9**).

---

## Conflict risks

| Conflict | Notes |
|----------|--------|
| **3001: CCP_Core vs moonriverweather** | **Coastal Care Core API** defaults to **3001** (`CCP_Core/backend/.env`). **moonriverweather-public** `npm run dev` uses **3001**. **Do not run both.** Options: stop one, or set `MOONRIVERWEATHER_DEV_PORT=3010` (example) and `npx next dev -p 3010 --webpack`, or change Core **PORT** in `backend/.env` for local only. |
| **8080** | Anything else (another `python`, Docker proxy, old `serve_frames`) can block MRW local serve. Safe wrapper **refuses** to start if port is owned by an unknown process. |
| **wx-i9 :8080** | Remote LAN server; does **not** by itself bind your Mac’s **8080**, but don’t confuse **local** `serve_frames` with opening **192.168.2.2:8080** in a browser. |

---

## Commands (operator)

From **radar-foundry** repo root:

| Command | Behavior |
|---------|----------|
| `./bin/weather_dev_status.sh` | Snapshot: **8080** + moonriverweather dev port (default **3001**); shows PID/command via `lsof`; warns about CCP **3001** overlap. |
| `./bin/dev_serve_frames_safe.sh` | If **8080** free **or** already **serve_frames** → start `serve_frames.py`. If foreign process → **exit 1**, print PID/cmd. Optional `MRW_USE_WRAPPER=1` uses `serve_frames_wrapper.sh` (WAITS for `/Volumes/WX_SCRATCH/mrw/radar`). **No** alternate port. |
| `./bin/dev_moonriverweather_safe.sh` | Resolves **moonriverweather-public** next to radar-foundry (or `MOONRIVERWEATHER_ROOT`). Same port logic for **3001** (or `MOONRIVERWEATHER_DEV_PORT`). **No** auto-kill. |

From **moonriverweather-public** (sibling of **radar-foundry**):

| Command | Behavior |
|---------|----------|
| `npm run dev:safe` | Runs safe wrapper via relative path to **radar-foundry** (see `package.json`). |

**Heuristics:** “Ours” uses `ps` command lines (e.g. `serve_frames.py`, `next dev`). **CCP_Core** on **3001** is detected as **foreign** to MRW Next — wrapper **exits with error** so you don’t stomp Core. If you intentionally share **3001**, align ports in config instead.

---

## What this does *not* do

- No Docker, no supervisor, no port reservation daemon.
- Does not stop processes on your machine.
- Does not manage **SSH** / **wx-i9** / **pi-wx** systemd services.
- Does not scan every possible port — only the MRW dev ports in the table above (`next start` **3000** is your responsibility unless we extend the status script).

---

## Related

- **CCP_Core:** `docs/LOCAL_DEV_PORTS.md`, `npm run ports:status`
- **radar-foundry:** `docs/PROJECT.md` § Deployment, `bin/serve_frames.py`
