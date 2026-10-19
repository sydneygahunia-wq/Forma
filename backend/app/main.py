"""FastAPI application: wiring only. Business logic lives in app/services."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import simulation, store
from app.config import Settings, get_settings
from app.db.seed import seed
from app.db.session import Database
from app.logging_config import RequestLogMiddleware, configure_logging
from app.services.bus import make_bus
from app.services.errors import DomainError
from app.services.hub import SnapshotHub
from app.services.rate_limit import RateLimiter
from app.services.sim_runner import SimulationRunner

log = logging.getLogger(__name__)


def run_migrations(url: str) -> None:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False  # keep the app's JSON logging
    command.upgrade(cfg, "head")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.database_url)
        if settings.auto_migrate:
            run_migrations(settings.database_url)
        if settings.seed_on_startup:
            with db.session() as s:
                if added := seed(s):
                    log.info("seeded %d products", added)

        bus = make_bus(settings.redis_url)
        hub = SnapshotHub(bus)
        app.state.db, app.state.bus, app.state.hub = db, bus, hub
        app.state.settings = settings
        app.state.rate_limiter = RateLimiter()
        await hub.start()

        runner = None
        if settings.sim_mode == "embedded":
            runner = SimulationRunner(settings, db, bus)
            await runner.start()
        app.state.runner = runner
        try:
            yield
        finally:
            if runner:
                await runner.stop()
            await hub.stop()
            await bus.close()
            db.engine.dispose()

    app = FastAPI(
        title="Forma API",
        version="0.1.0",
        description="E-commerce storefront + autonomous warehouse simulation.",
        lifespan=lifespan,
    )
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Idempotent-Replayed", "X-Request-ID"],
    )

    @app.exception_handler(DomainError)
    async def domain_error_handler(_request: Request, exc: DomainError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code, **exc.extra},
        )

    @app.get("/api/health", tags=["ops"])
    def health(request: Request):
        """Liveness + readiness: checks the database and the simulation feed."""
        db_ok = True
        try:
            with request.app.state.db.session() as s:
                s.execute(text("SELECT 1"))
        except Exception:
            db_ok = False
        latest = request.app.state.hub.latest
        body = {
            "status": "ok" if db_ok else "degraded",
            "database": db_ok,
            "simulation_tick": latest["tick"] if latest else None,
        }
        return JSONResponse(body, status_code=200 if db_ok else 503)

    app.include_router(store.router)
    app.include_router(simulation.router)
    app.include_router(simulation.ws_router)
    return app


app = create_app()
