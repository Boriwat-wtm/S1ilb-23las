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
        "connect_args": {"connect_timeout": 10},
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
