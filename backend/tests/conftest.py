import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import Settings
from app.db.models import Base
from app.db.session import Database
from app.main import create_app, run_migrations

PG_URL = os.environ.get("TEST_DATABASE_URL")

# Every DB-backed test runs on SQLite; if TEST_DATABASE_URL points at Postgres
# (as it does in CI) it runs there as well.
DB_BACKENDS = ["sqlite"] + (["postgres"] if PG_URL else [])


def _reset_postgres(url: str) -> None:
    engine = create_engine(url)
    with engine.begin() as conn:
        Base.metadata.drop_all(conn)
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    engine.dispose()


@pytest.fixture(params=DB_BACKENDS)
def db_url(request, tmp_path):
    if request.param == "postgres":
        _reset_postgres(PG_URL)
        return PG_URL
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def settings(db_url) -> Settings:
    # sim_mode=external: no background loop, so store tests are deterministic.
    return Settings(database_url=db_url, sim_mode="external", redis_url=None, log_level="WARNING")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def db(settings, client) -> Database:
    """A Database handle on the same (already migrated + seeded) database."""
    database = Database(settings.database_url)
    yield database
    database.engine.dispose()


@pytest.fixture
def migrated_db(db_url):
    """Migrated, seeded database without starting the app."""
    from app.db.seed import seed

    run_migrations(db_url)
    database = Database(db_url)
    with database.session() as s:
        seed(s)
    yield database
    database.engine.dispose()
