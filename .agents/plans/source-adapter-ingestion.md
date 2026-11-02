# Feature: Source-adapter ingestion

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Implement Phase 1 deliverable 3: the source-adapter ingestion seam plus adapters for typed/pasted text and `.txt`/`.md` file uploads. Every input becomes an immutable `SourceArtifact` (hashed, provenance metadata), is split into deterministic chunks with `(artifact_id, span, chunk_idx)`, embedded with fastembed from original text only, and indexed in both FTS5 (keyword, via the existing sync triggers) and the vec0 table (vector, rowid-aligned with `chunks.id`). Exposes `POST /artifacts`, `POST /artifacts/upload`, `GET /artifacts`, and `GET /artifacts/{id}` per PRD §10. Enforces `MAX_UPLOAD_MB` / `MAX_ARTIFACT_CHARS` from settings. Backend-only; no retrieval, no generation, no UI changes.

## User Story

As a ThoughtBridge user
I want to save notes, pastes, and text files into the system
So that everything I capture becomes searchable material for later retrieval, learning, and interview prep

## Problem Statement

The scaffold (deliverable 1) provides an empty database and no way to put content into it. Retrieval (deliverable 4), grounded Q&A (deliverable 5), and all of Phase 2–3 need artifacts → chunks → embeddings → FTS5/vec0 rows to exist. This deliverable builds the ingestion half of the one pipeline: the adapter seam every future capture method plugs into (TS-2), the deterministic chunker, the fastembed embedder, and the persist path — with provenance and caps enforced from day one.

## Scope

- In scope: `SourceAdapter` seam (`backend/app/ingest/adapters.py`); text adapter (`note|paste|summary`) and `.txt`/`.md` file adapter; deterministic chunker with exact spans; fastembed embedder wrapper (`backend/app/retrieval/embedder.py`); artifact/chunk/vec repository with single-transaction persist (`backend/app/db/artifacts.py`); ingest router (`POST /artifacts`, `POST /artifacts/upload`, `GET /artifacts`, `GET /artifacts/{id}`); startup DB init via lifespan; cap enforcement (413) and input validation (400/422); unit + API tests with stubbed embeddings.
- Out of scope: PDF/Word adapters (Preferred Phase 2 work); `tb_conversation` adapter (Phase 3); `DELETE /artifacts/{id}` (Phase 3 deletion cascade); `GET /chunks/{id}` (deliverable 4, retrieval inspection); hybrid retrieval, RRF, rerank, HyDE (deliverable 4+); any LLM calls, extraction, Q&A; any frontend changes (Capture placeholder stays).

## Solution Statement

