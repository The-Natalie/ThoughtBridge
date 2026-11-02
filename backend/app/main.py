"""ThoughtBridge API application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import liveness_router as health_liveness_router
from app.api.health import router as health_router
from app.api.ingest import router as ingest_router
from app.api.retrieval import router as retrieval_router
from app.core.config import get_settings
from app.db.connection import check_embedding_dim, init_db
from app.retrieval.embedder import EMBEDDING_DIM


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Prepare the SQLite file: mkdir parent, idempotent init, dim guard.

    Runs on server start and on `TestClient(app)` used as a context
    manager. A dim mismatch RAISES (fail fast — never serve writes into
    an uninterpretable vec table).
    """
    settings = get_settings()
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    init_db(settings.database_path)
    check_embedding_dim(settings.database_path, settings.embedding_model, EMBEDDING_DIM)
    yield


def create_app() -> FastAPI:
    """Build the FastAPI application. Routers mount under /api/v1 (later deliverables)."""
    app = FastAPI(title="ThoughtBridge", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # PRD §10 endpoints are relative to the /api/v1 base, so the full health
    # check is primary there; bare /health is a separate lightweight liveness
    # router (DB only, deliberately different body) for deploy probes.
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(ingest_router, prefix="/api/v1")
    app.include_router(retrieval_router, prefix="/api/v1")
    app.include_router(health_liveness_router)
    return app


app = create_app()
