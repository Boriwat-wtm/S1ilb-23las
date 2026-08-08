from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

_url = settings.sqlalchemy_url

if _url.startswith("postgresql"):
    # Neon autosuspends its compute after a few minutes idle, so a pooled
    # connection is usually dead by the time the next request arrives.
    # pool_pre_ping discards those instead of raising at query time.
    _engine_kwargs: dict = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 3,
        "max_overflow": 2,
        "connect_args": {
            "connect_timeout": 10,
            # psycopg3 starts preparing a statement server-side once it has
            # seen it five times. Neon's pooled endpoint is PgBouncer in
            # transaction mode, where the connection you get back is not
            # necessarily the one that holds the prepared statement, and the
            # symptom is an intermittent "prepared statement does not exist"
            # under load rather than a clean failure on the first request.
            # Nothing here is query-bound — the app is capped at five
            # connections on a 0.1 vCPU instance — so the plan cache is worth
            # nothing next to knowing this cannot happen.
            "prepare_threshold": None,
        },
    }
else:
    # Only reached by the offline smoke test, which points DATABASE_URL at a
    # throwaway SQLite file. Not a supported runtime — Neon is the database.
    _engine_kwargs = {}

engine = create_engine(_url, **_engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
