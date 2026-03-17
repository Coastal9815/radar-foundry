# UniFi Network Security Checklist

Use this to ensure nothing on your LAN is exposed to the internet without your knowledge. Run through it on your UniFi Dream Machine Pro Max.

---

## 1. Port Forwarding (most common exposure)

**Path:** UniFi Network app → Settings → Security → Port Forwarding

**Check:** List should be **empty** unless you intentionally added a rule.

**Action:** Delete any rules you don't recognize. If you need to expose something later (e.g. a web app), add it explicitly and document it.

---

## 2. UPnP (auto-opens ports)

**Path:** Settings → Advanced Features → Advanced Gateway Settings  
*Or:* Settings → Services → UPnP (classic layout)

**Check:** UPnP should be **disabled**.

**Action:** Turn it off. UPnP lets devices open ports without your approval.

---

## 3. DMZ

**Path:** Settings → Firewall & Security (or similar)

**Check:** DMZ should be **disabled** or **not configured**.

**Action:** If a host is in the DMZ, remove it. DMZ sends all unsolicited internet traffic to that host.

---

## 4. UniFi Teleport / Remote Access

**Path:** Settings → System → UniFi Teleport (or Remote Access)

**Check:** Know whether you use Teleport or any Ubiquiti remote access.

**Action:** If you use it, understand it creates a VPN tunnel. Your LAN stays behind the firewall; only your connected device gets access. This is controlled by you.

---

## 5. Firewall rules (WAN → LAN)

**Path:** Settings → Security → Firewall Rules

**Check:** Look for rules that allow traffic **from WAN** to your LAN.

**Action:** Default is to block WAN→LAN. Any allow rule from WAN is an intentional exposure. Document each one.

---

## 6. IPv6 (if enabled)

**Path:** Settings → Networks → [your network] → IPv6

**Check:** If IPv6 is enabled, devices may have global addresses.

**Action:** Either disable IPv6, or add firewall rules so WAN→LAN is blocked for IPv6 as well.

---

## 7. Document what you expose

Keep a simple list, e.g.:

| Service        | Port | Internal IP   | Purpose        |
|----------------|------|---------------|----------------|
| (none yet)     | —    | —             | —              |

When you add something (e.g. a weather dashboard), add a row and a matching port-forward rule.

---

## Quick audit (run periodically)

1. Port Forwarding: empty
2. UPnP: off
3. DMZ: off or unset
4. Firewall: no WAN→LAN allow rules unless documented

If all four are true, your LAN is not exposed to the internet.
