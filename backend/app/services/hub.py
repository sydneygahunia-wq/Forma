import asyncio
import contextlib
import logging
from collections import deque
from typing import Any

from app.services.bus import SIM_CHANNEL, Bus

log = logging.getLogger(__name__)


class SnapshotHub:
    """API-side cache of the most recent simulation snapshot and events.

    Lets REST endpoints and newly connected WebSocket clients get the current
    state immediately, regardless of which process runs the simulation.
    """

    def __init__(self, bus: Bus) -> None:
        self.bus = bus
        self.latest: dict[str, Any] | None = None
        self.recent_events: deque[dict[str, Any]] = deque(maxlen=100)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._consume(), name="snapshot-hub")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _consume(self) -> None:
        async for msg in self.bus.subscribe(SIM_CHANNEL):
            if msg.get("type") == "snapshot":
                self.latest = msg
            elif msg.get("type") == "events":
                self.recent_events.extend(msg["events"])
