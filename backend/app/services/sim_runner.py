"""Drives the pure simulation engine in real time and connects it to the world.

    ┌──────────┐ poll undispatched ┌───────────┐  tick()  ┌────────────┐
    │ Postgres │ ────────────────► │  Runner   │ ───────► │ Simulation │
    │ (orders) │ ◄──────────────── │ (asyncio) │ ◄─────── │  (engine)  │
    └──────────┘  status updates   └─────┬─────┘  events  └────────────┘
                                         │ publish snapshot + events
                                         ▼
                                   bus (memory / Redis) ──► WebSocket clients

The database is the source of truth and doubles as a durable queue: an order
row with ``dispatched_at IS NULL`` is work the simulation hasn't accepted yet
(the transactional outbox pattern). That makes crashes recoverable: on startup
the runner re-dispatches every order that never shipped.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db.models import Order, OrderEvent, OrderItem, OrderStatus, Product, utcnow
from app.db.session import Database
from app.services.bus import COMMAND_CHANNEL, SIM_CHANNEL, Bus
from app.services.orders import rowcount
from app.simulation import SimConfig, Simulation, default_warehouse

log = logging.getLogger(__name__)

# Simulation events that change an order's status in the database.
EVENT_STATUS = {
    "order_picking": (OrderStatus.PICKING, "A robot is picking your items"),
    "order_packing": (OrderStatus.PACKING, "All items reached the pack station"),
    "order_shipped": (OrderStatus.SHIPPED, "Packed and shipped"),
}
DISPATCH_BATCH = 100


class SimulationRunner:
    def __init__(self, settings: Settings, db: Database, bus: Bus) -> None:
        self.settings = settings
        self.db = db
        self.bus = bus
        self.paused = False
        self.tick_interval = settings.tick_interval_ms / 1000
        self.sim = self._new_sim(settings.scheduler)
        self.recent_events: deque[dict[str, Any]] = deque(maxlen=50)
        self._commands: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._tasks: list[asyncio.Task[None]] = []
        self.last_tick_ms = 0.0

    def _new_sim(self, scheduler: str) -> Simulation:
        sim = Simulation(
            default_warehouse(), self.settings.num_robots, SimConfig(scheduler=scheduler)
        )
        with self.db.session() as s:
            sim.register_skus(list(s.scalars(select(Product.sku).order_by(Product.id))))
        return sim

    # ------------------------------------------------------------- lifecycle

    async def start(self) -> None:
        await asyncio.to_thread(self._recover)
        self._tasks = [
            asyncio.create_task(self._loop(), name="sim-loop"),
            asyncio.create_task(self._listen_commands(), name="sim-commands"),
        ]
        log.info("simulation runner started (%s robots)", self.settings.num_robots)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def _recover(self) -> None:
        """After a restart the in-memory simulation is empty, so every order
        that hadn't shipped is handed to it again from the beginning."""
        with self.db.session() as s:
            result = s.execute(
                update(Order)
                .where(Order.status != OrderStatus.SHIPPED, Order.dispatched_at.is_not(None))
                .values(dispatched_at=None)
            )
            s.commit()
            if n := rowcount(result):
                log.warning("re-dispatching %d unfinished orders after restart", n)

    # ------------------------------------------------------------------ loop

    async def _loop(self) -> None:
        next_at = time.monotonic()
        while True:
            try:
                await self._drain_commands()
                if not self.paused:
                    started = time.perf_counter()
                    events = await asyncio.to_thread(self._step)
                    self.last_tick_ms = (time.perf_counter() - started) * 1000
                    self.recent_events.extend(events)
                    await self.bus.publish(SIM_CHANNEL, {"type": "events", "events": events})
                await self.bus.publish(SIM_CHANNEL, self.snapshot())
            except asyncio.CancelledError:
                raise
            except Exception:
                # Never let one bad tick (e.g. a DB blip) kill the loop.
                log.exception("simulation tick failed; continuing")
            # Fixed-rate schedule that doesn't drift when a tick runs long.
            next_at += self.tick_interval
            await asyncio.sleep(max(0.0, next_at - time.monotonic()))
            if time.monotonic() - next_at > 1:
                next_at = time.monotonic()  # fell far behind; resync

    def _step(self) -> list[dict[str, Any]]:
        """One tick. Runs in a worker thread so DB I/O doesn't block asyncio."""
        with self.db.session() as s:
            # 1. Pull new orders from the outbox.
            new_orders = list(
                s.scalars(
                    select(Order)
                    .where(Order.status != OrderStatus.SHIPPED, Order.dispatched_at.is_(None))
                    .order_by(Order.id)
                    .limit(DISPATCH_BATCH)
                    .options(selectinload(Order.items).selectinload(OrderItem.product))
                )
            )
            for order in new_orders:
                items = [(i.product.sku, i.quantity) for i in order.items]
                self.sim.submit_order(order.public_id, items)
                order.dispatched_at = utcnow()
            s.commit()

        # 2. Advance the world.
        events = self.sim.tick()

        # 3. Persist status changes (one transaction per tick).
        changes = [e for e in events if e["type"] in EVENT_STATUS]
        if changes:
            with self.db.session() as s:
                ids = {e["order_id"] for e in changes}
                by_id = {
                    o.public_id: o for o in s.scalars(select(Order).where(Order.public_id.in_(ids)))
                }
                for e in changes:
                    changed = by_id.get(e["order_id"])
                    if changed is None:
                        continue
                    status, message = EVENT_STATUS[e["type"]]
                    changed.status = status
                    if status is OrderStatus.SHIPPED:
                        changed.shipped_at = utcnow()
                    s.add(OrderEvent(order_id=changed.id, status=status, message=message))
                s.commit()
        return events

    # -------------------------------------------------------------- commands

    async def _listen_commands(self) -> None:
        async for cmd in self.bus.subscribe(COMMAND_CHANNEL):
            await self._commands.put(cmd)

    async def _drain_commands(self) -> None:
        while not self._commands.empty():
            cmd = self._commands.get_nowait()
            try:
                self.apply_command(cmd)
            except (KeyError, ValueError) as exc:
                log.warning("ignoring bad command %s: %s", cmd, exc)

    def apply_command(self, cmd: dict[str, Any]) -> None:
        action = cmd["action"]
        if action == "pause":
            self.paused = True
        elif action == "resume":
            self.paused = False
        elif action == "speed":
            self.tick_interval = max(0.02, min(2.0, float(cmd["tick_interval_ms"]) / 1000))
        elif action == "robot":
            self.sim.set_robot_online(int(cmd["robot_id"]), bool(cmd["online"]))
        elif action == "scheduler":
            # Swap strategy in place; robots and tasks keep their state.
            from app.simulation.scheduler import SCHEDULERS

            name = cmd["name"]
            self.sim.scheduler = SCHEDULERS[name]
            self.sim.config.scheduler = name
        else:
            raise ValueError(f"unknown action {action!r}")
        log.info("applied command %s", cmd)

    # --------------------------------------------------------------- output

    def snapshot(self) -> dict[str, Any]:
        snap = self.sim.snapshot()
        snap.update(
            type="snapshot",
            paused=self.paused,
            tick_interval_ms=round(self.tick_interval * 1000),
            last_tick_ms=round(self.last_tick_ms, 2),
        )
        return snap
