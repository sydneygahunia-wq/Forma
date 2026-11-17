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

## Free-tier trade-offs, and how the demo stays fast

- Render's free instance **sleeps after 15 minutes without traffic** and takes up to a minute to wake. Two things prevent that:
  - `.github/workflows/keep-warm.yml` pings `/api/ping` every 5 minutes. One always-on service uses about 744 of Render's 750 free hours a month.
  - The portfolio site sends the same ping when someone lands on it, so the API is already starting before they click through.
  If it does sleep anyway (for example, GitHub pauses scheduled workflows in repos with no activity for 60 days), the frontend shows a "Waking up the warehouse…" banner and keeps retrying.
- Neon's free plan has **100 compute-hours a month** and suspends after 5 minutes without queries. Always on, even the smallest compute would need about 186, so the API is built to send **no queries while idle**:
  - Render's health check and the keep-warm ping hit `/api/ping`, which never touches the database (`/api/health` does, for readiness).
  - New orders wake the simulation through the event bus instead of a query every tick. The outbox is only re-checked every 15 minutes as a safety net (`OUTBOX_IDLE_POLL_S`).
  - The demo restock only runs if orders have shipped since the last one.
  Tests assert that 200 idle ticks issue zero SQL statements.

## Public-demo safeguards

Enabled by environment variables in `render.yaml`:

- `DEMO_MODE=true`: a paused simulation resumes and offline robots recover after 2 minutes, and any product below a quarter of its starting stock is restocked every 5 minutes, so visitors can't permanently break or empty the demo.
- `RATE_LIMIT_ORDERS_PER_MIN=10`, `RATE_LIMIT_WRITES_PER_MIN=60`: per-client limits (HTTP 429). They're in-memory, which is correct for a single instance.
- Order history only lists orders placed from the visitor's own browser.

## Steps

1. **Neon:** create a project in region *AWS US East 2 (Ohio)* (Render's `ohio` region is in the same place). Copy the connection string with **connection pooling turned off** (the direct host, not `-pooler`). The app rewrites `postgresql://` to the psycopg driver automatically.
2. **Render:** *New → Blueprint*, connect the GitHub repo. Render reads `render.yaml`. Paste the Neon string into `DATABASE_URL`. On first boot the API runs the Alembic migrations and seeds the catalogue. Check `https://<service>.onrender.com/api/health`.
3. **Vercel:** *Add New → Project*, import the repo, set **Root Directory** to `frontend`, and add the environment variable `NEXT_PUBLIC_API_URL=https://<service>.onrender.com`. Name the project `forma` (the API's CORS rule accepts `https://forma*.vercel.app`; otherwise set `CORS_ORIGIN_REGEX` on Render to match).

Pushes to `main` redeploy both services automatically.
