# Production Deployment

This project is now split into two deployable folders:

- `backend/` - FastAPI model API, Dockerfile, Docker Compose, trained model artifacts, and runtime station data.
- `frontend/` - Vite React app configured for Vercel.

Current deployed backend:

```text
https://64-227-16-188.sslip.io
```

## Backend on VPS

1. Copy `backend/` to the VPS.
2. Create the environment file:

```bash
cp .env.example .env
```

3. Edit `.env` and set the Vercel frontend URL:

```env
BACKEND_CORS_ORIGINS=https://meteorological-data-analysis.vercel.app
```

Keep the packaged operational model path:

```env
OPERATIONAL_MODEL_PATH=/app/models/operational_forecast/model_bundle.joblib
BMD_LIVE_ENABLED=false
```

4. Build and run:

```bash
docker compose up --build -d
```

5. Check health:

```bash
curl http://127.0.0.1:8000/api/health
```

6. The included Compose stack runs Caddy on ports `80` and `443` and proxies to the API on localhost port `8000`.

## Frontend on Vercel

1. Create a Vercel project with `frontend/` as the root directory.
2. Add this Vercel environment variable:

```env
VITE_API_BASE=https://64-227-16-188.sslip.io
```

3. Deploy with the default Vite build settings:

```bash
npm ci
npm run build
```

## Required API Linkage

The frontend calls:

- `GET ${VITE_API_BASE}/api/stations`
- `POST ${VITE_API_BASE}/api/correct`

The backend must allow the deployed Vercel domain in `BACKEND_CORS_ORIGINS`.
