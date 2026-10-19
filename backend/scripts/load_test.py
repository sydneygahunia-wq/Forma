"""HTTP load test + invariant check against a running API.

    python scripts/load_test.py --url http://localhost:8000 --orders 300 --concurrency 30

What it does:
  1. Snapshots stock levels.
  2. Fires N orders from C concurrent clients. ~10% of requests are re-sent
     with the same Idempotency-Key (simulating client retries), and a burst of
     clients all try to buy the same scarce product at once.
  3. Reports latency percentiles and status codes.
  4. Verifies the books balance: for every product,
        stock_before - stock_after == units in successfully created orders
     and no stock went negative, and every retry returned the original order.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import time
import uuid
from collections import Counter

import httpx


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--orders", type=int, default=300)
    ap.add_argument("--concurrency", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    async with httpx.AsyncClient(base_url=args.url, timeout=30) as client:
        before = {p["id"]: p for p in (await client.get("/api/products")).json()}
        in_stock = [p for p in before.values() if p["stock"] > 0]
        scarce = min(in_stock, key=lambda p: p["stock"])

        latencies: list[float] = []
        codes: Counter[int] = Counter()
        created: dict[str, dict[int, int]] = {}  # order id -> {product_id: qty}
        replay_mismatches = 0
        sem = asyncio.Semaphore(args.concurrency)

        async def place(items: list[dict], key: str) -> httpx.Response:
            async with sem:
                t0 = time.perf_counter()
                res = await client.post(
                    "/api/orders",
                    json={"customer_email": "load@example.com", "items": items},
                    headers={"Idempotency-Key": key},
                )
                latencies.append((time.perf_counter() - t0) * 1000)
                codes[res.status_code] += 1
                return res

        async def customer(i: int) -> None:
            nonlocal replay_mismatches
            if i % 25 == 0:  # a crowd going for the scarcest item
                items = [{"product_id": scarce["id"], "quantity": 1}]
            else:
                picks = rng.sample(in_stock, k=rng.randint(1, 3))
                items = [{"product_id": p["id"], "quantity": rng.randint(1, 2)} for p in picks]
            key = str(uuid.uuid4())
            first = await place(items, key)
            if first.status_code == 201:
                body = first.json()
                created[body["id"]] = {it["product_id"]: it["quantity"] for it in body["items"]}
            if rng.random() < 0.10:  # client retry with the same key
                retry = await place(items, key)
                # A replay must be 200 + Idempotent-Replayed and return the
                # *same* order, never a second one.
                if first.status_code == 201 and not (
                    retry.status_code == 200
                    and retry.headers.get("idempotent-replayed") == "true"
                    and retry.json()["id"] == first.json()["id"]
                ):
                    replay_mismatches += 1

        started = time.perf_counter()
        await asyncio.gather(*(customer(i) for i in range(args.orders)))
        elapsed = time.perf_counter() - started

        after = {p["id"]: p for p in (await client.get("/api/products")).json()}

    sold: Counter[int] = Counter()
    for lines in created.values():
        sold.update(lines)
    mismatched = [
        pid for pid in before if before[pid]["stock"] - after[pid]["stock"] != sold.get(pid, 0)
    ]
    negative = [pid for pid in after if after[pid]["stock"] < 0]

    lat = sorted(latencies)

    def pct(p: float) -> float:
        return lat[min(len(lat) - 1, int(p / 100 * len(lat)))]

    print(f"requests       {len(lat)} in {elapsed:.2f}s  ({len(lat) / elapsed:.0f} req/s)")
    print(f"status codes   {dict(sorted(codes.items()))}")
    print(
        f"latency ms     p50={pct(50):.1f}  p95={pct(95):.1f}  p99={pct(99):.1f}  "
        f"mean={statistics.mean(lat):.1f}"
    )
    print(f"orders created {len(created)}")
    sid = scarce["id"]
    print(f"scarce item    {scarce['name']}: {before[sid]['stock']} -> {after[sid]['stock']}")
    ok = not mismatched and not negative and replay_mismatches == 0
    print(
        f"inventory books balance: {not mismatched}   negative stock: {bool(negative)}   "
        f"retry mismatches: {replay_mismatches}"
    )
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
