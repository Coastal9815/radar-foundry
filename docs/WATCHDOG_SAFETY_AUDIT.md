# Watchdog Safety Audit

Audit of watchdog logic to ensure the safety system does not cause problems itself.

---

## 1. watch_wx_core.sh (wx-i9 → wx-core backup)

**Risks identified:**
- **Trigger loop:** wx-i9 triggers watchdog → watchdog kills and kicks → recovery takes 5–10 min → wx-i9 runs again, sees stale, triggers again → kills recovery in progress.

**Safeguards added:**
- **Cooldown:** 20 min after last trigger.
- **Circuit breaker:** After 3 triggers with no recovery, stop. Resets when radar fresh (<5 min). No one present to disable — it disables itself.
- **Stale threshold:** 15 min (was 12).
- **Cooldown file:** `/tmp/mrw_watch_wx_core_triggered_at`
- **Circuit breaker file:** `/tmp/mrw_watch_wx_core_trigger_count`

---

## 2. watchdog_all.sh (wx-core)

**Risks identified:**

| Risk | Mitigation |
|------|------------|
| **MRMS full rebuild killed** | STALE_MRMS was 15 min; full rebuild ~25 min. At 15 min we could kill a legitimate rebuild. | **Fixed:** STALE_MRMS=30. |
| **Killing recovery in progress** | kill_if_stuck uses MIN_KILL_AGE (coord 8 min, MRMS 25 min). Won't kill fresh processes. | Already safe. |
| **Unconditional pkill** | publish_radar_frame, update_radar_loop, fetch_mrms, render_mrms_frame killed when stale. Could hit MRMS mid-rebuild. | STALE_MRMS=30 reduces window; MRMS rebuild completes before we consider stale. |
| **Overlapping runs** | launchd StartInterval=300; if previous run still running, next is skipped. | Already safe. |
| **Self-kill** | pkill patterns don't match "watchdog". | Already safe. |
| **Hanging** | curl -m 5, ssh ConnectTimeout=10. | Already safe. |

---

## 3. launchd / systemd

- **watchdog_all:** StartInterval=300. No ThrottleInterval (not KeepAlive). No overlap.
- **watch_wx_core:** Type=oneshot, timer every 10 min. No overlap.
- **lightning_nex_tail:** KeepAlive + ThrottleInterval=10. Prevents restart storms.

---

## 4. Summary of changes

1. **watch_wx_core.sh:** Cooldown 20 min, stale threshold 15 min.
2. **watchdog_all.sh:** STALE_MRMS 15 → 30 min.

---

## 5. Remaining considerations

- **serve_frames restart:** Only when HTTP fails. No change.
- **NEXRAD/Satellite/Lightning:** Thresholds unchanged; no identified risk.
- **If watchdog misbehaves:** Check `/tmp/mrw_watchdog.log` and `/tmp/mrw_watch_wx_core.log`. Disable cross-machine watch: `sudo systemctl stop mrw-watch-wx-core.timer`.
