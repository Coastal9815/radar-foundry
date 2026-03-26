# Air API Setup

The MRW Air Quality module uses a single endpoint `/api/air/summary` that collects all air-related data. API keys are **server-side only** and never exposed to the client.

## Metrics

| Metric | Source | Cache | Notes |
|--------|--------|-------|-------|
| PM2.5, PM10 | pi-wx Davis Air Link | — | Fetched via pi-wx proxy |
| Ozone | AirNow API | 15 min | Requires `airnow_api_key` |
| Smoke | NOAA HRRR GRIB2 (noaa-hrrr-bdp-pds) | 1 h | wrfsfcf00, MASSDEN 8m; see [HRRR_SMOKE_STEP1.md](HRRR_SMOKE_STEP1.md) |
| Saharan Dust | CAMS (Copernicus ADS) | 6 h | Requires ~/.cdsapirc; duaod550 → None/Light/Moderate/Heavy |
| Pollen | Google Pollen API | 3 h | NAB proxy; requires `google_pollen_api_key` |

## 1. Create `conf/air_api_keys.json`

```bash
cp conf/air_api_keys.json.example conf/air_api_keys.json
# Edit with your keys
```

**Do not commit** `air_api_keys.json` to version control.

## 2. API Keys

### AirNow (Ozone)
- Register at https://docs.airnowapi.org/
- Free for non-commercial use
- Add `airnow_api_key`

### Google Pollen API (Pollen proxy for NAB)
- Enable Pollen API in Google Cloud Console
- Add `google_pollen_api_key`

## 3. Environment Variables

- `AIRNOW_API_KEY`
- `GOOGLE_POLLEN_API_KEY`

## 4. Endpoint

- `GET /api/air/summary` — All air metrics (PM, ozone, smoke, saharan dust, pollen). Cache 5 min.

## 5. Location

All data uses MRW coordinates: 31.919117, -81.075932 (Savannah area).

## 6. Smoke (HRRR)

Smoke from NOAA HRRR GRIB2 (`s3://noaa-hrrr-bdp-pds`). Variable: MASSDEN at 8 m AGL in `wrfsfcf00.grib2`. Parsed with cfgrib/xarray. Classification: None/Light/Moderate/Heavy with colors. See [HRRR_SMOKE_STEP1.md](HRRR_SMOKE_STEP1.md).
