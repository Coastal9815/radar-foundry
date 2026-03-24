# AirLink + WeeWX — poll interval and timeout (pi-wx)

**Host:** pi-wx (`192.168.2.174`)  
**Purpose:** Reduce AirLink HTTP timeouts and log spam by using a **longer HTTP timeout** and **slower background polling**. The stock `weewx-airlink` extension **ignores** `poll_interval` in `weewx.conf` (it is hardcoded to 5 seconds), so a **small patch** to `airlink.py` is required for configurable polling.

**Tracked in repo:**

- This document — full procedure and `weewx.conf` snippet  
- `patches/pi-wx/weewx-airlink-poll-interval.patch` — apply after extension upgrades

---

## 1. `weewx.conf` — `[AirLink]` section

Merge or replace the `[AirLink]` block so it includes:

- `poll_interval` — seconds between background HTTP fetches to the AirLink (e.g. **30**).  
- `timeout` — per-request timeout in seconds (e.g. **12**; stock default in extension is **10**, pi-wx previously used **2** which was too aggressive).

Example (values can be tuned):

```ini
[AirLink]
    poll_interval = 30
    [[Sensor1]]
        enable = True
        hostname = 192.168.1.167
        port = 80
        timeout = 12
    [[Sensor2]]
        enable = False
        hostname = airlink2
        port = 80
        timeout = 12
```

Then:

```bash
sudo systemctl restart weewx
```

Confirm in logs:

```text
user.airlink: Source 1 for AirLink readings: 192.168.1.167:80, timeout: 12
```

---

## 2. Patch `airlink.py` — honor `poll_interval`

**On pi-wx**, the extension usually lives at:

`/etc/weewx/bin/user/airlink.py`

(Paths may differ if WeeWX is installed elsewhere; locate with `find /etc/weewx /usr/share/weewx -name airlink.py 2>/dev/null`.)

**After** upgrading or reinstalling `weewx-airlink`, re-apply the patch from this repo:

```bash
# From a copy of radar-foundry on the Office Mac or after git pull:
scp patches/pi-wx/weewx-airlink-poll-interval.patch pi-wx:/tmp/
ssh pi-wx
cd /etc/weewx/bin/user
sudo cp -a airlink.py "airlink.py.bak.$(date +%Y%m%d%H%M)"
sudo patch -p0 --dry-run < /tmp/weewx-airlink-poll-interval.patch   # verify
sudo patch -p0 < /tmp/weewx-airlink-poll-interval.patch
sudo systemctl restart weewx
```

The patch replaces the hardcoded `poll_interval = 5` in `AirLink.__init__` with:

`airlink_poll_interval = to_int(self.config_dict.get('poll_interval', 5))`

so the value under `[AirLink]` in `weewx.conf` is used.

---

## 3. Manual edit (if `patch` is unavailable)

In `airlink.py`, inside `AirLink.__init__`, change:

```python
        self.config_dict = config_dict.get('AirLink', {})

        self.cfg = Configuration(
            ...
            poll_interval    = 5,
```

to:

```python
        self.config_dict = config_dict.get('AirLink', {})
        airlink_poll_interval = to_int(self.config_dict.get('poll_interval', 5))

        self.cfg = Configuration(
            ...
            poll_interval    = airlink_poll_interval,
```

(`to_int` is already imported via `weeutil.weeutil` in this module.)

---

## 4. Rollback

- Restore `airlink.py` from backup: `sudo cp airlink.py.bak.* airlink.py`  
- Restore `weewx.conf` from backup  
- `sudo systemctl restart weewx`

---

## 5. Related

- Air quality JSON for MRW: `gen_air.sh` → `air.json` (see `docs/pi-wx-weather-inventory.md`).  
- WeeWX still ingests PM fields into loop/archive via this extension when the AirLink responds.
