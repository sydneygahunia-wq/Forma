# Engineering decisions

Each entry: the decision, the alternatives, and why. Newest last.

### D1. Modular monolith, not microservices
**Decision:** one FastAPI codebase with clear internal layers (`simulation` / `services` / `api`). The simulation can run in-process or as a separate worker *from the same code*.
**Alternatives:** separate order, inventory and simulation services.
**Why:** there's one team and one database. Microservices would add network failure modes, distributed transactions and deployment overhead without solving any real problem here. The worker split gives the one separation that matters (simulation load vs. request latency) without splitting the codebase.

### D2. The simulation engine is pure and deterministic
**Decision:** `app/simulation` has no I/O, clock or randomness. Time advances only via `tick()`.
**Why:** it's testable without a server, reproducible (`state_hash()` proves two runs are identical), and benchmarkable offline on identical workloads. Rendering and persistence are someone else's job.
**Trade-off:** the runner has to bridge real time to ticks and persist state separately.

### D3. Atomic conditional `UPDATE` for stock, not `SELECT … FOR UPDATE` and not optimistic version columns
**Decision:** `UPDATE inventory SET quantity = quantity - q WHERE product_id = p AND quantity >= q`, checking rows affected.
**Alternatives:** (a) read the stock, check it in Python, write it back: a race condition. (b) `SELECT … FOR UPDATE` then update: correct, but two round trips and more lock time. (c) An optimistic `version` column with retries: correct, but needs retry loops under contention.
**Why:** one statement is atomic, correct under READ COMMITTED, portable to SQLite, and holds the row lock for the shortest time. Lines are processed in ascending `product_id` so concurrent multi-item orders always lock in the same order and can't deadlock.

### D4. Stock is claimed at checkout, not when adding to the cart
**Why:** reserving on add-to-cart lets abandoned carts lock inventory and needs expiry jobs. Claiming atomically at checkout is simpler and correct. The cost is that a customer can see "in stock" and then get a `409` at checkout, which the UI explains.

### D5. Idempotency keys stored under a UNIQUE constraint
**Decision:** `orders.idempotency_key UNIQUE`, plus a hash of the request body.
**Why:** an application-level "check, then insert" has the same race as D3. Letting the database reject the duplicate means two identical requests arriving at the same instant still create one order. The loser rolls back its own stock decrements and returns the winner's order. Same key with a different body gives `422`, because that's a client bug, not a retry.

### D6. The database is the queue (transactional outbox), not Redis or Celery
**Decision:** the runner polls `orders WHERE dispatched_at IS NULL`.
**Alternatives:** publish "order created" to Redis or a broker after commit.
**Why:** publishing after commit loses the message if the process dies between commit and publish. The order row is written in the same transaction as the stock decrement, so it *is* the durable message. That also makes crash recovery trivial (reset `dispatched_at` for unfinished orders). At this scale, polling every 250 ms is negligible load. At much higher scale I'd switch to `LISTEN/NOTIFY` or change-data capture.

### D7. Redis only for pub/sub between processes
**Decision:** an in-memory bus by default, and Redis only when the API and simulation are separate processes.
**Why:** Redis earns its place exactly when there's more than one process: a worker publishing snapshots and API replicas each holding their own WebSocket clients. It isn't used as a cache, because nothing here is slow enough to need one.

### D8. WebSocket with full snapshots, not deltas, and no backpressure on the simulation
**Decision:** every message is the full world state (~6 robots, a few KB). Each client gets a bounded queue that drops its oldest messages when full.
**Alternatives:** Server-Sent Events (one-way, simpler; would also work for this feed); polling (simple but wasteful and laggy); deltas (smaller, but a dropped message corrupts client state).
**Why:** full snapshots make every message self-sufficient, so dropping some is harmless. That lets us protect the simulation loop from slow clients. WebSocket was chosen over SSE so the dashboard can grow into a bidirectional control channel. Today commands still go over REST (`202 Accepted`). Polling remains as the client's fallback.

### D9. One-way traffic lanes for collision avoidance
**Context:** with two-way 1-wide aisles, 8 robots gridlocked. One diagnostic run had 4,170 wait ticks and only 9/40 orders shipped before it stalled.
**Decision:** a lane overlay: vertical aisles alternate direction, cross-aisles are one-way, and the pack zone is a loop. Then layer execution-time conflict resolution, replanning, and priority yielding on top.
**Alternatives:** reservation tables / space-time A* (cooperative pathfinding), or CBS (conflict-based search).
**Why:** traffic rules are what real AMR warehouses use. They're simple, obviously correct (no head-on conflicts in aisles by construction), and cheap. The same workload dropped to 87 wait ticks with every order shipped. Space-time planning is the natural next step if throughput needs it (see ROADMAP).

