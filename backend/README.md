# ThoughtBridge backend

FastAPI + SQLite (FTS5 + sqlite-vec) API. Python 3.12 via `uv`.

## Setup

```bash
cd backend
uv sync
```

## Run

```bash
cd backend
uv run uvicorn app.main:create_app --factory --reload
```

Config loads from the repo-root `.env` (see `../.env.example`).

## Test / lint

```bash
cd backend
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy app
```

## Meta Model

All LLM reasoning goes through the Meta Model API (https://api.meta.ai/v1) via app/core/meta_client.py. Model: muse-spark-1.3 (recorded at CHECKPOINT 1, Phase 1; verified listed via GET /models, no inference call). Reachability: GET /api/v1/health (full DB + Meta check, HTTP 503 with detail when a dependency is down); GET /health (lightweight DB-only deploy probe, never calls Meta).
