# Project journal

## 2026-10-17: initial build

### Built
- **Simulation engine:** grid parser with lane overlay, BFS/Dijkstra/A*, robot FSM, three schedulers, conflict resolution, replanning, yielding, robot failure and recovery, metrics, determinism hash.
- **Backend:** SQLAlchemy models plus an Alembic migration, catalogue, carts, idempotent order placement, a simulation runner using the DB as an outbox, an in-memory or Redis event bus, WebSocket streaming, JSON request logging, a health check, and a seed catalogue.
- **Frontend:** storefront with an optimistic cart, idempotent checkout, live order tracking, a dashboard (SVG floor, KPIs, fleet table with fail/recover, controls, Recharts, event feed), and a pathfinding lab.
- **Tooling:** pytest (65 tests; 86 with Postgres), Vitest (15), Playwright (4), ruff, mypy, ESLint, a benchmark script, a load-test script, Dockerfiles, docker-compose, GitHub Actions.

### Problems found and how
Bugs 1–10 were caught by a test, a stress run or the build. Bug 11 was caught by watching the live demo, which is why it now has its own regression test.

1. **Gridlock with 8 robots** (stress test). Two-way 1-wide aisles left robots facing each other forever. A diagnostic printout of the grid showed all 8 robots jammed in column 4. Fix: one-way lanes (DECISIONS D9). Wait ticks on that workload went from 4,170 to 87.
2. **Pack-station hotspot livelock** (stress test, 4/150 runs failing). Every robot chose the same nearest station. Fix: load-balanced station choice (D10) and a one-way loop through the pack zone.
3. **Fake detour** (debugging the remaining failures). When the blocker sat *on* the goal, replanning returned the same blocked path and counted it as a successful detour, so the yield rule never ran. Fix: a detour must avoid the blocked cell. Result: 150/150 stress runs pass.
4. **Offline robots sealing aisles** (chaos test, 10/60 failures). An unrealistic test let 6/8 robots fail at once, and planning ignored known failures. Fix: plan around offline robots, with a graceful fallback when there's no other route. The test was changed to model ≤ 2 bounded outages. Result: 60/60 pass.
5. **Duplicate CHECK constraint on Postgres** (first Postgres test run). SQLite had hidden it (D13).
6. **Enums stored as names (`PLACED`) instead of values (`placed`)** (caught while reading the generated migration).
7. **`useParams` / `usePathname` outside Suspense** (`next build` with Cache Components).
8. **`setState` in an effect** (React Compiler lint). Replaced with `useSyncExternalStore` for the `localStorage` cart id, which also syncs the cart across tabs.
9. **Throughput chart froze after a backend restart** (Vitest). The sampling check ran before the "tick went backwards" check.
10. **Load-test false alarm.** The checker expected `201` on retries, but the correct replay response is `200` + `Idempotent-Replayed`. The bug was in the test script, not the API.
11. **Orders split across pack stations** (spotted by watching the live demo, not by any test). Load balancing chose a station per *item*, so a 3-item order could be delivered to 3 stations and never boxed. Fix: one station per order (DECISIONS D10), plus a regression test asserting every item of an order is delivered to the same station. All benchmark numbers were re-run. The headline scheduler gain dropped from −25.9% to −15.7%, because the old figure was flattered by the unrealistic behaviour.

### Verified manually
- Full purchase in the browser: add to cart → checkout → order page → robots highlighted → shipped in about 11 s.
- Killed the API with 217 orders in flight. On restart it logged `re-dispatching 217 unfinished orders after restart`, and the dashboard went "Reconnecting…" → "Live" without a reload.

### Measured
See `docs/BENCHMARKS.md`. Headline numbers:
- `batch_greedy` vs FIFO: −15.7% mean fulfillment at 0.10 orders/tick; faster on 10/10 seeds.
- A* vs Dijkstra: 26.5 vs 109.8 nodes expanded on average (same costs).
- Load test (local, SQLite): 330 requests in 0.94 s, p95 211 ms, ledger balanced.

