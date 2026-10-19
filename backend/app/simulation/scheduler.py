"""Task-assignment strategies.

A scheduler receives the available robots and the queued tasks (oldest first)
and returns ``(robot_id, task_id)`` pairs. Each robot and task appears at most
once. Schedulers must be deterministic.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.simulation.engine import Robot, Simulation, Task

Scheduler = Callable[["Simulation", list["Robot"], list["Task"]], list[tuple[int, int]]]


def fifo(sim: Simulation, robots: list[Robot], tasks: list[Task]) -> list[tuple[int, int]]:
    """Baseline: the oldest task goes to the lowest-numbered free robot."""
    return [(r.id, t.id) for r, t in zip(robots, tasks, strict=False)]


def nearest_robot(sim: Simulation, robots: list[Robot], tasks: list[Task]) -> list[tuple[int, int]]:
    """Oldest task first, but give it to the free robot closest to its shelf.

    Serving tasks in arrival order means no task can starve.
    """
    free = list(robots)
    pairs: list[tuple[int, int]] = []
    for task in tasks:
        if not free:
            break
        best = min(free, key=lambda r: (sim.travel_distance(r.pos, task.access), r.id))
        free.remove(best)
        pairs.append((best.id, task.id))
    return pairs


def batch_greedy(sim: Simulation, robots: list[Robot], tasks: list[Task]) -> list[tuple[int, int]]:
    """Look at a window of the oldest tasks and repeatedly commit the globally
    cheapest (robot, task) pair. Cost = travel to the shelf plus a small
    penalty for how long the task has already waited, which bounds starvation.
    """
    window = tasks[: max(len(robots) * 2, 1)]
    free = {r.id: r for r in robots}
    open_tasks = {t.id: t for t in window}
    pairs: list[tuple[int, int]] = []
    while free and open_tasks:
        best = min(
            (
                sim.travel_distance(r.pos, t.access) - 0.5 * (sim.tick_count - t.created_tick),
                r.id,
                t.id,
            )
            for r in free.values()
            for t in open_tasks.values()
        )
        _cost, rid, tid = best
        pairs.append((rid, tid))
        del free[rid]
        del open_tasks[tid]
    return pairs


SCHEDULERS: dict[str, Scheduler] = {
    "fifo": fifo,
    "nearest": nearest_robot,
    "batch_greedy": batch_greedy,
}
