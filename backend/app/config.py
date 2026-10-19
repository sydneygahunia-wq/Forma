from functools import lru_cache
from typing import Literal

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
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
