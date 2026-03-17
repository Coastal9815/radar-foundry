# HRRR Smoke — Step 1: Data Source Identification

**Status:** Complete  
**Machine:** wx-i9  
**Date:** 2026-03-10

---

## 1. Confirmation: NOAA HRRR (not CAMS)

The MRW Smoke metric uses **NOAA HRRR** from the AWS open-data bucket. CAMS is used for Saharan dust only.

---

## 2. Exact AWS File Path Pattern

```
s3://noaa-hrrr-bdp-pds/hrrr.YYYYMMDD/conus/hrrr.tHHz.wrfsfcfFF.grib2
```

Where:
- `YYYYMMDD` = date (e.g. `20260309`)
- `HH` = cycle hour (00–23 UTC)
- `FF` = forecast hour (00–48)

**For current/latest CONUS run:** Use the most recent cycle’s analysis file: `wrfsfcf00.grib2` (forecast hour 0).

**Example:**
```
s3://noaa-hrrr-bdp-pds/hrrr.20260309/conus/hrrr.t00z.wrfsfcf00.grib2
```

---

## 3. Exact GRIB2 Filename Pattern

```
hrrr.tHHz.wrfsfcfFF.grib2
```

- `wrfsfcf` = surface forecast (2D fields)
- `wrfnat` = native-level (3D); smoke near-surface is in **wrfsfcf**, not wrfnat

---

## 4. Smoke Variable in File Metadata

| Attribute | Value |
|----------|-------|
| **GRIB shortName** | `unknown` (cfgrib; HRRR uses local table) |
| **typeOfLevel** | `heightAboveGround` |
| **level** | `8` (meters) |
| **Physical meaning** | Smoke mass density (MASSDEN) at 8 m above ground |
| **Units (GRIB)** | kg/m³ (since Dec 2021 correction) |

**Note:** cfgrib reports `unknown` because the HRRR local GRIB table is not in the standard ecCodes tables. The variable is identified by `typeOfLevel=heightAboveGround` and `level=8`; there is only one such field in the wrfsfcf file.

---

## 5. Variable Token for Near-Surface Smoke (8 m AGL)

**Selection filter:**
```python
filter_by_keys={"typeOfLevel": "heightAboveGround", "level": 8}
```

**xarray variable name:** `unknown` (from cfgrib). Use the single data variable in the filtered dataset.

**Conversion:** GRIB units are kg/m³. For µg/m³: `value_ug_m3 = value_kg_m3 * 1e9`.

---

## 6. Confirmation: Near-Surface Smoke

Yes. The variable at `heightAboveGround` / `level=8` is the near-surface smoke mass density (MASSDEN) from the HRRR-Smoke extension. It represents smoke concentration at 8 m above ground level.

---

## 7. File Format and Parsing Approach

| Item | Choice |
|------|--------|
| **Format** | GRIB2 |
| **Library** | `cfgrib` (via `xarray` engine) |
| **Open pattern** | `xr.open_dataset(path, engine="cfgrib", backend_kwargs={"filter_by_keys": {"typeOfLevel": "heightAboveGround", "level": 8}}) |
| **Data variable** | Single variable (named `unknown` by cfgrib) |
| **Coordinates** | `latitude`, `longitude` (2D arrays) — longitude in 0–360° |

**Dependencies:** `cfgrib`, `xarray` (already in `.venv-wxi9` for CAMS/dust). No `s3fs` required if using `aws s3 cp` to fetch; for streaming from S3, add `s3fs`.

---

## 8. Target Location Verification

**Target:** lat 31.91918481533656, lon -81.07604504861318 (Moon River, GA)

**Sample (2026-03-09 00Z wrfsfcf00):**
- Nearest grid: lat 31.9234, lon 278.91° (≈ -81.09°)
- MASSDEN: 4.8e-11 kg/m³ = **0.048 µg/m³**
- Classification: None (0–<5 µg/m³)

---

## Summary for Implementation

| Item | Value |
|------|-------|
| **AWS path** | `s3://noaa-hrrr-bdp-pds/hrrr.YYYYMMDD/conus/hrrr.tHHz.wrfsfcf00.grib2` |
| **Filename** | `hrrr.tHHz.wrfsfcf00.grib2` |
| **Variable** | MASSDEN at 8 m AGL (select via `typeOfLevel=heightAboveGround`, `level=8`) |
| **Units** | kg/m³ → µg/m³ = ×1e9 |
| **Tool** | cfgrib + xarray |

---

## Step 2: Retrieval and Point Sampling

**Script:** `bin/sample_hrrr_smoke.py`

**Run on wx-i9:**
```bash
.venv-wxi9/bin/python bin/sample_hrrr_smoke.py
```

**Output:** Printed report + `out/hrrr_smoke_sample.json`

**Note:** Uses `decode_times=False` to avoid cfgrib datetime conversion issues; valid time is parsed from the S3 path.

---

## Step 3: MRW Smoke Metric (Integrated)

**Integration:** `bin/air_api.py` → `fetch_smoke()` → `/api/air/summary`

**Classification:** 0–<5 µg/m³ = None, 5–<15 = Light, 15–<35 = Moderate, 35+ = Heavy  
**Colors:** None=green, Light=yellow, Moderate=orange, Heavy=red

**Cache:** 60 minutes. Fallback: tries cycles 0–3h old.
