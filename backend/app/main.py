import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import settings
from .database import Base, engine
from .routers import auth, categories, slips, transactions

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bank")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Neon may be suspended when Render boots us. Failing to create tables must
    # not crash-loop the service — /health will report the DB as down and the
    # next request reconnects.
    try:
        Base.metadata.create_all(bind=engine)
        log.info("schema ready")
    except Exception as exc:  # noqa: BLE001
        log.warning("schema init skipped: %s", exc)
    yield


app = FastAPI(
    title="Bank — บัญชีรายจ่ายสองคน",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(categories.router)
app.include_router(transactions.router)
app.include_router(slips.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Wake-up probe for the frontend's loading screen.

    Deliberately returns 200 even when the database is down: the screen needs
    to distinguish "Render is still cold" (no response at all) from "Render is
    up, Neon is still waking" (response with database != ok). Touching the DB
    here also warms Neon in the same round trip.
    """
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db_status = "error"
        log.warning("health: db unreachable: %s", exc)

    return {
        "status": "ok",
        "database": db_status,
        "storage": "configured" if settings.storage_enabled else "disabled",
        "ocr_provider": settings.ocr_provider,
        "timezone": settings.app_timezone,
    }


@app.get("/", tags=["meta"])
def root() -> dict:
    return {"name": "bank-api", "docs": "/docs", "health": "/health"}
