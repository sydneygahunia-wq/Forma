import random

import pytest

from app.simulation.grid import DEFAULT_LAYOUT, Cell, Warehouse, default_warehouse
from app.simulation.pathfinding import (
    ALGORITHMS,
    astar,
    bfs,
    dijkstra,
    distance_map,
    manhattan,
)

OPEN = Warehouse.from_ascii(["P....", ".....", ".....", "....."])
WALLED = Warehouse.from_ascii(
    [
        "P.#..",
        "..#..",
        "..#..",
        ".....",
    ]
)
SEALED = Warehouse.from_ascii(["P.#..", "..#..", "###..", "....."])


def assert_valid_path(wh, path, start, goal):
    assert path[0] == start and path[-1] == goal
    for a, b in zip(path, path[1:]):
        assert manhattan(a, b) == 1, f"non-adjacent step {a}->{b}"
        assert wh.walkable(b)


def test_layout_parses_and_is_rectangular():
    wh = default_warehouse()
    assert wh.width == len(DEFAULT_LAYOUT[0]) and wh.height == len(DEFAULT_LAYOUT)
    assert len(wh.homes) == 8
    assert len(wh.pack_stations) == 4
    assert len(wh.shelves) == 72
    for shelf in wh.shelves:
        assert wh.cell(shelf.pos) is Cell.SHELF
        assert wh.cell(shelf.access) is Cell.FLOOR
        assert manhattan(shelf.pos, shelf.access) == 1


def test_one_way_layout_is_strongly_connected():
    """Every walkable cell must be reachable from every other one, or a robot
    could drive into a one-way aisle and never get out."""
    wh = default_warehouse()
    walkable = {(x, y) for y in range(wh.height) for x in range(wh.width) if wh.walkable((x, y))}
    for src in walkable:
        assert set(distance_map(wh, src)) == walkable, f"cells unreachable from {src}"


def test_lanes_are_respected():
    wh = default_warehouse()
    up_aisle = (4, 4)  # column 4 flows north
    assert (4, 3) in set(wh.neighbors(up_aisle))
    assert (4, 5) not in set(wh.neighbors(up_aisle))
    # Going "down" column 4 is illegal, so the route is longer than Manhattan.
    res = astar(wh, (4, 3), (4, 5))
    assert res.cost > 2
    for a, b in zip(res.path, res.path[1:]):
        assert b in set(wh.neighbors(a))


def test_reverse_distance_map_matches_forward_search():
    wh = default_warehouse()
    goal = wh.shelves[10].access
    to_goal = distance_map(wh, goal, reverse=True)
    for src in [(1, 2), (4, 9), (22, 12), (19, 5)]:
        assert to_goal[src] == bfs(wh, src, goal).cost


def test_layout_rejects_bad_input():
    with pytest.raises(ValueError):
        Warehouse.from_ascii(["P..", ".."])  # ragged
    with pytest.raises(ValueError):
        Warehouse.from_ascii(["P.Z"])  # unknown char
    with pytest.raises(ValueError):
        Warehouse.from_ascii(["..."])  # no pack station


@pytest.mark.parametrize("algo", ALGORITHMS.values(), ids=ALGORITHMS.keys())
def test_trivial_and_open_grid(algo):
    res = algo(OPEN, (0, 0), (0, 0))
    assert res.path == [(0, 0)] and res.cost == 0

    res = algo(OPEN, (0, 0), (4, 3))
    assert_valid_path(OPEN, res.path, (0, 0), (4, 3))
    assert res.cost == 7  # equals Manhattan distance on an empty grid


@pytest.mark.parametrize("algo", ALGORITHMS.values(), ids=ALGORITHMS.keys())
def test_routes_around_wall(algo):
    res = algo(WALLED, (0, 0), (4, 0))
    assert_valid_path(WALLED, res.path, (0, 0), (4, 0))
    assert res.cost == 10
    assert (2, 3) in res.path  # the only gap in the wall


@pytest.mark.parametrize("algo", ALGORITHMS.values(), ids=ALGORITHMS.keys())
def test_unreachable_returns_none(algo):
    res = algo(SEALED, (0, 0), (4, 0))
    assert res.path is None and not res.found


@pytest.mark.parametrize("algo", ALGORITHMS.values(), ids=ALGORITHMS.keys())
def test_blocked_cells_are_avoided(algo):
    res = algo(OPEN, (0, 0), (4, 0), blocked={(2, 0), (2, 1), (2, 2)})
    assert_valid_path(OPEN, res.path, (0, 0), (4, 0))
    assert not {(2, 0), (2, 1), (2, 2)} & set(res.path)


def test_all_three_agree_on_cost_for_random_pairs():
    """Property test: on unit costs BFS, Dijkstra and A* are all optimal."""
    wh = default_warehouse()
    walkable = [(x, y) for y in range(wh.height) for x in range(wh.width) if wh.walkable((x, y))]
    rng = random.Random(42)
    for _ in range(200):
        s, g = rng.choice(walkable), rng.choice(walkable)
        costs = {name: algo(wh, s, g).cost for name, algo in ALGORITHMS.items()}
        assert len(set(costs.values())) == 1, (s, g, costs)
        assert distance_map(wh, s)[g] == costs["bfs"]


def test_astar_expands_fewer_nodes_than_dijkstra():
    wh = default_warehouse()
    walkable = [(x, y) for y in range(wh.height) for x in range(wh.width) if wh.walkable((x, y))]
    rng = random.Random(7)
    a_total = d_total = 0
    for _ in range(100):
        s, g = rng.choice(walkable), rng.choice(walkable)
        a_total += astar(wh, s, g).expanded
        d_total += dijkstra(wh, s, g).expanded
    assert a_total < d_total


def test_weighted_costs_change_dijkstra_and_astar_but_not_bfs():
    # Make the straight route expensive; the weighted search should detour.
    expensive = {(1, 0), (2, 0), (3, 0)}

    def cost(p):
        return 10.0 if p in expensive else 1.0

    straight = bfs(OPEN, (0, 0), (4, 0))
    assert straight.cost == 4
    for algo in (dijkstra, astar):
        res = algo(OPEN, (0, 0), (4, 0), cost_fn=cost)
        assert not expensive & set(res.path)
        assert res.cost == 6
