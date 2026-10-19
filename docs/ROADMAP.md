# Roadmap

✅ built and verified · 🟡 built but not fully verified · ⬜ not started

| Phase | Status | Evidence |
|---|---|---|
| 1. Foundations: repo, FastAPI ↔ Next.js, REST | ✅ | Running stack; `GET /api/health` |
| 2. E-commerce backend: catalogue, inventory, cart, orders, status tracking, transactions, validation | ✅ | `tests/test_api_store.py`, `tests/test_concurrency.py` (SQLite + Postgres) |
| 3. Warehouse simulation: grid, shelves, stations, obstacles, robots, deterministic ticks | ✅ | `tests/test_engine.py::test_simulation_is_deterministic` |
| 4. Pathfinding: BFS, Dijkstra, A* from scratch, visualised and compared | ✅ | `tests/test_pathfinding.py`, `/pathfinding` page, `docs/BENCHMARKS.md` |
| 5. Multiple robots: assignment, FSMs, task queue, collision avoidance, replanning | ✅ | 150 stress runs + 8 chaos tests, zero collisions |
| 6. Real-time: WebSocket, reconnection, polling fallback | ✅ | `test_live_app_streams_snapshots_and_ships_orders`; manual kill/restart of the server |
| 7. Reliability: idempotency, last-unit race, duplicate requests, robot failure, worker crash, simultaneous orders, indexes, structured logging | ✅ | `test_concurrency.py`, `test_restart_recovers_unfinished_orders`, `scripts/load_test.py` |
| 7b. Redis pub/sub between API and worker | 🟡 | Tested against `fakeredis`; not yet against a real Redis server |
| 8. Optimization: baseline vs improved scheduler, reproducible benchmark | ✅ | `docs/BENCHMARKS.md` (−15.7% mean fulfillment at high load, 10/10 seeds) |
| 9. Production: tests, Docker, CI, API docs, architecture docs, logging | ✅ | GitHub Actions green: backend on Postgres, frontend, Playwright, and both Docker images build. OpenAPI at `/docs`. |
| 9b. Deployment to a public URL | ✅ | https://forma-ten-bice.vercel.app (Vercel) + Render API + Neon Postgres; live order verified end to end |
| 10. Portfolio: README, diagrams, benchmarks, screenshots | 🟡 | README with screenshots, ARCHITECTURE (Mermaid), BENCHMARKS done. Demo video and resume bullets not yet. |

## Next steps (in order)

1. ~~Push to GitHub and get CI green.~~ Done (2026-10-18).
2. ~~Deploy.~~ Done (2026-10-19). Optional: run `docker compose up` as a full local production-style check, then deploy (e.g. Render or Fly.io with managed Postgres and Redis).
3. Record a 60-second demo: place an order, watch it get picked, fail a robot, watch the task get re-queued.
4. Possible improvements, each needing a benchmark before it's claimed:
   - Space-time A* with a reservation table (cooperative pathfinding) to cut wait ticks further.
   - Batch picking: one robot collects several items for the same order in one trip.
   - `LISTEN/NOTIFY` instead of outbox polling.
   - Order cancellation (restock in the same transaction, only while not yet dispatched).
