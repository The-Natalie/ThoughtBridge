"""ThoughtBridge Modal deployment (CHECKPOINT 2): one public URL for API + chat.

Topology: a single Modal app ("thoughtbridge") serves create_app() via
@modal.asgi_app(). The prebuilt frontend dist/ bundle is attached at
/app/static (add_local_*, mounted on startup) and served by the app's
STATIC_DIR mount (same-origin, no CORS change). Volume "thoughtbridge-data" mounted at
/data holds the SQLite DB; Secret "thoughtbridge-env" provides config.
max_containers=1 is the SQLite single-writer guarantee.

All bake paths derive from Path(__file__), so this file is CWD-independent
(run from backend/ anyway). Top-level code runs LOCALLY at deploy time;
only serve()'s body runs remotely — hence lazy app imports inside serve().

Deploy: cd backend && uv run modal deploy modal_app.py (after modal setup
+ Volume/Secret creation; rebuild frontend/dist with VITE_API_URL= first).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import modal

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent
APP_DIR = BACKEND_DIR / "app"
FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"

# Keep in sync with backend/pyproject.toml [project] dependencies
# (Modal builds with pip, not uv.lock).
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "aiofiles",
        "fastapi[standard]>=0.136",
        "httpx>=0.28",
        "pydantic>=2.6",
        "pydantic-settings>=2.9",
        "sqlite-vec>=0.1",
        "fastembed",
        "python-multipart",
    )
    .env({"PYTHONPATH": "/app", "FASTEMBED_CACHE_PATH": "/opt/fastembed_cache"})
    .run_commands(
        'python -c "from fastembed import TextEmbedding; '
        "TextEmbedding(model_name='BAAI/bge-small-en-v1.5')\""
    )
    # Local files last: Modal requires add_local_* after all build steps
    # (mounted into containers on startup). Redeploy after any change.
    .add_local_dir(APP_DIR, "/app/app")
    .add_local_dir(FRONTEND_DIST, "/app/static")
)

app = modal.App("thoughtbridge", image=image)
volume = modal.Volume.from_name("thoughtbridge-data", create_if_missing=True)


@app.function(
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("thoughtbridge-env")],
    max_containers=1,
    scaledown_window=300,
)
@modal.asgi_app()
def serve():
    """Return the FastAPI app with Volume-commit middleware attached."""
    from fastapi import Request

    from app.main import create_app

    fastapi_app = create_app()

    @fastapi_app.middleware("http")
    async def commit_volume_after_writes(request: Request, call_next):
        response = await call_next(request)
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and response.status_code < 500:
            try:
                await asyncio.to_thread(volume.commit)
            # Intentional blind catch: commit must degrade to a warning, never 500.
            except Exception as exc:  # noqa: BLE001
                logger.warning("volume commit failed: %s", exc)
        return response

    return fastapi_app
