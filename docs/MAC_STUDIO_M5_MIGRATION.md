# Mac Studio M4 Max → M5 Ultra migration runbook

Scott's main workstation ("Scott's Mac Studio", `scottpierce`) moves from the
M4 Max (1 TB internal, 128 GB) to a new M5 Ultra. The Thunderbolt 5 NVMe dock
and the T7 mirror are **kept** and simply re-plugged into the M5. The M5
becomes "this computer": same account short name, same hostname, same
Tailscale identity, same `/Volumes/...` paths.

Status log is at the bottom. Agent-maintained; update as steps complete.

---

## 1. Inventory (captured 2026-10-18)

### Dock and external storage (move with the dock, nothing to copy)

| Volume | Device | Used | Holds |
|---|---|---|---|
| `CCP_Dropbox` | Samsung 990 EVO 2 TB (NVMe, in TB5 dock) | 376 GB | Dropbox Business root `/Volumes/CCP_Dropbox/Coastal Care Finance Dropbox`, `CCP_Core` + worktrees, `Cursor Riverwatch_Smart`, `Cursor CCP Web Work`, Finance Engine, Diligence, `_agent-bus`, `CCP_Backups` |
| `Pierce_Archive` | WD_BLACK SN7100 4 TB (NVMe, in TB5 dock) | 964 GB | `Cursor Weather Projects` (radar-foundry, moonriverweather-public), archive folders |
| `Cursor Backup` | Samsung PSSD T7 4 TB (USB) | 62 GB | Mirror of `CCP_Dropbox` project folders |

