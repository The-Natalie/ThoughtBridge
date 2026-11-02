# Feature: CHECKPOINT 1 — Meta Model API client wiring

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Wire the pre-verified Meta Model API access (`muse-spark-1.3`, HTTP 200 already confirmed manually with throwaway scripts) into the app's single Meta client module in `backend/app/core/`. Record the exact model ID in code and README. Add a full `GET /api/v1/health` check (DB + Meta, verifying `muse-spark-1.3` is listed in Meta's available models — no inference call) that returns HTTP 503 with the detailed JSON body when a required dependency is down, plus a lightweight bare `GET /health` deploy probe (DB only, never touches the network). Surfaced failures, never silent. Connectivity + health reporting only; no LLM features. This checkpoint blocks all LLM-dependent work.

## User Story

As a ThoughtBridge developer
I want the app to own one Meta API client module plus a full health check that verifies Meta reachability (503 with detail when degraded) and a lightweight deploy probe that stays fast
So that every later LLM feature builds on proven, observable connectivity instead of re-proving access ad hoc.

## Problem Statement

Meta API access was verified manually (outside the app) and the model ID lives only in the gitignored `.env`. The app itself has no Meta client module, no recorded model ID in code or README (PRD §8 requires both), and no `/health` endpoint (`GET /health` and `GET /api/v1/health` both return 404 today). Every LLM feature in Phases 1–3 depends on this wiring, so it must land first as a small, fully tested deliverable.

## Scope

- In scope: single Meta client module (`backend/app/core/meta_client.py`) with a cheap reachability probe that also verifies the configured model is listed in Meta's `/models` response (no inference call); exact model ID recorded in code + `backend/README.md` (+ one line in root `README.md`); full `GET /api/v1/health` check reporting `db` + `meta_api` honestly with surfaced error detail at HTTP 200 when healthy / 503 when a required dependency is down (detailed JSON preserved in both cases); lightweight bare `GET /health` deploy probe (DB only, never calls Meta); `httpx` promoted to a main dependency; contract tests with stubbed transport (no network in tests); live manual verification with the real key.
- Out of scope: any LLM generation/extraction/explanation/question/evaluation calls; grounding-mode prompt contracts (later deliverables own them); chat completions from the app; ingestion, retrieval, turn persistence; frontend changes; deploy (CHECKPOINT 2); new env vars.

## Solution Statement

Add a small async Meta client in `core/` that probes `GET {base}/models` with Bearer auth and a short timeout (cheap, zero inference tokens — the same probe shape as the manual verification — then verifies the configured model ID is listed in the response; owner decision: model-listed verification satisfies CHECKPOINT 1, no inference call needed). Add a read-only DB check helper in `db/connection.py` (side-effect-free, unlike `connect()` which can create files and set WAL mode). Add a thin `api/health.py` with two routers: the full check returning PRD §10's required keys (`status`, `db`, `meta_api`) plus `model` and nullable `db_error`/`meta_error` detail fields, mounted at `/api/v1/health` (primary, per base-URL convention); and a lightweight liveness check returning `{status, db, db_error}` with no Meta fields, mounted at bare `/health` for deploy probes (DB only — never calls Meta, so it stays fast and never blocks on the upstream). Each endpoint returns HTTP 200 with `status "ok"` when every dependency it checks is up, and HTTP 503 with `status "degraded"` plus the full detailed JSON body when a required dependency is down (owner decision: deploy probes must detect a down DB via status code; the 502 rule still governs future LLM-dependent endpoints). Tests stub the probe via `httpx.MockTransport` and injected clients, so the suite stays deterministic and offline.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: Low
**Primary Systems Affected**: Backend `core/` (new client), `api/` (new health router), `db/` (read-only check helper), app factory wiring, backend tests
**Dependencies**: `httpx>=0.28` (promote from dev to main deps; 0.28.1 already in lockfile/venv via `fastapi[standard]`) — no new SDK, no new test runner
**Assumptions**: (1) Root `.env` holds a live `MODEL_API_KEY` and `META_MODEL=muse-spark-1.3` — validated read-only in the prior inspection, re-check booleans only at execution. (2) `GET /v1/models` remains an OpenAI-shaped, key-authenticated endpoint on `https://api.meta.ai/v1` returning `{"data": [{"id": ...}]}` including `muse-spark-1.3` — validated by the manual HTTP 200 + external sources below; the live L4 step re-confirms. (3) FastAPI's default unique-ID generation keeps the two health routers (`router` + `liveness_router`, distinct handler names) collision-free — validated via `/openapi.json` in L3.

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `backend/app/main.py` (lines 1–21) - Why: app factory to extend with router includes; CORS + title pattern to preserve
- `backend/app/core/config.py` (lines 1–27) - Why: `Settings` surface to extend (`meta_model` default becomes the recorded ID); repo-root `.env` resolution + `lru_cache` pattern
- `backend/app/core/__init__.py` (line 1) - Why: docstring already reserves this package for the Meta API client
- `backend/app/api/__init__.py` (line 1) - Why: thin-router convention (logic lives outside routers)
- `backend/app/db/connection.py` (lines 1–69) - Why: module-logger pattern, `SCHEMA_PATH` idiom, `EmbeddingDimMismatchError` precedent; new read-only check must NOT reuse `connect()` (it creates files + sets WAL — a health-check side effect)
- `backend/app/db/schema.sql` (lines 1–12) - Why: `meta` table (`schema_version`) is the DB-readability probe target
- `backend/tests/test_app_boot.py` (lines 1–13) - Why: `TestClient(create_app())` boot-test pattern to mirror
- `backend/tests/test_config.py` (lines 1–44) - Why: cache-clear + `monkeypatch.delenv`/`setenv` + `Settings(_env_file=None)` pattern; secret-hygiene assertion pattern (`"dummy-key-123" not in repr(...)`) to mirror for error strings
- `backend/tests/test_db_init.py` (lines 1–28) - Why: `tmp_path` DB fixture + `init_db` idempotency pattern for the healthy-DB test case
- `backend/pyproject.toml` (lines 1–40) - Why: dependency style (lower bounds); `httpx` moves from `dev` to `project.dependencies`
- `backend/README.md` (lines 1–28) - Why: docs to extend with the recorded model ID (PRD §8 "recorded in code and README")
- `.env.example` (lines 1–27) - Why: config surface reference; placeholders stay placeholders (no edits)
- `frontend/src/api/client.test.ts` (lines 10–11) - Why: confirms `/api/v1/health` as the expected primary path (URL-join test only; no frontend changes in this deliverable)
- `PRD.md` (§6 lines 208–224; §8 line 276; §9 lines 294–298; §10 lines 312–318; §12 lines 414–423) - Why: authoritative requirements — client location, model-ID recording, `/health` contract, 502 rule, checkpoint + validation gate
- `.agents/plans/phase-1-build-list.md` (lines 15–19) - Why: deliverable scope boundary (connectivity + health only; blocks all LLM work)

### New Files to Create

