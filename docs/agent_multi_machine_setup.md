# Agent Multi-Machine Setup

SSH infrastructure for the AI agent to work across weather-core, wx-i9, pi-wx, wx-display, and the office Mac.

**Development:** Local-first on ScottsMacStudio. Both radar-foundry and moonriverweather-public live in the multi-root workspace under `/Volumes/Pierce_Archive/Weather Projects/`. wx-core and wx-i9 are runtime/deploy targets; code is deployed to `~/wx/radar-foundry` on those machines.

## Machine Roster

| Host | IP | Role |
|------|-----|------|
| weather-core (wx-core) | 192.168.1.220 | Mac Studio — primary compute (KCLX, KJAX, MRMS, IR/Vis); runtime deploy target |
| wx-i9 | 192.168.2.2 | Ubuntu — serve frames, 1TB wx-data; runtime deploy target |
| pi-wx | 192.168.2.174 | Raspberry Pi — WeeWX, weather/station data |
| wx-display (lightning) | 192.168.2.223 | Windows 11 — LIGHTNING-PC; NexStorm Lite, LD-350, .nex archive (read-only); lightning workstation |
| Office Mac (ScottsMacStudio) | — | Cursor runs here; development machine |

---

## SSH Config — Office Mac

`~/.ssh/config` must NOT force password auth or disable public key auth. Use key-based auth with `~/.ssh/id_ed25519`. Example config:

```
Host weather-core
  HostName 192.168.1.220
  User scott
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
  AddKeysToAgent yes
  UseKeychain yes

Host wx-i9
  HostName 192.168.2.2
  User scott
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
  AddKeysToAgent yes
  UseKeychain yes

Host pi-wx
  HostName 192.168.2.174
  User scott
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
  AddKeysToAgent yes
  UseKeychain yes

Host wx-display
  HostName 192.168.2.223
  User scott
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
  AddKeysToAgent yes
  UseKeychain yes

Host lightning
  HostName 192.168.2.223
  User scott
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
  AddKeysToAgent yes
  UseKeychain yes
```

Keys: `~/.ssh/id_ed25519` and `~/.ssh/id_ed25519.pub`. Both `wx-display` and `lightning` alias the same machine (LIGHTNING-PC).

---

## SSH Config — wx-core

On wx-core, for hostname shortcuts to wx-i9 and pi-wx:

```
Host wx-i9
  HostName 192.168.2.2
  User scott

Host pi-wx
  HostName 192.168.2.174
  User scott
```

---

## Trust Model

| From | To |
|------|-----|
| Office Mac | weather-core, wx-i9, pi-wx, wx-display |
| wx-core | wx-i9, pi-wx |

All passwordless via SSH keys. Login passwords remain enabled as fallback.

---

## Agent Authority

The agent has **full authority** to manage pi-wx, wx-i9, and weather-core. Dig in, make changes, connect, pull data. Do not assume lack of access. Do not change working products without discussing with the user first.

## How the Agent Uses This

| Target | Command pattern |
|--------|-----------------|
| weather-core | `ssh weather-core "cd ~/wx/radar-foundry && ./bin/..."` |
| wx-i9 | `ssh wx-i9 "..."` |
| pi-wx | `ssh pi-wx "..."` |
| wx-display / lightning | `ssh wx-display "..."` or `ssh lightning "..."` — read-only pull of .nex data from LIGHTNING-PC |
| Sync files | `rsync -az local/ wx-i9:~/path/` |

---

## Security

- No WAN port forwards
- UPnP disabled
- IPv6 disabled on WAN
- LAN-only; nothing exposed to internet
