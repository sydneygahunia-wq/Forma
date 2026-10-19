"""The runner is the bridge between the database and the engine. These tests
drive it tick by tick (no wall clock) so they are deterministic."""

import asyncio
import time

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.db.models import Order, OrderEvent, OrderStatus, Product
from app.main import create_app
from app.schemas import OrderCreate, OrderLineIn
from app.services.bus import InMemoryBus
from app.services.orders import place_order
from app.services.sim_runner import SimulationRunner


def _settings(db_url, **kw):
    return Settings(database_url=db_url, sim_mode="external", log_level="WARNING", **kw)


def _place(db, sku="MUG-001", qty=1, email="r@example.com"):
    with db.session() as s:
        pid = s.scalar(select(Product.id).where(Product.sku == sku))
        body = OrderCreate(customer_email=email, items=[OrderLineIn(product_id=pid, quantity=qty)])
        return place_order(s, body).order.id


def _status(db, public_id):
    with db.session() as s:
        return s.scalar(select(Order.status).where(Order.public_id == public_id))


def _run_until(runner, predicate, max_ticks=2000):
    for _ in range(max_ticks):
        runner._step()
        if predicate():
            return
    raise AssertionError("condition not reached")


def test_order_flows_from_database_through_simulation_to_shipped(migrated_db, db_url):
    db = migrated_db
    runner = SimulationRunner(_settings(db_url, num_robots=2), db, InMemoryBus())
    oid = _place(db, "MUG-001", 2)
    assert _status(db, oid) is OrderStatus.PLACED

    runner._step()  # dispatches the order into the simulation
    with db.session() as s:
        assert s.scalar(select(Order.dispatched_at).where(Order.public_id == oid)) is not None

    _run_until(runner, lambda: _status(db, oid) is OrderStatus.SHIPPED)
    with db.session() as s:
        order = s.scalar(select(Order).where(Order.public_id == oid))
        history = [
            e.status
            for e in s.scalars(
                select(OrderEvent).where(OrderEvent.order_id == order.id).order_by(OrderEvent.id)
            )
        ]
        assert order.shipped_at is not None
    assert history == [
        OrderStatus.PLACED,
        OrderStatus.PICKING,
        OrderStatus.PACKING,
        OrderStatus.SHIPPED,
    ]


def test_orders_are_dispatched_exactly_once(migrated_db, db_url):
    db = migrated_db
    runner = SimulationRunner(_settings(db_url), db, InMemoryBus())
    ids = [_place(db, email=f"x{i}@example.com") for i in range(5)]
    for _ in range(3):
        runner._step()
    assert set(runner.sim.orders) == set(ids)
    assert len(runner.sim.tasks) == 5


def test_restart_recovers_unfinished_orders(migrated_db, db_url):
    """Simulate a crash: the first runner accepts an order and dies mid-pick.
    A new runner (fresh, empty simulation) must pick it up and finish it."""
    db = migrated_db
    oid = _place(db, "LMP-008", 1)
    crashed = SimulationRunner(_settings(db_url), db, InMemoryBus())
    _run_until(crashed, lambda: _status(db, oid) is OrderStatus.PICKING)
    del crashed  # process "dies"; its in-memory state is gone

    fresh = SimulationRunner(_settings(db_url), db, InMemoryBus())
    assert fresh.sim.orders == {}
    fresh._recover()
    _run_until(fresh, lambda: _status(db, oid) is OrderStatus.SHIPPED)


def test_commands_apply(migrated_db, db_url):
    runner = SimulationRunner(_settings(db_url, num_robots=3), migrated_db, InMemoryBus())
    runner.apply_command({"action": "pause"})
    assert runner.paused
    runner.apply_command({"action": "resume"})
    runner.apply_command({"action": "speed", "tick_interval_ms": 100})
    assert runner.tick_interval == 0.1
    runner.apply_command({"action": "robot", "robot_id": 1, "online": False})
    assert runner.sim.robots[1].state.value == "offline"
    runner.apply_command({"action": "scheduler", "name": "fifo"})
    assert runner.sim.config.scheduler == "fifo"
    snap = runner.snapshot()
    assert snap["type"] == "snapshot" and len(snap["robots"]) == 3


