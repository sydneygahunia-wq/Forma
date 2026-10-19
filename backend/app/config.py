from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (or backend/.env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./forma.db"
    # Unset -> in-process event bus. Set -> Redis pub/sub, which lets the
    # simulation worker and the API run as separate processes / replicas.
    redis_url: str | None = None

    # "embedded": the API process runs the simulation loop itself.
    # "external": a separate `python -m app.worker` process runs it.
    sim_mode: Literal["embedded", "external"] = "embedded"
    tick_interval_ms: int = 250
    num_robots: int = 6
    # batch_greedy won on every seed in docs/BENCHMARKS.md, so it is the default.
    scheduler: Literal["fifo", "nearest", "batch_greedy"] = "batch_greedy"

    auto_migrate: bool = True
    seed_on_startup: bool = True
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    # Lets every deployment of the frontend (e.g. Vercel preview URLs) call
    # the API without listing each one: r"https://forma.*\.vercel\.app"
    cors_origin_regex: str | None = None
    log_level: str = "INFO"

    # Public-demo safeguards (off locally, on in production via env vars).
    # A shared demo must survive visitors: stock is topped up, anything a
    # visitor breaks heals itself, and request rates are capped per client.
    demo_mode: bool = False
    demo_restock_every_s: int = 300
    demo_heal_after_s: int = 120
    rate_limit_orders_per_min: int = 0  # 0 = unlimited
    rate_limit_writes_per_min: int = 0  # carts + simulation commands

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, url: str) -> str:
        """Hosted Postgres (Neon, Render, Heroku) hands out postgres:// or
        postgresql:// URLs; SQLAlchemy needs the driver named explicitly."""
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
