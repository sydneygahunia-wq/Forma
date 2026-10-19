import asyncio
import contextlib
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from app.api.deps import BusDep, HubDep, SessionDep
from app.services import orders
from app.services.bus import COMMAND_CHANNEL, SIM_CHANNEL
from app.simulation import default_warehouse
from app.simulation.pathfinding import ALGORITHMS

router = APIRouter(prefix="/api", tags=["simulation"])
ws_router = APIRouter(tags=["realtime"])
log = logging.getLogger(__name__)

_WAREHOUSE = default_warehouse()


@router.get("/warehouse/layout")
def warehouse_layout():
    return _WAREHOUSE.to_dict()


@router.get("/simulation/state")
def simulation_state(hub: HubDep):
    if hub.latest is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "simulation not running yet")
    return hub.latest


@router.get("/simulation/events")
def simulation_events(hub: HubDep, limit: Annotated[int, Query(ge=1, le=100)] = 30):
    return list(hub.recent_events)[-limit:][::-1]


class Command(BaseModel):
    action: Literal["pause", "resume", "speed", "robot", "scheduler"]
    robot_id: int | None = None
    online: bool | None = None
    tick_interval_ms: int | None = Field(default=None, ge=20, le=2000)
    name: Literal["fifo", "nearest", "batch_greedy"] | None = None


@router.post("/simulation/commands", status_code=status.HTTP_202_ACCEPTED)
async def send_command(cmd: Command, bus: BusDep):
    """Commands are asynchronous (202 Accepted): they're queued for the
    simulation loop, which applies them at the start of its next tick."""
    needs = {
        "robot": ("robot_id", "online"),
        "speed": ("tick_interval_ms",),
        "scheduler": ("name",),
    }
    missing = [f for f in needs.get(cmd.action, ()) if getattr(cmd, f) is None]
    if missing:
        raise HTTPException(422, f"action {cmd.action!r} requires {missing}")
    await bus.publish(COMMAND_CHANNEL, cmd.model_dump(exclude_none=True))
    return {"queued": cmd.model_dump(exclude_none=True)}


def _parse_pos(raw: str) -> tuple[int, int]:
    try:
        x, y = (int(v) for v in raw.split(","))
    except ValueError as exc:
        raise HTTPException(422, f"expected 'x,y', got {raw!r}") from exc
    if not _WAREHOUSE.walkable((x, y)):
        raise HTTPException(422, f"{(x, y)} is not a walkable cell")
    return x, y


@router.get("/pathfinding/compare")
def compare_pathfinding(start: str, goal: str):
    """Run BFS, Dijkstra and A* on the same query, for the visualiser."""
    s, g = _parse_pos(start), _parse_pos(goal)
    out = {}
    for name, algo in ALGORITHMS.items():
        res = algo(_WAREHOUSE, s, g)
        out[name] = {
            "path": res.path,
            "cost": res.cost if res.found else None,
            "expanded": res.expanded,
            "visited": sorted(res.visited),
        }
    return out


@router.get("/metrics")
def metrics(session: SessionDep, hub: HubDep):
    return {
        "store": orders.order_stats(session),
        "simulation": hub.latest["metrics"] if hub.latest else None,
    }


@ws_router.websocket("/ws/simulation")
async def simulation_ws(ws: WebSocket, hub: HubDep, bus: BusDep):
    """Push every snapshot and event batch to the client as JSON.

    The server never waits on a slow client: each connection reads from its own
    bounded queue, and the bus drops the oldest messages if it fills up.
    """
    await ws.accept()
    if hub.latest is not None:
        await ws.send_json(hub.latest)

    async def pump() -> None:
        async for msg in bus.subscribe(SIM_CHANNEL):
            await ws.send_json(msg)

    async def drain_client() -> None:
        # We don't expect client messages, but reading is how we notice a
        # disconnect promptly.
        while True:
            await ws.receive_text()

    tasks = [asyncio.create_task(pump()), asyncio.create_task(drain_client())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for t in tasks:
            t.cancel()
        for t in tasks:
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                await t