Dock: Intel "TBT5" Thunderbolt 5 enclosure. Also on Thunderbolt: Sonnet Solo
10G NIC (carries LAN 192.168.2.108 and 192.168.0.212; DHCP reservations are
on the Sonnet's MAC, so they follow the NIC, not the Mac).

"Backups of Scott's Mac Studio" in `/Volumes` is the Time Machine sparsebundle
mounted from the UGREEN NAS (`Backups_Tier1`), not a local disk.

All three external volumes are unencrypted APFS. FileVault is on for the
internal drive.

### Internal drive (must migrate) — 462 GB used

- Home `~` ≈ 225 GB. Largest: `~/Library/Application Support/Cursor` 89 GB
  (70 GB `User/` = chat/workspace history, 16 GB `snapshots`), Google 12 GB,
  Claude 8 GB, Xcode CoreSimulator 24 GB, iTunes 10 GB, `~/.npm` 10 GB,
  `~/.android` + `~/.gradle` 8 GB, `~/wx/radar-foundry` 6.8 GB (stale, see §3).
- `~/.cursor` 674 MB: projects (agent transcripts), plans, skills, plugins,
  extensions, MCP state. Project keys embed absolute paths; unchanged because
  the dock paths are identical on the M5.
- **Local Postgres 16** `/opt/homebrew/var/postgresql@16` (5.4 GB):
  `ccp_core_local`, `ccp_core_chart`, `ccp_finance_local`. CCP_Core dev API DB.
  Postgres 18 is installed but nearly empty (39 MB).
- Homebrew `/opt/homebrew` (134 formulae, 3 casks). Node 25.9 via fnm
  (`~/.local/share/fnm`).
- Credentials: `~/.ssh` (`id_ed25519`, `id_rsa`, `config` with wx-core /
  wx-i9 / pi-wx / wx-display / lightning / macstudio / ha-nuc / pi-flow),
  `~/.mrw/homeassistant.env`, `~/.aws`, `~/.railway`, `~/.config/gh`,
  `~/.config/vercel-plugin`, `~/.claude`, login Keychain (gh token lives
  there), Tailscale, Dropbox Business link, OneDrive.
- User LaunchAgents: `com.coastalcare.axiscare-scheduled-visits` (fnm node +
  `~/Library/Application Support/CoastalCare/sync-axiscare-scheduled-visits.cjs`),
  `homebrew.mxcl.postgresql@16`, `com.github.facebook.watchman`.
- System LaunchDaemons/Agents (non-Apple): Adobe, Malwarebytes, Microsoft
  (OneDrive/AutoUpdate/Office licensing), Jump Desktop Connect, QZ Tray,
  Zoom, ExpressVPN.
- Apps: Cursor, Adobe Acrobat + CC, MS 365 (Word/Excel/PPT/Outlook/Teams/
  OneNote/OneDrive), Xcode, Tailscale, ExpressVPN, Jump Desktop Connect,
  QZ Tray, Carbon Copy Cloner, superwhisper, Dropbox, Hue Menu, RadarScope,
  Home Designer Pro 2023, Affinity Designer 2, Malwarebytes, Windows App,
  balenaEtcher, Raspberry Pi Imager, Chrome.

### Identity

- ComputerName `Scott's Mac Studio`, LocalHostName `Scotts-Mac-Studio`.
- Tailscale node `scotts-mac-studio` = 100.99.92.89 (referenced only by the
  `macstudio` alias in `~/.ssh/config`).
- macOS 26.6.2 (25G83).

---

## 2. Approach

**Migration Assistant, Mac-to-Mac over a Thunderbolt cable**, dock and T7
disconnected from both machines during the transfer. Keep the `scottpierce`
short name so `/Users/scottpierce/...`, Homebrew ownership, and the AxisCare
LaunchAgent paths stay valid. Carries apps, Homebrew, Keychain, LaunchAgents,
Cursor state in one pass.

Rejected: fresh install + selective copy (a day of re-auth for no gain);
restore from NAS Time Machine (slow over SMB for ~400 GB).

---

## 3. Pre-migration (on the M4, before the M5 arrives)

### 3a. Safety copies — DONE 2026-10-18

- [x] `pg_dumpall` → `/Volumes/CCP_Dropbox/CCP_Backups/mac-studio-m4-migration/pg16_dumpall_20261018_1113.sql`
      (4.2 GB, 3 databases, "cluster dump complete").
- [ ] Confirm Time Machine has a backup from today (System Settings → General
      → Time Machine; terminal needs Full Disk Access).
- [ ] Refresh the T7 `Cursor Backup` mirror of `CCP_Dropbox` (CCC).
- [ ] Copy `~/.ssh`, `~/.mrw`, `~/.aws`, `~/.railway`, `~/.config/gh`,
      `~/.gitconfig`, `~/.zshrc`, `~/.zprofile`, user `LaunchAgents/*.plist`,
      and `~/Library/Application Support/CoastalCare/` to the same backup
      folder (belt and braces; MA should carry them).
- [ ] `brew bundle dump` → `Brewfile` in the backup folder.

### 3b. Cleanup (recommended; deletes regenerable data only) — PENDING GO

Approx. 65–70 GB. Nothing here is state.

| Target | Size | Why safe |
|---|---|---|
| `~/Library/Developer/CoreSimulator` (23 simulator devices) | 24 GB | Xcode recreates on demand |
| `~/Library/Developer/Xcode/DerivedData` | 4.9 GB | build cache |
| `~/.npm/_cacache` | ~10 GB | npm cache |
| `~/Library/Caches/*` (Google, CocoaPods, Cursor ShipIt, Homebrew, Raspberry Pi) | 12 GB | caches |
| `~/.gradle/caches`, `~/.android` emulator images if unused | ~8 GB | regenerable |
| `~/wx/radar-foundry` (not a git repo, last touched 2026-03-16, mostly `scratch/` + `backups/`) | 6.8 GB | stale copy; canonical repo is on `Pierce_Archive` |
| `~/.cursor-server` | 0.8 GB | remote-SSH server cache |
| `~/Library/Caches/com.todesktop.230313mzl4w4u92.ShipIt` | 1.4 GB | old Cursor updaters |

**Keep** (state, not cache): all of `~/Library/Application Support/Cursor`
including `snapshots`, `~/.cursor`, Claude, Postgres, `~/.ssh`, `~/.mrw`.

### 3c. License / seat releases on the M4

- [ ] Adobe Creative Cloud: sign out (device limit).
- [ ] Home Designer Pro 2023 (Chief Architect): deactivate license on M4.
- [ ] Malwarebytes: deactivate seat.
- [ ] Microsoft 365: sign out of Office apps (optional; seats are reclaimable).
- [ ] Jump Desktop Connect / QZ Tray: note settings; they get new machine IDs.

### 3d. Services that should not be mid-flight

- [ ] Quit Dropbox, OneDrive, Cursor before starting MA.
- [ ] `brew services stop postgresql@16` right before MA so the data dir is
      quiescent (restart after if the M4 stays in use).

---

## 4. Migration day

1. Unbox M5. Run Setup Assistant far enough to **update macOS to ≥ 26.6.2**
   (MA requires target ≥ source). Do not create the final user yet if the
   installer allows deferring; otherwise create a throwaway admin and let MA
   replace/merge into `scottpierce`.
2. On the M4: quit Dropbox, OneDrive, Cursor; `brew services stop postgresql@16`.
3. **Unplug the TB5 dock and the T7 from the M4.** Leave the Sonnet NIC on
   the M4 for now (M5 can use built-in Ethernet or Wi-Fi during MA).
4. Connect M4 ↔ M5 with a Thunderbolt cable. Run Migration Assistant on both
   (M4: "To another Mac"; M5: "From a Mac"). Transfer the user account,
   Applications, and "Other files and folders" (this is `/opt/homebrew`).
   Account short name must remain `scottpierce`.
5. On first login to the M5, **do not launch Dropbox yet.**
6. Shut down the M4. Move the TB5 dock, the T7, and the Sonnet NIC to the M5.
7. Verify in Terminal:
   ```
   ls /Volumes            # CCP_Dropbox, Pierce_Archive, "Cursor Backup"
   diskutil list external
   ```
8. Launch Dropbox. It should relink to
   `/Volumes/CCP_Dropbox/Coastal Care Finance Dropbox` without re-download.
   If it offers to create a new Dropbox folder, cancel, confirm the volume is
   mounted, and retry; do not accept a new location.

---

## 5. Post-migration verification (M5)

```
brew doctor
brew services start postgresql@16
psql -h localhost -U scottpierce -l         # expect ccp_core_local, ccp_core_chart, ccp_finance_local
fnm current && node -v                      # 25.x
launchctl list | grep -E "coastalcare|postgresql|watchman"
ssh wx-core hostname; ssh wx-i9 hostname; ssh pi-wx hostname; ssh ha-nuc hostname
gh auth status; vercel whoami; railway whoami
tailscale status
```

- Cursor: sign in; open `Cursor Weather Projects`, `CCP_Core`,
  `Cursor Riverwatch_Smart`; confirm chat history and agent transcripts are
  present.
- CCP_Core: `npm run dev:backend` smoke test against local Postgres.
- Dropbox and OneDrive both report "Up to date".
- Time Machine: either `tmutil inheritbackup` the existing NAS history or
  start a new backup set; decide and record below.
- Re-authenticate: Adobe CC, Home Designer Pro, Malwarebytes, Microsoft 365,
  Affinity, superwhisper, ExpressVPN, RadarScope, Jump Desktop Connect,
  QZ Tray.

### Network identity continuity (audited 2026-10-18)

**How this Mac is addressed today**

| Address | Interface | MAC | Assignment | Notes |
|---|---|---|---|---|
| **192.168.0.212** | Sonnet Solo 10G (TB, `en11`) | `00:30:93:1d:0a:f4` | DHCP from UniFi gateway 192.168.1.1, 24 h lease | **Default route. Every SSH/HTTP session to the stack originates from this IP** (verified: `$SSH_CLIENT` on wx-core, wx-i9, pi-wx, ha-nuc, pi-filter all show 192.168.0.212). Documented in Riverwatch `docs/network-topology.md` as Pro Max SFP+2. |
| 192.168.2.108 | Wi-Fi (`en1`) | `76:01:cb:19:cd:0e` (**Private Wi-Fi Address**, randomized) | DHCP, 24 h lease | Backup path only. Nothing in any repo or host references it. Will change on the M5 regardless. |
| 100.99.92.89 | Tailscale `scotts-mac-studio.tailf04fbe.ts.net` | — | Tailnet | Referenced only by `Host macstudio` in this Mac's own `~/.ssh/config`. Key expiry 2027-03-22. |

The LAN is one flat /22 (`255.255.252.0`, gateway 192.168.1.1), so
192.168.0.x / 1.x / 2.x / 3.x are the same broadcast domain; the
"1.x ↔ 2.x routing" language in older docs is really just the one subnet.

**What references this Mac from the stack side: nothing.** Audited
`~/.ssh/config`, `/etc/hosts`, launchd/systemd units, crontabs, nginx,
WeeWX, HA `/config`, pi-filter `~/monitor`, radar-foundry `bin/conf/docs` on
wx-core, wx-i9, pi-wx, ha-nuc, pi-filter, plus both Cursor repos and the
agent bus. No IP allowlists (wx-i9 UFW inactive; HA has no `http:`
allowlist). All access is outbound from this Mac using `~/.ssh/id_ed25519`,
which Migration Assistant carries, and the public key is already in
`authorized_keys` on wx-core (6 entries), wx-i9 (3), pi-wx (5), pi-filter (3).

**Why the M5 keeps 192.168.0.212 automatically:** the address is bound to the
Sonnet NIC's MAC, and the Sonnet moves to the M5. UniFi identifies the client
by MAC, so the client name, any Fixed IP, and any firewall rules follow it.
The M5 will come up as the same client on the same port.

**UniFi Fixed IP — CONFIRMED 2026-10-18.** UniFi client `ScottsMacStudio 0a:f4`
(`00:30:93:1d:0a:f4`) has **Fixed IP Address = 192.168.0.212** enabled.
Nothing to do here; the M5 inherits it the moment the Sonnet NIC is plugged in.

**Migration-day order for networking:**
1. During Migration Assistant the M5 may use built-in Ethernet or Wi-Fi; it
   will get a throwaway address. Fine.
2. After MA, move the Sonnet NIC to the M5 **before** verifying the stack.
   Confirm: `ipconfig getifaddr en<N>` → 192.168.0.212 and
   `route -n get default | grep interface` → the Sonnet device.
3. Set Network service order so the Sonnet is first. Turn Wi-Fi off (or leave
   it as a non-default backup) to avoid dual-homing.
4. Verify outbound from the M5: `ssh wx-core 'echo $SSH_CLIENT'` → must
   print `192.168.0.212`. Repeat for wx-i9, pi-wx, ha-nuc, pi@192.168.1.124.
5. Verify the HA REST calls the smart-home scripts use:
   `curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $HA_MAIN_TOKEN" http://192.168.1.230:8123/api/` → `200`.

**Tailscale:** the M5 registers as a new node (`scotts-mac-studio-1`). In the
admin console: delete the M4 node, rename the M5 to `scotts-mac-studio`, and
use *Edit machine IPv4* to assign **100.99.92.89** so the `macstudio` alias
and MagicDNS name keep working unchanged. Otherwise update `~/.ssh/config`.

**Inbound to this Mac:** Remote Login (22), Screen Sharing (5900), SMB (445),
Dropbox LAN sync, QZ Tray (8181/8182), AirPlay receiver are all enabled.
No stack host connects *into* this Mac. Jump Desktop Connect will need the
M5 registered as a new computer. If anything on the laptop has the M4 in
`known_hosts`, the new host key will warn once; `ssh-keygen -R` there.

**Verification script (run on the M5 after step 2):**
```
for h in wx-core wx-i9 pi-wx ha-nuc; do printf '%-8s ' $h; ssh -o ConnectTimeout=5 $h 'echo $SSH_CLIENT' | awk '{print $1}'; done
ssh -o ConnectTimeout=5 pi@192.168.1.124 'echo $SSH_CLIENT' | awk '{print "pi-filter "$1}'
```
Every line must end in `192.168.0.212`.

---

## 6. Decommission the M4

Keep the M4 powered off but intact for **one week** after the M5 passes §5.
Then: sign out of iCloud, `Erase All Content and Settings`.

---

## 7. Agent-bus note

Post a handoff in `/Volumes/CCP_Dropbox/_agent-bus/handoffs.md` on migration
day: monitor-facing identity of this Mac (Tailscale IP, SSH host key) changes;
LAN IPs do not. pi-filter monitor does not currently check this workstation.

---

## Status log

- 2026-10-18 11:13 — Inventory captured. `pg_dumpall` taken to CCP_Dropbox.
  Decisions: Mac-to-Mac MA; selective cleanup approved in principle; M5 takes
  over the same name and identity.
- 2026-10-18 11:20 — Brewfile + dotfile/credential copies staged in the
  backup folder. Network identity audited across all stack hosts: no
  references to this Mac anywhere; all access is outbound from 192.168.0.212
  on the Sonnet NIC, which moves with the dock.
- 2026-10-18 11:29 — Scott confirmed UniFi already has Fixed IP 192.168.0.212
  on `00:30:93:1d:0a:f4`. LAN identity is fully pinned.
- 2026-10-20 15:05 — Migration day prep. macOS still 26.6.2. Fresh
  `pg16_dumpall_20261020_1505.sql` (4.2 GB) taken. Cleanup (§3b) executed:
  simulators, DerivedData, npm/Gradle/Android caches, `~/wx`,
  `~/.cursor-server`, user caches, `brew cleanup` — ~60 GB of live files
  removed (Data volume still shows 465 GB because 9 APFS local snapshots hold
  the blocks; MA copies live files only, so the transfer shrinks regardless).
  Cursor state verified intact (91 GB + 679 MB).
