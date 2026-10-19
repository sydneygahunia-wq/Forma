"""Standalone simulation worker: ``python -m app.worker``.

Used when SIM_MODE=external. The API and this worker talk only through the
database (orders outbox) and Redis (snapshots out, commands in), so either can
be restarted without taking the other down.
"""

import asyncio
import logging
import signal

from app.config import get_settings
from app.db.session import Database
from app.logging_config import configure_logging
from app.main import run_migrations
from app.services.bus import make_bus
from app.services.sim_runner import SimulationRunner

log = logging.getLogger("forma.worker")


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if not settings.redis_url:
        raise SystemExit("the external worker needs REDIS_URL so the API can see its output")
    if settings.auto_migrate:
        run_migrations(settings.database_url)

    db = Database(settings.database_url)
    bus = make_bus(settings.redis_url)
    runner = SimulationRunner(settings, db, bus)
    await runner.start()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    log.info("shutting down")
    await runner.stop()
    await bus.close()


if __name__ == "__main__":
    asyncio.run(main())