### Not yet verified
- `docker compose up` (Docker isn't installed on the dev machine).
- A real Redis server (tested with fakeredis).
- CI on GitHub (not pushed yet).

## 2026-10-18: redesign after reviewing the live demo

### Feedback
Design review: the UI looked like a generic template. The fix was to study real references and copy their conventions (DECISIONS D16): the Shopify Dawn demo store, a MAPF research visualiser (Kei18/mapf-visualizer), Foxglove, and atoms.co.

### Built
- Storefront rebuilt: real product photos, Dawn-style grid, filter and sort, an "added to cart" popover that stays until dismissed, a cart drawer, an announcement bar, a footer, and a live floor preview in the hero.
- Order page rebuilt in the shape of Shopify's order status page.
- Ops console: panel workspace, HUD, playback speeds (0.25×–4×), toggles (HUD/paths/goals/lanes/axes), agent table with fail/recover, raw event log, metrics readout, step plots, status bar.
- New floor renderer: rack pods, hazard-striped stations, docks, lane chevrons, coordinate axes, heading ticks, goal diamonds, carrying rings.
- Backend: `products.image_url` plus a migration and seed backfill.

### Problems found
- Wall cells showed anti-aliased seams. Fixed with a slight overlap and `crispEdges`.
- The HUD covered robots in the top-left corner. Moved it top-right and made it toggleable.
- The popover auto-dismissed after 3.5 s, and a click landing just after went through to the element underneath. It now stays open like Dawn's: it closes on an outside click or Escape.

### Verified
Browser walkthrough of every page at 1280 px. All tests pass: backend 65, frontend unit 16, e2e 4 (updated for the drawer flow).

## 2026-10-18 (later): simulator restyle + landing page

### Feedback
Design review: the storefront worked, but the floor view was decorative rather than functional. Separately, it was unclear whether the app was for customers or for the seller.

### Built
- Floor renderer rewritten after PlanViz / RWARE / MAPF visualisers (DECISIONS D17).
- Console rebuilt as a light, plain tool: a sidebar with a time readout, playback, display checkboxes, a selectable robot list and statistics, plus task table, event log and throughput panels.
- Landing page at `/` with both roles; store moved to `/shop`; the store no longer links into internal tools.

### Problems found
- Robot IDs collided with the heading arrow. The label is now offset away from the heading.
- An e2e race: the pathfinding test read the "-" placeholder before the result loaded (NaN). It now waits for numeric text. The suite passed 3 runs in a row afterwards.

### Verified
Browser walkthrough of `/`, `/shop`, `/dashboard` (with live orders and robot selection) and `/pathfinding`. Production build, typecheck, lint, Vitest 16/16, Playwright 5/5.

## 2026-10-18 (later): pre-release audit

### Checks run
ruff, mypy, pip check, pip-audit (0 known vulnerabilities), pytest on SQLite and PostgreSQL (86 passed), ESLint, tsc, npm audit (0 in production dependencies), Vitest, Playwright, production build.

### Fixed
- **shadcn/ui set up properly:** `components.json` added, Sheet generated with the shadcn CLI, and the cart drawer rebuilt on it. This gives Radix Dialog's focus trap, Escape handling, scroll lock and focus restore; the hand-built drawer had no focus trap. Duplicate packages the CLI pulled in (`cn`, `@radix-ui/react-slot`) were consolidated onto the existing `cn` helper and the unified `radix-ui` package.
- **Dead code removed:** the unused product `emoji` field (model, API, types; Alembic migration `33a9e3326a72` with a downgrade tested on a table containing rows), plus unused colour and label helpers.
- **Scaffolding removed:** the default Next.js template SVGs and favicon (replaced with a custom icon). `AGENTS.md`, which `next dev` regenerates, is now git-ignored.
- **Test warning:** Starlette's TestClient deprecation, fixed by adding `httpx2`.
- **Docs:** moved into `docs/`. The README was rewritten with screenshots captured from the running app (`SCREENSHOTS=1 npx playwright test screenshots`), a stack table and known limitations.

### Known and accepted
- `npm audit` reports a `braces` advisory inside `eslint-config-next`. It's dev-only, and there's no patched release upstream; the only offered fix is downgrading to Next 14's config.

## 2026-10-18 (later): published to GitHub, CI green

- Pushed to github.com/sydneygahunia-wq/Forma.
- **First CI run failed** in the frontend type check: `Cannot find name 'LayoutProps'`. Next.js generates route types into `.next/`, which a fresh checkout doesn't have; locally an old `.next/` had hidden this. Reproduced in a fresh clone, then fixed with `next typegen && tsc --noEmit`.
- Moved the GitHub Actions to v7 (Node 24 runtime), clearing the Node 20 deprecation warnings.
- **Second run all green:** backend (including the race-condition tests on Postgres 16), frontend, Playwright end-to-end, and both Docker images build. This is the first verification of the Dockerfiles.
