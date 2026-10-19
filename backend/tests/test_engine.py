import random

import pytest

from app.simulation import RobotState, SimConfig, Simulation, default_warehouse
from app.simulation.grid import Warehouse
from app.simulation.pathfinding import manhattan

SKUS = [f"SKU-{i:03d}" for i in range(40)]


def make_sim(robots=4, scheduler="nearest", **cfg):
    sim = Simulation(default_warehouse(), robots, SimConfig(scheduler=scheduler, **cfg))
    sim.register_skus(SKUS)
    return sim


def random_orders(seed, n, max_lines=3):
    rng = random.Random(seed)
    return [
        (f"o{i}", [(rng.choice(SKUS), rng.randint(1, 3)) for _ in range(rng.randint(1, max_lines))])
        for i in range(n)
    ]


def test_single_robot_single_order_lifecycle():
    sim = make_sim(robots=1)
    sim.submit_order("o1", [("SKU-000", 1)])
    seen = []
    for _ in range(200):
        seen += [e["type"] for e in sim.tick()]
        if sim.all_shipped():
            break
    assert sim.all_shipped()
    assert seen.index("order_picking") < seen.index("task_picked") < seen.index("task_delivered")
    assert seen.index("task_delivered") < seen.index("order_packing") < seen.index("order_shipped")
    sim.run_until_idle() if not sim.all_shipped() else None
    # the robot eventually parks at home again
    for _ in range(100):
        sim.tick()
    robot = sim.robots[0]
    assert robot.state is RobotState.IDLE and robot.pos == robot.home


def test_robot_moves_one_cell_per_tick():
    sim = make_sim(robots=1)
    sim.submit_order("o1", [("SKU-010", 2)])
    prev = sim.robots[0].pos
    for _ in range(150):
        sim.tick()
        cur = sim.robots[0].pos
        assert manhattan(prev, cur) <= 1
        assert sim.wh.walkable(cur)
        prev = cur


def test_multi_order_with_multiple_robots_completes_without_collisions():
    sim = make_sim(robots=8)
    for oid, items in random_orders(seed=1, n=40):
        sim.submit_order(oid, items)

    prev = {r.id: r.pos for r in sim.robots.values()}
    for _ in range(20_000):
        sim.tick()  # _check_invariants raises on any vertex collision
        cur = {r.id: r.pos for r in sim.robots.values()}
        # no swaps: two robots never exchange cells in a single tick
        for a in cur:
            for b in cur:
                if a < b:
                    assert not (cur[a] == prev[b] and cur[b] == prev[a] and cur[a] != prev[a])
        prev = cur
        if sim.all_shipped():
            break
    assert sim.all_shipped(), sim.metrics()
    assert sim.metrics()["orders_shipped"] == 40


def test_simulation_is_deterministic():
    def run():
        sim = make_sim(robots=6)
        for oid, items in random_orders(seed=3, n=25):
            sim.submit_order(oid, items)
        hashes = []
        for _ in range(300):
            sim.tick()
            hashes.append(sim.state_hash())
        return hashes

    assert run() == run()


def test_submit_order_is_idempotent():
    sim = make_sim()
    first = sim.submit_order("dup", [("SKU-001", 1), ("SKU-002", 1)])
    again = sim.submit_order("dup", [("SKU-001", 1), ("SKU-002", 1)])
    assert [t.id for t in first] == [t.id for t in again]
    assert len(sim.tasks) == 2


@pytest.mark.parametrize("items", [[], [("SKU-001", 0)]])
def test_submit_order_validates(items):
    with pytest.raises(ValueError):
        make_sim().submit_order("bad", items)


def test_robot_going_offline_requeues_its_task_and_others_finish_it():
    sim = make_sim(robots=2, scheduler="fifo")
    sim.submit_order("o1", [("SKU-005", 1)])
    sim.tick()
    assert sim.robots[0].task_id is not None
    task_id = sim.robots[0].task_id

    sim.set_robot_online(0, False)
    offline_at, distance_before = sim.robots[0].pos, sim.robots[0].distance
    assert sim.robots[0].state is RobotState.OFFLINE
    assert sim.tasks[task_id].robot_id is None
    assert sim.queue[0] == task_id

    sim.run_until_idle(max_ticks=500)
    assert sim.tasks[task_id].robot_id == 1
    # the offline robot never moved again
    assert sim.robots[0].pos == offline_at and sim.robots[0].distance == distance_before

    sim.set_robot_online(0, True)
    for _ in range(50):
        sim.tick()
    assert sim.robots[0].state is RobotState.IDLE


