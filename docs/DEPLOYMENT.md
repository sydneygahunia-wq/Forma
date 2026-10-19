# Deployment

The public demo runs on three free services:

| Part | Host | Why |
|---|---|---|
| Next.js frontend | **Vercel** | Built by the Next.js team; zero-config builds, global CDN |
| FastAPI + simulation | **Render** (Docker, free) | Runs a long-lived process, which the simulation loop and WebSockets need; uses the same Docker image CI builds |
| PostgreSQL | **Neon** (free) | Managed Postgres whose free tier doesn't expire |

```
browser ──► Vercel (Next.js) ──REST/WebSocket──► Render (FastAPI + sim) ──► Neon (Postgres)
```

The API runs with `SIM_MODE=embedded` (one process, no Redis). Redis only becomes necessary with multiple API replicas or a separate simulation worker (see `docker-compose.yml`).

## Free-tier trade-offs

- Render's free instance **sleeps after ~15 minutes without traffic** and takes up to a minute to wake. The frontend shows a "Waking up the warehouse…" banner and keeps retrying instead of erroring. On wake, the runner re-dispatches any unfinished orders (the transactional outbox, see ARCHITECTURE.md).
- Neon suspends compute when idle; the first query after that takes about a second.

## Public-demo safeguards

Enabled by environment variables in `render.yaml`:

- `DEMO_MODE=true`: a paused simulation resumes and offline robots recover after 2 minutes, and any product below a quarter of its starting stock is restocked every 5 minutes, so visitors can't permanently break or empty the demo.
- `RATE_LIMIT_ORDERS_PER_MIN=10`, `RATE_LIMIT_WRITES_PER_MIN=60`: per-client limits (HTTP 429). They're in-memory, which is correct for a single instance.
- Order history only lists orders placed from the visitor's own browser.

## Steps

1. **Neon:** create a project in region *AWS US West 2 (Oregon)*. Copy the connection string with **connection pooling turned off** (the direct host, not `-pooler`). The app rewrites `postgresql://` to the psycopg driver automatically.
2. **Render:** *New → Blueprint*, connect the GitHub repo. Render reads `render.yaml`. Paste the Neon string into `DATABASE_URL`. On first boot the API runs the Alembic migrations and seeds the catalogue. Check `https://<service>.onrender.com/api/health`.
3. **Vercel:** *Add New → Project*, import the repo, set **Root Directory** to `frontend`, and add the environment variable `NEXT_PUBLIC_API_URL=https://<service>.onrender.com`. Name the project `forma` (the API's CORS rule accepts `https://forma*.vercel.app`; otherwise set `CORS_ORIGIN_REGEX` on Render to match).

Pushes to `main` redeploy both services automatically.
