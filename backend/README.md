# Bangladesh NASA-BMD Bias Correction Backend

Production FastAPI service for NASA POWER to BMD bias-corrected estimates.

Current deployed URL:

```text
https://64-227-16-188.sslip.io
```

## Runtime Layout

- `app/` - FastAPI application and correction core.
- `models/bias_correction/` - trained model bundle and metadata.
- `data/processed/` - station metadata, scraped OGIMET BMD SYNOP station CSVs, and scraped NASA POWER station CSVs used for anchors/training.
- `pipelines/` - retraining pipeline copied from the research workspace.

## Local Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/api/health
```

## Docker Run

```bash
copy .env.example .env
docker compose up --build -d
```

Set `BACKEND_CORS_ORIGINS` to your deployed Vercel domain before production use:

```env
BACKEND_CORS_ORIGINS=https://meteorological-data-analysis.vercel.app
```

## VPS Deployment

1. Copy the `backend/` folder to the VPS.
2. Install Docker and Docker Compose.
3. Create `.env` from `.env.example`.
4. Set `BACKEND_CORS_ORIGINS` to the Vercel frontend URL if it differs from the default.
5. Run `docker compose up --build -d`.
6. Caddy serves HTTPS and reverse-proxies to the API container.

## API

- `GET /api/health`
- `GET /api/stations`
- `POST /api/v2/estimate` - historical correction, NASA provisional forecast, and optional OGIMET BMD SYNOP observation lookup
- `POST /api/correct` - deprecated, historical requests through 2024 only

`POST /api/v2/estimate` request:

```json
{
  "latitude": 23.766667,
  "longitude": 90.383333,
  "timestamp_utc": "2026-06-19T06:00:00Z",
  "variables": ["T2M", "RH2M", "PRECTOTCORR", "WS10M"]
}
```

All timestamps are UTC. The frontend treats the `datetime-local` field as a UTC value
and sends it with a `Z` suffix. The backend rejects non-UTC offsets such as `+06:00`
instead of silently converting them.

For post-2024 requests the API fetches one 90-day NASA POWER UTC range. If the
requested 3-hour timestamp is missing, the packaged model forecasts directly from the
latest NASA timestamp. Temperature, humidity, rainfall, and wind are independently
gated by held-out BMD validation. A failed gate is returned as unavailable; climatology
is never presented as a live observation.

Packaged correction and forecasting artifacts are trained from scraped OGIMET BMD SYNOP
station CSVs plus scraped NASA POWER station CSVs. Excel-derived BMD weather CSVs are
not used by the default runtime or retraining commands.

When the requested UTC timestamp is not in the future, the API also queries OGIMET
`getsynop` for Bangladesh SYNOP rows at the exact UTC hour. If the nearest BMD station
has a valid SYNOP row, the response exposes that value separately as `bmd_raw` and
`bmd_actual`, includes the WMO id and raw SYNOP report, and keeps `corrected_nasa`
separate. If OGIMET has no row or is unavailable, the API does not fake BMD raw data;
it falls back to the model-only BMD estimate/forecast fields.

Available estimate payloads expose provider-specific fields instead of an ambiguous
combined label:

- Provisional mode: raw `nasa_forecast` plus the BMD-scale `bmd_forecast`/`corrected_nasa`.
  If OGIMET has the exact requested UTC SYNOP row, `bmd_actual`/`bmd_raw` are also set
  and remain distinct from the model forecast and corrected value.
- Historical mode: `nasa_raw`, nearest-station `bmd_actual`/`bmd_raw`, and `corrected_nasa`.
- Exact post-2024 NASA mode: `nasa_raw` and `bmd_estimate`; `bmd_raw` is set only when
  OGIMET provides the exact nearest-station SYNOP row.

`bmd_forecast` is produced by the operational forecast bundle. `corrected_nasa` is
calculated separately with the original `bias-correction-v1` bundle and its selected
per-variable method. For post-2024 timestamps, historical month/hour station
climatology is used only as an input feature to that legacy correction model and is
never returned or described as a current BMD observation.

For operational requests, the legacy correction features replace historical anchor
values with operational BMD/NASA estimates at the five nearest station coordinates.
Distance weighting uses the actual selected-point-to-station distances. Standard IDW
exact-point behavior is enforced: when the selected coordinate is exactly a BMD station,
that station's operational BMD value controls `corrected_nasa`.

## Retrain the operational forecast

Run from the repository root:

```powershell
python backend/pipelines/train_operational_forecast_model.py
```

The trainer uses 2021-2022 for fitting, 2023 for validation, and 2024 at seven unseen
stations for the final spatial/temporal test. It writes the deployable artifact under
`backend/models/operational_forecast/` and the quality-gate report under `outputs/`.

## Optional Chronos-2 tournament checks

Chronos-2 is evaluated offline and is not a runtime API dependency:

```powershell
pip install -r requirements-sota.txt
python backend/pipelines/benchmark_chronos2.py --device cpu
python backend/pipelines/evaluate_chronos2_accuracy.py --device cpu
```

The CPU benchmark and sampled spatial holdout metrics are written under
`outputs/tables/operational_forecast/`. The packaged direct gradient-boosting model
remains the production winner because it completed the full 2023 selection and 2024
spatial/temporal protocol with a roughly 2.3 MB artifact. Chronos-2 passed the raw
CPU resource ceiling, but its current accuracy run is supplemental rather than a
complete replacement validation. TimeXer, iTransformer, and PatchTST remain offline
research candidates and are not imported by the production service.
