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
