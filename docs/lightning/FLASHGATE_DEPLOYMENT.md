# MRW Lightning — Production Deployment (Lightning-PC)

## Architecture

- **Lightning-PC (192.168.2.223):** NexStorm + LD-350 + FlashGate relay. Lightweight source only.
- **Output:** `C:\MRW\lightning\lightning_rt.ndjson`, `lightning_status.json`, optionally `lightning_noise.ndjson`
- **Session constraint:** Relay must run in the same Windows interactive session as NexStorm (FlashGate IPC is session-scoped)

## Automated Pipeline

1. **Startup folder:** `MRW Lightning.lnk` → `start_lightning_pipeline.vbs` (runs hidden)
2. **Pipeline:** `start_lightning_pipeline.bat` starts NexStorm (if not running), waits 45s, runs relay in loop (restart on crash)
3. **Relay:** `flashgate_relay.exe` with `--retry-sec 600` (retries discovery for 10 min until NexStorm IPC appears)

## Deploy (from wx-core)

```bash
cd /path/to/radar-foundry
./scripts/lightning/windows/deploy_to_lightning_pc.sh
```

## 24/7 Unattended: Autologon (one-time setup)

Run **once** on Lightning-PC as Administrator:

```powershell
powershell -ExecutionPolicy Bypass -File C:\MRW\lightning\setup_autologon.ps1 -Username scott -Password YOUR_PASSWORD
```

After that: Boot → Autologon → Startup runs pipeline → NexStorm + relay run in user session.

## Start Immediately (if already logged in)

Log off and log back in. The Startup shortcut will run the pipeline.

Or double-click `C:\MRW\lightning\start_lightning_pipeline.vbs` (runs hidden).

## Verify

```bash
ssh scott@192.168.2.223 "type C:\\MRW\\lightning\\lightning_status.json"
```

Expect `relay_running: true` and `total_messages` / `total_strikes` counters.
