# Learning log

A map from concepts to the exact code that implements them, for studying the codebase and preparing to explain it. Tick a box once you can explain the concept *and* walk through the code without notes.

## Algorithms
- [ ] **BFS** and why it's optimal only for unit costs: `backend/app/simulation/pathfinding.py::bfs`
- [ ] **Dijkstra**, priority queues, and *lazy deletion* instead of decrease-key: `_best_first`
- [ ] **A\***, admissible and consistent heuristics, tie-breaking on `h`: `astar`, and `test_astar_expands_fewer_nodes_than_dijkstra`
- [ ] **Directed graphs:** why distance *to* ≠ distance *from* with one-way lanes: `distance_map(reverse=True)`
- [ ] **Testing algorithms:** property tests (all three agree on cost over 200 random pairs), edge cases (unreachable, start = goal): `tests/test_pathfinding.py`
- [ ] **Greedy assignment vs FIFO**, and starvation and aging: `backend/app/simulation/scheduler.py`

## Simulation and robotics
- [ ] **Discrete-time simulation** and why it's deterministic: `engine.py` module docstring, `state_hash`
- [ ] **Finite-state machines:** `RobotState` and `_arrive`
- [ ] **Multi-agent collisions:** vertex vs swap conflicts, fixpoint resolution: `_move`
- [ ] **Deadlock vs livelock** and how traffic rules + yielding break them: `_replan_around_robots`, `_maybe_yield`, DECISIONS D9
- [ ] **Separation of simulation and rendering:** the engine knows nothing about SVG or HTTP

## Databases
- [ ] **Schema design:** PK/FK, 1:1 (inventory), M:N via join tables (cart_items, order_items): `backend/app/db/models.py`
- [ ] **Joins and N+1:** `_product_rows`, `selectinload` in `get_order`
- [ ] **Transactions and atomicity:** `place_order` (all lines or none), `test_out_of_stock_rolls_back_the_whole_order`
- [ ] **Race conditions and conditional UPDATE:** `_create`, `test_many_buyers_for_the_last_unit`
- [ ] **Lock ordering to prevent deadlocks:** `sorted(lines)` in `_create`
- [ ] **Isolation levels:** why READ COMMITTED is enough here (ARCHITECTURE, Order placement)
- [ ] **Indexes:** `ix_orders_status_dispatched` and which query it serves
- [ ] **Migrations:** `backend/migrations/`

## APIs and distributed systems
- [ ] **REST semantics:** PUT is idempotent, POST isn't; 201 vs 200 vs 202 vs 404 vs 409 vs 422: `backend/app/api/store.py`
- [ ] **Idempotency keys** and the UNIQUE-constraint race: `place_order`, `test_duplicate_requests_racing_with_the_same_idempotency_key`
- [ ] **Transactional outbox** and at-least-once delivery: `sim_runner.py` docstring, `_recover`
- [ ] **Pub/sub** and why Redis appears only with multiple processes: `services/bus.py`
- [ ] **Backpressure:** bounded queues that drop the oldest messages: `InMemoryBus.publish`
- [ ] **asyncio:** event loop, `to_thread` for blocking I/O, fixed-rate scheduling: `SimulationRunner._loop`

## Frontend
- [ ] **Server vs client components, Suspense, partial prerendering:** `frontend/src/app/orders/[id]/page.tsx`
- [ ] **TanStack Query:** caching, polling with `refetchInterval`, optimistic updates and rollback: `use-cart.ts`
- [ ] **useSyncExternalStore** for browser storage: `use-cart.ts`
- [ ] **WebSocket lifecycle, exponential backoff with jitter, fallback polling:** `use-simulation-feed.ts`
- [ ] **SVG rendering and memoisation:** `warehouse-grid.tsx`

## Practice questions (answers are in the code and docs above)
1. Why A* instead of BFS? When would they return different paths?
2. Two customers click "buy" on the last unit at the same millisecond. Walk through exactly what Postgres does.
3. A client times out and retries a checkout. Why can't it be charged twice, even if both requests run concurrently?
4. How do you guarantee no two robots occupy the same cell? What about swapping places?
5. The simulation process crashes mid-order. What happens to that order?
6. Why send full snapshots over the WebSocket instead of deltas?
7. Your benchmark says scheduler B is 15.7% better. How do you know it isn't noise?
8. How would this architecture change at 10,000 orders per minute? (Consider the outbox poll, the single simulation loop, WebSocket fan-out, and the hot inventory rows.)
