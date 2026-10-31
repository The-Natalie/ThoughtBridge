"""ThoughtBridge API application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def create_app() -> FastAPI:
    """Build the FastAPI application. Routers mount under /api/v1 (later deliverables)."""
    app = FastAPI(title="ThoughtBridge")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app


app = create_app()
