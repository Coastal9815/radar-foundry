# wx-i9 Storage (Hybrid Strategy)

wx-i9 uses a dedicated 1TB LVM volume for wx-data, leveraging the 4TB NVMe.

## Layout

| Path | Purpose |
|------|---------|
| `/wx-data` | Mount point for 1TB LVM volume (ext4) |
| `~/wx-data` | Symlink → `/wx-data` (preserves existing paths) |
| `/wx-data/served/` | radar_local_KCLX, radar_local_KJAX, radar_local_mrms, radar_local_satellite |

## LVM

- **VG**: ubuntu-vg
- **LV**: wx-data, 1TB
- **Device**: /dev/ubuntu-vg/wx-data
- **fstab**: UUID=2d8187ac-ebd4-44c1-a96e-9bc971c0e764 /wx-data ext4 defaults,nofail 0 2

## Satellite (IR + Visible)

IR and Visible products are produced on **weather-core** and published to wx-i9:

- **Fetch**: GOES ABI L1b from S3 (channel 13 IR, channel 2 Visible)
- **Render**: Web Mercator (EPSG:3857) via `render_goes_frame.py`
- **Store**: `~/wx-data/served/radar_local_satellite/ir/`, `.../vis/`
- **Schedule**: launchd on weather-core (`com.mrw.goes_loop`), every 5 min
- **Player**: http://192.168.2.2:8080/player/satellite/?product=ir

## Expand Volume

To add more space (e.g. 500GB) from the ~2.5TB free in the VG:

```bash
sudo lvextend -L +500G /dev/ubuntu-vg/wx-data
sudo resize2fs /dev/ubuntu-vg/wx-data
```