### D10. One pack station per order, chosen by load and distance
**Context:** "nearest station" sent every robot to one hotspot, which livelocked in the stress test. The first fix balanced load *per item*, which split multi-item orders across several stations. That's physically wrong, because an order is boxed in one place. (Spotted while watching the live demo.)
**Decision:** when an order's first item is assigned, choose one station for the whole order: `cost = Σ travel(shelf → station) over the order's items + 15 × undelivered items other orders are sending there`. Every item of the order goes there.
**Why:** it's correct (items consolidate) and it still spreads *orders* across stations with one tunable constant. Choosing at first assignment rather than at order arrival reflects current traffic.
**Cost:** benchmarks got slightly slower (FIFO mean fulfillment at high load went from 203.6 to 234.5 ticks), because items can no longer use whichever station happens to be closest. That's the price of realism, and the earlier numbers were flattered by it.

### D11. `batch_greedy` as the default scheduler, decided by benchmark
**Decision:** default `SCHEDULER=batch_greedy`.
**Evidence:** `docs/BENCHMARKS.md` shows it beat FIFO on mean fulfillment on 10/10 paired seeds at both load levels, with −15.7% mean fulfillment at high load. `nearest` won only 7/10 seeds at high load.
**Trade-off:** it's O(robots × window) per tick instead of O(robots), which is trivial at this size. It includes an aging term so old tasks can't starve.

### D12. SQLite for local dev and tests; Postgres in Docker and CI
**Why:** zero-setup local runs. Everything that matters for correctness (conditional updates, UNIQUE, CHECK, FKs via `PRAGMA foreign_keys`) behaves the same. The race-condition tests run on both, because SQLite serializes writers and could hide bugs that Postgres would expose. Running on Postgres immediately caught a bug SQLite tolerated (D13).

### D13. Explicit, uniquely named CHECK constraints for enums
**Context:** `Enum(create_constraint=True)` made Alembic emit the same `CHECK` three times. SQLite accepted it and Postgres rejected it.
**Decision:** store enum *values* as `VARCHAR` with an explicitly named `CHECK (status IN (…))` per table.

### D14. Next.js Cache Components and partial prerendering kept on
**Decision:** keep the Next 16 defaults. Wrap request-time hooks (`useParams`, `usePathname`) in `<Suspense>`.
**Why:** each page shell is prerendered statically and only the dynamic part streams. The build enforces this, which is how both issues were found.

### D15. SVG, not Canvas, for the warehouse
**Why:** 364 cells and ≤ 8 robots is small for the DOM. SVG is inspectable in devtools, accessible (`role="img"`, `<title>` tooltips), testable with Testing Library, and animates with CSS transitions. Canvas would be the move at thousands of entities.

### D16. Visual design taken from real products, not a generic dashboard template
**Context:** the first UI used default component-library styling (rounded cards, emoji product images, one theme everywhere). It looked like a generic template rather than a real product.
**Decision:** each surface copies the conventions of a real product its users would recognise:
- **Storefront:** Shopify's Dawn theme. Real product photography (Unsplash licence) on light grey, no cards, a full-width quick-add button, the "added to cart" popover, a slide-out cart drawer, and an order page shaped like Shopify's order status page (with the live floor where Shopify shows the delivery map).
- **Ops console:** robotics tooling. Foxglove's dense panel workspace with topic-style titles (`/sim/world`, `/sim/events`), a raw message log, and step plots. From MAPF research visualisers: agents as circles, goal markers in each agent's colour, and an ImGui-style HUD (`time step`, `dt`, `agents`). Tableau 10 for agent colours, as in most plotting tools.
**Why:** for a portfolio piece aimed at Shopify and Atoms, looking like the tools those teams actually use says more than a generic dashboard. Splitting the light store from the dark console also matches how real companies separate customer UI from internal tools.
**Schema impact:** product images needed `products.image_url`, added in Alembic migration `4adb1450fc56`. The seed backfills existing rows.

### D17. Simulator view rebuilt in research-tool style; landing page for roles
**Context:** design review after D16: the store looked real, but the floor view (dark theme, hazard stripes, rack pods, rainbow robots, diamonds) was decorative rather than functional, and it was unclear who the console was for.
**Research:** PlanViz (the League of Robot Runners visualiser), RWARE (the standard multi-robot warehouse benchmark) and a MAPF research visualiser all share the same functional conventions: white cells on a grey grid, black obstacles, flat shelf squares, *one* agent colour, orange task/goal squares, IDs on agents, cell coordinates on the edges, and a plain sidebar of checkboxes, a time readout and a task table.
**Decision:** adopt those conventions exactly. State is encoded functionally: blue = working, grey = idle, red outline = offline, teal square under a robot = carrying, teal shelf = requested. Clicking a robot highlights its path, like agent selection in PlanViz. The console is light and plain, with native controls.
**Roles:** `/` is now a landing page that states Forma is a simulated company and offers *the store (customers)* or *the operations console (internal)*. The store no longer links customers into internal tools.
