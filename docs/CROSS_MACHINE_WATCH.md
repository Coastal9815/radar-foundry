# Cross-Machine Watch — wx-i9 Watches wx-core

**Purpose:** When you're away, wx-i9 can detect stale radar and trigger wx-core's watchdog as a backup. If wx-core's launchd misses a run or the pipeline hangs, wx-i9 will SSH in and kick recovery.

## Flow

```
wx-core (Mac)                    wx-i9 (Ubuntu)
     │                                │
     │  produces radar frames         │  serves frames
     │  ──────────────────────────►  │
     │                                │
     │  watchdog_all (launchd 5min)    │  watch_wx_core (timer 10min)
     │  restarts serve_frames ──────► │  checks: radar stale?
     │                                │  if yes + wx-core reachable:
     │  ◄──────────────────────────  │  SSH run watchdog_all
```

## Prerequisites

1. **SSH from wx-i9 to wx-core:** `ssh scott@wx-core` must work without password (copy ssh key to wx-core).
2. **wx-core resolvable from wx-i9:** Add to `/etc/hosts` on wx-i9 if needed:
   ```
   192.168.1.220  wx-core
   ```
   (Adjust IP if your topology differs.)

## Install on wx-i9

After syncing radar-foundry to wx-i9:

```bash
ssh wx-i9
cd ~/wx/radar-foundry
sudo cp conf/systemd/mrw-watch-wx-core.service conf/systemd/mrw-watch-wx-core.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mrw-watch-wx-core.timer
sudo systemctl start mrw-watch-wx-core.timer
```

Verify:

```bash
systemctl list-timers | grep mrw-watch
tail -20 /tmp/mrw_watch_wx_core.log
```

## What It Does

- Every 10 min: ping wx-core; if unreachable, log (wx-core may be asleep).
- If reachable and KCLX manifest >15 min old: SSH to wx-core, run `watchdog_all.sh`.
- **Cooldown:** 20 min after last trigger.
- **Circuit breaker:** After 3 triggers with no recovery, stop. Resets when radar is fresh (<5 min). No manual intervention needed.
- Watchdog kills stuck processes, kicks radar/satellite recovery.

## Limitations

- **wx-core asleep:** Ping fails; SSH fails. Nothing can wake it from wx-i9. Set Energy Saver to prevent sleep.
- **wx-core crashed/rebooted:** Launchd jobs restart. Watch resumes when wx-core is back.

## Log

`/tmp/mrw_watch_wx_core.log` on wx-i9. Check when you return if something went wrong.
