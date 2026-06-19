# Bangladesh NASA-BMD Bias Correction Frontend

Vite + React frontend for the Bangladesh map and correction UI.

## Local Run

```bash
npm ci
copy .env.example .env
npm run dev
```

The local default expects the backend at:

```env
VITE_API_BASE=http://127.0.0.1:8000
```

## Vercel Deployment

1. Deploy the `frontend/` folder as the Vercel project root.
2. Add this environment variable in Vercel:

```env
VITE_API_BASE=https://your-backend-domain.com
```

3. Deploy.
4. On the backend VPS, set `BACKEND_CORS_ORIGINS` to the Vercel URL.

## Build

```bash
npm run build
```
