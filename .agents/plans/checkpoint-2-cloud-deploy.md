# Feature: CHECKPOINT 2 — Cloud-deploy checkpoint

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Deploy ThoughtBridge to a public URL so the Phase 1 pipeline is reachable end to end: one Modal deployment serving the FastAPI backend AND the built frontend chat view at a single public URL, backed by a persistent Modal Volume holding the SQLite `.db` file. This is Phase 1 deliverable 6 (`.agents/plans/phase-1-build-list.md` lines 39-43): reachability + persistence decision only. The persistence decision is made by doing: Modal Volume first (verified by a write → redeploy → read proof); seed-on-boot on ephemeral disk only as the documented backup if the Volume path fails. No production hardening, no custom domain, no Phase 4 demo seeding.

Single-URL topology (backend + static frontend from one Modal app) is the primary approach because the build list demands a singular "deployed URL [that] serves the chat view end to end", it needs no Vercel project and no CORS changes (same-origin), and it is the fastest path per the "decided by what works fastest" rule. The Vercel-split alternative stays a documented fallback.

## User Story

As a ThoughtBridge developer
I want the backend and chat view live at one public URL with a database that survives container recycles (or a proven seed-on-boot backup)
So that Phase 1's validation gate ("deployed URL serves the chat view") passes and all Phase 2-4 work builds on proven deployability instead of a last-minute deploy gamble.

## Problem Statement

Everything runs locally today: `uvicorn` on localhost:8000 + Vite on localhost:5173, SQLite at `./data/thoughtbridge.db`, no deploy config anywhere in the repo (`modal` CLI not installed, no Modal/Vercel files, CORS allows only `http://localhost:5173`). PRD §14 risk #5 (SQLite persistence on serverless deploy) is still open: ephemeral filesystems wipe the `.db`, fastembed downloads its ~90 MB model to the OS temp dir on first use, and the `MODEL_API_KEY` lives only in the gitignored local `.env`. CHECKPOINT 2 closes this now (Phase 1, not Phase 4) by proving one public URL serves the chat view against a persistent (or provably re-seedable) database.

## Scope

- In scope: `backend/modal_app.py` Modal deployment (App + Image + Volume + Secret refs, ASGI serving, volume-commit middleware); `STATIC_DIR` setting + StaticFiles mount in the app factory so the deployed URL serves the chat view; frontend production build with `VITE_API_URL=` (empty = same-origin, zero frontend code changes); Modal Volume + Secret creation via CLI; fastembed model baked into the image; live verification (health honesty, cited vague-query answer, turn persistence, write → redeploy → read persistence proof); deploy notes + URL recorded in `backend/README.md`; persistence-decision record (Volume vs seed-on-boot).
- Out of scope: production hardening (auth, rate limiting, audit logging — PRD §9 deferred); custom domain; Phase 4 demo seeding (validation seeds through the API with throwaway synthetic notes only); Vercel project (fallback only, implemented solely if single-URL serving fails); reranker/HyDE; any Phase 2 feature (explainer, extraction, profiles, PDF/Word); any Phase 3 work (deletion cascade, `tb_conversation`).

## Solution Statement

