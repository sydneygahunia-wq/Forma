"""Grid search algorithms: BFS, Dijkstra and A*, written from scratch.

All three share the same signature and return a ``SearchResult`` that records
how many nodes were expanded, so they can be compared on identical inputs.

Complexity on a grid with V cells (E <= 4V edges):
  BFS       O(V + E)          unit-cost edges only
  Dijkstra  O((V + E) log V)  any non-negative edge costs
  A*        O((V + E) log V)  worst case; far fewer expansions with a good heuristic
"""

from __future__ import annotations

import heapq
from collections import deque
from collections.abc import Callable, Collection
from dataclasses import dataclass

from app.simulation.grid import Pos, Warehouse

CostFn = Callable[[Pos], float]


@dataclass(frozen=True)
class SearchResult:
    path: list[Pos] | None  # start..goal inclusive, or None if unreachable
    cost: float
    expanded: int  # nodes popped from the frontier
    visited: frozenset[Pos]  # every node that was expanded (for visualisation)

    @property
    def found(self) -> bool:
        return self.path is not None


def manhattan(a: Pos, b: Pos) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _reconstruct(came_from: dict[Pos, Pos | None], goal: Pos) -> list[Pos]:
    path = [goal]
    while (prev := came_from[path[-1]]) is not None:
        path.append(prev)
    path.reverse()
    return path


def _passable(wh: Warehouse, blocked: Collection[Pos]) -> Callable[[Pos], list[Pos]]:
    def neighbors(pos: Pos) -> list[Pos]:
        return [n for n in wh.neighbors(pos) if n not in blocked]

    return neighbors


def bfs(wh: Warehouse, start: Pos, goal: Pos, blocked: Collection[Pos] = ()) -> SearchResult:
    neighbors = _passable(wh, blocked)
    came_from: dict[Pos, Pos | None] = {start: None}
    queue = deque([start])
    visited: set[Pos] = set()

    while queue:
        cur = queue.popleft()
        visited.add(cur)
        if cur == goal:
            path = _reconstruct(came_from, goal)
            return SearchResult(path, len(path) - 1, len(visited), frozenset(visited))
        for nxt in neighbors(cur):
            if nxt not in came_from:
                came_from[nxt] = cur
                queue.append(nxt)

    return SearchResult(None, float("inf"), len(visited), frozenset(visited))


def _best_first(
    wh: Warehouse,
    start: Pos,
    goal: Pos,
    blocked: Collection[Pos],
    cost_fn: CostFn | None,
    heuristic: Callable[[Pos], float],
) -> SearchResult:
    """Shared core of Dijkstra (heuristic = 0) and A*.

    Heap entries are (f, h, seq, node). Breaking f-ties on lower h prefers
    nodes closer to the goal; ``seq`` makes ordering fully deterministic.
    Stale heap entries are skipped (lazy deletion) instead of decrease-key.
    """
    neighbors = _passable(wh, blocked)
    step_cost = cost_fn or (lambda _pos: 1.0)

    g: dict[Pos, float] = {start: 0.0}
    came_from: dict[Pos, Pos | None] = {start: None}
    h0 = heuristic(start)
    frontier: list[tuple[float, float, int, Pos]] = [(h0, h0, 0, start)]
    seq = 1
    closed: set[Pos] = set()

    while frontier:
        _f, _h, _seq, cur = heapq.heappop(frontier)
        if cur in closed:
            continue
        closed.add(cur)
        if cur == goal:
            return SearchResult(
                _reconstruct(came_from, goal), g[goal], len(closed), frozenset(closed)
            )
        for nxt in neighbors(cur):
            new_g = g[cur] + step_cost(nxt)
            if new_g < g.get(nxt, float("inf")):
                g[nxt] = new_g
                came_from[nxt] = cur
                h = heuristic(nxt)
                heapq.heappush(frontier, (new_g + h, h, seq, nxt))
                seq += 1

    return SearchResult(None, float("inf"), len(closed), frozenset(closed))


def dijkstra(
    wh: Warehouse,
    start: Pos,
    goal: Pos,
    blocked: Collection[Pos] = (),
    cost_fn: CostFn | None = None,
) -> SearchResult:
    return _best_first(wh, start, goal, blocked, cost_fn, heuristic=lambda _p: 0.0)


def astar(
    wh: Warehouse,
    start: Pos,
    goal: Pos,
    blocked: Collection[Pos] = (),
    cost_fn: CostFn | None = None,
) -> SearchResult:
    # Manhattan distance is admissible and consistent on a 4-connected grid
    # as long as every step costs >= 1, so A* stays optimal.
    return _best_first(
        wh, start, goal, blocked, cost_fn, heuristic=lambda p: float(manhattan(p, goal))
    )


ALGORITHMS = {"bfs": bfs, "dijkstra": dijkstra, "astar": astar}


def distance_map(
    wh: Warehouse, source: Pos, blocked: Collection[Pos] = (), reverse: bool = False
) -> dict[Pos, int]:
    """BFS flood fill: shortest step count from ``source`` to every reachable cell.

    With ``reverse=True`` it walks edges backwards, giving the distance from
    every cell *to* ``source``. On a grid with one-way lanes those differ.
    """
    step = wh.predecessors if reverse else wh.neighbors

    def neighbors(pos: Pos) -> list[Pos]:
        return [n for n in step(pos) if n not in blocked]

    dist = {source: 0}
    queue = deque([source])
    while queue:
        cur = queue.popleft()
        for nxt in neighbors(cur):
            if nxt not in dist:
                dist[nxt] = dist[cur] + 1
                queue.append(nxt)
    return dist