def test_head_on_corridor_resolves():
    # Two robots must pass each other in a long 1-wide corridor that has a
    # single side pocket; without replanning they would deadlock forever.
    wh = Warehouse.from_ascii(
        [
            "#########",
            "#H.....P#",
            "####.####",
            "#########",
        ]
    )
    wh.homes.append((7, 1))  # second robot starts on the pack station side
    sim = Simulation(wh, 2, SimConfig(scheduler="fifo"))
    sim.robots[1].pos = sim.robots[1].home = (6, 1)
    sim.robots[0].path = [(x, 1) for x in range(2, 7)]
    sim.robots[0].state = RobotState.RETURNING
    sim.robots[1].path = [(x, 1) for x in range(5, 0, -1)]
    sim.robots[1].state = RobotState.RETURNING
    sim.robots[0].home, sim.robots[1].home = (6, 1), (1, 1)
    for _ in range(60):
        sim.tick()
    assert sim.robots[0].pos == (6, 1)
    assert sim.robots[1].pos == (1, 1)


@pytest.mark.parametrize("scheduler", ["fifo", "nearest", "batch_greedy"])
def test_every_scheduler_finishes_the_same_workload(scheduler):
    sim = make_sim(robots=6, scheduler=scheduler)
    for oid, items in random_orders(seed=9, n=30):
        sim.submit_order(oid, items)
    sim.run_until_idle(max_ticks=20_000)
    assert sim.metrics()["orders_shipped"] == 30


def test_too_many_robots_rejected():
    with pytest.raises(ValueError):
        Simulation(default_warehouse(), 99)


@pytest.mark.parametrize("seed", range(8))
def test_chaos_streaming_orders_with_robot_outages(seed):
    """Orders arrive mid-run while up to two robots at a time fail and recover.
    Every order must still ship, with no collisions along the way."""
    rng = random.Random(seed)
    sim = make_sim(robots=8, scheduler=rng.choice(["fifo", "nearest", "batch_greedy"]))
    orders = random_orders(seed=seed + 100, n=60)
    outages: dict[int, int] = {}
    for tick in range(20_000):
        if orders and rng.random() < 0.3:
            sim.submit_order(*orders.pop())
        for rid, back in list(outages.items()):
            if tick >= back:
                sim.set_robot_online(rid, True)
                del outages[rid]
        if len(outages) < 2 and rng.random() < 0.01:
            rid = rng.randrange(8)
            if rid not in outages:
                sim.set_robot_online(rid, False)
                outages[rid] = tick + rng.randint(50, 400)
        sim.tick()
        if not orders and not outages and sim.all_shipped():
            break
    assert sim.all_shipped() and sim.metrics()["orders_shipped"] == 60


def test_all_items_of_an_order_meet_at_one_pack_station():
    """An order is boxed at a single station, so every item must go there."""
    sim = make_sim(robots=8)
    for oid, items in random_orders(seed=4, n=40, max_lines=3):
        sim.submit_order(oid, items)
    delivered_at: dict[str, set] = {}
    for _ in range(20_000):
        for e in sim.tick():
            if e["type"] == "task_delivered":
                robot_pos = sim.robots[e["robot_id"]].pos
                delivered_at.setdefault(e["order_id"], set()).add(robot_pos)
        if sim.all_shipped():
            break
    assert sim.all_shipped()
    multi_item = [o for o in sim.orders.values() if len(o.task_ids) > 1]
    assert multi_item, "workload should contain multi-item orders"
    for order in sim.orders.values():
        assert delivered_at[order.id] == {order.pack_station}, order.id
    # Load balancing still spreads orders across stations.
    assert len({o.pack_station for o in sim.orders.values()}) > 1