Ingestion is a straight deterministic pipeline with one seam: `adapt (SourceAdapter) → chunk (chunker) → embed (fastembed passage_embed) → persist (single SQLite transaction)`. Adapters normalize all inputs to `(source_type, title, content, origin)`; the chunker packs paragraphs greedily to ~1000 chars with ~150 chars overlap and records exact `[span_start, span_end)` offsets; the embedder is a lazy fastembed singleton injected as a callable so tests never download the model; the repository inserts artifact + chunks + `chunks_vec` rows in one `with conn:` block (FTS follows automatically through the scaffold's triggers). Routers stay thin (validation + status codes only); endpoints are sync `def` so SQLite/fastembed work runs in FastAPI's threadpool instead of blocking the event loop. DB creation moves to a startup lifespan handler (mkdir parent + `init_db` + `check_embedding_dim`), keeping `check_readable` side-effect-free for health probes.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: Medium
**Primary Systems Affected**: backend ingest pipeline (`ingest/`, `retrieval/embedder.py`), artifact repository (`db/artifacts.py`), ingest API router, app lifespan wiring
**Dependencies**: prerequisite deliverables — scaffold (deliverable 1: schema, connection helper, config, test patterns) — already landed; no new third-party deps (fastembed, sqlite-vec, python-multipart already in `backend/pyproject.toml`); fastembed model download (`BAAI/bge-small-en-v1.5`, ~90 MB) happens once at first real embed
**Assumptions**: (validate before/during execution) fastembed registry serves `BAAI/bge-small-en-v1.5` with 384 dims matching `schema.sql` vec0 + `meta.embedding_dim`; `UploadFile.file` sync `.read()` works inside sync `def` endpoints; TestClient without context manager does not run lifespan (existing health tests unaffected); uploads reasonably recorded as `source_type "file"` (PRD §10 constrains `note|paste|summary` only for `POST /artifacts`)

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

All paths repo-root-relative:

- `backend/pyproject.toml` (lines 1-40) — Why: exact deps (fastembed, sqlite-vec, python-multipart already present — add nothing), ruff line-length 100 / py312, pytest config
- `backend/app/main.py` (lines 12-29) — Why: app-factory + `include_router(prefix="/api/v1")` pattern to mirror when mounting the ingest router and adding the lifespan handler
- `backend/app/api/health.py` (lines 15-16, 34-65) — Why: thin-router pattern (`get_settings()` inside handler, response via Pydantic model); mirror for ingest router structure
- `backend/app/core/config.py` (lines 14-28) — Why: `Settings` fields `max_upload_mb`, `max_artifact_chars`, `embedding_model`, `database_path`, cached `get_settings()` — caps and paths come from here, never hardcoded
- `backend/app/core/meta_client.py` (lines 30-44) — Why: module pattern to mirror for the embedder — explicit params, no global-settings import, injectable client/dep for tests
- `backend/app/db/connection.py` (lines 21-70) — Why: ONLY sanctioned DB path — `connect()` (WAL, FKs, vec0 ext) + `init_db()` + `check_embedding_dim()`; repository and lifespan must use these, never raw `sqlite3.connect` for writes
- `backend/app/db/schema.sql` (lines 14-58) — Why: exact `artifacts` / `chunks` / `chunks_fts` + triggers / `chunks_vec` DDL the repository writes to; `chunks.id INTEGER PK` shared with vec0 rowid by construction
- `backend/tests/test_db_init.py` (lines 19-20, 66-124) — Why: THE vec-row pattern to mirror — `struct.pack(f"{n}f", *vec)`, `INSERT INTO chunks_vec (rowid, embedding)`, `embedding MATCH ? ORDER BY distance`; plus FTS insert/update/delete trigger expectations
- `backend/tests/test_health.py` (lines 21-42) — Why: test-isolation pattern to mirror — autouse fixture clearing `get_settings` cache, scrubbing env vars, `Settings(_env_file=None)` so tests never touch the real repo-root `.env`
- `backend/tests/test_config.py` (lines 1-44) — Why: settings-override test pattern (`monkeypatch.setenv` + `Settings(_env_file=None)`)
- `backend/tests/test_app_boot.py` (lines 1-13) — Why: TestClient boot pattern; extend awareness: new router must appear in OpenAPI
- `.agents/plans/phase-1-build-list.md` (deliverable 3, lines 21-25) — Why: binding scope boundaries — text/paste/txt-md only, no retrieval or generation
- `PRD.md` (§7 F-1; §8 Backend + AI/inference; §9 upload caps + untrusted-input discipline; §10 Ingest endpoints; §12 Phase 1) — Why: authoritative requirements, API contracts, and acceptance criteria
- `AGENTS.md` (Commands section) — Why: exact backend commands (`uv run pytest`, `uv run ruff check . && uv run ruff format --check .`, `uv run mypy app`, all from `backend/`)

### New Files to Create

Backend (`backend/`, paths repo-root-relative):

- `backend/app/ingest/chunker.py` — deterministic paragraph-aware chunker: `(content) -> list[Chunk(text, span_start, span_end, chunk_idx)]`; module constants for target/overlap sizes
- `backend/app/ingest/adapters.py` — `SourceAdapter` Protocol, `AdaptedSource` dataclass, `TextAdapter` (`note|paste|summary`), `TextFileAdapter` (`.txt`/`.md`), extension/source-type registry + `adapt_*` entry points
- `backend/app/retrieval/embedder.py` — lazy fastembed `TextEmbedding` singleton, `embed_passages(texts) -> list[list[float]]`, dim constant, injectable embed callable for tests
- `backend/app/db/artifacts.py` — repository: `store_artifact()` single-transaction persist (artifact + chunks + vec rows), `list_artifacts()` with counts, `get_artifact_detail()` with chunks + linked ids
- `backend/app/ingest/pipeline.py` — orchestration: `ingest_source(adapted, db_path, *, embed_fn) -> IngestResult(artifact_id, chunk_count)`; enforces char cap, hashing, timestamps, dim guard
- `backend/app/api/ingest.py` — thin router: `POST /artifacts` (201), `POST /artifacts/upload` (201), `GET /artifacts`, `GET /artifacts/{id}` (404)
- `backend/tests/test_chunker.py` — chunker unit tests (spans, overlap, boundaries, empty/long inputs)
- `backend/tests/test_adapters.py` — adapter unit tests (validation, extension mapping, UTF-8 errors, origin metadata)
- `backend/tests/test_ingest_pipeline.py` — pipeline + repository tests with stub embed_fn (transactionality, FTS/vec rows, caps, dim guard)
- `backend/tests/test_ingest_api.py` — API contract tests with stubbed embedder (status codes, shapes, 400/404/413/422 cases, multipart upload)

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [FastAPI — Request Files](https://fastapi.tiangolo.com/tutorial/request-files/)
  - Specific section: `UploadFile` vs `bytes` parameter declaration; multipart requires `python-multipart`
  - Why: `POST /artifacts/upload` shape; `UploadFile.filename` / `.file` sync-read pattern for the sync endpoint
- [SQLite FTS5 — External Content Tables](https://www.sqlite.org/fts5.html#external_content_fts5_tables)
  - Specific section: external-content FTS5 tables + the three sync triggers (already in `schema.sql`)
  - Why: confirms FTS needs no direct writes from the repository — plain `chunks` INSERTs suffice; don't fight the triggers
- [sqlite-vec — vec0 / Python usage](https://github.com/asg017/sqlite-vec)
  - Specific section: README sample usage — `CREATE VIRTUAL TABLE ... USING vec0(embedding float[N])`, `INSERT INTO ... (rowid, embedding)`, `... WHERE embedding MATCH ? ORDER BY distance`
  - Why: vec-row SQL the repository must emit; rowid alignment with `chunks.id` (in-repo proof in `tests/test_db_init.py:66-90` takes precedence over the README if they differ)
- [FastEmbed — Text Embedding](https://qdrant.github.io/fastembed/)
  - Specific section: `TextEmbedding(model_name=...)` init; `passage_embed(texts)` for documents vs `query_embed` for queries (generator of numpy arrays — materialize with `list()`)
  - Why: embedder wrapper API; documents MUST use `passage_embed` (BGE prefix behavior), never `query_embed`
- [FastEmbed source / model registry](https://github.com/qdrant/fastembed)
  - Specific section: supported models list — `BAAI/bge-small-en-v1.5` (384 dims)
  - Why: validates the configured `EMBEDDING_MODEL` default and the 384-dim vec0 table agree; first use downloads ~90 MB

### Patterns to Follow

**Naming Conventions:**

Backend `snake_case` modules/functions, `PascalCase` models/classes (AGENTS.md). Router module `backend/app/api/ingest.py` with module-level `router = APIRouter(tags=["ingest"])` mirroring `backend/app/api/health.py:15`. Repository functions verb-led (`store_artifact`, `list_artifacts`, `get_artifact_detail`) mirroring `connect`/`init_db`/`check_readable` in `backend/app/db/connection.py`.

**Error Handling:**

FastAPI-default `{"detail": ...}` shape (PRD §10). Client errors via `HTTPException`: 400 bad extension / undecodable bytes / empty file; 413 over `MAX_UPLOAD_MB` (raw bytes) or `MAX_ARTIFACT_CHARS` (decoded content); 404 unknown artifact id. Pydantic `Literal` + `min_length=1` produce 422 for bad `source_type` / empty JSON content — accept the default 422 shape (it is the FastAPI default). Never swallow upstream/config errors: dim mismatch → 500 with cause (fail fast, per `EmbeddingDimMismatchError` semantics). Mirror `health.py` honesty: report the cause, never fake success.

**Settings access:**

Routers call `get_settings()` inside the handler (mirror `health.py:43`); library modules (`chunker`, `adapters`, `embedder`, `artifacts`, `pipeline`) take explicit params and NEVER import `app.core.config` (mirror `meta_client.py` cycle-avoidance rule). Tests scrub env + use `Settings(_env_file=None)` (mirror `test_health.py:21-35`) so the real `.env` is never loaded.

**DB access:**

`connect()` from `app.db.connection` is the only write path; one `with conn:` transaction per ingest; `row_factory = sqlite3.Row` already set. Mirror the vec insert exactly (`test_db_init.py:80-83`): `struct.pack(f"{len(vec)}f", *vec)` then `INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)` with `chunk_id = cursor.lastrowid` from the `chunks` INSERT. Never write to `chunks_fts` directly — triggers own it (`schema.sql:43-52`).

**Logging Pattern:**

Module `logger = logging.getLogger(__name__)`; `logger.info` one-line ingest summary (`artifact_id`, `source_type`, chunk count, char count); `logger.warning` on rejected inputs (oversize, bad extension, decode failure) with no content bytes in the log line. Mirror `connection.py:42-48` / `meta_client.py:54-58` (no secrets/content in logs).

**Sync-endpoint rule:**

Ingest endpoints are sync `def` (not `async def`) because sqlite3 + fastembed are blocking/CPU-bound — FastAPI runs them in the threadpool. Read uploads via the sync `file.file.read(n)` handle, never `await file.read()` (no `await` in a `def` endpoint). Size-guard with a single `read(limit + 1)` and compare length — never load unbounded bytes.

**Test-injection rule:**

The pipeline takes `embed_fn: Callable[[list[str]], list[list[float]]]` (default: real `embed_passages`); API tests monkeypatch the router's embed symbol with a deterministic stub (e.g. `[0.1] * 384`-style vectors, distinct per chunk) so the suite never downloads the model. One optional real-model smoke test gated behind `TB_REAL_EMBEDDINGS=1` (skip otherwise) proves the fastembed path end to end.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

Deterministic core with no I/O beyond stdlib: the chunker (pure function over text → spans) and the adapter seam (validation + normalization to `AdaptedSource`). Both fully unit-testable without a database or model. Constants live in their modules: `CHUNK_TARGET_CHARS = 1000`, `CHUNK_OVERLAP_CHARS = 150` (fits BGE-small's 512-token window with wide margin; overlap preserves cross-boundary context), `ALLOWED_UPLOAD_SUFFIXES = {".txt", ".md"}`, `UPLOAD_SOURCE_TYPE = "file"`.

**Tasks:**

- CREATE `backend/app/ingest/chunker.py` — `Chunk` dataclass + `chunk_text(content) -> list[Chunk]`; paragraph-aware greedy packing, exact spans, overlap via trailing slice of prior chunk
- CREATE `backend/tests/test_chunker.py` — span/exactness, overlap, boundary, empty/whitespace/long-paragraph cases
- CREATE `backend/app/ingest/adapters.py` — `AdaptedSource` dataclass, `SourceAdapter` Protocol, `TextAdapter`, `TextFileAdapter`, `adapt_text()` / `adapt_upload()` entry points, sha-adjacent validation (length checked in pipeline against settings; adapters enforce shape)
- CREATE `backend/tests/test_adapters.py` — source-type validation, extension mapping, title defaults, strict UTF-8 decode errors, origin metadata

### Phase 2: Core Implementation

Embedding + persistence + orchestration. The embedder wraps fastembed behind a lazy singleton with an injectable seam; the repository owns all SQL for the artifact subtree; the pipeline composes adapt → chunk → embed → persist with hashing, timestamps, cap enforcement, and the dim guard.

**Tasks:**

- CREATE `backend/app/retrieval/embedder.py` — `EMBEDDING_DIM = 384`, `get_model()` lazy singleton, `embed_passages(texts)`, empty-input guard (fastembed generators reject empty lists — return `[]` without calling the model)
- CREATE `backend/app/db/artifacts.py` — `store_artifact(conn-args...)`, `list_artifacts()`, `get_artifact_detail()`; single-transaction writes; vec rows via `struct.pack`; rowid alignment
- CREATE `backend/app/ingest/pipeline.py` — `IngestResult` dataclass; `ingest_source(*, source_type, title, content, origin, db_path, max_artifact_chars, embed_fn=embed_passages)`; char-cap check (413 signal via `ArtifactTooLargeError`), `content_hash = sha256(content)`, `created_at = UTC ISO-8601`, `check_embedding_dim` fail-fast before embedding

### Phase 3: Integration

Thin HTTP surface plus startup wiring. Router validates and maps domain errors to status codes; `main.py` mounts the router and adds a lifespan handler that prepares the DB file (mkdir parent + `init_db` + dim check) so first-request ingestion never hits missing tables.

**Tasks:**

- CREATE `backend/app/api/ingest.py` — Pydantic request/response models mirroring PRD §10 shapes; four endpoints; `UploadFile` handling with `MAX_UPLOAD_MB` byte guard; domain-error → `HTTPException` mapping
- UPDATE `backend/app/main.py` — `include_router(ingest_router, prefix="/api/v1")`; lifespan context (parent-mkdir + `init_db` + `check_embedding_dim` with warning-not-crash semantics when the DB file is fresh vs. mismatch — mismatch raises, missing file inits)
- Wire response models: `POST` → 201 `{"artifact_id", "chunks"}` (+ `extracted_chars` for upload); `GET` list → provenance + counts; `GET` detail → full content + chunks + linked fact/interpretation ids

### Phase 4: Testing & Validation

Contract + integration coverage with stubbed embeddings, then full-gate validation. Every behavior in this deliverable gets a test: chunk determinism, adapter validation, transactionality (artifact + chunks + vec + FTS all-or-nothing), cap enforcement at both layers (bytes + chars), status-code mapping, list/detail shapes and counts, dim-mismatch fail-fast, UTF-8 strictness.

**Tasks:**

- CREATE `backend/tests/test_ingest_pipeline.py` — stub-`embed_fn` pipeline tests over tmp DBs (persist shape, FTS/vec row presence, all-or-nothing on embed failure, char-cap error, dim-guard error)
- CREATE `backend/tests/test_ingest_api.py` — TestClient tests with monkeypatched embed symbol (201 shapes, multipart upload incl. `.md`, 400/404/413/422 matrix, list counts, detail content round-trip, OpenAPI contains routes)
- Run L1–L4 validation commands; fix regressions; confirm pre-existing suite still green

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

### CREATE backend/app/ingest/chunker.py

- **IMPLEMENT**: `Chunk` dataclass (`text: str`, `span_start: int`, `span_end: int`, `chunk_idx: int`); constants `CHUNK_TARGET_CHARS = 1000`, `CHUNK_OVERLAP_CHARS = 150`; `chunk_text(content: str) -> list[Chunk]` — greedy paragraph packing: split on `\n\n` (keep spans via running offsets, do NOT rejoin-and-reslice blindly), accumulate paragraphs until adding the next would exceed target, then cut; paragraphs longer than target split on sentence boundaries (`.!?` + space), then hard word-wrap as final fallback; overlap = last `CHUNK_OVERLAP_CHARS` chars of the cut chunk prepended to the next chunk's text with spans adjusted so `content[span_start:span_end] == text` ALWAYS holds; strip each chunk text but keep spans pointing at the stripped slice; empty/whitespace-only content → `[]` (caller decides 400/422); deterministic — same input, same chunks, no randomness, no hashing
- **PATTERN**: pure stdlib module, no app imports — MIRROR `backend/app/db/schema.sql` span contract (`span_start`/`span_end` INTEGER columns) so repository can persist verbatim
- **IMPORTS**: `from __future__ import annotations`, `dataclasses.dataclass` only
- **GOTCHA**: spans must index the ORIGINAL `content`, not a normalized copy — compute offsets against the input string as given; `str.split` discards separators, so track offsets manually (search from cursor) instead of `"".join` reconstruction; overlap slicing must not produce negative `span_start` on short inputs; chunk `text` stripped for embedding quality but span covers the stripped slice exactly
- **VALIDATE**: `cd backend && uv run ruff check app/ingest/chunker.py && uv run ruff format --check app/ingest/chunker.py`

### CREATE backend/tests/test_chunker.py

- **IMPLEMENT**: unit tests — (1) short text → single chunk with `span == (0, len)` and round-trip `content[s:e] == text`; (2) multi-paragraph long text → multiple chunks, every chunk round-trips its span, `chunk_idx` sequential from 0; (3) overlap: chunk N+1 text starts with tail of chunk N (assert shared substring of length `CHUNK_OVERLAP_CHARS` on a long input); (4) determinism: two calls same input → identical lists; (5) empty string + whitespace-only → `[]`; (6) single 5000-char paragraph (no newlines) → splits, all spans round-trip, no chunk exceeds `CHUNK_TARGET_CHARS + CHUNK_OVERLAP_CHARS` by more than one sentence; (7) spans are within `[0, len(content)]` and non-decreasing; (8) content of exactly `CHUNK_TARGET_CHARS` chars → single chunk (no split at the exact boundary); (9) `\r\n` line endings → paragraphs split and every span round-trips; (10) multibyte unicode (emoji/CJK) → spans are CHAR offsets, every chunk round-trips `content[s:e] == text`
- **PATTERN**: plain pytest functions, no fixtures needed — MIRROR style of `backend/tests/test_config.py` (small asserts, no I/O)
- **IMPORTS**: `from app.ingest.chunker import CHUNK_OVERLAP_CHARS, CHUNK_TARGET_CHARS, chunk_text`
- **GOTCHA**: no DB, no model, no settings in this file — pure-function tests must run in milliseconds; do not import pipeline/repository (dependency order)
- **VALIDATE**: `cd backend && uv run pytest tests/test_chunker.py -q`

### CREATE backend/app/ingest/adapters.py

- **IMPLEMENT**: `AdaptedSource` dataclass (`source_type: str`, `title: str`, `content: str`, `origin: dict[str, str]`); `SourceAdapter` Protocol with `source_types: frozenset[str]` attr + `adapt(payload) -> AdaptedSource`; `TEXT_SOURCE_TYPES = frozenset({"note", "paste", "summary"})`, `ALLOWED_UPLOAD_SUFFIXES = {".txt", ".md"}`, `UPLOAD_SOURCE_TYPE = "file"`; `adapt_text(source_type, title, content) -> AdaptedSource` — raises `ValueError` on unknown `source_type` (router maps to 422 via Pydantic `Literal` BEFORE this, so this is defense-in-depth), strips title, `origin = {"adapter": "text"}`; `adapt_upload(filename: str | None, content_type: str | None, raw: bytes) -> AdaptedSource` — raises `UnsupportedSuffixError(ValueError)` when suffix not in allowed set (`None`/missing/empty filename → error BEFORE touching `Path`, so `None` is a 400 not a `TypeError`; otherwise check `Path(filename).suffix.lower()`), strict `raw.decode("utf-8")` raising `UndecodableUploadError(ValueError)` on `UnicodeDecodeError`, title = stem of filename, `origin = {"adapter": "txt_md", "filename": ..., "suffix": ..., "content_type": ...}`; error classes subclass `ValueError` for single-mapping convenience
- **PATTERN**: explicit-params, no settings import — MIRROR `backend/app/core/meta_client.py:1-6` module rule; dataclasses like `ProbeResult`/`DbProbeResult`
- **IMPORTS**: `from __future__ import annotations`, `dataclasses.dataclass/field`, `pathlib.Path`, `typing.Protocol`
- **GOTCHA**: suffix check on the FILENAME, not `content_type` (browsers lie about MIME for `.md`); compare `suffix.lower()` — accept `.MD`/`.TXT`; title from stem must handle filenames without suffix gracefully (already rejected) and strip whitespace; `origin` values must all be JSON-serializable strings (repository `json.dumps` it); untrusted-input discipline (PRD §9): content is data, never interpolated into prompts here — no prompt construction in this module at all
- **VALIDATE**: `cd backend && uv run ruff check app/ingest/adapters.py && uv run ruff format --check app/ingest/adapters.py`

### CREATE backend/tests/test_adapters.py

- **IMPLEMENT**: unit tests — (1) each of `note|paste|summary` adapts with title passthrough + `origin["adapter"] == "text"`; (2) unknown `source_type` raises `ValueError`; (3) `.txt` + `.md` (+ uppercase `.MD`) adapt with title == stem, `source_type == "file"`, origin carries filename/suffix; (4) `.pdf`/`.docx`/no-suffix/empty/`None` filename raise `UnsupportedSuffixError`; (5) invalid-UTF-8 bytes raise `UndecodableUploadError`; (6) origin dict JSON-round-trips (`json.dumps`/`loads`); (7) mislabeled `content_type` (`.md` sent as `application/octet-stream`) still adapts — suffix rules, MIME ignored
- **PATTERN**: plain pytest + `pytest.raises` — MIRROR `backend/tests/test_config.py` (no I/O, no fixtures)
- **IMPORTS**: `json`, `pytest`, `from app.ingest.adapters import (...)`
- **GOTCHA**: keep byte fixtures tiny inline literals (e.g. `b"\xff\xfe bad"`); do not touch the DB or settings
- **VALIDATE**: `cd backend && uv run pytest tests/test_adapters.py -q`

### CREATE backend/app/retrieval/embedder.py

- **IMPLEMENT**: `EMBEDDING_DIM = 384` (must equal `schema.sql` vec0 dim + `meta.embedding_dim`); `EMBEDDING_MODEL_DEFAULT = "BAAI/bge-small-en-v1.5"` (mirror `config.py:21` default — settings value passed in at call time, default is fallback); module `_model: TextEmbedding | None` + `get_model(model_name) -> TextEmbedding` lazy singleton keyed by name (raise-no — single name in MVP, assert same-name reuse or re-init on change; simplest: cache `(name, model)` tuple and rebuild if name differs); `embed_passages(texts: list[str], model_name: str = EMBEDDING_MODEL_DEFAULT) -> list[list[float]]` — `[]` in → `[]` out WITHOUT touching fastembed (generator APIs misbehave on empty input), else `list(model.passage_embed(texts))` converted via `[np.asarray(v, dtype=float).tolist() ...]`; `EmbedFn = Callable[[list[str]], list[list[float]]]` type alias for pipeline injection; import `TextEmbedding` at module top (dep is installed) but NEVER instantiate at import time
- **PATTERN**: explicit-params / injectable-seam — MIRROR `backend/app/core/meta_client.py:30-44` (`client: ... | None = None` injection becomes `embed_fn` injection at the pipeline layer)
- **IMPORTS**: `from __future__ import annotations`, `logging`, `collections.abc.Callable`, `from fastembed import TextEmbedding`
- **GOTCHA**: `passage_embed` returns a GENERATOR of numpy arrays — must `list()` it; `query_embed` is for queries — documents MUST use `passage_embed` (BGE asymmetric prefixes); first real call downloads ~90 MB — unit tests must NEVER reach this (pipeline default only; tests always pass stubs); numpy arrays are not JSON/SQL-bindable — convert to `list[float]`; keep the singleton lazy so `import app.retrieval.embedder` stays fast and offline-safe
- **VALIDATE**: `cd backend && uv run ruff check app/retrieval/embedder.py && uv run ruff format --check app/retrieval/embedder.py && uv run python -c "import app.retrieval.embedder; print('import ok')"`

### CREATE backend/app/db/artifacts.py

- **IMPLEMENT**: repository over `app.db.connection.connect` — `store_artifact(*, db_path, source_type, title, content, content_hash, origin_json, created_at, chunks: list[Chunk], embeddings: list[list[float]]) -> str (artifact_id)` — validates `len(chunks) == len(embeddings)` (`ValueError` otherwise) and every embedding length == 384 (`ValueError` — never persist wrong-dim vectors into vec0); ONE `with conn:` transaction: `INSERT INTO artifacts (id uuid4hex, ...)` then per chunk `INSERT INTO chunks (artifact_id, chunk_idx, span_start, span_end, text)` capturing `cursor.lastrowid` then `INSERT INTO chunks_vec (rowid, embedding) VALUES (lastrowid, struct.pack(...))`; returns `artifact_id`; `list_artifacts(db_path) -> list[ArtifactSummary]` — `id, title, source_type, created_at` + `chunk_count` (COUNT chunks) + `fact_count` (COUNT DISTINCT facts via `fact_chunks` JOIN chunks of this artifact); `get_artifact_detail(db_path, artifact_id) -> ArtifactDetail | None` — full row + ordered chunks (`id, chunk_idx, span_start, span_end, text`) + `fact_ids` (via join) + `interpretation_ids` (by `artifact_id`); small dataclasses `ArtifactSummary`/`ArtifactChunk`/`ArtifactDetail`; module creates no connections at import; callers pass `db_path` explicitly
- **PATTERN**: SQL + transaction style — MIRROR `backend/tests/test_db_init.py:69-86` (artifact → chunk `lastrowid` → vec row with packed bytes, all inside `with conn:`); connection acquisition — MIRROR `backend/app/db/connection.py:21-30` (`connect(path)`, `Row` factory already set); dataclasses like `DbProbeResult`
- **IMPORTS**: `from __future__ import annotations`, `logging`, `sqlite3`, `struct`, `uuid`, `dataclasses`, `from app.db.connection import connect`, `from app.ingest.chunker import Chunk` (type-only — db importing an ingest type is acceptable; alternative `Sequence` protocol — prefer the concrete import for clarity)
- **GOTCHA**: `struct.pack(f"{len(vec)}f", *vec)` — MIRROR `test_db_init.py:19-20` exactly (`f` = float32, matches vec0 `float[384]`); vec0 rowid MUST equal `chunks.id` — use the `lastrowid` of each chunk INSERT, never recompute; NEVER touch `chunks_fts` (triggers own it); `fact_count` counts facts WITH support in this artifact (join through chunks), not all facts; `origin` stored as the caller-provided JSON string (no re-serialization here); close every connection in `finally` (mirror `connection.py:35-50`); UUIDs via `uuid.uuid4().hex`
- **VALIDATE**: `cd backend && uv run ruff check app/db/artifacts.py && uv run ruff format --check app/db/artifacts.py`

### CREATE backend/app/ingest/pipeline.py

- **IMPLEMENT**: `IngestResult` dataclass (`artifact_id: str`, `chunk_count: int`); domain errors `ArtifactTooLargeError(ValueError)` (char cap) and re-export adapter errors for the router; `ingest_source(*, db_path: str, source_type: str, title: str, content: str, origin: dict[str, str], max_artifact_chars: int, embedding_model: str, embed_fn: EmbedFn | None = None) -> IngestResult` — (1) `len(content) > max_artifact_chars` → raise `ArtifactTooLargeError`; (2) `chunks = chunk_text(content)`; (3) `check_embedding_dim(db_path, embedding_model, EMBEDDING_DIM)` fail-fast BEFORE embedding (no wasted model call on a broken DB); (4) `vectors = (embed_fn or default)([c.text for c in chunks])` where default = `functools.partial(embed_passages, model_name=embedding_model)`; (5) `content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()`; (6) `created_at = datetime.now(timezone.utc).isoformat()`; (7) `store_artifact(...)`; (8) `logger.info` one-line summary; return `IngestResult`. Note: empty-chunks input (`[]` from whitespace content) persists the artifact with 0 chunks — the ROUTER rejects empty content earlier (422/400), so the pipeline never sees it in practice; document this contract in the docstring
- **PATTERN**: explicit-params orchestration, no settings import — MIRROR `meta_client.py` rule; default-callable injection — MIRROR `check_meta_reachability(..., client=None)` owned-vs-injected pattern (`meta_client.py:47-48,89-91`)
- **IMPORTS**: `from __future__ import annotations`, `datetime`, `functools`, `hashlib`, `json`, `logging`, `from app.db.artifacts import store_artifact`, `from app.db.connection import check_embedding_dim`, `from app.ingest.chunker import chunk_text`, `from app.retrieval.embedder import EMBEDDING_DIM, EmbedFn, embed_passages`
- **GOTCHA**: cap compares CHARACTER count (`len(content)`), not bytes — PRD §9 `MAX_ARTIFACT_CHARS`; hash the exact stored `content` string (UTF-8 bytes) so the hash verifies the immutable original; `origin` JSON-serialized HERE (`json.dumps(origin, sort_keys=True)`) so the repository stays dumb; dim guard BEFORE embed (model call is the expensive step); keep `embed_fn` signature `(list[str]) -> list[list[float]]` — model name binds via `functools.partial` in the default, stubs ignore it
- **VALIDATE**: `cd backend && uv run ruff check app/ingest/pipeline.py && uv run ruff format --check app/ingest/pipeline.py`

### CREATE backend/app/api/ingest.py

- **IMPLEMENT**: `router = APIRouter(tags=["ingest"])`; Pydantic models — `ArtifactCreate (source_type: Literal["note","paste","summary"], title: str = "", content: str = Field(min_length=1, max_length=None))`, `ArtifactCreated (artifact_id: str, chunks: int)`, `UploadCreated (artifact_id: str, chunks: int, extracted_chars: int)`, `ArtifactListItem (id, title, source_type, created_at, chunk_count, fact_count)`, `ArtifactChunkOut (id, chunk_idx, span: tuple[int,int] | list, text)`, `ArtifactDetailOut (id, title, source_type, content, content_hash, origin: dict, created_at, chunks: list[...], fact_ids: list[str], interpretation_ids: list[str])`; `POST /artifacts` (status 201): `get_settings()` → `adapt_text()` → `ingest_source(embed_fn=None→real)` mapping `ArtifactTooLargeError` → 413; `POST /artifacts/upload` (status 201): `file: UploadFile = File(...)` — SYNC `def`, read `file.file.read(max_bytes + 1)` where `max_bytes = settings.max_upload_mb * 1024 * 1024`, `len > max` → 413 WITHOUT further processing, map `UnsupportedSuffixError`/`UndecodableUploadError` → 400, empty-after-decode (whitespace-only → zero chunks AND zero non-ws chars) → 400, else `ingest_source` (413 on char cap) returning `extracted_chars=len(content)`; `GET /artifacts` → `list_artifacts`; `GET /artifacts/{artifact_id}` → `get_artifact_detail` or 404; all endpoints sync `def`; module-level `EMBED_FN_OVERRIDE: EmbedFn | None = None` seam? NO — tests monkeypatch `app.api.ingest.<symbol>` directly (mirror `test_health.py` probe monkeypatching): router calls `ingest_source(..., embed_fn=None)` and tests patch `app.api.ingest.ingest_source` wrapper OR patch `app.ingest.pipeline` symbol — DECIDE: router imports `ingest_source` by name (`from app.ingest.pipeline import ingest_source`) so tests `monkeypatch.setattr("app.api.ingest.ingest_source", stub)` — document this seam in the module docstring
- **PATTERN**: thin router — MIRROR `backend/app/api/health.py:15-16,34-65` (`router`, `get_settings()` in handler, Pydantic response models); test seam — MIRROR `test_health.py` `monkeypatch.setattr("app.api.health.check_meta_reachability", ...)` by importing the pipeline function BY NAME into the router namespace
- **IMPORTS**: `from __future__ import annotations`, `logging`, `typing.Literal`, `fastapi (APIRouter, File, HTTPException, UploadFile, status)`, `pydantic (BaseModel, Field)`, `from app.core.config import get_settings`, `from app.db.artifacts import get_artifact_detail, list_artifacts`, `from app.ingest.adapters import (UndecodableUploadError, UnsupportedSuffixError, adapt_text, adapt_upload)`, `from app.ingest.pipeline import ArtifactTooLargeError, ingest_source`
- **GOTCHA**: `min_length=1` on `content` yields 422 for `""` (FastAPI default — accept it, PRD-conformant); whitespace-only JSON content passes `min_length` — explicitly reject `content.strip() == ""` with 422 to match upload-side 400 semantics... DECIDE: reject whitespace-only in BOTH paths — JSON path raises 422 (`HTTPException(422, "content must not be blank")`), upload path raises 400 (file problem, not schema problem) — document the split; `UploadFile.filename` may be `None` → treat as `""` → 400; byte-cap uses BINARY MB (`1024*1024`); char-cap inside pipeline raises AFTER decode (correct layering: bytes at router, chars in pipeline); response `span` shape: emit `[span_start, span_end]` list (JSON-native, matches PRD §10 `span: [s, e]` citation shape for forward-compat); NEVER log content bytes — log sizes/ids only
- **VALIDATE**: `cd backend && uv run ruff check app/api/ingest.py && uv run ruff format --check app/api/ingest.py`

### UPDATE backend/app/main.py

- **IMPLEMENT**: ADD lifespan: `@asynccontextmanager async def lifespan(app)` — `settings = get_settings()`; `Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)`; `init_db(settings.database_path)`; `check_embedding_dim(settings.database_path, settings.embedding_model, EMBEDDING_DIM)` (import from `app.retrieval.embedder` — creates main→retrieval edge, acceptable: main is the composition root); `yield`; pass `lifespan=lifespan` to `FastAPI(...)`; ADD `from app.api.ingest import router as ingest_router` + `app.include_router(ingest_router, prefix="/api/v1")` next to the health mount; keep liveness router untouched
- **PATTERN**: composition-root wiring — MIRROR existing `create_app()` structure (`main.py:12-26`); lifespan is the standard FastAPI startup hook (no deprecated `@app.on_event`)
- **IMPORTS**: ADD `contextlib.asynccontextmanager`, `pathlib.Path`, `from app.api.ingest import router as ingest_router`, `from app.core.config import get_settings`, `from app.db.connection import check_embedding_dim, init_db`, `from app.retrieval.embedder import EMBEDDING_DIM`
- **GOTCHA**: lifespan runs on server start AND on `TestClient(app)` used as a context manager — existing tests use bare `TestClient(create_app())` (no lifespan, unaffected — VERIFY by running the suite); most new API tests ALSO avoid lifespan (bare TestClient + explicit `init_db(tmp)` + settings override) so they never touch the real `./data/` DB — EXCEPT the two lifespan tests, which deliberately use `with TestClient(...)` with `DATABASE_PATH` pointed at tmp paths; `mkdir` on the parent covers fresh checkouts where `./data/` doesn't exist; dim mismatch at startup RAISES (fail fast — a misconfigured deploy must not serve writes into an uninterpretable vec table); circular-import check: `app.api.ingest` → pipeline → embedder/db must not import `app.main` (they don't)
- **VALIDATE**: `cd backend && uv run ruff check app/main.py && uv run ruff format --check app/main.py && uv run pytest tests/test_app_boot.py tests/test_health.py -q`

### CREATE backend/tests/test_ingest_pipeline.py

- **IMPLEMENT**: fixtures — `db_path(tmp_path)` with `init_db()`; `stub_embed(texts) -> [[float(i)] * 384 ...]` deterministic distinct-per-index vectors (e.g. `[(i + 1) * 0.01] * 384`); `settings_caps (max_artifact_chars=500_000, embedding_model="BAAI/bge-small-en-v1.5")` as plain constants (no settings import — pipeline takes explicit params); tests — (1) round-trip: `ingest_source(...)` returns id + count, artifact row + chunk rows + vec rows exist, FTS `MATCH` finds a distinctive term; (2) embed-failure all-or-nothing: `embed_fn` raising leaves ZERO artifact/chunk/vec/FTS rows (nothing persisted before the model call returns); (3) in-transaction rollback: monkeypatch `app.db.artifacts.connect` to return a thin proxy whose `execute` raises on `chunks_vec` INSERTs (after artifact + chunk rows have landed) → the raise propagates and ZERO artifact/chunk/vec rows plus zero FTS hits remain (proves the `with conn:` block rolled back, triggers included); (4) char cap: content of `max+1` chars raises `ArtifactTooLargeError` and persists nothing; (5) dim guard: `tmp` DB re-inited then `meta.embedding_model` tampered (UPDATE meta SET value='other') → `ingest_source` raises `EmbeddingDimMismatchError` WITHOUT calling embed_fn (assert via flag); (6) wrong-dim vectors (`[0.0]*128`) AND wrong-count vector list (fewer vectors than chunks) → `ValueError` from repository, nothing persisted; (7) `embed_passages([])` returns `[]` without touching fastembed (offline-safe — asserts the empty-input guard, never downloads the model); (8) `list_artifacts` counts (ingest 2 artifacts, chunk counts right, `fact_count == 0`); (9) `get_artifact_detail` round-trip (content/hash/origin/chunks/spans exact, empty fact/interpretation lists); (10) missing id → `None`; (11) REAL-model smoke `@pytest.mark.skipif(os.environ.get("TB_REAL_EMBEDDINGS") != "1", reason=...)` — single short ingest with `embed_fn=None`, assert 384-dim vectors landed in vec0 (slow, downloads model — NEVER in default runs)
- **PATTERN**: tmp-DB fixture — MIRROR `test_db_init.py:23-28`; vec assertions via `MATCH ... ORDER BY distance` — MIRROR `test_db_init.py:84-90`; FTS assertions — MIRROR `test_db_init.py:106-121`
- **IMPORTS**: `os`, `struct`, `pytest`, `from app.db.artifacts import ...`, `from app.db.connection import connect, init_db`, `from app.ingest.pipeline import ArtifactTooLargeError, IngestResult, ingest_source`
- **GOTCHA**: vec0 `MATCH` needs a packed query vector — MIRROR `_pack` helper from `test_db_init.py:19-20`; tamper `meta` via raw UPDATE inside `with conn:` then close before calling pipeline (pipeline opens its own connections); stub vectors must be VALID floats packable by `struct` (no NaN/inf); rollback proxy: `sqlite3.Connection` forbids attribute assignment, so WRAP the connection in a delegating proxy class (raise on `chunks_vec` SQL, delegate everything else incl. `__enter__`/`__exit__` so the real rollback runs) — do not patch connection methods; keep the real-model test to ONE tiny artifact (fast even when enabled)
- **VALIDATE**: `cd backend && uv run pytest tests/test_ingest_pipeline.py -q`

### CREATE backend/tests/test_ingest_api.py

- **IMPLEMENT**: fixtures — autouse `_isolated_settings` MIRROR of `test_health.py:21-35` (cache clear + env scrub + `Settings(_env_file=None)` patching `app.api.ingest.get_settings`; the two lifespan tests additionally patch `app.main.get_settings` to the same tmp-path settings so startup initializes the tmp DB, never the real one); `_client(monkeypatch, tmp_path)` helper: `init_db(tmpdb)`, set `DATABASE_PATH=tmpdb` env, monkeypatch `app.api.ingest.ingest_source` with a stub that delegates to the REAL pipeline but forces `embed_fn=fake` (preserves router→pipeline→repository integration while stubbing only the model — implement as `def _stub(**kw): kw["embed_fn"] = fake; return real_ingest_source(**kw)`); tests — (1) `POST /api/v1/artifacts` note → 201 `{"artifact_id","chunks"}` with `chunks >= 1`; (2) paste + summary source types → 201; (3) bad `source_type` → 422; (4) empty `content` → 422; whitespace-only → 422; (5) over-char-cap (`MAX_ARTIFACT_CHARS=10`) → 413; (6) `POST /api/v1/artifacts/upload` `.txt` file → 201 with `extracted_chars`; (7) `.md` uppercase `.MD` → 201; (8) `.pdf` → 400; (9) invalid-UTF-8 bytes → 400; (10) oversized bytes (`MAX_UPLOAD_MB=0`... careful 0 MB = 0 bytes → any content 413; use tiny file + `MAX_UPLOAD_MB` unset-but-monkeypatched to 0) → 413; (11) whitespace-only file → 400; (12) `GET /api/v1/artifacts` → list with `chunk_count`/`fact_count` keys; (13) `GET /api/v1/artifacts/{id}` → 200 full round-trip (content exact, chunks spans, `fact_ids == []`); (14) unknown id → 404; (15) OpenAPI contains `/api/v1/artifacts` paths; (16) oversized upload persists NOTHING (`GET` list empty after 413); (17) lifespan fresh-init: `DATABASE_PATH` set to a tmp path whose PARENT dir does not exist, `with TestClient(create_app())` boots cleanly, parent dir + DB file get created, `meta.schema_version` row present, `GET /health` → 200; (18) lifespan dim-mismatch: pre-`init_db` a tmp DB then tamper `meta.embedding_model` → entering `with TestClient(create_app())` raises `EmbeddingDimMismatchError` (assert with `pytest.raises` around the `with` statement); (19) exact-boundary bytes: with `MAX_UPLOAD_MB=1` AND `MAX_ARTIFACT_CHARS=2097152` (char cap raised well clear so only the byte cap is exercised — the default 500000 would 413 a 1 MB ASCII file on chars first), a file of exactly `1048576` bytes → 201 and a `1048577`-byte file → 413 via the byte cap alone; (20) exact-boundary chars: with `MAX_ARTIFACT_CHARS=10`, 10-char JSON content → 201 and 11-char content → 413 with nothing persisted
- **PATTERN**: settings isolation + TestClient — MIRROR `test_health.py:21-42` exactly (same env-var scrub list); probe monkeypatch — MIRROR `test_health.py:65-66` (`monkeypatch.setattr("app.api.ingest.ingest_source", _stub)`)
- **IMPORTS**: `io`, `pytest`, `fastapi.testclient.TestClient`, `from app.core.config import Settings`, `from app.db.connection import init_db`, `from app.main import create_app`, `import app.ingest.pipeline as pipeline_mod` (for the real function reference)
- **GOTCHA**: multipart in TestClient: `client.post(url, files={"file": ("note.txt", b"...", "text/plain")})` — field name MUST be `file` (matches router param); `MAX_UPLOAD_MB=0` edge: `0 * 1024 * 1024 = 0` bytes allowed — assert 413 for ANY non-empty file, but ALSO assert an empty file still 400s (decode/blank check order: bytes-cap FIRST, then suffix, then decode, then blank — document order in router); stub `ingest_source` must accept the router's exact kwargs — write it as `(*a, **k)` passthrough setting `k["embed_fn"]`; NEVER let tests hit the real fastembed (no-network guarantee) except the gated smoke in `test_ingest_pipeline.py`; boundary tests isolate ONE cap at a time (test 19 raises `MAX_ARTIFACT_CHARS` clear of both byte cases; test 20's 10/11-char bodies never near the byte cap)
- **VALIDATE**: `cd backend && uv run pytest tests/test_ingest_api.py -q`

---

## TESTING STRATEGY

Backend `pytest` only (no frontend changes). Deterministic layers get exhaustive unit tests; the model boundary gets stubbed contract tests plus one gated real-model smoke test. All tests offline-safe by default.

### Unit Tests

`tests/test_chunker.py` — pure-function coverage: single-chunk span exactness, multi-chunk sequencing, overlap substring sharing, determinism (repeat-call equality), empty/whitespace → `[]`, long-paragraph fallback splitting, span bounds/monotonicity, exact-target-length boundary (tests 8–10: no split at exactly `CHUNK_TARGET_CHARS`, `\r\n` spans, multibyte char-offset spans). Must run in milliseconds, no fixtures.

`tests/test_adapters.py` — validation matrix: all three text source types, unknown type rejection, extension allowlist incl. case-insensitivity, title-from-stem, strict UTF-8 rejection, origin JSON-round-trip, `None`/empty filename rejection, mislabeled `content_type` ignored (suffix rules). No I/O.

### Integration Tests

`tests/test_ingest_pipeline.py` — real SQLite (tmp DBs), stubbed embeddings: full persist round-trip with FTS `MATCH` + vec0 `MATCH ... ORDER BY distance` assertions proving both indexes landed; all-or-nothing on embed failure PLUS an in-transaction rollback test (forced vec-insert failure → zero artifact/chunk/vec/FTS rows); char-cap rejection with zero residue; dim-guard fail-fast without invoking the model; wrong-dim AND wrong-count vector rejection; `embed_passages([])` empty guard (offline-safe); list counts; detail round-trip; `None` on missing id. Gated real-model smoke (`TB_REAL_EMBEDDINGS=1`) for the true fastembed path.

`tests/test_ingest_api.py` — TestClient over tmp DBs with router-level `ingest_source` stub wrapper (real pipeline + repository, fake vectors): 201 shapes for all three text types and both upload suffixes; full error matrix (422 bad type / empty / blank JSON; 400 bad suffix / bad bytes / blank file; 413 byte-cap / char-cap); exact-boundary cap tests (`limit` → 201, `limit+1` → 413, both layers); list/detail shapes and counts; 404; OpenAPI path presence; no-residue-after-413; lifespan startup tests (`with TestClient`: fresh parent-dir + DB init; tampered-meta raise).

### Edge Cases

- Empty string vs. whitespace-only vs. normal content (chunker test 5 → `[]`; API tests 4/11 → 422/400; pipeline contract documented)
- `MAX_UPLOAD_MB=0` zero-byte allowance (API test 10) and exact-boundary sizes — `limit` passes, `limit+1` 413s — at the byte layer (API test 19) and char layer (API test 20)
- Filenames: uppercase suffix (API test 7), no suffix / empty / `None` filename (adapters test 4), `content_type` lies — `.md` as `application/octet-stream` still accepted since suffix rules (adapters test 7). Unicode-stem case deliberately NOT tested (no unicode-specific logic; `Path.stem` passthrough — owner judgment, Cycle 1)
- Chunker: content exactly `CHUNK_TARGET_CHARS` (chunker test 8), single mega-paragraph (chunker test 6), `\r\n` line endings (chunker test 9), multibyte chars with CHAR-offset spans (chunker test 10 — `content[s:e]` slicing, never byte offsets)
- DB: fresh file + missing parent dir created by lifespan (API test 17), tampered `meta.embedding_dim` fails fast (pipeline test 5 + API test 18), sequential ingests each on their own connection (pipeline test 8 ingests 2 artifacts — single-writer SQLite, no shared-connection state)
- Embeddings: empty chunk-text list → `[]` without model call (pipeline test 7); stub returning wrong count/dim → `ValueError`, nothing persisted (pipeline test 6)

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

Every command or block MUST state its exact pass signal on an `Expected:` line (exit code plus the key output, count, or observation that proves success — e.g. `Expected: exit 0, "11 passed"`, `Expected: exit 0, docs:200`). A check whose passing output is not specified cannot confirm anything; do not write checks you cannot describe passing.

### Level 1: Syntax & Style

```bash
cd backend && uv run ruff check .
```
Expected: exit 0, `All checks passed!`

```bash
cd backend && uv run ruff format --check .
```
Expected: exit 0, N files `would be left unchanged` (zero `would be reformatted`)

```bash
cd backend && uv run mypy app
```
Expected: exit 0, `Success: no issues found in M files` (non-strict config per AGENTS.md)

### Level 2: Unit Tests

```bash
cd backend && uv run pytest tests/test_chunker.py tests/test_adapters.py -q
```
Expected: exit 0, `N passed` (N = total new pure-unit tests, zero failures/skips)

### Level 3: Integration Tests

```bash
cd backend && uv run pytest tests/test_ingest_pipeline.py tests/test_ingest_api.py -q
```
Expected: exit 0, `M passed, 1 skipped` (the skip is the `TB_REAL_EMBEDDINGS`-gated real-model smoke)

```bash
cd backend && uv run pytest -q
```
Expected: exit 0, full suite green — all pre-existing tests (boot, config, health, db-init, meta-client) still pass plus all new tests; zero failures, zero errors

Optional real-embedding proof (downloads ~90 MB model on first run; run once, then note the result):
```bash
cd backend && TB_REAL_EMBEDDINGS=1 uv run pytest tests/test_ingest_pipeline.py -q -k real
```
Expected: exit 0, smoke test passes, vec0 row with 384-dim vector present (proves `passage_embed` + pack + rowid path with true vectors)

### Level 4: Manual Validation

Performer: `agent` (all steps executable in this environment via dev server + curl — the executor MUST run them).

Setup (once):
1. `cd backend && uv sync` to ensure deps installed; expected: exit 0, environment ready
2. Start the server with a scratch DB: `DATABASE_PATH=/tmp/tb_ingest_manual.db uv run uvicorn app.main:create_app --factory --port 8011 &` then `sleep 3`; expected: log line shows uvicorn startup without traceback; `curl -s localhost:8011/health` returns `{"status":"ok","db":true,...}` proving lifespan init created the DB

Step 1 — text ingest round-trip:
1. `curl -s -X POST localhost:8011/api/v1/ingest-safety-check -o /dev/null -w "%{http_code}"` — sanity: expect `404` (route must NOT exist; guards against router-prefix typos shadowing real paths)
2. `curl -s -X POST localhost:8011/api/v1/artifacts -H 'Content-Type: application/json' -d '{"source_type":"note","title":"SQLAlchemy fix","content":"Fixed the lazy loading problem by adding selectinload to the query. The N+1 queries are gone."}'`; expected: HTTP 201, body `{"artifact_id":"<32-hex>","chunks":1}`
3. `curl -s localhost:8011/api/v1/artifacts`; expected: HTTP 200, list contains the artifact with `chunk_count: 1`, `fact_count: 0`, matching `title`/`source_type`
4. `curl -s localhost:8011/api/v1/artifacts/<id-from-step-2>`; expected: HTTP 200, `content` exactly the posted string, `content_hash` 64-hex, one chunk with `span: [0, <len>]`, `fact_ids: []`, `interpretation_ids: []`

Step 2 — upload ingest:
1. `printf '# Dev log\n\nPostgres index tuning cut p99 in half.' > /tmp/tb_note.md && curl -s -X POST localhost:8011/api/v1/artifacts/upload -F "file=@/tmp/tb_note.md"`; expected: HTTP 201, body has `artifact_id`, `chunks: 1`, `extracted_chars: 49`
2. `curl -s localhost:8011/api/v1/artifacts | python3 -c "import json,sys; print([a['source_type'] for a in json.load(sys.stdin)])"`; expected: includes `"file"`
3. `printf 'x' > /tmp/tb_bad.pdf && curl -s -o /dev/null -w "%{http_code}" -X POST localhost:8011/api/v1/artifacts/upload -F "file=@/tmp/tb_bad.pdf"`; expected: `400`

Step 3 — error matrix spot-check:
1. `curl -s -o /dev/null -w "%{http_code}" -X POST localhost:8011/api/v1/artifacts -H 'Content-Type: application/json' -d '{"source_type":"email","title":"t","content":"x"}'`; expected: `422`
2. `curl -s -o /dev/null -w "%{http_code}" localhost:8011/api/v1/artifacts/does-not-exist`; expected: `404`
3. `curl -s localhost:8011/api/v1/artifacts/does-not-exist`; expected: body `{"detail": "..."}` (FastAPI default shape)

Step 4 — index proof (both indexes landed):
1. From `backend/`, run `uv run python -c "from app.db.connection import connect; c = connect('/tmp/tb_ingest_manual.db'); print(c.execute('SELECT COUNT(*) FROM chunks').fetchone()[0], c.execute('SELECT COUNT(*) FROM chunks_vec').fetchone()[0], c.execute(\"SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH 'selectinload'\").fetchone()[0]); c.close()"`; expected: `2 2 1` (two artifacts → two chunks → two vec rows; FTS finds the distinctive term once). Must go through the app's `connect()` so the sqlite-vec extension loads — plain `sqlite3` fails on `chunks_vec` with `no such module: vec0`
2. Stop the server (`kill %1` or the recorded PID); expected: process exits, no traceback in server log

### Level 5: Additional Validation (Optional)

None required — no MCP servers, browser flows, or extra CLIs apply to this backend-only deliverable. If the executor has `sqlite3` CLI available, `.schema chunks_vec` eyeball-check of the vec0 table is a free extra confidence signal (not a gate).

---

## MANUAL VERIFICATION CHECKLIST

Label each item `agent` or `human` (same performer rule as Level 4). Each item MUST give numbered steps and the exact expected observable result — never a bare "verify X works."

- [ ] [agent] text-ingest round-trip: 1. POST a note via `/api/v1/artifacts`; 2. GET list; 3. GET detail by id; expected: 201 `{"artifact_id","chunks":1}` → list shows `chunk_count: 1` → detail `content` byte-exact, `span [0,len]`, empty link lists
- [ ] [agent] upload-ingest round-trip: 1. POST `/tmp/tb_note.md` via `/api/v1/artifacts/upload`; 2. GET list; expected: 201 with `extracted_chars: 49` → new row has `source_type "file"`
- [ ] [agent] rejection matrix: 1. POST `.pdf` file; 2. POST unknown `source_type`; 3. GET bogus id; expected: `400`, `422`, `404` respectively, each with FastAPI `{"detail": ...}` body
- [ ] [agent] dual-index proof: 1. from `backend/`, run `uv run python` opening the manual DB via `app.db.connection.connect` (loads sqlite-vec — plain `sqlite3` cannot query `chunks_vec`) and print `COUNT(*)` on `chunks`, `chunks_vec`, and `chunks_fts MATCH 'selectinload'`; expected: `2 2 1`
- [ ] [agent] cap enforcement: 1. restart server with `MAX_ARTIFACT_CHARS=10`; 2. POST 50-char note; 3. GET list; expected: `413` on POST, list does NOT contain the rejected artifact (no residue)
- [ ] [agent] lifespan init: 1. delete `/tmp/tb_ingest_manual.db*`; 2. start server; 3. GET `/health`; expected: `200 {"status":"ok","db":true,...}` and the DB file exists (created by lifespan, not by the probe); automated proof: L3 API lifespan tests 17 (fresh parent-dir + DB init) and 18 (tampered-meta raise)
- [ ] [agent] real-embedding smoke (one-time, network): 1. run `TB_REAL_EMBEDDINGS=1 uv run pytest tests/test_ingest_pipeline.py -q -k real`; expected: pass; if the sandbox has no network, record `SKIPPED (no network)` as a coverage gap instead of failing the gate

## ROLLBACK CONSIDERATIONS

- Code rollback is a clean `git checkout` of the new files + `main.py` (lifespan + router mount are additive; removing them restores prior boot behavior). No migration to reverse: `schema.sql` is UNCHANGED by this deliverable.
- Data rollback: artifacts created during manual validation live in scratch DBs (`/tmp/tb_ingest_manual.db`) — delete the files. If the executor ingested into the real `./data/thoughtbridge.db`, delete the artifact rows (`DELETE FROM artifacts` cascades to chunks; vec rows for deleted chunk ids must be removed explicitly — `DELETE FROM chunks_vec WHERE rowid NOT IN (SELECT id FROM chunks)` — until the Phase 3 cascade owns this) or simply delete the dev DB file and let lifespan re-init.
- Model cache: fastembed downloads to its HF cache dir on first real embed — harmless to keep; no rollback needed.

## ACCEPTANCE CRITERIA

Each criterion MUST name the check that proves it: the validation level/command, the test file, or the manual-checklist item — plus the exact expected result. A criterion with no verification named is an incomplete plan.

- [ ] `POST /artifacts` ingests `note|paste|summary` and returns 201 `{"artifact_id","chunks"}` (L3 `test_ingest_api.py` create tests; L4 manual Step 1.2 → 201 with 32-hex id)
- [ ] `POST /artifacts/upload` ingests `.txt`/`.md` (case-insensitive) and returns 201 with `extracted_chars` (L3 `test_ingest_api.py` upload tests; L4 manual Step 2.1 → `extracted_chars: 49`)
- [ ] Every chunk persists with exact `(artifact_id, span, chunk_idx)` and `content[s:e] == text` (L2 `test_chunker.py` round-trip tests; L4 manual Step 1.4 → `span [0,len]`)
- [ ] Embeddings come from original chunk text and land rowid-aligned in vec0 (L3 `test_ingest_pipeline.py` vec `MATCH` test; L4 manual Step 4.1 → `chunks_vec` count equals `chunks` count; L3 gated smoke proves the real fastembed path)
- [ ] FTS5 index follows automatically with zero direct FTS writes (L3 pipeline FTS `MATCH` test; L4 manual Step 4.1 → `MATCH 'selectinload'` returns 1)
- [ ] Ingest writes are all-or-nothing: mid-pipeline failures leave zero artifact/chunk/vec/FTS rows (L3 `test_ingest_pipeline.py` embed-failure test 2 + in-transaction rollback test 3)
- [ ] `GET /artifacts` lists provenance + `chunk_count`/`fact_count` (L3 API list test; L4 manual Step 1.3)
- [ ] `GET /artifacts/{id}` returns full content + chunks + linked ids, 404 on unknown id (L3 API detail/404 tests; L4 manual Steps 1.4 + 3.2)
- [ ] `MAX_UPLOAD_MB` (bytes) and `MAX_ARTIFACT_CHARS` (chars) reject with 413 and persist nothing (L3 API 413 + no-residue tests + pipeline cap test; manual checklist cap-enforcement item)
- [ ] Bad suffix / undecodable bytes / blank inputs rejected (400 upload-side, 422 JSON-side) (L3 API error-matrix tests; L4 manual Steps 2.3 + 3.1)
- [ ] Dim/config drift fails fast without embedding (L3 pipeline dim-guard test 5 asserting embed_fn uncalled; L3 API lifespan test 18 proving tampered-meta raises `EmbeddingDimMismatchError` on boot; L3 API lifespan test 17 proving fresh parent-dir + DB init on boot)
- [ ] All validation commands pass with zero errors (L1 ruff + mypy + format; L3 full `pytest -q` green incl. pre-existing tests)
- [ ] Test coverage: new modules covered per TESTING STRATEGY; no stated repo threshold exists (AGENTS.md sets none), so the bar is every behavior above asserted, not a percentage
- [ ] Code follows project conventions and patterns (thin router, explicit-params modules, no settings imports outside router/main, logging without content — reviewer checks against CONTEXT REFERENCES)
- [ ] No regressions in existing functionality (L3 full-suite run: boot/config/health/db-init/meta-client tests all still pass; lifespan does not alter bare-TestClient behavior)
- [ ] No frontend changes (acceptance: `git status` shows zero modifications under `frontend/`)

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

- **Design decision — chunk sizing (1000/150 chars):** BGE-small-en-v1.5 has a 512-token window (~2000 chars); 1000-char targets with 150-char overlap stay well inside it while keeping passages coherent. Char-based (not token-based) keeps the chunker dependency-free and deterministic. Revisit only if deliverable 4 measures recall failures.
- **Design decision — uploads as `source_type "file"`:** PRD §10 constrains `note|paste|summary` only for `POST /artifacts`; the upload endpoint carries no such constraint. `"file"` keeps provenance honest (typed vs. uploaded stays distinguishable for Phase 2 extraction prompts), with filename/suffix/adapter in `origin`. If review prefers `note`-for-all, it's a one-constant change (`UPLOAD_SOURCE_TYPE`) plus test updates.
- **Design decision — strict UTF-8 (400 on failure):** `.txt`/`.md` are near-universally UTF-8; mojibake in a memory system is worse than a clear rejection. Latin-1 fallback deliberately NOT added (silent corruption risk).
- **Design decision — startup lifespan owns DB init:** keeps `check_readable` side-effect-free (health-probe contract), guarantees tables exist before first ingest, and centralizes the dim guard. Bare-TestClient tests never trigger it, so existing tests are unaffected.
- **Design decision — sync `def` endpoints:** sqlite3 and fastembed block; sync endpoints run in FastAPI's threadpool, async ones would stall the event loop. No `await` anywhere in the ingest path.
- **Design decision — 422-vs-400 split for blank content:** JSON blank → 422 (schema/validation problem, FastAPI-idiomatic); file blank → 400 (file problem). Both tested; both documented in the router.
- **Trade-off — no streaming embed/batch tuning:** MVP embeds all chunks of one artifact in a single `passage_embed` call. Fine for `MAX_ARTIFACT_CHARS=500k` worst case (~500 chunks, seconds on CPU). Batching only if measured slow.
- **Trade-off — `db` imports `ingest` type:** `artifacts.py` imports `Chunk` from `chunker.py` for signature clarity. `chunker.py` is stdlib-only so no cycle is possible. If review objects, fall back to a `Sequence[tuple[str,int,int,int]]` protocol.
- **Risk — fastembed first-download (~90 MB):** only affects the L4 manual run and the gated smoke test, never the default suite. If the sandbox is offline, L4 text/upload flows still fully validate (server uses real fastembed — OFFLINE IT WILL FAIL): mitigation — L4 manual steps REQUIRE network for the real model; if offline, the executor must instead run the API suite (stubbed) and record L4 server-flow as blocked-on-network with the stubbed suite as the evidence. Flag this early in execution.
- **Risk — `UploadFile.file.read` in sync endpoint:** relies on Starlette's `SpooledTemporaryFile` sync handle. Well-established pattern, but if the installed Starlette version surprises, fallback is `async def` endpoint with `await file.read()` + `anyio.to_thread` for the pipeline. Pin: verify in the first API test run.
- **Out-of-scope guard:** if execution tempts toward `GET /chunks/{id}`, DELETE, or Capture UI — stop. Those belong to deliverables 4, Phase 3, and an unscheduled UI task respectively. The plan is backend-only by build-list authority.
- **Forward-compat:** `SourceAdapter` Protocol + `origin.adapter` naming reserves `pdf`/`docx` (Phase 2) and `tb_conversation` (Phase 3) without touching `chunk_text`, the embedder, or the repository. `span: [s, e]` list shape in detail responses matches the PRD §10 citation shape deliverable 5 will reuse.
- **Open follow-up — Capture UI scheduling (undecided, non-blocking):** PRD F-1 and §11 assume a capture text box/upload UI and a demo that "capture[s] a note", but no Phase 1 build-list deliverable schedules a Capture UI. Owner decision (2026-11-02): leave undecided for now; this deliverable stays backend-only. This plan deliberately does NOT assign Capture UI to any phase or deliverable — scheduling it is a separate owner action outside this plan.

---

## Revision History

### Cycle 1

Owner direction for this cycle: apply the four routine corrections (using judgment to avoid unnecessary edge-case tests); record Capture UI as an undecided, non-blocking open follow-up without phase/deliverable assignment; continue the automated loop, escalating only genuine blocking decisions.

Findings addressed (from `.agents/plans/reviews/source-adapter-ingestion-plan-review.md`, review 1):

1. "Fix manual index proof" — L4 Step 4.1 and the `[agent] dual-index proof` checklist item ran plain `python3 sqlite3` against `chunks_vec` without the sqlite-vec extension (`no such module: vec0`). Changed both to run from `backend/` via `uv run python` opening the DB through `app.db.connection.connect`, with an explicit note on why plain `sqlite3` fails. Expected output unchanged (`2 2 1`).
2. "Add a real rollback test" — the old all-or-nothing test failed in `embed_fn` (before any write) and the wrong-dim test failed in pre-transaction validation, so neither exercised rollback. Added pipeline test 3 (in-transaction rollback via a delegating connection proxy that raises on `chunks_vec` INSERTs; asserts zero artifact/chunk/vec rows + zero FTS hits), renumbered the pipeline tests to 11, added the proxy-pattern GOTCHA (wrap, don't patch — `sqlite3.Connection` forbids attribute assignment), updated TESTING STRATEGY, and added an explicit all-or-nothing acceptance criterion naming tests 2 + 3.
3. "Add lifespan tests" — the "lifespan mismatch raises on boot" criterion and lifespan checklist item had no automated proof. Added API tests 17 (fresh parent-dir + DB init via `with TestClient`) and 18 (tampered `meta` → `pytest.raises(EmbeddingDimMismatchError)` around `with TestClient`); clarified the settings fixture so lifespan tests also patch `app.main.get_settings`; carved the two tests out of the main.py GOTCHA's avoid-lifespan rule; updated TESTING STRATEGY, the dim-drift criterion, and the lifespan checklist item to name tests 17/18.
4. "Align edge cases with tests" — added chunker tests 8–10 (exact-target boundary, `\r\n` spans, multibyte char-offset spans), adapters test 7 (mislabeled `content_type` ignored), API tests 19–20 (exact-boundary bytes/chars: `limit` → 201, `limit+1` → 413), pipeline test 7 (`embed_passages([])` empty guard, offline-safe), extended pipeline test 6 (wrong-count in addition to wrong-dim) and adapters test 4 (`None` filename; `adapt_upload` signature widened to `str | None` with `None` → `UnsupportedSuffixError` before touching `Path`). Every Edge Cases bullet now names its proving test number(s). Per owner judgment: the unicode-stem case was deliberately NOT given a test (no unicode-specific logic; `Path.stem` passthrough) and is recorded as such in the Edge Cases section. Also fixed the "concurrent Sequential ingests" wording (now "sequential ingests", mapped to pipeline test 8).
5. Capture UI scheduling — recorded as an open follow-up NOTES line per the owner decision above (undecided, non-blocking, no phase/deliverable assignment). No UI tasks added.

Not done / open: Capture UI scheduling remains undecided by explicit owner choice (non-blocking for this plan). Nothing else outstanding from review 1.

### Cycle 2

Finding addressed (from `.agents/plans/reviews/source-adapter-ingestion-plan-review.md`, review 2 — the only open item; all Cycle 1 fixes verified PASS, no escalations):

1. "API test 19 (exact-boundary bytes) must also raise MAX_ARTIFACT_CHARS to at least 1048576, or the 1048576-byte ASCII file will hit the char cap (413) instead of returning the expected 201." Amended test 19 to set `MAX_ARTIFACT_CHARS=2097152` alongside `MAX_UPLOAD_MB=1` (chosen well clear of BOTH byte cases so the 1048577-byte 413 is provably byte-cap-only, not ambiguous between the two caps), with the rationale inline, plus a GOTCHA rule that boundary tests isolate one cap at a time. TESTING STRATEGY and Edge Cases text needed no change (they reference test 19 without restating its env setup). Verified test 20 has no symmetric problem (10/11-char bodies never near the byte cap).

Not done / open: nothing — review 2's single correction is fully applied. Capture UI remains an owner-deferred open follow-up (non-blocking).

