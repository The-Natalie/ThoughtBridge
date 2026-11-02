"""ThoughtBridge API application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import liveness_router as health_liveness_router
from app.api.health import router as health_router


def create_app() -> FastAPI:
    """Build the FastAPI application. Routers mount under /api/v1 (later deliverables)."""
    app = FastAPI(title="ThoughtBridge")
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
    app.include_router(health_liveness_router)
    return app


app = create_app()