def test_bus_drops_oldest_for_slow_subscribers():
    async def scenario():
        bus = InMemoryBus(max_queue=3)
        sub = bus.subscribe("c")
        first = asyncio.ensure_future(anext(sub))  # registers the subscriber
        await asyncio.sleep(0)
        for i in range(10):
            await bus.publish("c", {"n": i})
        got = [(await first)["n"]]
        got += [(await anext(sub))["n"] for _ in range(2)]
        return got

    assert asyncio.run(scenario()) == [7, 8, 9]


# ------------------------------------------------------------ live endpoints


def test_live_app_streams_snapshots_and_ships_orders(db_url):
    settings = Settings(
        database_url=db_url, sim_mode="embedded", tick_interval_ms=20, log_level="WARNING"
    )
    with TestClient(create_app(settings)) as client:
        layout = client.get("/api/warehouse/layout").json()
        assert layout["width"] == 26 and layout["lanes"]

        with client.websocket_connect("/ws/simulation") as ws:
            msg = ws.receive_json()
            while msg["type"] != "snapshot":
                msg = ws.receive_json()
            assert len(msg["robots"]) == settings.num_robots

        mug = client.get("/api/products").json()[0]
        order = client.post(
            "/api/orders",
            json={
                "customer_email": "live@example.com",
                "items": [{"product_id": mug["id"], "quantity": 1}],
            },
        ).json()
        deadline = time.time() + 30
        while time.time() < deadline:
            if client.get(f"/api/orders/{order['id']}").json()["status"] == "shipped":
                break
            time.sleep(0.05)
        else:
            raise AssertionError("order never shipped")

        state = client.get("/api/simulation/state").json()
        assert state["metrics"]["orders_shipped"] >= 1
        assert client.get("/api/health").json()["simulation_tick"] > 0
        events = client.get("/api/simulation/events").json()
        assert any(e["type"] == "order_shipped" for e in events)

        assert client.post("/api/simulation/commands", json={"action": "pause"}).status_code == 202
        bad = client.post("/api/simulation/commands", json={"action": "robot"})
        assert bad.status_code == 422


def test_pathfinding_compare_endpoint(client):
    res = client.get("/api/pathfinding/compare", params={"start": "1,2", "goal": "22,12"})
    assert res.status_code == 200
    body = res.json()
    assert body["bfs"]["cost"] == body["dijkstra"]["cost"] == body["astar"]["cost"]
    assert body["astar"]["expanded"] < body["dijkstra"]["expanded"]
    assert (
        client.get("/api/pathfinding/compare", params={"start": "0,0", "goal": "1,2"}).status_code
        == 422
    )
    assert (
        client.get("/api/pathfinding/compare", params={"start": "a", "goal": "1,2"}).status_code
        == 422
    )


def test_redis_bus_round_trip():
    """The Redis backend (used by the API/worker split) against fakeredis."""
    fakeredis = __import__("pytest").importorskip("fakeredis")
    from app.services.bus import RedisBus

    async def scenario():
        bus = RedisBus(client=fakeredis.FakeAsyncRedis(decode_responses=True))
        sub = bus.subscribe("forma:test")
        first = asyncio.ensure_future(anext(sub))
        await asyncio.sleep(0.05)  # let SUBSCRIBE reach the server
        await bus.publish("forma:test", {"type": "snapshot", "tick": 7})
        msg = await asyncio.wait_for(first, timeout=2)
        await sub.aclose()
        await bus.close()
        return msg

    assert asyncio.run(scenario()) == {"type": "snapshot", "tick": 7}
