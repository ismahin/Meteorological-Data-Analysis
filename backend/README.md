# Bangladesh NASA-BMD Bias Correction Backend

Production FastAPI service for NASA POWER to BMD bias-corrected estimates.

## Runtime Layout

- `app/` - FastAPI application and correction core.
- `models/bias_correction/` - trained model bundle and metadata.
- `data/processed/` - station metadata and historical station time series used for anchors.
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

Set `BACKEND_CORS_ORIGINS` in `.env` to your deployed Vercel domain before production use:

```env
BACKEND_CORS_ORIGINS=https://your-project.vercel.app
```

## VPS Deployment

1. Copy the `backend/` folder to the VPS.
2. Install Docker and Docker Compose.
3. Create `.env` from `.env.example`.
4. Set `BACKEND_CORS_ORIGINS` to the Vercel frontend URL.
5. Run `docker compose up --build -d`.
6. Put Nginx/Caddy in front of port `8000` and terminate HTTPS there.

## API

- `GET /api/health`
- `GET /api/stations`
- `POST /api/correct`

`POST /api/correct` request:

```json
{
  "latitude": 23.766667,
  "longitude": 90.383333,
  "timestamp_utc": "2026-06-19T06:00:00Z",
  "variables": ["T2M", "RH2M", "PRECTOTCORR", "WS10M"]
}
```
