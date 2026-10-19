"""Reproducible benchmarks for the simulation (no server, no database).

    python scripts/benchmark.py                # prints markdown tables
    python scripts/benchmark.py --out ../docs/BENCHMARKS.md

Part 1: task-assignment strategies. Every strategy sees exactly the same
        workloads (same seeds -> same orders, same arrival ticks).
Part 2: pathfinding. BFS vs Dijkstra vs A* on the same random queries.

Everything is deterministic except wall-clock timings in part 2.
"""

from __future__ import annotations

import argparse
import platform
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.simulation import SimConfig, Simulation, default_warehouse  # noqa: E402
from app.simulation.pathfinding import ALGORITHMS  # noqa: E402

SKUS = [f"SKU-{i:03d}" for i in range(48)]
SCHEDULERS = ["fifo", "nearest", "batch_greedy"]


def workload(seed: int, n_orders: int, rate: float) -> list[tuple[int, str, list[tuple[str, int]]]]:
    """Orders with Poisson arrivals: (arrival_tick, order_id, items)."""
    rng = random.Random(seed)
    tick, out = 0.0, []
    for i in range(n_orders):
        tick += rng.expovariate(rate)
        items = [(rng.choice(SKUS), rng.randint(1, 3)) for _ in range(rng.randint(1, 3))]
        out.append((int(tick), f"o{i}", items))
    return out


def run(scheduler: str, robots: int, orders) -> dict:
    sim = Simulation(default_warehouse(), robots, SimConfig(scheduler=scheduler))
    sim.register_skus(SKUS)
    pending = list(orders)
    while pending or not sim.all_shipped():
        while pending and pending[0][0] <= sim.tick_count:
            _, oid, items = pending.pop(0)
            sim.submit_order(oid, items)
        sim.tick()
        if sim.tick_count > 200_000:
            raise RuntimeError("did not finish")
    times = sorted(o.shipped_tick - o.created_tick for o in sim.completed_orders)
    m = sim.metrics()
    return {
        "avg": statistics.mean(times),
        "p95": times[int(0.95 * (len(times) - 1))],
        "makespan": sim.tick_count,
        "distance": m["total_distance"],
        "wait": m["total_wait_ticks"],
    }


def fmt(values: list[float]) -> str:
    mean = statistics.mean(values)
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    return f"{mean:,.1f} ± {sd:,.1f}"


def scheduler_benchmark(seeds: int, n_orders: int, robots: int, rate: float) -> list[str]:
    results = {
        s: [run(s, robots, workload(seed, n_orders, rate)) for seed in range(seeds)]
        for s in SCHEDULERS
    }
    base = {k: statistics.mean(r[k] for r in results["fifo"]) for k in results["fifo"][0]}
    lines = [
        f"**{robots} robots, {n_orders} orders, Poisson arrivals at {rate} orders/tick, "
        f"{seeds} seeds** (mean ± std dev across seeds; Δ = change in mean vs FIFO)",
        "",
        "| Scheduler | Avg fulfillment (ticks) | p95 fulfillment | Makespan "
        "| Robot distance | Wait ticks | Faster avg than FIFO on |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in SCHEDULERS:
        cells = []
        for k in ("avg", "p95", "makespan", "distance", "wait"):
            vals = [r[k] for r in results[s]]
            delta = (statistics.mean(vals) - base[k]) / base[k] * 100 if base[k] else 0.0
            cells.append(fmt(vals) + ("" if s == "fifo" else f" ({delta:+.1f}%)"))
        # Paired comparison: same seed = same workload, so compare run by run.
        wins = sum(r["avg"] < b["avg"] for r, b in zip(results[s], results["fifo"], strict=True))
        cells.append("-" if s == "fifo" else f"{wins}/{seeds} seeds")
        lines.append(f"| `{s}` | " + " | ".join(cells) + " |")
    return lines


def pathfinding_benchmark(queries: int) -> list[str]:
    wh = default_warehouse()
    cells = [(x, y) for y in range(wh.height) for x in range(wh.width) if wh.walkable((x, y))]
    rng = random.Random(0)
    pairs = [(rng.choice(cells), rng.choice(cells)) for _ in range(queries)]
    lines = [
        f"**{queries} random start/goal pairs on the default 26×14 layout (one-way lanes)**",
        "",
        "| Algorithm | Mean nodes expanded | Mean path cost | Mean time per query |",
        "|---|---|---|---|",
    ]
    for name, algo in ALGORITHMS.items():
        expanded, costs = [], []
        t0 = time.perf_counter()
        for s, g in pairs:
            res = algo(wh, s, g)
            expanded.append(res.expanded)
            costs.append(res.cost)
        per_query_us = (time.perf_counter() - t0) / queries * 1e6
        lines.append(
            f"| {name} | {statistics.mean(expanded):.1f} | {statistics.mean(costs):.2f} | "
            f"{per_query_us:.0f} µs |"
        )
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--orders", type=int, default=150)
    ap.add_argument("--robots", type=int, default=6)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    out = [
        "# Benchmarks",
        "",
        "Generated by `backend/scripts/benchmark.py` "
        f"(Python {platform.python_version()}, {platform.machine()}). "
        "Re-run it to reproduce; all simulation numbers are deterministic.",
        "",
        "## Task assignment",
        "",
        "Lower is better in every column. *Fulfillment* = ticks from order arrival to shipped.",
        "",
    ]
    for rate in (0.05, 0.10):
        out += scheduler_benchmark(args.seeds, args.orders, args.robots, rate) + [""]
    out += ["## Pathfinding", ""] + pathfinding_benchmark(1000) + [""]
    text = "\n".join(out)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)


if __name__ == "__main__":
    main()
