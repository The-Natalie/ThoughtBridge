"""Health endpoints — thin routers composing the core Meta probe and DB check."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.meta_client import DEFAULT_META_MODEL, check_meta_reachability
from app.db.connection import check_readable

router = APIRouter(tags=["health"])
liveness_router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    db: bool
    meta_api: bool
    model: str
    db_error: str | None = None
    meta_error: str | None = None


class LivenessResponse(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    db: bool
    db_error: str | None = None


@router.get("/health", response_model=HealthResponse)
async def get_health() -> JSONResponse:
    """Full health check: DB readability + live Meta model-listed verification.

    Returns HTTP 200 + `status "ok"` when every checked dependency is up, and
    HTTP 503 + `status "degraded"` with the full detailed JSON body when a
    required dependency is down (owner decision: deploy probes must detect a
    down dependency via status code, while keeping the honest detail fields).
    """
    settings = get_settings()
    db_result = check_readable(settings.database_path)
    model_wanted = settings.meta_model or DEFAULT_META_MODEL
    key = settings.model_api_key.get_secret_value()
    if not key:
        meta_api = False
        meta_error: str | None = "MODEL_API_KEY not configured"
    else:
        probe = await check_meta_reachability(key, model_wanted)
        meta_api = probe.ok
        meta_error = probe.error
    body = HealthResponse(
        status="ok" if (db_result.ok and meta_api) else "degraded",
        db=db_result.ok,
        db_error=db_result.error,
        meta_api=meta_api,
        meta_error=meta_error,
        model=model_wanted,
    )
    return JSONResponse(
        status_code=200 if body.status == "ok" else 503,
        content=body.model_dump(mode="json"),
    )


@liveness_router.get("/health", response_model=LivenessResponse)
async def get_liveness() -> JSONResponse:
    """Lightweight deploy probe: DB readability only, never calls Meta.

    Same 200-`"ok"` / 503-`"degraded"` rule as the full check, but local-only
    so it stays fast and never blocks on the upstream Meta timeout.
    """
    db_result = check_readable(get_settings().database_path)
    body = LivenessResponse(
        status="ok" if db_result.ok else "degraded",
        db=db_result.ok,
        db_error=db_result.error,
    )
    return JSONResponse(
        status_code=200 if body.status == "ok" else 503,
        content=body.model_dump(mode="json"),
    )
