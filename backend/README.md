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

All LLM reasoning goes through the Meta Model API (https://api.meta.ai/v1) via app/core/meta_client.py. Model: muse-spark-1.3 (recorded at CHECKPOINT 1, Phase 1; verified listed via GET /models (CHECKPOINT 1); first inference via POST /v1/chat/completions from POST /api/v1/query (grounded Q&A, Phase 1)). Reachability: GET /api/v1/health (full DB + Meta check, HTTP 503 with detail when a dependency is down); GET /health (lightweight DB-only deploy probe, never calls Meta).

## Deploy (CHECKPOINT 2)

Live URL: https://the-natalie--thoughtbridge-serve.us-east.modal.run

Topology: single-URL Modal app (`thoughtbridge`, see `modal_app.py`) serving the FastAPI API plus the built chat SPA from `frontend/dist` via the `STATIC_DIR` mount (same-origin, no CORS change).

Persistence decision: Modal Volume `thoughtbridge-data` mounted at `/data` (`DATABASE_PATH=/data/thoughtbridge.db`); a commit middleware persists Volume writes after mutating requests; `max_containers=1` keeps SQLite single-writer. Proven by write → redeploy → re-query returning identical chunk IDs.

Reproduce:

```bash
cd backend
uv run modal volume create thoughtbridge-data
uv run modal secret create thoughtbridge-env <KEY=VALUE ...>  # keys: MODEL_API_KEY, META_MODEL, DATABASE_PATH, EMBEDDING_MODEL, MAX_UPLOAD_MB, MAX_ARTIFACT_CHARS, STATIC_DIR; values from repo-root .env, never committed
cd ../frontend && VITE_API_URL= npm run build && cd ../backend
uv run modal deploy modal_app.py
```

Freshness rule: rebuild `dist/` (`VITE_API_URL= npm run build`) and redeploy after ANY backend or frontend change — the deploy snapshots current `app/` + `dist/`.