Add a thin Modal wrapper at `backend/modal_app.py` (kept OUTSIDE `app/` so product code stays Modal-free) that builds a Python 3.12 image with the 7 pinned backend deps, bakes the `app/` package + the prebuilt `frontend/dist/` bundle into the image, pre-downloads the BGE-small model to a non-tmp cache path at build time, mounts a `thoughtbridge-data` Volume at `/data` (`DATABASE_PATH=/data/thoughtbridge.db` via the `thoughtbridge-env` Modal Secret), pins `max_containers=1` (SQLite single-writer), and serves `create_app()` via `@app.function(...)` + `@modal.asgi_app()`. An HTTP middleware added in the wrapper (not in `app/`) runs `volume.commit()` in a thread after each mutating request so writes actually persist to the Volume backend. The app factory gains an opt-in `STATIC_DIR` setting (default `None` = local dev unchanged): when set to an existing dir it mounts `StaticFiles(html=True)` at `/` AFTER all API routers, so `/` serves the chat SPA while `/api/v1/*`, `/docs`, and `/health` keep working. The frontend needs no code change: building with an empty `VITE_API_URL` makes `apiUrl()` emit relative paths (same-origin). Validation is live and behavioral: real `modal deploy`, real health checks, a synthetic note ingested through the public API, a vague query returning the cited passage, turn persistence asserted through the API, then redeploy and re-query to prove Volume persistence.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: Medium
**Primary Systems Affected**: Backend app factory + config (`STATIC_DIR` static serving), new `backend/modal_app.py` deploy module, frontend build invocation (no code change), Modal Volume/Secret/Image (external service), `backend/README.md` deploy notes
**Dependencies**: `modal>=1.0` (new dev dependency, local deploy CLI only — never imported by `app/`); `aiofiles` (new main dependency ONLY if `import aiofiles` fails in the backend venv — Starlette StaticFiles requires it); Modal account + `modal setup` auth (human step); prior Phase 1 deliverables 1-5 (all present: scaffold, health, ingest, retrieval, grounded Q&A + chat UI)
**Assumptions**: (1) Owner has or will create a Modal account (free-tier-scale usage; verify cost in dashboard — do NOT assert pricing). (2) `modal.Image.debian_slim(python_version="3.12")`, `@app.function(volumes=..., secrets=..., max_containers=..., scaledown_window=...)`, `@modal.asgi_app()`, `Volume.from_name(..., create_if_missing=...)`, `Secret.from_name(...)` shapes hold as documented below — re-verify with `uv run modal --help` / docs at execution; `modal deploy` failing fast on a bad param is itself the signal. (3) Real local `.env` holds effective `MODEL_API_KEY`/`META_MODEL=muse-spark-1.3` — executor re-checks booleans/effective config only, never prints the key. (4) fastembed honors `FASTEMBED_CACHE_PATH` (corroborated by 4+ independent sources below; Task 2 proves it locally before any deploy).

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `backend/app/main.py` (lines 22-54) - Why: `lifespan` (mkdir parent + `init_db` + dim guard — this is what creates the fresh Volume DB on first boot) and `create_app` (CORS line 42, router mounts lines 49-53 — the StaticFiles mount goes AFTER these)
- `backend/app/core/config.py` (lines 11-28) - Why: `Settings` surface to extend with `static_dir`; repo-root `.env` resolution + `lru_cache` pattern; env names map case-insensitively (`STATIC_DIR` → `static_dir`)
- `backend/app/api/health.py` (lines 34-65 full check, 68-84 liveness) - Why: deploy probes — `/api/v1/health` (DB + live Meta check, 200/503) proves secret wiring; bare `/health` (DB-only, never calls Meta) proves Volume DB readability
- `backend/app/db/connection.py` (lines 33-50 `init_db`, 79-105 `check_readable`) - Why: idempotent schema init (fresh Volume DB path) + side-effect-free probe the health checks use
- `backend/app/db/schema.sql` (lines 6-12 meta, 56-58 chunks_vec) - Why: baked `embedding_model=BAAI/bge-small-en-v1.5` + `embedding_dim=384` — the Modal Secret's `EMBEDDING_MODEL` MUST match or `check_embedding_dim` fail-fast kills the deploy
- `backend/app/retrieval/embedder.py` (lines 19-36) - Why: `EMBEDDING_MODEL_DEFAULT`, lazy singleton, NO `cache_dir` passed — so fastembed uses its default (`/tmp/fastembed_cache` on Linux) unless `FASTEMBED_CACHE_PATH` is set; this is why the image bake sets the env var
- `backend/app/api/query.py` (lines 89-191 `post_query`, 194-227 conversation reads) - Why: the E2E proof path — `POST /api/v1/query` (ingest-then-ask) + `GET /api/v1/conversations/{id}` (turn persistence with role labels)
- `backend/pyproject.toml` (lines 1-40, deps lines 7-15, dev group lines 17-22) - Why: the 7 main deps to mirror in `modal_app.py`'s `pip_install` list; `modal` joins the dev group; lower-bound style
- `backend/tests/test_config.py` - Why: cache-clear + `monkeypatch` env pattern (`get_settings.cache_clear()`) to mirror in the new static-serving tests
- `backend/tests/test_app_boot.py` (lines 1-13) - Why: `TestClient(create_app())` boot pattern; proves `/docs` serves (mount-order regression guard lives next to this)
- `frontend/src/api/client.ts` (lines 4-7 `apiUrl`) - Why: `VITE_API_URL ?? 'http://localhost:8000'` — empty-string `VITE_API_URL` yields relative URLs (`"/api/v1/query"`), which is the entire same-origin mechanism; NO frontend edit needed
- `frontend/src/api/query.ts` (lines 10-28) - Why: chat proof path from the UI side (`POST /api/v1/query`, `GET /api/v1/chunks/{id}`)
- `frontend/src/App.tsx` (lines 1-44) - Why: tab-state SPA with NO client-side router — only `/` + `/assets/*` must serve; no SPA fallback route needed
- `.env.example` - Why: config surface reference — placeholders stay placeholders; the Modal Secret takes VALUES from the real gitignored `.env`, verified via effective-Settings print (never `cat .env`)
- `.gitignore` (ThoughtBridge block: `/data/`, `*.db`, `frontend/dist/`, `.env*`) - Why: deploy artifacts that must NEVER be committed (built bundle, any DB, secret values)
- `backend/README.md` - Why: docs to extend with the deploy section (URL, commands, persistence decision)
- `PRD.md` (§4 lines 130-136 deployment; §8 lines 280-286 infrastructure; §9 lines 292-310 config+deploy considerations; §10 lines 312-331 health/ingest/query contracts; §12 lines 414-423 Phase 1 + gate; §14 line 474 risk #5) - Why: authoritative requirements — Modal leads but "decided by what works fastest", persistent volume vs seed-on-boot decided HERE, single-user deployment sufficient
- `.agents/plans/phase-1-build-list.md` (lines 39-43 deliverable, 45-50 gate) - Why: scope boundary (reachability + persistence decision only; no hardening/domain/demo seeding) and the gate items this checkpoint must satisfy

### New Files to Create

- `backend/modal_app.py` - Modal deployment: App + Image (py3.12, pip deps, app code + frontend dist baked in, fastembed pre-download), Volume + Secret refs, single-container ASGI serving, volume-commit middleware
- `backend/tests/test_static_serving.py` - Static-mount contract tests (serves index/assets when set, API/docs/health unaffected, absent-by-default, set-but-missing raises)

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [Modal: Deploy a FastAPI app](https://modal.com/docs/examples/fastapi_app)
  - Specific section: full example — `@app.function()` over `@modal.asgi_app()`, `modal.App("...", image=image)`
  - Why: the exact decorator order + App-level image pattern `modal_app.py` mirrors
- [Modal: Volumes guide](https://modal.com/docs/guide/volumes)
  - Specific section: `Volume.from_name` + `volumes={"/data": vol}` mount + `vol.commit()` after writes; `modal volume create`
  - Why: the persistence mechanism — writes need `commit()` to reach the Volume backend; single-writer mount at `/data`
- [Modal: Secrets guide](https://modal.com/docs/guide/secrets)
  - Specific section: `modal secret create NAME KEY=VALUE...` CLI + `modal.Secret.from_name(...)` + `os.environ` access
  - Why: `thoughtbridge-env` creation from verified local values; Secrets land as env vars that `Settings` reads
- [fastembed cache default (`/tmp/fastembed_cache`)](https://github.com/elara-labs/code-context-engine/issues/67)
  - Specific section: issue body — fastembed's default `cache_dir` is `tempfile.gettempdir()/fastembed_cache`
  - Why: proves the bake MUST set `FASTEMBED_CACHE_PATH` to a non-tmp path (Modal `/tmp` is not image-persistent)
- [fastembed honors `FASTEMBED_CACHE_PATH`](https://github.com/elara-labs/code-context-engine/commit/077d14ba2e79fb1312c25ed5eb0c9b00911ec353)
  - Specific section: commit message — "fastembed itself honours that var"
  - Why: corroborates the env-var mechanism Task 2 proves locally before deploy
- [Baking a fastembed model into an image](https://github.com/aira-org/aira_relay/blob/HEAD/ARCHITECTURE.md)
  - Specific section: `FASTEMBED_CACHE_PATH=/app/.fastembed_cache` set at BOTH build and runtime so "no internet download at runtime"
  - Why: the bake-into-image pattern (build-step download + same path at runtime)

### Patterns to Follow

**Thin deploy wrapper, product code stays Modal-free (new pattern, justified):**

`modal` is imported ONLY by `backend/modal_app.py`. Nothing under `backend/app/` imports modal, reads Modal env, or knows about Volumes. The commit middleware is attached in the wrapper, not the factory:

```python
# backend/modal_app.py — Modal-only file (top level runs LOCALLY at deploy time)
import modal

volume = modal.Volume.from_name("thoughtbridge-data", create_if_missing=True)

@app.function(volumes={"/data": volume}, secrets=[...], max_containers=1)
@modal.asgi_app()
def serve():  # body runs REMOTELY — app imports stay INSIDE
    from app.main import create_app
    fastapi_app = create_app()

    @fastapi_app.middleware("http")
    async def commit_volume_after_writes(request, call_next):
        response = await call_next(request)
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and response.status_code < 500:
            await asyncio.to_thread(volume.commit)
        return response

    return fastapi_app
```

Rationale: `modal_app.py` top level executes locally during `modal deploy` (builds the App definition); only `serve()`'s body runs remotely. App imports inside `serve()` + absolute `Path(__file__)`-derived bake paths keep this CWD-independent.

**Settings extension (MIRROR `backend/app/core/config.py` lines 14-23):**

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")
    # ... existing fields ...
    static_dir: str | None = None  # NEW: None = no static serving (local dev unchanged)
```

`extra="ignore"` already tolerates Modal-only env vars; a missing `.env` on Modal is silently ignored by pydantic-settings (env vars from the Secret win).

**Static mount order (ADD to `create_app` AFTER `include_router` lines 49-53):**

```python
if settings.static_dir:
    static_path = Path(settings.static_dir)
    if not static_path.is_dir():
        raise RuntimeError(f"STATIC_DIR does not exist: {settings.static_dir}")
    app.mount("/", StaticFiles(directory=static_path, html=True), name="static")
```

Mount LAST so `/api/v1/*`, `/health`, `/docs`, `/openapi.json` (registered earlier) always win. `html=True` serves `index.html` at `/`. Set-but-missing raises (fail fast — a misconfigured deploy must 500 loudly at boot, never serve silent 404s).

**Naming Conventions:** Modal resource names share the `thoughtbridge-` prefix: App `thoughtbridge`, Volume `thoughtbridge-data`, Secret `thoughtbridge-env`. New setting `static_dir` (env `STATIC_DIR`) per existing `snake_case` Settings style.

**Error Handling:** Upstream Meta failures stay 502-with-cause (unchanged). Deploy probes keep the 200-vs-503 rule (`/api/v1/health` full, `/health` DB-only). Volume commit failures inside the middleware must NOT break the response — log a warning and continue (a failed commit risks data loss on recycle, but failing the user's request is worse; persistence proof in L3 catches systemic commit failure).

**Logging Pattern:** module `logger = logging.getLogger(__name__)` (MIRROR `connection.py`/`query.py`); one `logger.info` when static serving is enabled with the resolved dir; one `logger.warning` per failed volume commit with the exception.

**Secret hygiene (load-bearing):** secret VALUES travel only as `modal secret create ... KEY="$VAR"` process args (the shape Modal's own docs show) sourced from the gitignored `.env` without echoing; they never appear in chat output, logs, files, or commits. `ANTHROPIC_API_KEY` (reviewer key) is NEVER copied to Modal. The local dev DB (`backend/data/thoughtbridge.db`) is NEVER uploaded to the Volume (may contain real notes — PRD §9: deployed artifacts are seeded sample content only); the Volume DB starts fresh via `init_db` and validation content enters through the public API.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

Prove the two external unknowns LOCALLY before touching Modal: (a) fastembed honors `FASTEMBED_CACHE_PATH` (the bake mechanism), (b) `aiofiles` presence for StaticFiles. Install the `modal` client as a backend dev dependency, verify Modal auth state (human `modal setup` if needed), and print effective non-secret config to source Secret values.

**Tasks:**

- Verify `FASTEMBED_CACHE_PATH` redirect with a scratch cache dir (real `TextEmbedding` load, then delete scratch)
- Check `import aiofiles` in the backend venv; add to main deps only if missing
- Add `modal>=1.0` to backend dev deps + `uv sync` (lockfile update)
- Auth probe (`modal secret list`); human runs `modal setup` iff unauthenticated
- Print effective non-secret Settings (model IDs, caps, key-present boolean) to source Secret values

### Phase 2: Core Implementation

Small app change (opt-in static serving) + the Modal wrapper + the same-origin frontend build. App behavior with `STATIC_DIR` unset must be byte-identical to today.

**Tasks:**

- ADD `static_dir: str | None = None` to `Settings`
- ADD fail-fast StaticFiles mount at `/` (after routers) in `create_app` + info log
- CREATE `backend/modal_app.py` (App + py3.12 Image + baked app/dist + fastembed pre-download + Volume/Secret refs + commit middleware)
- CREATE `backend/tests/test_static_serving.py` (serve/mount-order/absent-by-default/set-but-missing-raises)
- BUILD frontend with empty `VITE_API_URL` + verify no `localhost:8000` in the bundle

### Phase 3: Integration

Create the Modal Volume + Secret from verified values, deploy, and record the public URL. No app-code integration beyond Phase 2 (routers/CORS untouched — same-origin needs no CORS change).

**Tasks:**

- `modal volume create thoughtbridge-data` (idempotent; `create_if_missing=True` in code backs it)
- `modal secret create thoughtbridge-env` with the 7 verified keys (Secret values from `.env` via vars, never echoed)
- `modal deploy modal_app.py` from `backend/`; record the `https://...modal.run` URL
- UPDATE `backend/README.md` with the deploy section (URL, commands, persistence decision)

### Phase 4: Testing & Validation

Live behavioral proof against the public URL: probe honesty, cited vague-query answer over API-seeded synthetic notes, turn persistence, then redeploy and re-query to prove Volume persistence. Local suite must stay green throughout.

**Tasks:**

- L1/L2: backend `ruff` + `pytest`, frontend `vitest run` (no regressions)
- L3 (agent, live): `/health` + `/api/v1/health` probes; `/` serves chat HTML; seed 2 synthetic notes via API; vague query returns cited passage; conversation turns persisted with roles
- L3 (agent, live): redeploy (fresh container, same Volume) → re-query returns the SAME cited passage = persistence proven
- L4: human browser pass over the deployed chat view (ask, cited answer, citation click) + agent curl equivalents
- Fallback (CONDITIONAL, only if Volume persistence fails twice or costs >2h): seed-on-boot tasks F1-F3

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### Task Format Guidelines

Use information-dense keywords for clarity:

- **CREATE**: New files or components
- **UPDATE**: Modify existing files
- **ADD**: Insert new functionality into existing code
- **REMOVE**: Delete deprecated code
- **REFACTOR**: Restructure without changing behavior
- **MIRROR**: Copy pattern from elsewhere in codebase

### Task 0: READ the context references

- **IMPLEMENT**: Read every file in CONTEXT REFERENCES (codebase files fully, not just cited lines) plus the 3 Modal docs links before any edit. Confirm `main.py` mount lines, `config.py` Settings shape, `client.ts` `apiUrl` empty-string behavior, and `schema.sql` embedding meta values match this plan; if any cited fact drifted, stop and reconcile the plan first.
- **PATTERN**: plan-feature Phase 2 — no code before context
- **IMPORTS**: none
- **GOTCHA**: the repo may have moved since planning (Nov 2); line numbers are approximate — trust content, not numbers
- **VALIDATE**: `cd backend && uv run pytest -x -q 2>&1 | tail -n 3` — Expected: exit 0, all tests pass (green baseline before changes)

### Task 1: ADD `modal` dev dependency + auth probe

- **IMPLEMENT**: ADD `modal>=1.0` to `[dependency-groups] dev` in `backend/pyproject.toml` (alphabetical position per existing list), then `uv sync`. Then probe auth: `uv run modal secret list`.
- **PATTERN**: MIRROR `pyproject.toml` lower-bound dep style; Modal docs CLI (`modal secret list`)
- **IMPORTS**: none (no code imports modal except the later `modal_app.py`)
- **GOTCHA**: `modal` is deploy-tooling only — if any file under `backend/app/` or `backend/tests/` imports it, the layering is broken. If the probe prints an auth error, STOP and hand the human Task 1b before continuing.
- **VALIDATE**: `cd backend && uv run modal --version && git status --short pyproject.toml uv.lock` — Expected: exit 0, a `modal` version string, both files modified (dep + lockfile)

### Task 1b (human): `modal setup` — ONLY if Task 1 probe fails unauthenticated

- **IMPLEMENT**: Human runs `cd backend && uv run modal setup`, completes the browser flow (create a Modal account first if needed), and confirms back to the agent. Agent does NOT run this (browser + account ownership).
- **PATTERN**: Modal standard auth (`modal setup`)
- **IMPORTS**: none
- **GOTCHA**: never paste tokens into chat; the CLI stores them in `~/.modal.toml` itself
- **VALIDATE**: agent re-runs `cd backend && uv run modal secret list` — Expected: exit 0, a secret list (possibly empty), no auth error

### Task 2: VERIFY `FASTEMBED_CACHE_PATH` redirect locally

- **IMPLEMENT**: Run a real `TextEmbedding` load with a scratch cache path and confirm the model lands there (proves the image-bake mechanism before any deploy): `cd backend && FASTEMBED_CACHE_PATH=/tmp/fb-ckpt2-test uv run python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5'); print('load ok')" && ls /tmp/fb-ckpt2-test && rm -rf /tmp/fb-ckpt2-test`. First run downloads ~90 MB (slow, network) — that IS the mechanism under test.
- **PATTERN**: none (throwaway probe, not committed)
- **IMPORTS**: none
- **GOTCHA**: if the model does NOT land under the scratch dir, the `FASTEMBED_CACHE_PATH` assumption is wrong — STOP, do not design the bake around it; research `cache_dir=` wiring instead (would need an `embedder.py` change — flag as plan deviation)
- **VALIDATE**: the `ls` shows a model cache subtree (e.g. `model.onnx*` / tokenizer files) — Expected: exit 0, `load ok`, non-empty cache dir listing

### Task 3: CHECK `aiofiles`, ADD to main deps only if missing

- **IMPLEMENT**: `cd backend && uv run python -c "import aiofiles; print('present')"`. If it prints `present`, do NOTHING (no pyproject change). If `ModuleNotFoundError`, ADD `aiofiles` to `[project] dependencies` (alphabetical) + `uv sync`.
- **PATTERN**: MIRROR dep style in `pyproject.toml` lines 7-15
- **IMPORTS**: none
- **GOTCHA**: Starlette `StaticFiles` imports `aiofiles` at response time, not at mount time — a missing dep passes boot tests and fails only on first static GET, so this check must precede the static tests
- **VALIDATE**: `cd backend && uv run python -c "import aiofiles; print('present')"` — Expected: exit 0, `present` (via pre-existing `fastapi[standard]` or the new pin)

### Task 4: PRINT effective non-secret config (Secret value source)

- **IMPLEMENT**: `cd backend && uv run python -c "from app.core.config import get_settings; s = get_settings(); print('meta_model=' + s.meta_model); print('embedding_model=' + s.embedding_model); print('max_upload_mb=' + str(s.max_upload_mb)); print('max_artifact_chars=' + str(s.max_artifact_chars)); print('model_api_key_present=' + str(bool(s.model_api_key.get_secret_value())))"`. Record the four values + boolean for Task 10. Do NOT print `.env` or the key.
- **PATTERN**: MIRROR `get_settings()` usage in `api/health.py` lines 44-46
- **IMPORTS**: none
- **GOTCHA**: `.env` may hold placeholder `EMBEDDING_MODEL` — the Secret MUST use `BAAI/bge-small-en-v1.5` regardless (schema meta + `check_embedding_dim` fail-fast enforce it); likewise `META_MODEL` must be `muse-spark-1.3`. If `model_api_key_present=False`, STOP — no deploy without the live key.
- **VALIDATE**: output shows the 5 lines with expected model IDs and `model_api_key_present=True` — Expected: exit 0, `meta_model=muse-spark-1.3`, `embedding_model=BAAI/bge-small-en-v1.5`, `model_api_key_present=True`

### Task 5: UPDATE `backend/app/core/config.py` — ADD `static_dir`

- **IMPLEMENT**: ADD field `static_dir: str | None = None` to `Settings` with a one-line comment (`# Modal/single-URL static serving; None = API only (local dev)`). No other change.
- **PATTERN**: MIRROR existing field style (`config.py` lines 17-23); env `STATIC_DIR` maps automatically
- **IMPORTS**: none new
- **GOTCHA**: keep the default `None` — any other default changes local-dev behavior and breaks the "absent-by-default" contract
- **VALIDATE**: `cd backend && uv run ruff check app/core/config.py && uv run ruff format --check app/core/config.py` — Expected: exit 0, `All checks passed!` / `1 file would be left unchanged`

### Task 6: UPDATE `backend/app/main.py` — ADD opt-in StaticFiles mount

- **IMPLEMENT**: In `create_app()`, AFTER the `include_router` calls (lines 49-53) and BEFORE `return app`: read `get_settings()`; if `settings.static_dir` is set, resolve to `Path`, `raise RuntimeError` if not `is_dir()`, else `app.mount("/", StaticFiles(directory=static_path, html=True), name="static")` + `logger.info("serving static dir: %s", static_path)`. ADD module logger + imports (`logging`, `fastapi.staticfiles.StaticFiles`). `Path` already imported.
- **PATTERN**: MIRROR module-logger idiom from `db/connection.py` line 12 / `api/query.py` line 34; mount order per Solution Statement
- **IMPORTS**: `import logging`, `from fastapi.staticfiles import StaticFiles`
- **GOTCHA**: (1) mounting `/` BEFORE the routers would shadow `/api/v1/*` — mount LAST; (2) `html=True` is what serves `index.html` at `/` — without it `/` 404s; (3) no SPA catch-all — the tab-state SPA (`App.tsx`) needs only `/` + `/assets/*`
- **VALIDATE**: `cd backend && STATIC_DIR=/nonexistent uv run python -c "from app.main import create_app; create_app()" 2>&1 | tail -n 2` — Expected: exit 1, `RuntimeError: STATIC_DIR does not exist: /nonexistent` (fail-fast proves the branch runs; unset-STATIC_DIR boot is covered by Task 0's suite)

### Task 7: CREATE `backend/tests/test_static_serving.py`

- **IMPLEMENT**: CREATE tests MIRRORING `test_config.py` (cache-clear + `monkeypatch.setenv("STATIC_DIR", ...)` + `get_settings.cache_clear()` fixture) and `test_app_boot.py` (`TestClient(create_app())`): (1) with `STATIC_DIR`→tmp dir containing `index.html` + `assets/app.js`: `GET /` 200 contains the index marker; `GET /assets/app.js` 200; `GET /docs` 200 (mount-order guard); `GET /api/v1/health` responds (shape per `test_health.py` healthy-mock pattern — reuse its stub approach, do not call Meta); (2) with `STATIC_DIR` unset: `GET /` 404 (absent-by-default); (3) with `STATIC_DIR`→nonexistent path: `create_app()` raises `RuntimeError`. Use `tmp_path` (MIRROR `test_db_init.py`).
- **PATTERN**: MIRROR `test_config.py` env/cache-clear idiom + `test_app_boot.py` TestClient idiom + `test_health.py` Meta-stub approach
- **IMPORTS**: `from fastapi.testclient import TestClient`, `from app.main import create_app`, `from app.core.config import get_settings`
- **GOTCHA**: `get_settings` is `lru_cache`d — every env change needs `cache_clear()` + restore (autouse fixture), or tests pollute each other; never let the health assertion hit real Meta (mirror the existing stub, no network in tests)
- **VALIDATE**: `cd backend && uv run pytest tests/test_static_serving.py -q 2>&1 | tail -n 3` — Expected: exit 0, all new tests pass (count printed, e.g. `5 passed`)

### Task 8: CREATE `backend/modal_app.py`

- **IMPLEMENT**: CREATE the Modal wrapper per the Solution Statement sketch: `modal.App("thoughtbridge", image=image)`; `modal.Image.debian_slim(python_version="3.12")` + `.pip_install(...)` mirroring the 7 pyproject main deps with identical lower bounds (+ `aiofiles` ONLY if Task 3 added it) with a `# Keep in sync with backend/pyproject.toml [project] dependencies (Modal uses pip, not uv.lock)` NOTE; `.add_local_dir(APP_DIR, "/app/app")` + `.add_local_dir(FRONTEND_DIST, "/app/static")` with `Path(__file__)`-derived absolute paths; `.env({"PYTHONPATH": "/app", "FASTEMBED_CACHE_PATH": "/opt/fastembed_cache"})`; `.run_commands("python -c \"from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')\"")`; `volume = modal.Volume.from_name("thoughtbridge-data", create_if_missing=True)`; `@app.function(volumes={"/data": volume}, secrets=[modal.Secret.from_name("thoughtbridge-env")], max_containers=1, scaledown_window=300)` over `@modal.asgi_app()` on `serve()` with lazy `from app.main import create_app` INSIDE + commit middleware (`POST/PUT/PATCH/DELETE`, status < 500, `asyncio.to_thread(volume.commit)`, try/except → `logger.warning`, never break the response). Module docstring records: single-URL topology, CWD-independence, and the `modal deploy` command.
- **PATTERN**: MIRROR official Modal FastAPI example (App-level image, decorator order) + volumes guide (`from_name`, `/data` mount, `commit()`) — links above
- **IMPORTS**: top level `modal`, `pathlib.Path`, `logging`, `asyncio` ONLY — `asyncio` is required for the commit middleware's `asyncio.to_thread(volume.commit)` (app imports stay lazy inside `serve()` — top level runs locally at deploy time)
- **GOTCHA**: (1) `max_containers=1` is the SQLite single-writer guarantee — never raise it without a locking design; (2) `.env()` must precede `.run_commands()` so the build-step download uses `/opt/fastembed_cache`; (3) do NOT set `timeout=` (unverified against ASGI long-running semantics — defaults rule); (4) `add_local_dir` bakes CURRENT code+dist — every code change needs rebuild + redeploy
- **VALIDATE**: `cd backend && uv run ruff check modal_app.py && uv run ruff format --check modal_app.py && uv run python -c "import ast; ast.parse(open('modal_app.py').read()); print('parses ok')"` — Expected: exit 0, checks pass, `parses ok` (live deploy in Task 11 is the real validation — no pytest for this file by design)

### Task 9: BUILD frontend same-origin bundle + VERIFY

- **IMPLEMENT**: `cd frontend && VITE_API_URL= npm run build` (empty value → relative API paths via `client.ts` `apiUrl`), then verify the bundle is same-origin: `grep -r "localhost:8000" dist/ && echo STALE || echo SAME_ORIGIN_OK`, and confirm `dist/index.html` + `dist/assets/` exist. No frontend source edits.
- **PATTERN**: existing `VITE_API_URL` contract (`client.ts` lines 4-7; honored-URL tests in `client.test.ts`/`query.test.ts`)
- **IMPORTS**: none
- **GOTCHA**: (1) a stale `dist/` (built earlier with default localhost) baked into the image = chat calling localhost from the user's browser — the grep gate MUST pass before deploy; (2) rebuild + redeploy after ANY frontend change; (3) `dist/` stays gitignored — never `git add -f` it
- **VALIDATE**: `cd frontend && ls dist/index.html dist/assets && (grep -r "localhost:8000" dist/ && echo STALE || echo SAME_ORIGIN_OK)` — Expected: exit 0, `index.html` + assets listed, `SAME_ORIGIN_OK`

### Task 10: CREATE Modal Volume + Secret

- **IMPLEMENT**: From `backend/`: (1) `uv run modal volume create thoughtbridge-data` (succeeds or reports existing — either proceeds; code also passes `create_if_missing=True`). (2) Export the key WITHOUT echoing: `export MODEL_API_KEY="$(grep -E '^MODEL_API_KEY=' ../.env | cut -d= -f2-)"` (no `echo`, no print). (3) `uv run modal secret create thoughtbridge-env MODEL_API_KEY="$MODEL_API_KEY" META_MODEL="muse-spark-1.3" DATABASE_PATH="/data/thoughtbridge.db" EMBEDDING_MODEL="BAAI/bge-small-en-v1.5" MAX_UPLOAD_MB="<Task-4 value>" MAX_ARTIFACT_CHARS="<Task-4 value>" STATIC_DIR="/app/static"` — substitute the two `<Task-4 value>`s with the Task 4 printout (expected `10` / `500000`). (4) `unset MODEL_API_KEY`. Verify with `uv run modal secret list` (names only — values never display).
- **PATTERN**: Modal secrets guide CLI shape (`modal secret create NAME KEY=VALUE...`)
- **IMPORTS**: none
- **GOTCHA**: (1) `DATABASE_PATH` MUST be `/data/thoughtbridge.db`, NOT the `.env` value (`./data/...` is ephemeral on Modal); (2) NEVER copy `ANTHROPIC_API_KEY`; (3) if the secret already exists from a prior attempt, `modal secret delete thoughtbridge-env` first (or follow the CLI's overwrite guidance) — stale values fail silently at runtime; (4) `EMBEDDING_MODEL` mismatch = boot-time `EmbeddingDimMismatchError` — value locked to `BAAI/bge-small-en-v1.5`
- **VALIDATE**: `cd backend && uv run modal secret list && uv run modal volume list 2>/dev/null | grep thoughtbridge-data` — Expected: exit 0, `thoughtbridge-env` listed; volume list contains `thoughtbridge-data` (if `volume list` is unsupported in the installed CLI, `modal volume --help` + dashboard check substitutes — record which)

### Task 11: DEPLOY + record URL

- **IMPLEMENT**: `cd backend && uv run modal deploy modal_app.py` (first build takes minutes: pip installs + ~90 MB fastembed download — use a generous command timeout, do NOT background-and-forget). Record the printed `https://...modal.run` URL as `DEPLOYED_URL` for all L3/L4 steps. Check boot logs for `db init ok` (fresh Volume DB via `lifespan`) and no `EmbeddingDimMismatchError`.
- **PATTERN**: Modal standard deploy (`modal deploy`)
- **IMPORTS**: none
- **GOTCHA**: (1) deploy bakes CURRENT `app/` + `dist/` — Task 9's grep gate must have passed; (2) `STATIC_DIR=/app/static` missing from the image = boot `RuntimeError` (Task 6 fail-fast) — that error MEANS the dist bake failed, fix `FRONTEND_DIST`, don't unset the var; (3) never paste the Secret values into any log — the URL alone is safe to record
- **VALIDATE**: command prints `Created ... deployment` + the `https://...modal.run` URL — Expected: exit 0, URL captured; `curl -s -o /dev/null -w "%{http_code}" $DEPLOYED_URL/health` returns `200`

### Task 12: UPDATE `backend/README.md` — deploy section

- **IMPLEMENT**: APPEND a `## Deploy (CHECKPOINT 2)` section: the `DEPLOYED_URL`, topology (single-URL Modal: API + static chat), persistence decision (Volume `thoughtbridge-data` at `/data` + commit middleware + `max_containers=1`) OR seed-on-boot if the fallback ran, the 4 reproduce commands (`modal volume create`, `modal secret create` with KEY NAMES ONLY — no values, `VITE_API_URL= npm run build`, `modal deploy`), and the freshness rule (rebuild dist + redeploy after any change). No secret values, no key material.
- **PATTERN**: MIRROR existing README terseness (setup/run/test sections)
- **IMPORTS**: none
- **GOTCHA**: grep the diff for `sk-`, `MODEL_API_KEY=`, and the key prefix before finishing — any match = rewrite the section
- **VALIDATE**: `git diff --stat backend/README.md && grep -c -i "modal.run" backend/README.md` — Expected: exit 0, README modified, ≥1 `modal.run` URL occurrence

### Fallback tasks F1-F3 (CONDITIONAL — run ONLY if Volume persistence fails the L3 proof twice, or Volume debugging exceeds ~2h)

Trigger record (write it in the execution report): which L3 persistence step failed, the observed vs expected output, and the time spent — then proceed:

- **F1**: ADD `seed_on_boot: bool = False` to `Settings` + CREATE `backend/app/db/seed_checkpoint.py` with `seed_checkpoint_notes(db_path)` inserting EXACTLY 2 fixed synthetic notes (same texts as the L3 artifact-seed block) via the ingest pipeline with real embeddings, guarded to run only when `artifacts` is empty; call it from `lifespan` in `main.py` ONLY when `settings.seed_on_boot` is true (default False = local/dev/Volume behavior unchanged). Tests in `backend/tests/test_seed_checkpoint.py`: empty-DB seeds 2, non-empty-DB seeds 0, `seed_on_boot=False` never seeds.
  - **VALIDATE**: `cd backend && uv run pytest tests/test_seed_checkpoint.py -q 2>&1 | tail -n 2` — Expected: exit 0, all 3 seed tests pass
- **F2**: UPDATE Secret: `DATABASE_PATH` → ephemeral (e.g. `/tmp/thoughtbridge.db`) + ADD `SEED_ON_BOOT=true`; redeploy. (Volume mount may stay or go — irrelevant on this path; record the choice.)
  - **VALIDATE**: `cd backend && uv run modal deploy modal_app.py 2>&1 | tail -n 2 && curl -s -o /dev/null -w "health:%{http_code}\n" "$DEPLOYED_URL/health"` — Expected: exit 0, deploy prints `Created ... deployment`, `health:200`
- **F3**: RE-RUN the L3 probe/query/conversations blocks against the new deploy; persistence proof becomes "recycle → boot log shows seed → same vague query returns cited passage" (documented degradation: user-added content does NOT survive recycle on this path). Record the decision (`seed-on-boot`) in README + report.
  - **VALIDATE**: same L3 query-block Expected holds (`mode: evidence`, ≥1 citation to a seeded chunk) — Expected: exit 0, vague query returns the cited passage after a fresh boot-seed

---

## TESTING STRATEGY

This checkpoint is infra-heavy and code-light: one new behavior (opt-in static serving) gets full unit coverage; the Modal wrapper gets live validation, not pytest (it cannot run without a Modal account — testing it with mocks would assert nothing real).

### Unit Tests

`backend/tests/test_static_serving.py` (Task 7): static index + asset serving when `STATIC_DIR` set; `/docs` + `/api/v1/health` unaffected (mount-order guard); `GET /` 404 when unset (local-dev contract); `create_app()` raises `RuntimeError` when set-but-missing. Fixtures: `tmp_path` static dir, autouse `monkeypatch` + `get_settings.cache_clear()` env isolation (MIRROR `test_config.py`). No network (Meta stubbed per `test_health.py` pattern). Fallback F1 adds seed tests (empty→2, non-empty→0, flag-off→never).

Design unit tests with fixtures and assertions following existing testing approaches (`test_app_boot.py`, `test_config.py`, `test_db_init.py`, `test_health.py`).

### Integration Tests

No new pytest integration tests: the integration surface IS the live deploy (Modal Volume + Secret + Image + Meta API), which no repo test can reach. L3 below is the integration suite, executed as scripted `curl` against `DEPLOYED_URL`. The existing backend suite (`pytest`) + frontend suite (`vitest run`) must stay fully green as the regression gate.

### Edge Cases

- `STATIC_DIR` set-but-missing → boot `RuntimeError` (unit-tested; deploy symptom = `modal deploy` logs the traceback — fix the bake, not the var)
- Stale `dist/` (localhost bundle) baked into image → chat calls localhost from the browser (prevented by Task 9 grep gate; symptom = browser console connection-refused)
- `EMBEDDING_MODEL` Secret mismatch → boot `EmbeddingDimMismatchError` (prevented by Task 4 value lock)
- Volume commit silently failing → data lost on recycle (caught ONLY by the L3 redeploy proof — never skip it)
- Cold start (scale-to-zero → first request): lifespan `init_db` + first-query embedding load; first query may take ~30-90s (baked model, no download) — expected, not a failure
- `modal deploy` from the wrong CWD → `Path(__file__)`-derived bake paths make this a non-issue, but run from `backend/` anyway per README

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

Every command or block MUST state its exact pass signal on an `Expected:` line. `DEPLOYED_URL` = the `https://...modal.run` URL from Task 11 (substitute in every L3/L4 command).

### Level 1: Syntax & Style

```bash
cd backend && uv run ruff check . && uv run ruff format --check .
```
Expected: exit 0, `All checks passed!`, all files unchanged.

```bash
cd backend && uv run mypy app
```
Expected: exit 0, no errors (non-strict gate per AGENTS.md; `modal_app.py` excluded — deploy config, validated live).

```bash
cd frontend && npx tsc -b
```
Expected: exit 0, no output (no frontend source changes — proves it).

### Level 2: Unit Tests

```bash
cd backend && uv run pytest -q 2>&1 | tail -n 3
```
Expected: exit 0, full suite passes including `test_static_serving.py` (no skips, no failures).

```bash
cd frontend && npm test -- --run 2>&1 | tail -n 5
```
Expected: exit 0, all vitest suites pass (regression gate — untouched code stays green).

```bash
cd backend && grep -rn "^import modal\|^from modal\|import modal" app/ tests/ ; echo "modal-imports-in-app: $?"
```
Expected: exit 0 of the echo with `modal-imports-in-app: 1` (grep finds NOTHING — Modal stays out of product code).

### Level 3: Integration Tests

All live against `DEPLOYED_URL`. Allow cold-start latency on the first call (~30-90s for first embedding load is expected).

```bash
DEPLOYED_URL="<paste Task 11 URL>"
curl -s -w "\nHTTP %{http_code}\n" "$DEPLOYED_URL/health"
```
Expected: exit 0, `HTTP 200`, body `{"status":"ok","db":true,"db_error":null}` (Volume DB readable; fast — never touches Meta).

```bash
curl -s -w "\nHTTP %{http_code}\n" "$DEPLOYED_URL/api/v1/health"
```
Expected: exit 0, `HTTP 200`, body contains `"status":"ok"`, `"db":true`, `"meta_api":true`, `"model":"muse-spark-1.3"` (Secret wiring proven end to end; if `meta_api:false`, debug the Secret — never proceed to query tests).

```bash
curl -s "$DEPLOYED_URL/" -o /tmp/ckpt2-index.html -w "index:%{http_code}\n"
head -c 600 /tmp/ckpt2-index.html; echo
ASSET=$(grep -o '/assets/[^"]*' /tmp/ckpt2-index.html | head -n 1); echo "probing: $ASSET"
curl -s -o /dev/null -w "asset:%{http_code}\n" "$DEPLOYED_URL$ASSET"
```
Expected: exit 0, `index:200`, HTML containing `<div id="root">` and `ThoughtBridge` (chat view served); `probing:` prints a real bundle path (e.g. `/assets/index-XXXX.js`); `asset:200` for that file (a real StaticFiles hit — directory probing is meaningless since StaticFiles 404s bare dirs even when the mount works).

```bash
curl -s -X POST "$DEPLOYED_URL/api/v1/artifacts" -H 'Content-Type: application/json' \
  -d '{"source_type":"note","title":"ckpt2 probe A","content":"The production database lives on a Modal Volume mounted at /data, so SQLite survives container restarts."}' -w "\nHTTP %{http_code}\n"
curl -s -X POST "$DEPLOYED_URL/api/v1/artifacts" -H 'Content-Type: application/json' \
  -d '{"source_type":"note","title":"ckpt2 probe B","content":"Retrieval fuses BM25 keyword search with vector similarity using Reciprocal Rank Fusion."}' -w "\nHTTP %{http_code}\n"
```
Expected: exit 0, both `HTTP 201` with `artifact_id` + `chunks >= 1` (synthetic validation content in through the public API — the ONLY seeding this checkpoint does).

```bash
curl -s -o /tmp/ckpt2-q1.json -w "\nHTTP %{http_code}\n" -X POST "$DEPLOYED_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"question":"what keeps stored information safe when servers recycle?","mode":"auto"}'
python3 -c "import json; d=json.load(open('/tmp/ckpt2-q1.json')); print('mode:', d['mode_used'], '| citations:', len(d['citations']), '| conv:', d['conversation_id'][:8])"
```
Expected: exit 0, `HTTP 200`, `mode: evidence`, `citations >= 1`, answer mentions the Modal Volume/`/data` (vague query shares NO content word with probe A — "database/lives" never appear in the question — yet returns the right cited passage; Phase 1 gate item 1).

```bash
CID=$(python3 -c "import json; print(json.load(open('/tmp/ckpt2-q1.json'))['conversation_id'])")
curl -s "$DEPLOYED_URL/api/v1/conversations/$CID" | python3 -c "import json,sys; d=json.load(sys.stdin); print([(t['idx'], t['role'], t['id'][:8]) for t in d['turns']])"
```
Expected: exit 0, `[(0, 'user', ...), (1, 'assistant', ...)]` — ordered, role-labeled turns with stable ids (Phase 1 gate item 2).

```bash
cd backend && uv run modal deploy modal_app.py 2>&1 | tail -n 3
sleep 20
curl -s -X POST "$DEPLOYED_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"question":"what keeps stored information safe when servers recycle?","mode":"auto"}' | python3 -c "import json,sys; d=json.load(sys.stdin); print('mode:', d['mode_used'], '| citations:', [(c['chunk_id'], c['artifact_id'][:8]) for c in d['citations']])"
```
Expected: exit 0, redeploy succeeds (fresh container, same Volume); re-query returns `mode: evidence` with the SAME `chunk_id`/`artifact_id` as `/tmp/ckpt2-q1.json` (compare explicitly) — PERSISTENCE PROVEN. If citations differ or the query 500s, the Volume path has failed once: debug commit middleware, retry once, then trigger fallback F1-F3.

```bash
cd backend && uv run modal app logs thoughtbridge --tail 50 2>&1 | grep -E "db init ok|loading embedding model|Downloading|EmbeddingDimMismatch|Traceback" | head -n 10
```
Expected: exit 0, `db init ok` present (fresh Volume DB created at first boot), `loading embedding model` present WITHOUT any `Downloading`/HF-progress lines (bake worked — if download lines appear, the bake missed and cold starts pay ~90 MB; fix `FASTEMBED_CACHE_PATH`/`.env()` order), no `Traceback`.

### Level 4: Manual Validation

Performer: `agent` = executable in this environment (executor MUST run it); `human` = needs a real browser the agent lacks. `DEPLOYED_URL` substituted from Task 11.

Performer: `agent` — API-level chat round-trip (curl mirror of the browser pass):

1. `CID=$(curl -s -X POST "$DEPLOYED_URL/api/v1/query" -H 'Content-Type: application/json' -d '{"question":"how is keyword and vector search combined?","mode":"auto"}' | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['conversation_id'])")` then `curl -s "$DEPLOYED_URL/api/v1/conversations/$CID" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['turns']))"`.
2. Expected: second command prints `2` (user + assistant turns persisted through the public API exactly as the UI path persists them).

Performer: `human` — browser chat pass (requires the deployed URL + a real browser):

1. Open `DEPLOYED_URL` (from the execution report, a `https://...modal.run` URL) in a browser; the ThoughtBridge header with Chat/Capture/Learn/Work/Practice/Interview tabs renders (Chat active, "Ask about your notes…" input visible).
2. Type `what keeps stored information safe when servers recycle?` (same zero-overlap vague query as L3 — no shared content word with the stored note) and press Enter; within ~90s (cold start) an answer appears mentioning the Modal Volume/`/data`, with a `from your notes` grounding label and at least one `[chunk_id]` citation button.
3. Click the citation button; a chunk panel opens showing chunk id, artifact id, span, and the passage text ("The production database lives on a Modal Volume...").
4. Ask a follow-up (`what mounts at /data?`); the answer arrives FASTER (warm container) and stays cited.
5. Expected: all four steps behave as described; any browser-console `localhost:8000` or connection-refused error = stale `dist/` bake (Task 9 gate failed — rebuild + redeploy, do not patch around it).

### Level 5: Additional Validation (Optional)

```bash
cd backend && git status --short && echo "---" && git diff --stat
```
Expected: exit 0; modified/untracked set is EXACTLY the planned surface (`backend/modal_app.py`, `backend/tests/test_static_serving.py`, `backend/app/core/config.py`, `backend/app/main.py`, `backend/pyproject.toml`, `backend/uv.lock`, `backend/README.md`, this plan file) — no `.env`, no `*.db`, no `frontend/dist/` committed.

```bash
grep -rn "sk-\|MODEL_API_KEY=\|ANTHROPIC" backend/modal_app.py backend/README.md backend/app/ 2>/dev/null; echo "secret-leak-grep: $?"
```
Expected: `secret-leak-grep: 1` (no matches — the README names the Secret's KEY names only, never values).

---

## MANUAL VERIFICATION CHECKLIST

Label each item `agent` or `human` (same performer rule as Level 4). Each item gives numbered steps and the exact expected observable result.

- [ ] [agent] probes honest: 1. `curl -s $DEPLOYED_URL/health`; 2. `curl -s $DEPLOYED_URL/api/v1/health`; expected: (1) `{"status":"ok","db":true,...}` HTTP 200 fast (<5s); (2) `"meta_api":true`, `"model":"muse-spark-1.3"` HTTP 200
- [ ] [agent] chat view served: 1. `curl -s $DEPLOYED_URL/ | grep -o '<div id="root">'`; expected: prints `<div id="root">` (plus `ThoughtBridge` in the HTML head/body)
- [ ] [agent] vague query cited: 1. seed probes A+B via L3 POSTs; 2. POST the zero-overlap vague query ("what keeps stored information safe when servers recycle?"); expected: `mode_used=evidence`, ≥1 citation, answer mentions Modal Volume/`/data`, `conversation_id` returned
- [ ] [agent] turns persisted: 1. `GET /api/v1/conversations/{cid}` with the returned id; expected: 2 turns `[(0,user),(1,assistant)]` with stable non-empty ids and ISO timestamps
- [ ] [agent] persistence across recycle: 1. `modal deploy` again; 2. re-run the vague query; expected: SAME `chunk_id`/`artifact_id` as before the redeploy (diff `/tmp/ckpt2-q1.json` citations vs new — identical)
- [ ] [agent] edge: cold start + bake: 1. read `modal app logs thoughtbridge` after first query; expected: `db init ok` once, `loading embedding model` once, ZERO download-progress lines, zero tracebacks
- [ ] [agent] edge: local dev unchanged: 1. `cd backend && uv run pytest -q`; 2. `cd frontend && npm test -- --run`; 3. `STATIC_DIR` unset + `TestClient` `GET /` → 404; expected: both suites fully green; `/` 404 without the var
- [ ] [agent] docs/config reflection: 1. `grep -c modal.run backend/README.md`; 2. `grep -rn "sk-" backend/modal_app.py backend/README.md backend/app/`; expected: (1) ≥1; (2) no matches
- [ ] [human] browser chat pass: 1. open `DEPLOYED_URL`, tabs render with Chat active; 2. ask the database question → cited answer ≤90s with `from your notes`; 3. click citation → chunk panel with id/artifact/span/text; 4. follow-up answers faster and cited; expected: all four as described, zero `localhost` console errors

## ROLLBACK CONSIDERATIONS

- Deploy rollback: `cd backend && uv run modal app stop thoughtbridge` (tears down the deployment; Volume `thoughtbridge-data` + Secret `thoughtbridge-env` persist independently — delete via `modal volume delete` / `modal secret delete` ONLY if the human confirms; the Volume holds only synthetic probe notes).
- Code rollback: `git checkout -- backend/app/main.py backend/app/core/config.py backend/pyproject.toml && rm backend/modal_app.py backend/tests/test_static_serving.py` + `git checkout -- backend/uv.lock backend/README.md` — local dev is unaffected either way because `STATIC_DIR` defaults to `None` (no-behavior-change guarantee is unit-tested).
- Data/migrations: no schema change in this checkpoint (fresh Volume DB via existing idempotent `init_db`); nothing to migrate back. The local dev DB is never touched by any deploy step.
- Fallback-path rollback (F1-F3 only): `seed_on_boot` defaults `False` — unset `SEED_ON_BOOT` in the Secret + redeploy returns to empty-DB boots; remove `seed_checkpoint.py` + the lifespan call to fully revert.

## ACCEPTANCE CRITERIA

Each criterion names the check that proves it plus the exact expected result.

- [ ] Public URL serves the chat view end to end (L4 human browser pass steps 1-4; expected: tabs render, cited answer ≤90s, citation panel opens, follow-up faster + cited)
- [ ] `/health` reports DB honestly + `/api/v1/health` reports Meta honestly (L3 probe blocks; expected: both HTTP 200, `db:true`, `meta_api:true`, `model:muse-spark-1.3`)
- [ ] Vague zero-overlap query ("what keeps stored information safe when servers recycle?") over API-seeded notes returns the right cited passage (L3 query block; expected: `mode: evidence`, ≥1 citation to probe-A chunk, answer mentions Modal Volume/`/data`)
- [ ] Conversation turns persisted with stable ids and role labels (L3 conversations block; expected: `[(0,'user'),(1,'assistant')]` with stable ids)
- [ ] Persistence decision proven: Volume (L3 redeploy block; expected: SAME chunk/artifact ids after redeploy) OR documented seed-on-boot fallback (F3; expected: recycle → boot seed → same cited passage + decision recorded in README)
- [ ] All validation commands pass with zero errors (L1 `ruff`+`mypy`+`tsc`, L2 `pytest`+`vitest`+grep, L3 full script, L5 status/secret greps; expected: every `Expected:` line holds)
- [ ] Test coverage: new behavior fully covered (`test_static_serving.py` green in L2; no coverage threshold is stated in repo config, so no threshold is claimed; `modal_app.py` validated live by design — stated, not hidden)
- [ ] Code follows project conventions (L2 modal-import grep empty in `app/`+`tests/`; thin-wrapper + Settings + logger patterns per CONTEXT REFERENCES)
- [ ] No regressions in existing functionality (L2 full suites green; manual-checklist local-dev item: `/` 404 without `STATIC_DIR`)
- [ ] Documentation updated (Task 12: `backend/README.md` deploy section with URL + commands + persistence decision; secret-leak grep clean)
- [ ] No secrets or private data in repo or deployed artifacts (L5 greps; Volume DB contains ONLY synthetic probe notes; local dev DB never uploaded)
- [ ] Performance within checkpoint bounds (manual-checklist cold-start item: first query ≤90s with baked model, warm queries at normal Meta-API latency; no perf gate beyond "demo-usable")

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order (0-12; 1b iff auth probe fails; F1-F3 iff Volume path fails twice or >2h)
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + integration)
- [ ] No linting or type checking errors
- [ ] Manual testing confirms feature works
- [ ] Acceptance criteria all met
- [ ] Code reviewed for quality and maintainability

---

## NOTES

Design decisions, trade-offs, and deliberately-rejected alternatives:

1. **Single-URL Modal serving (primary) over Vercel-split.** Decisive factors: build-list wording ("Deployed URL serves the chat view" — singular), speed (one deploy, no Vercel project/OAuth, no CORS debugging), and zero frontend code changes (empty `VITE_API_URL` → relative URLs already works in `client.ts`). Vercel stays available for Phase 4 if judging needs it; the split would additionally require an `ALLOWED_ORIGINS` env + CORS change + two deploys. This decision IS the "finalized at deploy checkpoint" static-hosting call PRD §8 requires.
2. **Volume + commit middleware (primary) over seed-on-boot.** The middleware (mutating-methods-only, failure-logged-never-fatal) keeps `app/` Modal-free while making every write durable; `max_containers=1` is the single-writer lock SQLite needs. Seed-on-boot stays the honest backup with a crisp trigger (2 failed proofs or ~2h), not a silent downgrade.
3. **`modal` as dev dep, not `uv tool install`.** Locks the client version in `uv.lock` so any executor (or judge, or Phase 4) reproduces the exact deploy toolchain via the documented `uv sync` + `uv run modal ...` path.
4. **Inline `pip_install` list, not requirements export.** `uv.lock` is uv-specific; Modal builds with pip. Duplicating the 7 bounds with a sync NOTE is the smallest one-pass mechanism; drift risk is real but bounded (review at Phase 4).
5. **No `timeout=` on the Modal function.** Unverified interaction with ASGI long-running semantics — Modal defaults rule until docs prove otherwise. If warm queries ever hit a platform timeout, that's a measured follow-up, not a guessed parameter.
6. **Fresh Volume DB, never upload local `thoughtbridge.db`.** PRD §9 forbids real private data in deployed artifacts; the 1.7 MB local DB's contents are unverified for this purpose. Validation content enters ONLY through the public API as fixed synthetic text.
7. **`scaledown_window=300` (5 min warm).** Demo-friendly (no cold start mid-clickthrough) at trivial scale-to-zero cost. Drop it if the installed CLI rejects the param — `modal deploy` errors fast and the plan still holds.
8. **What this checkpoint PROVES for later phases:** the deploy loop (build → secret → volume → deploy → verify) is scripted and repeatable, so Phase 4's "live deployment verified end-to-end" is a re-run, not a new project.

## VALIDATION OUTPUT REFERENCE — EXACT OUTPUTS TO CHECK (DO NOT SKIP)

Each check appears EXACTLY once. Prefer the validation-command version. Nothing from MANUAL VERIFICATION CHECKLIST may be omitted. Nothing that does NOT produce visible output may be included. `DEPLOYED_URL` = Task 11 URL.

- Item to check:
  `cd backend && uv run ruff check . && uv run ruff format --check .`
  Expected output or result:
  exit 0, `All checks passed!`, `N files would be left unchanged` (ruff's exact success lines, zero errors)
- Item to check:
  `cd backend && uv run mypy app`
  Expected output or result:
  exit 0, `Success: no issues found in N source files` (non-strict gate)
- Item to check:
  `cd frontend && npx tsc -b`
  Expected output or result:
  exit 0, no output (proves zero frontend source changes)
- Item to check:
  `cd backend && uv run pytest -q 2>&1 | tail -n 3`
  Expected output or result:
  exit 0, tail shows the full-suite pass line (e.g. `NN passed in Ns` — includes `test_static_serving.py`, no failures/skips)
- Item to check:
  `cd frontend && npm test -- --run 2>&1 | tail -n 5`
  Expected output or result:
  exit 0, tail shows all vitest suites passed (regression gate)
- Item to check:
  `cd backend && grep -rn "^import modal\|^from modal\|import modal" app/ tests/ ; echo "modal-imports-in-app: $?"`
  Expected output or result:
  grep prints nothing; `modal-imports-in-app: 1`
- Item to check:
  `curl -s -w "\nHTTP %{http_code}\n" "$DEPLOYED_URL/health"`
  Expected output or result:
  exit 0, body `{"status":"ok","db":true,"db_error":null}` on the first line(s), final line `HTTP 200`, fast (<5s)
- Item to check:
  `curl -s -w "\nHTTP %{http_code}\n" "$DEPLOYED_URL/api/v1/health"`
  Expected output or result:
  exit 0, body containing `"status":"ok"`, `"db":true`, `"meta_api":true`, `"model":"muse-spark-1.3"`, final line `HTTP 200`
- Item to check:
  `curl -s "$DEPLOYED_URL/" -o /tmp/ckpt2-index.html -w "index:%{http_code}\n"` + `ASSET=$(grep -o '/assets/[^"]*' /tmp/ckpt2-index.html | head -n 1)` + `curl -s -o /dev/null -w "asset:%{http_code}\n" "$DEPLOYED_URL$ASSET"`
  Expected output or result:
  exit 0, `index:200`, HTML containing `<div id="root">` and `ThoughtBridge`; `probing:` prints a real bundle path (e.g. `/assets/index-XXXX.js`); `asset:200` for that file
- Item to check:
  the two `POST $DEPLOYED_URL/api/v1/artifacts` probe calls (ckpt2 probe A + B, exact bodies in L3)
  Expected output or result:
  exit 0, each prints a JSON body with `artifact_id` + `chunks >= 1` and final line `HTTP 201`
- Item to check:
  `curl -s -o /tmp/ckpt2-q1.json -w "\nHTTP %{http_code}\n" -X POST $DEPLOYED_URL/api/v1/query` with question "what keeps stored information safe when servers recycle?" + the `python3` citation print
  Expected output or result:
  exit 0, `HTTP 200`, prints `mode: evidence | citations: >=1 | conv: <8 hex>`; saved `/tmp/ckpt2-q1.json` answer mentions the Modal Volume/`/data` (question shares no content word with probe A)
- Item to check:
  `GET $DEPLOYED_URL/api/v1/conversations/$CID` + the `python3` turn print
  Expected output or result:
  exit 0, prints `[(0, 'user', '<8 hex>'), (1, 'assistant', '<8 hex>')]`
- Item to check:
  `cd backend && uv run modal deploy modal_app.py` (second, proof deploy) + re-query + citation print + diff vs `/tmp/ckpt2-q1.json`
  Expected output or result:
  exit 0, redeploy prints the `Created ... deployment` + same `https://...modal.run` URL; re-query prints `mode: evidence` with `chunk_id`/`artifact_id` IDENTICAL to `/tmp/ckpt2-q1.json`
- Item to check:
  `cd backend && uv run modal app logs thoughtbridge --tail 50 2>&1 | grep -E "db init ok|loading embedding model|Downloading|EmbeddingDimMismatch|Traceback" | head -n 10`
  Expected output or result:
  exit 0, output includes `db init ok` and `loading embedding model`, includes NO `Downloading`/HF-progress line and NO `Traceback`/`EmbeddingDimMismatch`
- Item to check:
  agent L4 API round-trip (`POST /api/v1/query` "how is keyword and vector search combined?" → `GET /conversations/{cid}` turn count)
  Expected output or result:
  exit 0, turn-count print outputs `2`
- Item to check:
  human L4 browser pass (4 steps in L4, performed at `DEPLOYED_URL` in a real browser)
  Expected output or result:
  tabs render with Chat active; cited answer ≤90s mentioning Modal Volume/`/data` with `from your notes` label; citation click opens chunk panel (id/artifact/span/text); follow-up faster and cited; zero `localhost` console errors
- Item to check:
  `cd backend && git status --short && echo "---" && git diff --stat`
  Expected output or result:
  exit 0; changed/untracked files are exactly the planned surface (modal_app.py, test_static_serving.py, config.py, main.py, pyproject.toml, uv.lock, README.md, this plan file); no `.env`, `*.db`, or `frontend/dist/` entries
- Item to check:
  `grep -rn "sk-\|MODEL_API_KEY=\|ANTHROPIC" backend/modal_app.py backend/README.md backend/app/ 2>/dev/null; echo "secret-leak-grep: $?"`
  Expected output or result:
  grep prints nothing; `secret-leak-grep: 1`
- Item to check:
  Files created: `backend/modal_app.py`, `backend/tests/test_static_serving.py`
  Expected output or result:
  both files exist on disk with the specified contents (runnable/lint-clean per their task validations)
- Item to check:
  Files modified: `backend/app/core/config.py`, `backend/app/main.py`, `backend/pyproject.toml`, `backend/uv.lock`, `backend/README.md`
  Expected output or result:
  `git diff --stat` lists exactly these as modified (plus the two created files as untracked); each matches its task's specified delta

---

## Revision History

### Cycle 1

Review: `.agents/plans/reviews/checkpoint-2-cloud-deploy-plan-review.md` (Overall: NEEDS_REVISION — 4 actionable findings + 1 structural gap).

1. Finding: "The L3 vague-query command pipes curl into `tee /tmp/ckpt2-q1.json -w ... -o /dev/null`, which hands curl's -w/-o flags to tee, so the file is never written and every later citation comparison breaks."
   Changed: L3 query block now runs `curl -s -o /tmp/ckpt2-q1.json -w "\nHTTP %{http_code}\n" ...` (curl writes the body itself) followed by a separate `python3` summary print; the matching VALIDATION OUTPUT REFERENCE item updated to the same command shape.
2. Finding: "The `/assets/` probe expects 200 or 403, but Starlette StaticFiles returns 404 for a directory without index.html even when the mount works."
   Changed: L3 `/` block now saves the index, greps a real `/assets/...` bundle path out of it, and curls that file expecting `asset:200`; the 200/403/never-404 rule removed everywhere (L3 + output reference). Verified no remaining `403`/`/assets/`-dir references.
3. Finding: "The plan claims the vague query proves retrieval 'WITHOUT exact keywords', but 'where does the database live' shares 'database' and 'live(s)' with probe A."
   Changed: the vague query is now "what keeps stored information safe when servers recycle?" (zero shared content words with probe A) in L3, the redeploy proof, L4 human step 2, the manual checklist, the acceptance criteria, and the output reference — all consistent; the WITHOUT-exact-keywords claim now holds as written. Verified no remaining occurrences of the old query text.
4. Finding: "The Task 8 imports line allows only modal/pathlib/logging at top level, yet the commit middleware uses `asyncio.to_thread`."
   Changed: Task 8 IMPORTS now permits `modal`, `pathlib.Path`, `logging`, `asyncio`, with the `asyncio.to_thread` justification inline; agrees with the Patterns sketch.
5. Additional (structural, flagged by the script's Structure check but not in Give to Builder): "1/15 tasks lack VALIDATE: Fallback tasks F1-F3."
   Changed: F1/F2/F3 each gained an executable VALIDATE line with an Expected signal (F1 names its test file `backend/tests/test_seed_checkpoint.py`); also fixed F1/F3's stale "L3 step 5"/"steps 1-7" references to name the L3 blocks.
6. Incidental repair (no requirement impact): the plan's chunked authoring had left L5's secret-leak block orphaned at the file end; moved it back into Level 5 so section order is L1→L5 → checklist → rollback → criteria → completion → notes → output reference. Content unchanged.

Not done: nothing — all 4 corrections plus the structural VALIDATE gap applied. No escalations; no requirements redefined.
