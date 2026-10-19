"""Discrete-time, deterministic warehouse simulation.

The engine is pure Python: no I/O, no clock, no randomness. Calling ``tick()``
advances the world by exactly one step and returns the events produced in that
step. Given the same layout, config and inputs it always produces the same
history, which is what makes the tests and benchmarks reproducible.

Each tick runs four phases in a fixed order:
  1. assign   - the scheduler gives queued tasks to available robots
  2. move     - every robot proposes its next cell; conflicts are resolved so
                that no two robots share a cell or swap through each other
  3. arrive   - robots that reached their goal change state / run timers
  4. orders   - orders whose items are all at a pack station are packed/shipped
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.simulation.grid import Pos, Warehouse
from app.simulation.pathfinding import astar, distance_map, manhattan
from app.simulation.scheduler import SCHEDULERS, Scheduler


class RobotState(StrEnum):
    IDLE = "idle"  # parked at home
    TO_SHELF = "to_shelf"
    PICKING = "picking"
    TO_PACK = "to_pack"
    DROPPING = "dropping"
    RETURNING = "returning"  # heading home with no task
    OFFLINE = "offline"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    ASSIGNED = "assigned"
    PICKED = "picked"
    DELIVERED = "delivered"


class OrderPhase(StrEnum):
    QUEUED = "queued"
    PICKING = "picking"
    PACKING = "packing"
    SHIPPED = "shipped"


# Robot states that follow a path and therefore try to move every tick.
MOVING_STATES = {RobotState.TO_SHELF, RobotState.TO_PACK, RobotState.RETURNING}
# Robots in these states can accept a new task.
AVAILABLE_STATES = {RobotState.IDLE, RobotState.RETURNING}
STATION_LOAD_WEIGHT = 15


@dataclass
class SimConfig:
    pick_ticks: int = 2  # base time to pick one unit; +1 per extra unit
    drop_ticks: int = 1
    pack_ticks: int = 3  # time at the pack station once every item has arrived
    replan_after: int = 2  # consecutive blocked ticks before replanning
    scheduler: str = "nearest"


@dataclass
class Task:
    id: int
    order_id: str
    sku: str
    quantity: int
    shelf_id: int
    access: Pos
    pack_station: Pos
    created_tick: int
    status: TaskStatus = TaskStatus.QUEUED
    robot_id: int | None = None
    assigned_tick: int | None = None
    delivered_tick: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "sku": self.sku,
            "quantity": self.quantity,
            "shelf_id": self.shelf_id,
            "access": self.access,
            "pack_station": self.pack_station,
            "status": self.status.value,
            "robot_id": self.robot_id,
        }


@dataclass
class Robot:
    id: int
    pos: Pos
    home: Pos
    state: RobotState = RobotState.IDLE
    task_id: int | None = None
    path: list[Pos] = field(default_factory=list)  # remaining cells, excluding pos
    timer: int = 0
    blocked_ticks: int = 0
    # metrics
    distance: int = 0
    wait_ticks: int = 0
    busy_ticks: int = 0
    replans: int = 0

    @property
    def goal(self) -> Pos | None:
        return self.path[-1] if self.path else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pos": self.pos,
            "home": self.home,
            "state": self.state.value,
            "task_id": self.task_id,
            "path": self.path,
            "distance": self.distance,
            "wait_ticks": self.wait_ticks,
        }


@dataclass
class OrderTrack:
    id: str
    task_ids: list[int]
    created_tick: int
    phase: OrderPhase = OrderPhase.QUEUED
    pack_timer: int = 0
    shipped_tick: int | None = None
    # Every item in an order must meet at ONE pack station to be boxed
    # together. Chosen when the order's first item is assigned a robot.
    pack_station: Pos | None = None


class Simulation:
    def __init__(
        self,
        warehouse: Warehouse,
        num_robots: int,
        config: SimConfig | None = None,
    ) -> None:
        if num_robots > len(warehouse.homes):
            raise ValueError(
                f"layout has {len(warehouse.homes)} home cells, cannot place {num_robots} robots"
            )
        self.wh = warehouse
        self.config = config or SimConfig()
        self.scheduler: Scheduler = SCHEDULERS[self.config.scheduler]
        self.tick_count = 0
        self.robots: dict[int, Robot] = {
            i: Robot(id=i, pos=home, home=home)
            for i, home in enumerate(warehouse.homes[:num_robots])
        }
        self.tasks: dict[int, Task] = {}
        self.queue: list[int] = []  # task ids awaiting a robot, oldest first
        self.orders: dict[str, OrderTrack] = {}
        self.sku_shelf: dict[str, int] = {}
        self._next_task_id = 0
        self._events: list[dict[str, Any]] = []
        self._dist_cache: dict[Pos, dict[Pos, int]] = {}
        self.completed_orders: list[OrderTrack] = []

    # ------------------------------------------------------------------ inputs

    def register_skus(self, skus: list[str]) -> None:
        """Assign each SKU a shelf slot, in the order given (wraps if needed)."""
        for sku in skus:
            if sku not in self.sku_shelf:
                self.sku_shelf[sku] = len(self.sku_shelf) % len(self.wh.shelves)

    def submit_order(self, order_id: str, items: list[tuple[str, int]]) -> list[Task]:
        """Turn an order into one pick task per line item. Idempotent per order id."""
        if order_id in self.orders:
            return [self.tasks[t] for t in self.orders[order_id].task_ids]
        if not items:
            raise ValueError("order has no items")

        created: list[Task] = []
        for sku, qty in items:
            if qty <= 0:
                raise ValueError("quantity must be positive")
            self.register_skus([sku])
            shelf = self.wh.shelves[self.sku_shelf[sku]]
            task = Task(
                id=self._next_task_id,
                order_id=order_id,
                sku=sku,
                quantity=qty,
                shelf_id=shelf.id,
                access=shelf.access,
                pack_station=self._nearest_pack_station(shelf.access),
                created_tick=self.tick_count,
            )
            self._next_task_id += 1
            self.tasks[task.id] = task
            self.queue.append(task.id)
            created.append(task)

        self.orders[order_id] = OrderTrack(
            id=order_id, task_ids=[t.id for t in created], created_tick=self.tick_count
        )
        self._emit("order_queued", order_id=order_id, tasks=len(created))
        return created

    def set_robot_online(self, robot_id: int, online: bool) -> None:
        robot = self.robots[robot_id]
        if not online and robot.state is not RobotState.OFFLINE:
            if robot.task_id is not None:
                self._requeue(robot.task_id)
            robot.task_id = None
            robot.path = []
            robot.state = RobotState.OFFLINE
            self._emit("robot_offline", robot_id=robot_id, pos=robot.pos)
        elif online and robot.state is RobotState.OFFLINE:
            self._go_home(robot)
            self._emit("robot_online", robot_id=robot_id, pos=robot.pos)

    # -------------------------------------------------------------------- tick

    def tick(self) -> list[dict[str, Any]]:
        self.tick_count += 1
        self._assign()
        self._move()
        self._arrive()
        self._advance_orders()
        for r in self.robots.values():
            if r.state not in (RobotState.IDLE, RobotState.OFFLINE):
                r.busy_ticks += 1
        events, self._events = self._events, []
        return events

    def run_until_idle(self, max_ticks: int = 100_000) -> int:
        """Tick until every submitted order has shipped. Returns ticks used."""
        start = self.tick_count
        while not self.all_shipped():
            if self.tick_count - start >= max_ticks:
                raise RuntimeError(f"simulation did not finish within {max_ticks} ticks")
            self.tick()
        return self.tick_count - start

    def all_shipped(self) -> bool:
        return all(o.phase is OrderPhase.SHIPPED for o in self.orders.values())

    # ------------------------------------------------------------------ phases

    def _assign(self) -> None:
        available = [
            r
            for r in sorted(self.robots.values(), key=lambda r: r.id)
            if r.state in AVAILABLE_STATES
        ]
        if not available or not self.queue:
            return
        queued = [self.tasks[t] for t in self.queue]
        for robot_id, task_id in self.scheduler(self, available, queued):
            robot, task = self.robots[robot_id], self.tasks[task_id]
            self.queue.remove(task_id)
            task.status = TaskStatus.ASSIGNED
            task.robot_id = robot_id
            task.assigned_tick = self.tick_count
            order = self.orders[task.order_id]
            if order.pack_station is None:
                order.pack_station = self._choose_pack_station(order)
            task.pack_station = order.pack_station
            robot.task_id = task_id
            robot.state = RobotState.TO_SHELF
            self._plan(robot, task.access)
            if order.phase is OrderPhase.QUEUED:
                order.phase = OrderPhase.PICKING
                self._emit("order_picking", order_id=order.id)
            self._emit("task_assigned", task_id=task_id, robot_id=robot_id, order_id=task.order_id)

    def _move(self) -> None:
        robots = sorted(self.robots.values(), key=lambda r: r.id)
        target: dict[int, Pos] = {}
        for r in robots:
            wants_move = r.state in MOVING_STATES and r.path
            target[r.id] = r.path[0] if wants_move else r.pos

        # Resolve conflicts to a fixpoint. A move is only ever cancelled (robot
        # stays put), never added, so this terminates in at most N rounds.
        changed = True
        while changed:
            changed = False
            # Vertex conflicts: at most one robot may end the tick in a cell.
            by_cell: dict[Pos, list[Robot]] = defaultdict(list)
            for r in robots:
                by_cell[target[r.id]].append(r)
            for cell, group in by_cell.items():
                if len(group) < 2:
                    continue
                stayer = next((r for r in group if r.pos == cell), None)
                winner = stayer or group[0]  # lowest id wins a contested cell
                for r in group:
                    if r is not winner and target[r.id] != r.pos:
                        target[r.id] = r.pos
                        changed = True
            # Edge (swap) conflicts: two robots may not pass through each other.
            pos_owner = {r.pos: r for r in robots}
            for r in robots:
                dest = target[r.id]
                other = pos_owner.get(dest)
                if other and other is not r and target[other.id] == r.pos and dest != r.pos:
                    target[r.id] = r.pos
                    target[other.id] = other.pos
                    changed = True

        for r in robots:
            if r.state not in MOVING_STATES or not r.path:
                continue
            if target[r.id] != r.pos:
                r.pos = r.path.pop(0)
                r.distance += 1
                r.blocked_ticks = 0
            else:
                r.wait_ticks += 1
                r.blocked_ticks += 1
                if r.blocked_ticks >= self.config.replan_after:
                    self._replan_around_robots(r)

        self._check_invariants()

    def _arrive(self) -> None:
        for r in sorted(self.robots.values(), key=lambda r: r.id):
            task = self.tasks.get(r.task_id) if r.task_id is not None else None

            if r.state is RobotState.TO_SHELF and not r.path:
                assert task is not None
                r.state = RobotState.PICKING
                r.timer = self.config.pick_ticks + task.quantity - 1
            elif r.state is RobotState.PICKING:
                assert task is not None
                r.timer -= 1
                if r.timer <= 0:
                    task.status = TaskStatus.PICKED
                    r.state = RobotState.TO_PACK
                    self._plan(r, task.pack_station)
                    self._emit(
                        "task_picked", task_id=task.id, robot_id=r.id, order_id=task.order_id
                    )
            elif r.state is RobotState.TO_PACK and not r.path:
                r.state = RobotState.DROPPING
                r.timer = self.config.drop_ticks
            elif r.state is RobotState.DROPPING:
                assert task is not None
                r.timer -= 1
                if r.timer <= 0:
                    task.status = TaskStatus.DELIVERED
                    task.delivered_tick = self.tick_count
                    r.task_id = None
                    self._go_home(r)
                    self._emit(
                        "task_delivered", task_id=task.id, robot_id=r.id, order_id=task.order_id
                    )
            elif r.state is RobotState.RETURNING and not r.path:
                if r.pos == r.home:
                    r.state = RobotState.IDLE
                else:  # path was blocked and dropped; try again
                    self._plan(r, r.home)

    def _advance_orders(self) -> None:
        for order in self.orders.values():
            if order.phase is OrderPhase.PICKING and all(
                self.tasks[t].status is TaskStatus.DELIVERED for t in order.task_ids
            ):
                order.phase = OrderPhase.PACKING
                order.pack_timer = self.config.pack_ticks
                self._emit("order_packing", order_id=order.id)
            elif order.phase is OrderPhase.PACKING:
                order.pack_timer -= 1
                if order.pack_timer <= 0:
                    order.phase = OrderPhase.SHIPPED
                    order.shipped_tick = self.tick_count
                    self.completed_orders.append(order)
                    self._emit(
                        "order_shipped",
                        order_id=order.id,
                        fulfillment_ticks=order.shipped_tick - order.created_tick,
                    )

    # ----------------------------------------------------------------- helpers

    def _static_blocked(self, robot: Robot) -> set[Pos]:
        # Other robots' parking spots are off-limits so idle robots never block,
        # and robots known to be offline are treated as walls.
        others = [r for r in self.robots.values() if r.id != robot.id]
        return {r.home for r in others} | {r.pos for r in others if r.state is RobotState.OFFLINE}

    def _plan(self, robot: Robot, goal: Pos) -> None:
        if robot.pos == goal:
            robot.path = []
            return
        homes = {r.home for r in self.robots.values() if r.id != robot.id}
        result = astar(self.wh, robot.pos, goal, blocked=self._static_blocked(robot) - {goal})
        if result.path is None:
            # The only route runs through an offline robot. Plan through it
            # anyway; the robot will queue behind it until it is recovered.
            result = astar(self.wh, robot.pos, goal, blocked=homes - {goal})
        if result.path is None:
            raise RuntimeError(f"robot {robot.id}: no path from {robot.pos} to {goal}")
        robot.path = result.path[1:]

    def _replan_around_robots(self, robot: Robot) -> None:
        """Path replanning: treat robots currently in the way as obstacles."""
        goal = robot.goal
        if goal is None:
            return
        others = {r.pos for r in self.robots.values() if r.id != robot.id}
        blocked = (self._static_blocked(robot) | others) - {goal}
        result = astar(self.wh, robot.pos, goal, blocked=blocked)
        robot.blocked_ticks = 0
        robot.replans += 1
        # Only take the detour if it exists and isn't absurdly long; otherwise
        # keep waiting on the original path (the blocker is usually transient).
        # A "detour" that still steps into the blocked cell (it happens when the
        # blocker is standing on our goal) is no detour at all.
        if (
            result.path is not None
            and len(result.path) > 1
            and result.path[1] != robot.path[0]
            and len(result.path) - 1 <= len(robot.path) + 12
        ):
            robot.path = result.path[1:]
            return
        self._maybe_yield(robot)

    def _maybe_yield(self, robot: Robot) -> None:
        """Break head-on deadlocks with a fixed priority: lower id has right of way.

        If the robot in front of us wants our cell, and it outranks us, we step
        into a free side cell, then continue to our goal from there.
        """
        if not robot.path:
            return
        blocker = next((r for r in self.robots.values() if r.pos == robot.path[0]), None)
        if (
            blocker is None
            or blocker.id > robot.id
            or blocker.state not in MOVING_STATES
            or not blocker.path
            or blocker.path[0] != robot.pos
        ):
            return
        occupied = {r.pos for r in self.robots.values()}
        forbidden = occupied | self._static_blocked(robot)
        sides = [n for n in self.wh.neighbors(robot.pos) if n not in forbidden]
        if not sides:
            return
        # Prefer a cell the blocker won't drive through.
        sides.sort(key=lambda c: c in blocker.path)
        side = sides[0]
        rest = astar(self.wh, side, robot.path[-1], blocked=self._static_blocked(robot))
        if rest.path is not None:
            robot.path = [side, *rest.path[1:]] if rest.path[1:] else [side]
            self._emit("robot_yield", robot_id=robot.id, to=side, blocker=blocker.id)

    def _go_home(self, robot: Robot) -> None:
        robot.state = RobotState.RETURNING
        self._plan(robot, robot.home)
        if not robot.path:
            robot.state = RobotState.IDLE

    def _requeue(self, task_id: int) -> None:
        task = self.tasks[task_id]
        task.status = TaskStatus.QUEUED
        task.robot_id = None
        task.assigned_tick = None
        self.queue.insert(0, task_id)  # it was already waiting; put it first
        self._emit("task_requeued", task_id=task_id, order_id=task.order_id)

    def _nearest_pack_station(self, pos: Pos) -> Pos:
        return min(self.wh.pack_stations, key=lambda p: (manhattan(p, pos), p))

    def _choose_pack_station(self, order: OrderTrack) -> Pos:
        """Pick one station for the whole order.

        Cost = total travel from each of the order's shelves to the station,
        plus ``STATION_LOAD_WEIGHT`` for every undelivered item that other
        orders are already sending there (spreads orders across stations).
        """
        load: dict[Pos, int] = defaultdict(int)
        for other in self.orders.values():
            if other.id == order.id or other.pack_station is None:
                continue
            load[other.pack_station] += sum(
                self.tasks[t].status is not TaskStatus.DELIVERED for t in other.task_ids
            )
        shelves = [self.tasks[t].access for t in order.task_ids]
        return min(
            self.wh.pack_stations,
            key=lambda p: (
                sum(self.travel_distance(a, p) for a in shelves) + STATION_LOAD_WEIGHT * load[p],
                p,
            ),
        )

    def travel_distance(self, src: Pos, dst: Pos) -> int:
        """Static shortest-path distance, cached per destination (BFS flood fill)."""
        dmap = self._dist_cache.get(dst)
        if dmap is None:
            dmap = self._dist_cache[dst] = distance_map(self.wh, dst, reverse=True)
        return dmap.get(src, 10**9)

    def _check_invariants(self) -> None:
        cells = [r.pos for r in self.robots.values()]
        if len(cells) != len(set(cells)):
            raise AssertionError(f"collision at tick {self.tick_count}: {cells}")

    def _emit(self, kind: str, **data: Any) -> None:
        self._events.append({"type": kind, "tick": self.tick_count, **data})

    # ----------------------------------------------------------------- outputs

    def metrics(self) -> dict[str, Any]:
        done = self.completed_orders
        robots = list(self.robots.values())
        ticks = max(self.tick_count, 1)
        fulfil = [o.shipped_tick - o.created_tick for o in done if o.shipped_tick is not None]
        return {
            "tick": self.tick_count,
            "orders_total": len(self.orders),
            "orders_shipped": len(done),
            "orders_in_progress": sum(
                o.phase in (OrderPhase.PICKING, OrderPhase.PACKING) for o in self.orders.values()
            ),
            "tasks_queued": len(self.queue),
            "avg_fulfillment_ticks": round(sum(fulfil) / len(fulfil), 2) if fulfil else None,
            "max_fulfillment_ticks": max(fulfil) if fulfil else None,
            "total_distance": sum(r.distance for r in robots),
            "total_wait_ticks": sum(r.wait_ticks for r in robots),
            "total_replans": sum(r.replans for r in robots),
            "utilization": round(sum(r.busy_ticks for r in robots) / (ticks * len(robots)), 3),
            "throughput_per_100_ticks": round(len(done) * 100 / ticks, 2),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "tick": self.tick_count,
            "scheduler": self.config.scheduler,
            "robots": [r.to_dict() for r in sorted(self.robots.values(), key=lambda r: r.id)],
            "tasks": [
                t.to_dict() for t in self.tasks.values() if t.status is not TaskStatus.DELIVERED
            ],
            "orders": {
                o.id: o.phase.value
                for o in self.orders.values()
                if o.phase is not OrderPhase.SHIPPED
            },
            "metrics": self.metrics(),
        }

    def state_hash(self) -> str:
        """Fingerprint of the full world state, used to prove determinism."""
        state = {
            "tick": self.tick_count,
            "robots": [r.to_dict() for r in sorted(self.robots.values(), key=lambda r: r.id)],
            "tasks": [t.to_dict() for t in self.tasks.values()],
        }
        return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
