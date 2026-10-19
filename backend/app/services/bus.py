"""Publish/subscribe event bus with two interchangeable backends.

* ``InMemoryBus`` - single process. Used for local dev and tests.
* ``RedisBus``    - Redis pub/sub. Needed once the simulation worker and the
  API run as separate processes, or when there are several API replicas that
  each hold their own WebSocket connections.

Messages are JSON-serialisable dicts. Delivery is at-most-once (fire and
forget), which is fine here because every snapshot carries the *full* world
state: a client that misses one simply renders the next.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any, Protocol

log = logging.getLogger(__name__)

SIM_CHANNEL = "forma:sim"  # snapshots + events, worker -> API
COMMAND_CHANNEL = "forma:commands"  # control commands, API -> worker


class Bus(Protocol):
    async def publish(self, channel: str, message: dict[str, Any]) -> None: ...

    def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]: ...

    async def close(self) -> None: ...


class InMemoryBus:
    def __init__(self, max_queue: int = 64) -> None:
        self._subs: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._max_queue = max_queue

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        for queue in list(self._subs[channel]):
            if queue.full():
                # Slow consumer: drop its oldest message rather than block the
                # publisher (the simulation loop must never wait on a client).
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(message)

    async def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._max_queue)
        self._subs[channel].add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subs[channel].discard(queue)

    async def close(self) -> None:
        self._subs.clear()


class RedisBus:
    def __init__(self, url: str | None = None, client: Any = None) -> None:
        if client is None:
            import redis.asyncio as redis

            if not url:
                raise ValueError("RedisBus needs a url or a client")
            client = redis.from_url(url, decode_responses=True)
        self._redis = client  # injectable so tests can use fakeredis

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        await self._redis.publish(channel, json.dumps(message))

    async def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        backoff = 0.5
        while True:  # reconnect loop: survive a Redis restart
            pubsub = self._redis.pubsub()
            try:
                await pubsub.subscribe(channel)
                backoff = 0.5
                async for raw in pubsub.listen():
                    if raw.get("type") == "message":
                        yield json.loads(raw["data"])
            except (ConnectionError, OSError) as exc:
                log.warning("redis subscription lost (%s); retrying in %.1fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10)
            finally:
                with contextlib.suppress(Exception):
                    await pubsub.aclose()

    async def close(self) -> None:
        await self._redis.aclose()


def make_bus(redis_url: str | None) -> Bus:
    return RedisBus(redis_url) if redis_url else InMemoryBus()