- `backend/app/core/meta_client.py` - Single Meta API client: base-URL + model constants, `ProbeResult`, async `check_meta_reachability()` via `GET /v1/models` + model-listed verification
- `backend/app/api/health.py` - Thin health routers: `HealthResponse` model + full `GET /health` handler (DB + Meta, 200/503) and `LivenessResponse` + lightweight handler (DB only, 200/503, no Meta call)
- `backend/tests/test_meta_client.py` - Client contract tests (model ID, ok/model-missing/bad-body/401/timeout/connection-error via `MockTransport`, error truncation, key never in errors)
- `backend/tests/test_health.py` - Endpoint tests (healthy-200, meta-down-503, no-key-503, db-missing-503, liveness shape + never-calls-Meta, required keys, key never in body, no-files-created)

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [Meta Model API provider notes (promptfoo)](https://www.promptfoo.dev/docs/providers/meta/)
  - Specific section: base URL + OpenAI-compatible chat completions
  - Why: confirms `https://api.meta.ai/v1` base and OpenAI-compatible surface
- [Meta Model API (LiteLLM providers)](https://docs.litellm.ai/docs/providers/meta)
  - Specific section: supported endpoints table (`/chat/completions`, `/responses`, `/v1/messages`)
  - Why: confirms endpoint shapes share one base URL, auth, and models
- [Muse Spark for Developers (shipwithmuse)](https://shipwithmuse.live/blog/muse-spark-for-developers)
  - Specific section: Bearer auth + `muse-spark-1.3` as the current model
  - Why: corroborates Bearer `MODEL_API_KEY` auth and the exact model ID family
- [httpx MockTransport](https://www.python-httpx.org/advanced/mock/)
  - Specific section: `MockTransport(handler)` + `AsyncClient(transport=...)`
  - Why: the exact stubbing pattern for deterministic offline tests (httpx 0.28.1 already in venv — verified)
- [FastAPI `include_router` + `response_model`](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
  - Specific section: including the same router with different prefixes
  - Why: `include_router` with different prefixes for `/api/v1/health` (full router) + bare `/health` (liveness router)

### Patterns to Follow

**Naming Conventions:** `snake_case` modules/functions (`meta_client.py`, `check_meta_reachability`); `PascalCase` models (`HealthResponse`, `ProbeResult`); module-level `UPPER_SNAKE` constants (`META_API_BASE_URL`, `DEFAULT_META_MODEL`).

**Error Handling:** upstream failures surface with cause, never swallowed (PRD §10: 502 rule for future LLM endpoints; health reports `false` + `*_error` detail with `status "degraded"` at HTTP 503 when a checked dependency is down, `status "ok"` at HTTP 200 when all are up — detailed JSON preserved in both cases). Truncate remote error bodies (~200 chars). The API key must never appear in error strings, responses, `repr`, or logs — mirror `test_config.py:40-44` with equivalent assertions.

**Logging Pattern:** module logger + lazy `%s` args, mirrored from `db/connection.py:11,41-47`:
```python
logger = logging.getLogger(__name__)
logger.warning("meta probe failed: status=%s detail=%s", status_code, detail)
```
No `print(` in `backend/app` (scaffold convention).

**Test Pattern:** sync test functions; `TestClient(create_app())` (mirror `test_app_boot.py`); env isolation via autouse cache-clear + `monkeypatch` (mirror `test_config.py:8-21`), and in `test_health.py` the fixture additionally replaces `app.api.health.get_settings` with a `Settings(_env_file=None)` factory so the repo-root `.env` can never leak into a case (especially the unset-key case); `tmp_path` + `init_db` for DB fixtures (mirror `test_db_init.py:23-28`); `asyncio.run(...)` to drive the async probe in tests (stdlib only — no new test-runner dependency); `httpx.MockTransport` for stubbed HTTP.

**Other Relevant Patterns:** routers stay thin — `api/health.py` composes `core` + `db` helpers, no inline HTTP/DB logic (per `api/__init__.py`); client functions take explicit params (`api_key`, `model`, `base_url`, `timeout_s`, optional injected `httpx.AsyncClient`) and never read global settings directly, so tests stay env-free (the probe takes an explicit `model` argument and verifies it is listed in the `/models` response — owner decision, deliberately reversing the Cycle 2 model-independent shape); `core/meta_client.py` must NOT import `core/config.py` and vice versa (cycle avoidance — the router wires settings to client params; a test cross-asserts `Settings().meta_model == DEFAULT_META_MODEL` to guard drift).

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

Constants, dependency promotion, and the read-only DB helper — everything the router needs, no endpoints yet.

**Tasks:**

- Promote `httpx` to main dependencies in `pyproject.toml` (keep in dev too or remove from dev — removing is cleaner since main deps are visible to tests)
- Create `core/meta_client.py` with constants + `ProbeResult` + async probe with model-listed verification (injected-client seam)
- Change `Settings.meta_model` default to the recorded ID (single literal; drift-guarded by test)
- Add side-effect-free `check_readable()` helper to `db/connection.py`

### Phase 2: Core Implementation

The health router + response model.

**Tasks:**

- Create `api/health.py` with `HealthResponse` (`status`, `db`, `meta_api` required per PRD §10 + `model`, `db_error`, `meta_error`) and async full `GET /health` handler (HTTP 200 + `"ok"` when healthy, 503 + `"degraded"` with full JSON when a dependency is down), plus `LivenessResponse` (`status`, `db`, `db_error`) and async lightweight handler (DB only, same 200/503 rule, never calls Meta)
- Missing/empty key short-circuits the full check to `meta_api=false` with "not configured" detail (no network call) — still HTTP 503 since Meta is a required dependency there

### Phase 3: Integration

- Wire the routers into the app factory: `include_router(health.router, prefix="/api/v1")` (full check, primary) + `include_router(health.liveness_router)` (lightweight bare `/health` deploy probe) with a comment citing the PRD base-URL reading and the differing bodies
- Record the model ID in `backend/README.md` (new "Meta Model" section) + one line on root `README.md` "AI: Meta Model API" entry
- `uv sync` to relock with the promoted dependency

### Phase 4: Testing & Validation

- `test_meta_client.py`: constant exactness + drift guard, probe ok/model-missing/bad-body/401/timeout/connection-error via `MockTransport`, truncation, key-never-in-error
- `test_health.py`: healthy-200 / meta-down-503 / no-key-503 / db-missing-503 / liveness-shape + never-calls-Meta / required-keys / key-never-in-body / no-files-created via `TestClient` + `monkeypatch` + `tmp_path`, with the repo-root `.env` blocked via a `Settings(_env_file=None)` factory
- Full validation ladder L1–L4 (lint, unit, integration incl. live-server curl, manual negative cases)

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### UPDATE backend/pyproject.toml

- **IMPLEMENT**: move `httpx` from `[dependency-groups] dev` to `[project] dependencies` as `httpx>=0.28` (0.28.1 already locked — lower bound matches reality); remove it from `dev` (main deps are importable in tests)
- **PATTERN**: lower-bound style of existing entries (`backend/pyproject.toml:8-14`)
- **IMPORTS**: none (TOML edit)
- **GOTCHA**: `uv sync` (not `--frozen`) after the edit so the lockfile relocks; verify with `uv run python -c "import httpx"` from `backend/`
- **VALIDATE**: `cd backend && uv sync && uv run python -c "import tomllib; d=tomllib.load(open('pyproject.toml','rb')); deps=d['project']['dependencies']; dev=d.get('dependency-groups',{}).get('dev',[]); assert any('httpx' in r for r in deps), deps; assert not any('httpx' in r for r in dev), dev; print('httpx promoted ok')" && uv run python -c "import httpx; print(httpx.__version__)"`

### CREATE backend/app/core/meta_client.py

- **IMPLEMENT**: `META_API_BASE_URL = "https://api.meta.ai/v1"`; `DEFAULT_META_MODEL = "muse-spark-1.3"`; `META_PROBE_TIMEOUT_S = 10.0`; `MAX_ERROR_CHARS = 200`; `@dataclass ProbeResult(ok: bool, error: str | None, status_code: int | None)`; `async def check_meta_reachability(api_key: str, model: str = DEFAULT_META_MODEL, *, base_url: str = META_API_BASE_URL, timeout_s: float = META_PROBE_TIMEOUT_S, client: httpx.AsyncClient | None = None) -> ProbeResult` — `GET {base_url}/models` with `Authorization: Bearer <key>`; on HTTP 200 parse the JSON body expecting the OpenAI `{"data": [{"id": ...}]}` shape and set `ok` iff `model` is among the listed ids; model absent → `error=f"model {model} not listed by Meta API ({n} models returned)"`; unparseable JSON or unexpected shape → `error=f"unexpected /models response body: {body[:200]}"`; on non-200 `error=f"Meta API models probe: HTTP {status}: {body[:200]}"`; `httpx.TimeoutException` → `"timed out after {timeout_s}s"`; `httpx.ConnectError` → `"connection failed: {exc}"`; other `httpx.HTTPError` → `str(exc)` truncated; module `logger.warning` on failure (never logging the key); when `client` is None, create `httpx.AsyncClient(timeout=timeout_s)` internally and close it, else use the injected client without closing
- **PATTERN**: module logger `db/connection.py:11`; `snake_case` async function; no settings import (explicit params)
- **IMPORTS**: `from __future__ import annotations`, `dataclasses.dataclass`, `logging`, `httpx`
- **GOTCHA**: NEVER interpolate `api_key` into `error`, logs, or `repr` — tests assert absence with a canary key; `base_url` trailing slash — strip it when joining (`base_url.rstrip("/") + "/models"`); wrap `response.json()` in `try/except ValueError` and validate the `data` list defensively (entries may lack `id` — use `.get("id")`) so a bad body yields `ok=False`, never a raise; compare the exact model-id string (no prefix/case folding); do NOT import `app.core.config` (cycle — router wires settings)
- **VALIDATE**: `cd backend && uv run python -c "from app.core.meta_client import DEFAULT_META_MODEL, META_API_BASE_URL; print(DEFAULT_META_MODEL, META_API_BASE_URL)"`

### UPDATE backend/app/core/config.py

- **IMPLEMENT**: change `meta_model: str = ""` to `meta_model: str = "muse-spark-1.3"` with comment `# Recorded at CHECKPOINT 1 — must equal core.meta_client.DEFAULT_META_MODEL (drift-guarded by test)`
- **PATTERN**: existing field style `config.py:17-22`
- **IMPORTS**: none new (keep zero imports from `meta_client` — cycle avoidance)
- **GOTCHA**: tests must still pass with monkeypatched env and `_env_file=None`; the drift-guard test imports both modules (allowed in tests, no cycle there)
- **VALIDATE**: `cd backend && uv run python -c "from app.core.config import Settings; print(Settings(_env_file=None).meta_model)"`

### UPDATE backend/app/db/connection.py

- **IMPLEMENT**: add `@dataclass DbProbeResult(ok: bool, error: str | None)` + `def check_readable(path: str | Path) -> DbProbeResult` — open read-only via `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`, run `SELECT value FROM meta WHERE key = 'schema_version'`, close in `finally`; `ok=True` iff a row returns; `FileNotFoundError`/missing file, `sqlite3.OperationalError` (e.g. no `meta` table), and `sqlite3.DatabaseError` → `ok=False` with short cause in `error`; `logger.warning` on failure. No `init_db`, no `connect()`, no WAL pragmas — strictly side-effect-free
- **PATTERN**: module logger + `finally: conn.close()` idiom `connection.py:11,35-49`; `SCHEMA_PATH`-style `Path` handling
- **IMPORTS**: `dataclasses.dataclass` (sqlite3/Path/logger already imported)
- **GOTCHA**: `mode=ro` URI fails honestly on missing files — that is the desired `db:false` path, do not pre-create; `Path` with special chars in URI — wrap `str(path)` as-is (MVP; document limitation in a comment); never create parent dirs here
- **VALIDATE**: `cd backend && uv run python -c "from app.db.connection import check_readable; print(check_readable('/tmp/tb_health_probe_definitely_missing.db'))"`

### CREATE backend/app/api/health.py

- **IMPLEMENT**: `router = APIRouter(tags=["health"])` + `liveness_router = APIRouter(tags=["health"])`; `class HealthResponse(BaseModel)` with `status: Literal["ok", "degraded"] = "ok"`, `db: bool`, `meta_api: bool`, `model: str`, `db_error: str | None = None`, `meta_error: str | None = None`; `@router.get("/health", response_model=HealthResponse) async def get_health() -> JSONResponse` — read `get_settings()` once; `db_result = check_readable(settings.database_path)`; `model_wanted = settings.meta_model or DEFAULT_META_MODEL`; `key = settings.model_api_key.get_secret_value()`; if empty → `meta_api=False, meta_error="MODEL_API_KEY not configured"` (no network call), else `probe = await check_meta_reachability(key, model_wanted)` → `meta_api=probe.ok, meta_error=probe.error`; build `HealthResponse(db=db_result.ok, db_error=db_result.error, meta_api=..., meta_error=..., model=model_wanted, status="ok" if (db_result.ok and meta_api) else "degraded")` and return `JSONResponse(status_code=200 if status == "ok" else 503, content=body.model_dump(mode="json"))` so the detailed JSON is preserved at both statuses (document the 200/503 rule in the docstring with the owner-decision rationale); `class LivenessResponse(BaseModel)` with `status: Literal["ok", "degraded"] = "ok"`, `db: bool`, `db_error: str | None = None` (no Meta fields — it must not claim what it does not check); `@liveness_router.get("/health", response_model=LivenessResponse) async def get_liveness() -> JSONResponse` — `db_result = check_readable(get_settings().database_path)` only (no key read, no Meta call, sync-safe local check), same 200-`"ok"`/503-`"degraded"` + `JSONResponse` rule
- **PATTERN**: thin routers (`api/__init__.py:1`); Pydantic v2 models; `get_settings()` from `app.core.config`
- **IMPORTS**: `from __future__ import annotations`, `typing.Literal`, `fastapi.APIRouter`, `fastapi.responses.JSONResponse`, `pydantic.BaseModel`, `from app.core.config import get_settings`, `from app.core.meta_client import DEFAULT_META_MODEL, check_meta_reachability`, `from app.db.connection import check_readable`
- **GOTCHA**: `model_wanted` falls back to `DEFAULT_META_MODEL` when settings value is empty (env explicitly blanked) so the probe and the response always name the pinned model; do NOT include any key-derived value in the response; both handlers must be `async def` (full handler awaits the probe; liveness stays async for a uniform router signature even though its check is sync); `response_model=` is kept for OpenAPI docs even though the handlers return `JSONResponse`
- **VALIDATE**: `cd backend && uv run python -c "from app.api.health import router, liveness_router; print([(r.path, sorted(r.methods)) for r in router.routes], [(r.path, sorted(r.methods)) for r in liveness_router.routes])"`

### UPDATE backend/app/main.py

- **IMPLEMENT**: import both health routers; `app.include_router(health.router, prefix="/api/v1")` (full check — primary, since PRD §10 endpoints are relative to the `/api/v1` base) + `app.include_router(health.liveness_router)` (lightweight bare `/health` deploy probe — DB only, deliberately different body) with a three-line comment stating this reading and the body difference; keep CORS + title untouched
- **PATTERN**: factory-body wiring `main.py:9-18`
- **IMPORTS**: `from app.api.health import router as health_router, liveness_router as health_liveness_router`
- **GOTCHA**: both includes must not break `/openapi.json` (L3 validates both paths present with distinct operation IDs — guaranteed by the distinct handler names `get_health`/`get_liveness`); keep `create_app()` the single factory (tests construct via `create_app()`)
- **VALIDATE**: `cd backend && uv run python -c "from app.main import create_app; print(sorted({r.path for r in create_app().routes}))"`

### CREATE backend/tests/test_meta_client.py

- **IMPLEMENT**: `test_default_model_id_is_recorded` (`DEFAULT_META_MODEL == "muse-spark-1.3"`); `test_settings_default_matches_client_constant` (`Settings(_env_file=None).meta_model == DEFAULT_META_MODEL`, with the `test_config.py` cache-clear fixture pattern); probe tests driving `check_meta_reachability("canary-key-xyz", "muse-spark-1.3", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))` via `asyncio.run` (model passed explicitly so the verification path is exercised, not the default): 200 with `{"data": [{"id": "muse-spark-1.3"}, {"id": "other"}]}` → `ok True, error None`; 200 with `{"data": [{"id": "other-model"}]}` → `ok False`, `"muse-spark-1.3" in error`, `"not listed" in error`; 200 with bad body (parametrize over `not-json{{{` and `{"unexpected": "shape"}`) → `ok False`, `"unexpected" in error`; 401 → `ok False`, `"401" in error`, `"canary-key-xyz" not in error`; timeout handler raising `httpx.ConnectTimeout("boom")` → `ok False`, `"timed" in error.lower()`; connection-error handler raising `httpx.ConnectError("boom")` → `ok False`, `"connection failed" in error`, `"canary-key-xyz" not in error` (distinct from the timeout case — asserts the `ConnectError` branch); long-body 500 → `len(error) <= len("Meta API models probe: HTTP 500: ") + MAX_ERROR_CHARS` (assert `"canary-key-xyz" not in error` and the exact length bound); base-url trailing slash tolerated (`base_url="https://x.test/v1/"` + handler asserting `request.url.path == "/v1/models"` and returning the listed-model body → `ok True`)
- **PATTERN**: mirror `test_config.py` fixture + canary style (`:40-44`); `httpx.MockTransport` per docs link
- **IMPORTS**: `asyncio`, `httpx`, `pytest`, `from app.core.config import Settings, get_settings`, `from app.core.meta_client import DEFAULT_META_MODEL, MAX_ERROR_CHARS, check_meta_reachability`
- **GOTCHA**: every test offline — no test may construct a real `AsyncClient()` without `MockTransport`; `asyncio.run` per test (no async plugin in this repo); clear `get_settings` cache around the drift test even though it uses `_env_file=None` (defensive, mirrors existing fixture)
- **VALIDATE**: `cd backend && uv run pytest tests/test_meta_client.py -q`

### CREATE backend/tests/test_health.py

- **IMPLEMENT**: autouse fixture mirroring `test_config.py:8-21` (cache clear + delenv all six vars) that additionally runs `monkeypatch.setattr("app.api.health.get_settings", lambda: Settings(_env_file=None))` so no case can read the repo-root `.env` (this is what makes the unset-key case meaningful even with a live `.env` on disk); helper `_client(monkeypatch, **env)` setting env and returning `TestClient(create_app())` (no cache juggling — the stub builds fresh settings per call from the monkeypatched environ); `test_healthy` — `tmp_path` DB via `init_db`, `DATABASE_PATH=str(db)`, `MODEL_API_KEY=dummy`, `META_MODEL=muse-spark-1.3`, monkeypatch `app.api.health.check_meta_reachability` with `async def ok(_k, _m, **_kw): assert _m == "muse-spark-1.3"; return ProbeResult(True, None, 200)` (proves the configured model is passed to the probe) → 200 + `{"status":"ok","db":True,"meta_api":True,"model":"muse-spark-1.3","db_error":None,"meta_error":None}`; `test_meta_down_reported_honestly` — stub returns `ProbeResult(False, "Meta API models probe: HTTP 401: ...", 401)` → 503 + `status "degraded"` + `meta_api False` + `meta_error` containing "401" (detailed JSON preserved at 503); parametrize `test_missing_key_skips_network` over unset (`monkeypatch.delenv("MODEL_API_KEY", raising=False)`) and empty-string (`monkeypatch.setenv("MODEL_API_KEY", "")`) key, stub raising `AssertionError("must not be called")` → 503 + `status "degraded"` + `meta_api False` + `"not configured" in meta_error` in both cases; `test_empty_model_falls_back_to_default` — healthy setup with `META_MODEL=""` → 200 + `model == DEFAULT_META_MODEL`; `test_check_readable_missing_file` — direct `check_readable("/tmp/tb_health_direct_missing_<pid>.db")` (assert path not exists first) → `ok False`, `error` non-empty, and afterwards assert the path plus its `-wal`/`-shm` siblings still do not exist (side-effect-free proof); `test_missing_db_reported` — `DATABASE_PATH=/tmp/tb_health_missing_<pid>.db` (assert not exists) → 503 + `status "degraded"` + `db False` + `db_error` non-empty, and afterwards assert the path plus its `-wal`/`-shm` siblings still do not exist; `test_liveness_is_lightweight` — healthy DB setup, probe stubbed with a raising `AssertionError("must not be called")`, `GET /health` → 200 + exactly `{"status":"ok","db":True,"db_error":None}` with `"meta_api" not in body` (proves the deploy probe never calls Meta); `test_liveness_db_down_returns_503` — missing-DB setup → `GET /health` → 503 + `status "degraded"` + `db False`; `test_key_never_in_body` — key `canary-health-999`, meta-down stub → `"canary-health-999" not in response.text`; `test_required_keys_present` — full body satisfies `{"status","db","meta_api"} <= set(body)` and liveness body satisfies `set(body) == {"status","db","db_error"}`
- **PATTERN**: `TestClient(create_app())` (`test_app_boot.py:9`); `monkeypatch.setattr("app.api.health.check_meta_reachability", stub)`; `tmp_path`+`init_db` (`test_db_init.py:23-28`)
- **IMPORTS**: `os`, `pytest`, `fastapi.testclient.TestClient`, `from app.main import create_app`, `from app.core.config import Settings, get_settings`, `from app.core.meta_client import DEFAULT_META_MODEL, ProbeResult`, `from app.db.connection import check_readable, init_db`
- **GOTCHA**: the `get_settings` stub returns `Settings(_env_file=None)` fresh per call, so monkeypatched env IS honored (pydantic-settings always reads `os.environ`) while the repo-root `.env` is never read — app-creation order does not matter since settings resolve per request; `monkeypatch` targets are the names imported INTO `app.api.health` (`get_settings`, `check_meta_reachability`), not their home modules; every probe stub takes `(key, model, **kw)` positionally; never hit the real network — every test stubs the probe or omits the key; `tmp_path` fixture param on tests needing a DB; sibling paths are `str(path) + "-wal"` / `str(path) + "-shm"` asserted with `os.path.exists`
- **VALIDATE**: `cd backend && uv run pytest tests/test_health.py -q`

### UPDATE backend/README.md

- **IMPLEMENT**: append `## Meta Model` section: `All LLM reasoning goes through the Meta Model API (https://api.meta.ai/v1) via app/core/meta_client.py. Model: muse-spark-1.3 (recorded at CHECKPOINT 1, Phase 1; verified listed via GET /models, no inference call). Reachability: GET /api/v1/health (full DB + Meta check, HTTP 503 with detail when a dependency is down); GET /health (lightweight DB-only deploy probe, never calls Meta).` Keep existing sections untouched
- **PATTERN**: existing markdown section style (`backend/README.md:1-28`)
- **IMPORTS**: none
- **GOTCHA**: no secrets, no key material — model ID and base URL only
- **VALIDATE**: `grep -n "muse-spark-1.3" backend/README.md`

### UPDATE README.md

- **IMPLEMENT**: extend the `* AI: Meta Model API` line (line 40) to `* AI: Meta Model API (Muse Spark — model muse-spark-1.3, recorded at Phase 1 CHECKPOINT 1)`; nothing else
- **PATTERN**: existing bullet style
- **IMPORTS**: none
- **GOTCHA**: root README is user-facing — one line only, no internals
- **VALIDATE**: `grep -n "muse-spark-1.3" README.md`

---

## TESTING STRATEGY

Pytest suite in `backend/tests/` (existing runner, no new plugins). All new tests deterministic and offline: HTTP stubbed via `httpx.MockTransport` or `monkeypatch` stub of the probe; DB via `tmp_path` + `init_db`; env via `monkeypatch` + a `Settings(_env_file=None)` factory stubbing `app.api.health.get_settings` so the repo-root `.env` can never leak into a case. The one live-network confirmation is a manual L4 agent curl step, not a committed test (suite must pass without keys or network).

### Unit Tests

`test_meta_client.py`: constant exactness + config drift guard; probe maps 200-listed / 200-model-missing / 200-bad-body / 401 / timeout / connection-error to `ProbeResult` correctly; error truncation bound; trailing-slash base URL; canary key absent from every error string. `check_readable` covered via `test_health.py` missing-DB case plus a direct missing-file test, both asserting the path and its `-wal`/`-shm` siblings still do not exist afterwards (side-effect-free proof, kept in `test_health.py` with the deliverable's tests).

### Integration Tests

`test_health.py` via `TestClient`: full request path for healthy-200 / meta-down-503 / no-key-503 / db-missing-503; liveness shape + never-calls-Meta proof (raising stub) + liveness-503 on down DB; required-keys assertions for both bodies; key-never-in-body. L3 adds live-server curl of both paths (different expected bodies) + `/openapi.json` containing both health paths.

### Edge Cases

- Empty-string `MODEL_API_KEY` and unset `MODEL_API_KEY` both short-circuit without network and return HTTP 503 + `"degraded"` (committed parametrized test: `monkeypatch.delenv` vs `setenv(..., "")`)
- Empty-string `META_MODEL` falls back to `DEFAULT_META_MODEL` for both the probe call and the response `model` field (committed test)
- `DATABASE_PATH` pointing at a directory or garbage file → `db:false` with cause at HTTP 503 on both endpoints (missing-file committed with sibling-absence assertions; garbage-file asserted manually in L4 with `head -c`)
- Meta 5xx with huge body → truncated error (committed via MockTransport)
- Slow Meta (>10s) → timeout error, full endpoint returns 503 with detail; liveness endpoint unaffected (never calls Meta) (committed via raising transport; live timeout not forced in tests)
- Meta 200 that does not list the model, or a non-JSON/unexpected-shape 200 body → `meta_api:false` with cause at HTTP 503 (committed via MockTransport)
- Two routers keep `/openapi.json` valid with both paths and distinct operation IDs (L3 check)

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

```bash
cd backend && uv run ruff check . && uv run ruff format --check .
```
Expected: exit 0, `All checks passed!` + `N files already formatted` (no failures).

```bash
cd backend && uv run mypy app
```
Expected: exit 0, `Success: no issues found` (non-strict config per AGENTS.md).

### Level 2: Unit Tests

```bash
cd backend && uv run pytest tests/test_meta_client.py tests/test_health.py -q
```
Expected: exit 0, all new tests pass (no failures/errors).

```bash
cd backend && uv run pytest -q
```
Expected: exit 0, full suite passes (11 pre-existing + all new, zero regressions).

### Level 3: Integration Tests

```bash
cd backend && uv run python -c "
from fastapi.testclient import TestClient
from app.main import create_app
c = TestClient(create_app())
paths = c.get('/openapi.json').json()['paths']
assert '/api/v1/health' in paths and '/health' in paths, sorted(paths)
print('openapi health paths ok:', sorted(p for p in paths if 'health' in p))"
```
Expected: exit 0, `openapi health paths ok: ['/api/v1/health', '/health']`.

```bash
cd backend && (uv run uvicorn app.main:create_app --factory --port 8123 &>/tmp/tb_cp1_server.log & echo $! > /tmp/tb_cp1_server.pid) && sleep 4 && curl -s -w '\nHTTP:%{http_code}\n' http://localhost:8123/api/v1/health && curl -s -w '\nHTTP:%{http_code}\n' http://localhost:8123/health && kill $(cat /tmp/tb_cp1_server.pid)
```
Expected: exit 0; full-path curl prints a JSON object with `"status":"ok"|"degraded"`, `"db":true|false` (honest for local `./data/` state), `"meta_api":true` (live key in root `.env` — proves `muse-spark-1.3` is listed, no inference call), `"model":"muse-spark-1.3"`, then `HTTP:200` when db is true else `HTTP:503`; bare-path curl prints a liveness JSON object with only `status`/`db`/`db_error` keys (no `meta_api` key), then `HTTP:200` when db is true else `HTTP:503`; server stops cleanly. NOTE: uses the real root `.env` — run from the repo so `REPO_ROOT/.env` resolves; never print the key itself (response contains no key — verified by test).

### Level 4: Manual Validation

Performer `agent` for all steps (executable here; live key present in gitignored root `.env`).

1. `agent` — Healthy live probe: `cd backend && uv run python -c "from app.db.connection import init_db; init_db('/tmp/tb_cp1_healthy.db')"`; start server with `DATABASE_PATH=/tmp/tb_cp1_healthy.db uv run uvicorn app.main:create_app --factory --port 8123` (+sleep 4), `curl -s http://localhost:8123/api/v1/health | python -m json.tool`; expected: HTTP 200 (confirm `curl -s -o /dev/null -w '%{http_code}' http://localhost:8123/api/v1/health` → `200`) with `status "ok"`, `db true`, `meta_api true` (proves `muse-spark-1.3` is listed live — the CHECKPOINT 1 bar, no inference call), `meta_error null`, `model "muse-spark-1.3"`; `curl -s http://localhost:8123/health` → liveness JSON with exactly `status`/`db`/`db_error` keys and `db true`. Stop server after; `rm -f /tmp/tb_cp1_healthy.db*`.
2. `agent` — Honest Meta failure: `MODEL_API_KEY=invalid-canary-key-abc DATABASE_PATH=/tmp/tb_cp1_neg.db uv run uvicorn app.main:create_app --factory --port 8124` (+sleep), `curl -s -w '\nHTTP:%{http_code}\n' http://localhost:8124/api/v1/health`; expected: `HTTP:503` with `status "degraded"`, `meta_api false`, `meta_error` containing the upstream status (e.g. "401"/"403"), `db false` (no such file) with `db_error` cause, and response text NOT containing `invalid-canary-key-abc`. Stop server; `rm -f /tmp/tb_cp1_neg.db*` (also removes any `-wal`/`-shm` if created — `check_readable` creates none, this is hygiene).
3. `agent` — Missing-key short-circuit: `MODEL_API_KEY= DATABASE_PATH=/tmp/tb_cp1_neg2.db uv run uvicorn app.main:create_app --factory --port 8125` (+sleep 4), `curl -s -w '\nHTTP:%{http_code}\n' http://localhost:8125/api/v1/health`; expected: `HTTP:503` with `status "degraded"`, `meta_api false`, `meta_error` containing "not configured", `db false` (no such file) with `db_error` cause. Stop server; `rm -f /tmp/tb_cp1_neg2.db*` (hygiene — `check_readable` creates none). (Committed parametrized test covers unset and empty key; this step confirms the empty-key case through a live server.)
4. `agent` — Liveness degraded + full degraded shape: `MODEL_API_KEY= DATABASE_PATH=/tmp/tb_cp1_neg3.db uv run uvicorn app.main:create_app --factory --port 8126` (+sleep 4); `curl -s -w '\nHTTP:%{http_code}\n' http://localhost:8126/health` → liveness JSON (`status "degraded"`, `db false`, no `meta_api` key) + `HTTP:503`; `curl -s -w '\nHTTP:%{http_code}\n' http://localhost:8126/api/v1/health` → full JSON (`status "degraded"`, `db false` + cause, `meta_api false` + "not configured") + `HTTP:503`. Stop server; `rm -f /tmp/tb_cp1_neg3.db*` (hygiene — `check_readable` creates none).

### Level 5: Additional Validation (Optional)

None required — no browser surface, no MCP flows. Skip.

---

## MANUAL VERIFICATION CHECKLIST

- [ ] [agent] Live healthy response: init `/tmp/tb_cp1_healthy.db` and start server per L4 step 1, `curl -s http://localhost:8123/api/v1/health | python -m json.tool`; expected: HTTP 200 JSON with `status: "ok"`, `db: true`, `meta_api: true` (proves `muse-spark-1.3` listed live), `meta_error: null`, `model: "muse-spark-1.3"`; bare `/health` returns exactly `status`/`db`/`db_error` keys.
- [ ] [agent] Live honest Meta failure: server with `MODEL_API_KEY=invalid-canary-key-abc`, curl `/api/v1/health`; expected: HTTP 503, `status: "degraded"`, `meta_api: false`, `meta_error` names the upstream HTTP status, canary key absent from the entire body.
- [ ] [agent] Missing-key short-circuit through live server: server with empty `MODEL_API_KEY`, curl `/api/v1/health`; expected: HTTP 503, `status: "degraded"`, `meta_api: false`, `meta_error` contains "not configured".
- [ ] [agent] Liveness degraded path: server with missing DB, curl bare `/health`; expected: HTTP 503, `status: "degraded"`, `db: false`, no `meta_api` key in the body.
- [ ] [agent] Garbage-DB honesty: `head -c 64 /dev/urandom > /tmp/tb_cp1_garbage.db`, server with `DATABASE_PATH=/tmp/tb_cp1_garbage.db`, curl `/api/v1/health`; expected: HTTP 503, `db: false`, `db_error` non-empty cause; then `rm -f /tmp/tb_cp1_garbage.db`.
- [ ] [agent] Secret hygiene: `grep -rn` the canary values from the negative runs across `backend/app backend/tests` (they must appear only in test source as canaries, never in app code); scoped `git status --short -- backend frontend README.md` shows no `.env` entry; expected: no live or canary key material outside test canaries, `.env` untouched.
- [ ] [agent] Docs reflection: `grep -n "muse-spark-1.3" backend/README.md README.md backend/app/core/meta_client.py backend/app/core/config.py`; expected: one exact match per file (config default, client constant, both READMEs).

## ROLLBACK CONSIDERATIONS

Fully additive except six small edits (`pyproject.toml` dep move, `config.py` one-line default, `db/connection.py` read-only helper, `main.py` two includes, two README lines). Revert: delete the four new files (`backend/app/core/meta_client.py`, `backend/app/api/health.py`, `backend/tests/test_meta_client.py`, `backend/tests/test_health.py`), `git checkout -- backend/pyproject.toml backend/app/core/config.py backend/app/db/connection.py backend/app/main.py backend/README.md README.md`, then `uv sync` to relock (also reverts any `backend/uv.lock` change). No migrations, no data changes, no frontend impact. `check_readable` is read-only by construction (URI `mode=ro`), so no database state can require cleanup.

## ACCEPTANCE CRITERIA

- [ ] Single Meta client module exists at `backend/app/core/meta_client.py` with `GET /v1/models` probe + model-listed verification, timeout, truncation, key-never-in-error (L2 `test_meta_client.py`: all pass incl. model-missing/bad-body cases; L1 mypy clean)
- [ ] Exact model ID `muse-spark-1.3` recorded in code (`meta_client.py` constant + `config.py` default, drift-guarded) and README (`backend/README.md` section + root line) (L2 drift test passes; manual checklist grep item: 4 files match)
- [ ] `GET /api/v1/health` returns `{"status":"ok"|"degraded","db":bool,"meta_api":bool,"model":str,"db_error":str|null,"meta_error":str|null}` with required PRD keys present: HTTP 200 when healthy, HTTP 503 with the full detailed JSON when a required dependency is down (L2 `test_health.py` healthy/meta-down cases; L3 live curl shows the shape)
- [ ] Meta reachability checked live per full-check request with model-listed verification (no inference call); failures reported honestly as `meta_api:false` + cause at HTTP 503 + `"degraded"`, never silent; liveness endpoint never calls Meta (L2 meta-down/no-key/liveness cases; L4 live invalid-key + missing-key + liveness steps)
- [ ] Missing/empty key short-circuits the full check without network at HTTP 503 + `"degraded"` (L2 `test_missing_key_skips_network` with raising stub; L4 live empty-key step)
- [ ] DB reachability honest and side-effect-free: missing/garbage DB → `db:false` + cause at HTTP 503 on both endpoints, path plus `-wal`/`-shm` siblings proven absent afterwards (L2 missing-DB case + direct test with sibling assertions; L4 garbage-DB step; `check_readable` uses `mode=ro`)
- [ ] Bare `/health` serves the lightweight liveness body (`status`/`db`/`db_error` only, no `meta_api` key) with the same 200/503 rule and never calls Meta (L2 liveness tests with raising stub; L4 liveness steps; L3 openapi lists both paths)
- [ ] Full suite green with zero regressions (L2 full `pytest -q`: 11 pre-existing + all new pass)
- [ ] Lint + types clean (L1 ruff + mypy: exit 0)
- [ ] Root `.env` untouched, no secret material in new/edited files (manual secret-hygiene item: scoped `git status` shows no `.env` entry, canary grep confined to tests)
- [ ] No LLM generation calls, no grounding contracts, no frontend changes, no new env vars (review: scoped `git status --short -- backend frontend README.md` file list contains only the 4 new files + 6 modified files named in this plan, plus optional `backend/uv.lock` from relock; pre-existing `.agents/`/`.claude/` noise excluded by path scoping)

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + integration)
- [ ] No linting or type checking errors
- [ ] Manual testing confirms feature works
- [ ] Acceptance criteria all met
- [ ] Code reviewed for quality and maintainability

---

## NOTES

- **Design decision — `httpx`, not the OpenAI SDK:** the checkpoint needs exactly one endpoint (`GET /v1/models`) with explicit timeout/error surfacing. `httpx` 0.28.1 is already in the lockfile and venv; adding the `openai` package for a single probe call buys nothing and widens the audit surface. Later deliverables making chat-completions calls may revisit (still `httpx`-shaped REST is fine for those too).
- **Design decision — probe is `GET /models` + model-listed check, not a chat completion:** zero inference tokens, validates key + reachability + base URL + that `muse-spark-1.3` is actually available to the key, and matches the manual verification already performed. A chat probe would burn hidden reasoning tokens (per prime-summary concern #2) on every full health check. Owner decision: listed-verification (not inference) is the CHECKPOINT 1 bar.
- **Design decision — health returns HTTP 503 when degraded:** an earlier draft kept health at always-200 with flags-as-data; the owner decided deploy probes must detect a down dependency via status code, so each endpoint returns 200 + `"ok"` when everything it checks is up and 503 + `"degraded"` with the full detailed JSON body otherwise. The 502 rule governs future LLM-dependent endpoints that *fail* on upstream errors.
- **Design decision — full check at `/api/v1/health` + lightweight liveness at `/health`:** PRD §10 lists endpoints relative to the `/api/v1` base (cf. `POST /artifacts`, scaffold factory docstring, frontend `client.test.ts` expecting `/api/v1/health`), so the primary full check is `/api/v1/health`. The bare path is a separate liveness router (DB only, no Meta fields, never touches the network) serving conventional deploy probes ahead of CHECKPOINT 2 — deliberately different bodies, so no equivalence test.
- **Design decision — `check_readable` bypasses `connect()`:** `connect()` creates missing files and sets WAL mode — unacceptable side effects for a health check. The read-only URI open is deliberately separate; the docstring says so.
- **Greenfield note:** no existing router/client patterns to mirror beyond the scaffold's thin-router docstring, module loggers, and test fixtures — all cited above with file:line. Conventions come from AGENTS.md/CLAUDE.md + PRD §6.
- **Token/time budget:** this is a ~half-day deliverable; the plan is intentionally fine-grained so `/execute` succeeds in one pass.

---

## VALIDATION OUTPUT REFERENCE — EXACT OUTPUTS TO CHECK (DO NOT SKIP)

- Item to check:
  `cd backend && uv run ruff check . && uv run ruff format --check .`
  Expected output or result:
  exit 0; ruff prints `All checks passed!` and a line of the form `N files already formatted` (file count varies); no error lines.
- Item to check:
  `cd backend && uv run mypy app`
  Expected output or result:
  exit 0; final line `Success: no issues found in N source files` (file count varies).
- Item to check:
  `cd backend && uv run pytest tests/test_meta_client.py tests/test_health.py -q`
  Expected output or result:
  exit 0; final line of the form `N passed in Ns` with no `failed`/`error` (N = number of new tests, all passing).
- Item to check:
  `cd backend && uv run pytest -q`
  Expected output or result:
  exit 0; final line `M passed in Ns` where M = 11 pre-existing + all new tests; no `failed`/`error`/`skipped`.
- Item to check:
  openapi health-paths one-liner from L3 (exact command in VALIDATION COMMANDS Level 3)
  Expected output or result:
  exit 0; stdout exactly `openapi health paths ok: ['/api/v1/health', '/health']`.
- Item to check:
  L3 live-server double-curl block (exact command in VALIDATION COMMANDS Level 3)
  Expected output or result:
  exit 0; full-path output is a JSON object containing `"meta_api":true, "model":"muse-spark-1.3"` (spacing varies) followed by `HTTP:200` when local `./data/` db is readable else `HTTP:503`; bare-path output is a liveness JSON object with no `meta_api` key followed by the same conditional `HTTP:` line; server process stopped afterward (`kill` succeeds).
- Item to check:
  L4 step 1 — `curl -s http://localhost:8123/api/v1/health | python -m json.tool` against healthy server (+ status-code confirm + bare-path curl)
  Expected output or result:
  HTTP 200; pretty JSON with `"status": "ok"`, `"db": true`, `"meta_api": true`, `"meta_error": null`, `"model": "muse-spark-1.3"`; status-code confirm prints `200`; bare-path body parses to exactly the keys `status`/`db`/`db_error`.
- Item to check:
  L4 step 2 — curl against server with `MODEL_API_KEY=invalid-canary-key-abc`
  Expected output or result:
  `HTTP:503`; `"status": "degraded"`, `"meta_api": false`, `"meta_error"` contains the upstream HTTP status digits (e.g. `401`); the string `invalid-canary-key-abc` appears nowhere in the body (verify with `curl -s ... | grep -c invalid-canary-key-abc` → `0`).
- Item to check:
  L4 step 3 — curl against server with empty `MODEL_API_KEY`
  Expected output or result:
  `HTTP:503`; `"status": "degraded"`, `"meta_api": false`, `"meta_error"` contains `not configured`.
- Item to check:
  L4 step 4 — bare + full curls against missing-DB, empty-key server (port 8126)
  Expected output or result:
  bare curl prints liveness JSON (`"status": "degraded"`, `"db": false`, no `meta_api` key) + `HTTP:503`; full curl prints full JSON (`"status": "degraded"`, `"db": false`, `"meta_api": false`, both error causes non-empty) + `HTTP:503`.
- Item to check:
  Manual checklist garbage-DB step — curl with `DATABASE_PATH=/tmp/tb_cp1_garbage.db` (64 random bytes)
  Expected output or result:
  `HTTP:503`; `"db": false`, `"db_error"` a non-empty cause string; file removed afterward.
- Item to check:
  `grep -n "muse-spark-1.3" backend/README.md README.md backend/app/core/meta_client.py backend/app/core/config.py` (from repo root)
  Expected output or result:
  exit 0; exactly one matching line per file (4 lines total), each containing the exact string `muse-spark-1.3`.
- Item to check:
  `git status --short -- backend frontend README.md` after implementation (before any commit; run from repo root)
  Expected output or result:
  shows exactly the 4 new files (`?? backend/app/core/meta_client.py`, `?? backend/app/api/health.py`, `?? backend/tests/test_meta_client.py`, `?? backend/tests/test_health.py`) and the 6 modified files (`M backend/pyproject.toml`, `M backend/app/core/config.py`, `M backend/app/db/connection.py`, `M backend/app/main.py`, `M backend/README.md`, `M README.md`); no `.env` entry; no frontend entries. (`backend/uv.lock` may additionally show as modified from relock — acceptable, single exception.) Pre-existing untracked `.agents/plans/` and unstaged `.claude/` changes are excluded by the path scoping and must not fail this check.
- Item to check:
  Files created: `backend/app/core/meta_client.py`, `backend/app/api/health.py`, `backend/tests/test_meta_client.py`, `backend/tests/test_health.py`
  Expected output or result:
  all four exist on disk with the contents described in STEP-BY-STEP TASKS (existence confirmed by the passing L2 commands above, not by re-printing contents).
- Item to check:
  Files modified: `backend/pyproject.toml`, `backend/app/core/config.py`, `backend/app/db/connection.py`, `backend/app/main.py`, `backend/README.md`, `README.md` (+ optionally `backend/uv.lock` from relock)
  Expected output or result:
  diffs confined to the changes described in STEP-BY-STEP TASKS; nothing else under `backend/`, `frontend/`, or root `README.md` (judge via the scoped `git status` item above, not the whole working tree).

---

## Revision History

### Cycle 1

Review findings addressed (all 4 from `Give to Builder`, `.agents/plans/reviews/checkpoint-1-meta-client-wiring-plan-review.md`):

1. Health test completeness — addressed. `CREATE backend/tests/test_health.py` IMPLEMENT now names: parametrized `test_missing_key_skips_network` over unset (`monkeypatch.delenv`) and empty-string (`setenv(..., "")`) keys with a raising stub; `test_empty_model_falls_back_to_default` asserting `model == DEFAULT_META_MODEL` with `META_MODEL=""`; direct `test_check_readable_missing_file` asserting `ok False` on a missing path. IMPORTS extended with `os`, `DEFAULT_META_MODEL`, and `check_readable`. Covered by the existing L2 `pytest tests/test_health.py` command.
2. Meta client connection-error coverage — addressed. `CREATE backend/tests/test_meta_client.py` IMPLEMENT now names a distinct `httpx.ConnectError` probe test (`"connection failed" in error`, canary absent) alongside the existing 200/401/timeout cases.
3. File inventory consistency — addressed. Final acceptance criterion now states 4 new files + 6 modified files plus optional `backend/uv.lock`; `git status --short` validation-output item now states the 6 modified files explicitly. No remaining text claims four edited files.
4. Rollback completeness — addressed. Rollback now deletes the four named new files, reverts all six named modified files (explicitly including `backend/app/db/connection.py`), and runs `uv sync` to relock (reverting any `uv.lock` change).

Not done: nothing — all findings applied. No escalations; no requirement ambiguity encountered. Only this plan file was edited; no implementation started.

### Cycle 2

Review findings addressed (all 4 from `Give to Builder`, second review at `.agents/plans/reviews/checkpoint-1-meta-client-wiring-plan-review.md`):

1. Health handler result handling — addressed. `CREATE backend/app/api/health.py` IMPLEMENT now assigns `db_result = check_readable(settings.database_path)` and builds `HealthResponse(db=db_result.ok, db_error=db_result.error, ...)` — no tuple unpacking of the `DbProbeResult` dataclass.
2. Meta client signature consistency — addressed. Patterns to Follow explicit-params list no longer includes `model` (probe takes no model argument — `GET /models` is model-independent). Verified the specified signature, handler call shape (`check_meta_reachability(key)`), and test call shapes (no model argument) are now mutually consistent.
3. Dependency-promotion validation — addressed. `UPDATE backend/pyproject.toml` VALIDATE now runs a TOML-aware assertion proving `httpx` is listed under `[project] dependencies` and absent from the dev group (fails if the move was not made despite transitive importability), followed by the existing import check.
4. L4 missing-key live step — addressed. Level 4 step 3 rewritten as a fully executable procedure mirroring step 2: exact server start (`MODEL_API_KEY= DATABASE_PATH=/tmp/tb_cp1_neg2.db ... --port 8125`), sleep, curl, expected output (`meta_api false` + "not configured", `db false` + cause), server stop, temp-file cleanup.

Not done: nothing — all findings applied. No escalations; no requirement ambiguity encountered. Only this plan file was edited; no implementation started.

### Cycle 3

Owner decisions applied (all 3 from the `### Needs Decision` escalation, third review at `.agents/plans/reviews/checkpoint-1-meta-client-wiring-plan-review.md`, decided by the owner in session):

1. Model verification without inference — applied. `check_meta_reachability` now takes an explicit `model` argument (default `DEFAULT_META_MODEL`) and, on HTTP 200, parses the OpenAI `{"data": [{"id": ...}]}` body with `ok` iff the model is listed; model-absent and unparseable/unexpected-body cases yield distinct `ok=False` errors (defensive `.get("id")`, `try/except ValueError`, exact-string match). This deliberately reverses the Cycle 2 model-independent probe shape; the explicit-params pattern note, handler call shape (`check_meta_reachability(key, model_wanted)` with `settings.meta_model or DEFAULT_META_MODEL` fallback), and all test call shapes are mutually consistent. Committed tests: 200-listed → ok; 200-without-model → "not listed"; parametrized bad bodies → "unexpected". L4 step 1's live `meta_api:true` is documented as the CHECKPOINT 1 proof (no inference call anywhere).
2. HTTP 503 on degraded health — applied. Both endpoints return 200 + `status "ok"` when everything they check is up, and 503 + `status "degraded"` with the full detailed JSON body (via `JSONResponse(status_code=..., content=body.model_dump(mode="json"))`, `response_model=` kept for OpenAPI docs) when a required dependency is down. This supersedes the earlier always-200 draft and its design note; the 502 rule still governs future LLM-dependent endpoints. All L2/L3/L4 expectations, checklist items, criteria, and validation-output items now assert the 200/503 split with `curl -w '%{http_code}'` / `-w '\nHTTP:%{http_code}\n'` status confirms.
3. Lightweight deploy probe — applied. Bare `/health` is now a separate `liveness_router` serving `LivenessResponse` (`status`/`db`/`db_error` only — no Meta fields, since it must not claim what it does not check) from a DB-only check; it never reads the key and never calls Meta (committed test proves this with a raising probe stub), so deploy probes stay fast and never block on the 10s upstream timeout. Full Meta verification remains available at `/api/v1/health`. The old equivalence test/step is replaced by liveness-shape + liveness-503 coverage; `main.py` wiring, imports, and the L3 openapi check now cover two routers with distinct `get_health`/`get_liveness` operation IDs.

Routine corrections applied (all 3 from `### Give to Builder`):

1. Health-test `.env` isolation — applied. `test_health.py` autouse fixture now also runs `monkeypatch.setattr("app.api.health.get_settings", lambda: Settings(_env_file=None))`; the `_client` helper just sets env and builds the client (fresh settings per call from monkeypatched `os.environ`, repo-root `.env` never read). Test Pattern note, IMPORTS (`Settings` added), and GOTCHA updated to explain why the unset-key case is now meaningful.
2. DB side-effect assertions — applied. `test_check_readable_missing_file` and `test_missing_db_reported` now assert the path plus its `-wal`/`-shm` siblings still do not exist after the check; acceptance criterion and unit-test paragraph cite these assertions as the side-effect-free proof.
3. Satisfiable file-inventory check — applied. The `git status` validation item, final acceptance criterion, secret-hygiene item, and files-modified item now use the scoped form `git status --short -- backend frontend README.md` (run from repo root), explicitly excluding pre-existing `.agents/plans/` + `.claude/` noise; the L4 step-1 healthy probe was additionally made deterministic by init-ing `/tmp/tb_cp1_healthy.db` first instead of depending on local `./data/` state.

Not done: nothing — all decisions and findings applied. No new escalations; no requirement ambiguity encountered. Only this plan file was edited; no implementation started, nothing committed.

### Cycle 4

Review finding addressed (single item from `### Give to Builder`, fourth review at `.agents/plans/reviews/checkpoint-1-meta-client-wiring-plan-review.md`, owner-authorized beyond the 3-cycle cap):

1. Exact truncation bound in the Meta client tests — addressed. `CREATE backend/tests/test_meta_client.py` IMPLEMENT long-body-500 assertion changed from the vague `` `len(error) <= len(prefix) + 200`-ish `` bound to the exact `` `len(error) <= len("Meta API models probe: HTTP 500: ") + MAX_ERROR_CHARS` `` bound tied to the defined non-200 error format (`error=f"Meta API models probe: HTTP {status}: {body[:200]}"`); the canary-absence assertion is kept; `MAX_ERROR_CHARS` added to that task's IMPORTS line. No hedging words remain in the assertion.

Not done: nothing — the single finding applied. No escalations; no requirement ambiguity encountered. Only this plan file was edited; no implementation started, nothing committed.
