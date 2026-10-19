from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")  # SQLite ignores FKs by default
            cur.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer
            cur.close()

        return engine
    return create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)


class Database:
    """Owns the engine and session factory so tests can swap in their own."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.engine = make_engine(url)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self.session_factory()

    def dependency(self) -> Iterator[Session]:
        with self.session_factory() as session:
            yield session
