# Feature: Hybrid retrieval

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Implement Phase 1 deliverable 4: hybrid BM25 (FTS5) + dense-vector (sqlite-vec) search fused with Reciprocal Rank Fusion (RRF, k=60), exposed through a top-k inspection endpoint plus the PRD §10 citation target. `POST /api/v1/retrieval/search` takes `{query, top_k}` and returns ranked `[{chunk_id, artifact_id, span, excerpt, rrf_score, bm25_rank, vector_rank}]`; `GET /api/v1/chunks/{chunk_id}` returns full chunk text with its artifact link. Query embedding uses fastembed `query_embed` (BGE asymmetric path; documents already use `passage_embed`). Raw user text is sanitized into a safe FTS5 `MATCH` expression (quoted-OR tokens) so injection strings can never cause syntax errors. The vector index is treated as derived: every returned field is hydrated from the canonical `chunks` table. Backend-only; no answer generation, no reranker, no HyDE, no UI changes.

## User Story

As a ThoughtBridge user
I want vague natural-language queries to retrieve the right saved passages without exact keywords
So that forgotten terminology never blocks recovering what I know

## Problem Statement

Ingestion (deliverable 3) fills `chunks` + FTS5 + vec0 rows, but nothing reads them back: there is no query path, no ranking, and no way to verify the "retrieval without terminology" promise (PRD US-1, Phase 1 gate). Grounded Q&A (deliverable 5) needs a retrieval function to assemble evidence; this deliverable builds exactly that function plus a thin inspection surface over it, proving recall at the retrieval level before any generation is added.

## Scope

- In scope: `embed_query` in the embedder wrapper; chunk repository (`backend/app/db/chunks.py`: BM25 leg, vector leg, batch hydrate, single-chunk read); retrieval orchestration (`backend/app/retrieval/search.py`: FTS sanitizer, RRF fusion, `hybrid_search`); thin router (`POST /retrieval/search`, `GET /chunks/{chunk_id}`); router mount in `main.py`; pure-unit + integration + API tests with stubbed query vectors and one gated real-model recall test.
- Out of scope: `POST /query` answer generation (deliverable 5); cross-encoder rerank and HyDE (Phase 3 stretch, only if measured recall fails); `DELETE` cascade and vec cleanup (Phase 3); rebuild-vec endpoint or CLI (no rebuild surface in this deliverable — the derived-index principle is honored by hydrating everything from `chunks`); PDF/Word adapters (Phase 2); any frontend changes (chat UI lands in deliverable 5).

## Solution Statement

Retrieval is a deterministic pipeline with one model call: `sanitize query → check_embedding_dim → embed query (query_embed) → BM25 leg + vector leg (over-fetched per-leg LIMITs) → RRF fuse (1-indexed ranks, k=60) → batch-hydrate from chunks → truncate excerpts → return top_k`. SQL lives in `db/chunks.py` (mirroring `db/artifacts.py` ownership of SQL); fusion/sanitization/orchestration lives in `retrieval/search.py` (mirroring the `ingest/pipeline.py` orchestration split). Legs return ordered chunk-ID lists; RRF sees ranks only, never raw scores. Endpoints are sync `def` (sqlite3 + fastembed block → FastAPI threadpool). Tests stub only the query vector; FTS runs for real on tmp DBs.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: Medium
**Primary Systems Affected**: retrieval (`retrieval/search.py`, `retrieval/embedder.py`), chunk repository (`db/chunks.py`), retrieval API router, app router wiring
**Dependencies**: prerequisite deliverables — scaffold (schema, connection helper, config) and source-adapter ingestion (chunks/FTS/vec writes, embedder singleton, test patterns) — already landed (commits `cc01fa7`, `dc0c804`); no new third-party deps (sqlite-vec 0.1.9, fastembed 0.9.1 already pinned in `backend/uv.lock`); fastembed model `BAAI/bge-small-en-v1.5` (~90 MB) downloads once at first real embed if not already cached
**Assumptions**: (validate before/during execution) fastembed 0.9.1 `TextEmbedding.query_embed` accepts a single `str` and yields one vector per call (probe the signature in Task 1 before implementing); `bm25(chunks_fts)` ascending = best-first (SQLite inverted convention); vec0 `MATCH`-with-packed-blob + `ORDER BY distance LIMIT n` without a `k =` constraint is correct on 0.1.9 (already proven in-repo by `test_db_init.py:84-87` — in-repo proof takes precedence over upstream README variants)

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

All paths repo-root-relative:

- `backend/pyproject.toml` (lines 1-40) — Why: pinned deps (add nothing), ruff line-length 100 / py312, pytest config
- `backend/app/main.py` (lines 20-50) — Why: lifespan (DB init + dim guard, already correct — this plan adds no lifespan change) + `include_router(..., prefix="/api/v1")` mount pattern to mirror for the retrieval router
- `backend/app/api/ingest.py` (lines 31, 84-110, 190) — Why: thin-router pattern to mirror — `get_settings()` in handler, pipeline function imported BY NAME as the monkeypatch seam (line 31), blank-content 422 rule (lines 87-89), `EmbeddingDimMismatchError` → 500 mapping (lines 106-110), `span: [s, e]` list shape (line 190)
- `backend/app/api/health.py` (lines 15-16, 34-65) — Why: `router = APIRouter(tags=[...])` + Pydantic response-model structure to mirror
- `backend/app/core/config.py` (lines 14-28) — Why: `Settings` fields (`database_path`, `embedding_model`); routers read settings, library modules take explicit params — add NO new settings in this deliverable (RRF/excerpt/top-k bounds are code constants)
- `backend/app/db/connection.py` (lines 21-70) — Why: ONLY sanctioned DB path — `connect()` (WAL, FKs, vec0 ext) + `check_embedding_dim()`; chunk repository and `hybrid_search` must use these, never raw `sqlite3.connect`
- `backend/app/db/schema.sql` (lines 26-58) — Why: exact `chunks` / external-content `chunks_fts` (`tokenize='porter'`) / `chunks_vec float[384]` DDL the legs query; `chunks.id INTEGER PK` shared with vec0 rowid and FTS rowid by construction
- `backend/app/db/artifacts.py` (lines 50-94) — Why: repository pattern to mirror — explicit `db_path` param, one connection per call closed in `finally`, dataclass row shapes, `with conn:` writes; read path (`list_artifacts`, lines 97-120) shows the SELECT-over-`connect()` idiom the chunk repository copies
- `backend/app/retrieval/embedder.py` (lines 1-45, ALL) — Why: module this plan extends — lazy `get_model()` singleton (lines 27-35), `passage_embed` materialization idiom (line 45), `EmbedFn` alias pattern for the new `QueryEmbedFn`; module docstring (lines 1-8) already reserves `query_embed` for this deliverable
- `backend/app/ingest/pipeline.py` (lines 45-85) — Why: orchestration pattern to mirror — kw-only explicit params, char/blank contract in docstring, `check_embedding_dim` BEFORE the model call (lines 62-64), `functools.partial` default-injection of the real embed function (line 63)
- `backend/tests/test_db_init.py` (lines 19-20, 84-87, 106-112) — Why: THE SQL patterns to mirror verbatim — `struct.pack(f"{n}f", *vec)`, vec KNN `SELECT rowid FROM chunks_vec WHERE embedding MATCH ? ORDER BY distance LIMIT ?` (no `k =` constraint on 0.1.9), FTS `SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?`
- `backend/tests/test_ingest_pipeline.py` (lines 34-42, 180-205, 300-321) — Why: test patterns to mirror — deterministic stub vectors (lines 34-35), tmp-DB `init_db` fixture (lines 38-42), dim-guard-asserts-embed-uncalled (lines 180-205), `TB_REAL_EMBEDDINGS`-gated real-model smoke (lines 300-321)
- `backend/tests/test_ingest_api.py` (lines 23-56) — Why: API-test patterns to mirror — autouse settings isolation (lines 28-42), `_client` helper over tmp DBs (lines 45-55), `_stub` wrapper delegating to the REAL function with forced fake embed (lines 23-25)
- `.agents/plans/phase-1-build-list.md` (deliverable 4, lines 27-31) — Why: binding scope boundaries — retrieval only, top-k inspection endpoint, derived/rebuildable vec, no reranker, no HyDE
- `PRD.md` (§4 Technical hybrid+RRF; §6 Retrieval + "vector index as derived artifact"; §10 Retrieval & Q&A `GET /chunks/{id}` + `POST /query top_k: 8` default; §11 vague-query criterion; §12 Phase 1 gate) — Why: authoritative requirements and acceptance criteria

### New Files to Create

Backend (`backend/`, paths repo-root-relative):

- `backend/app/db/chunks.py` — chunk repository: `ChunkDetail` dataclass, `get_chunks(db_path, ids)` batch hydrate (one connection, dict keyed by id), `search_bm25_ids(db_path, match_expr, limit)` ordered chunk IDs, `search_vector_ids(db_path, query_vec, limit)` ordered chunk IDs
- `backend/app/retrieval/search.py` — `RRF_K = 60`, `EXCERPT_CHARS = 300`, `TOP_K_DEFAULT = 8`, `TOP_K_MAX = 50`, `PER_LEG_MULT = 5`, `PER_LEG_MIN = 50`; `build_fts_match(query) -> str | None`; `per_leg_limit(top_k)`; `rrf_fuse(bm25_ids, vector_ids, *, k, top_k)`; `excerpt_of(text)`; `hybrid_search(*, db_path, query, top_k, embedding_model, embed_fn=None)` returning `list[SearchHit]`
- `backend/app/api/retrieval.py` — thin router: `POST /retrieval/search` (200 `{results: [...]}`), `GET /chunks/{chunk_id}` (200 full chunk, 404 unknown)
- `backend/tests/test_search.py` — pure unit tests (sanitizer, RRF math, excerpt, per-leg formula): no DB, no model, milliseconds
- `backend/tests/test_retrieval.py` — legs + `hybrid_search` integration over tmp DBs (stub query vectors, real FTS) + gated real-model vague-recall test
- `backend/tests/test_retrieval_api.py` — endpoint contracts via TestClient (shapes, top_k behavior, 404/422/500 matrix, OpenAPI presence, empty-DB `[]`)

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [SQLite FTS5 — Full-text Query Syntax](https://www.sqlite.org/fts5.html#full_text_query_syntax)
  - Specific section: §3 — phrase syntax, boolean operators (`AND`/`OR`/`NOT`), prefix (`*`), column filters; anything raw user text can contain that breaks `MATCH`
  - Why: proves raw queries MUST be sanitized — `WHAT'S my name?`, `cat AND dog`, unbalanced quotes are syntax errors or silent mis-parses without quoting
- [SQLite FTS5 — The bm25() function](https://www.sqlite.org/fts5.html#the_bm25_function)
  - Specific section: §5.1.1 — "better matches are numerically SMALLER"; `ORDER BY bm25(ft)` ascending = best first
  - Why: the BM25 leg's `ORDER BY` direction; `DESC` here silently inverts ranking — the most likely silent-corruption bug in this deliverable
- [SQLite FTS5 — External Content Tables](https://www.sqlite.org/fts5.html#external_content_tables)
  - Specific section: §4.4.3 — FTS `rowid` aliases the content-table rowid (`content_rowid='id'`)
  - Why: confirms `SELECT rowid FROM chunks_fts ...` returns `chunks.id` directly, no join needed for the ID list
- [SQLite FTS5 — Porter Tokenizer](https://www.sqlite.org/fts5.html#porter_tokenizer)
  - Specific section: §4.3.3 — stemming applies to indexed text AND query tokens symmetrically
  - Why: sanitized plain tokens get stemmed consistently with the indexed chunks — no manual stemming in `build_fts_match`
- [sqlite-vec](https://github.com/asg017/sqlite-vec)
  - Specific section: README sample usage — `WHERE embedding MATCH ? ORDER BY distance LIMIT ?` with a bound query vector
  - Why: vec-leg SQL shape; in-repo proof (`test_db_init.py:84-87`, passing on pinned 0.1.9) takes precedence over README variants (notably: NO `k =` constraint in our queries)
- [FastEmbed — Retrieval with FastEmbed](https://qdrant.github.io/fastembed/qdrant/Retrieval_with_FastEmbed/)
  - Specific section: "Prefer using `query_embed` for queries and `passage_embed` for documents"
  - Why: `embed_query` MUST use `query_embed` (BGE asymmetric retrieval); documents already use `passage_embed` — mixing them degrades recall
- [Reciprocal Rank Fusion explainer](https://spice.ai/learn/reciprocal-rank-fusion)
  - Specific section: `RRF(d) = Σ 1/(k + rank_i(d))`, `k = 60` standard (Cormack, Clarke & Buettcher, SIGIR 2009), 1-indexed ranks, absent-from-list contributes nothing
  - Why: normative formula for `rrf_fuse` — rank-only (raw BM25/vector scores never mixed), `k=60`, missing-leg → `None` rank + single-term score

### Patterns to Follow

**Naming Conventions:**

Backend `snake_case` modules/functions, `PascalCase` models/classes (AGENTS.md). Router module `backend/app/api/retrieval.py` with module-level `router = APIRouter(tags=["retrieval"])` mirroring `health.py:15`. Repository functions verb-led (`get_chunks`, `search_bm25_ids`, `search_vector_ids`) mirroring `connect`/`init_db`/`store_artifact`. Pure helpers noun-led (`build_fts_match`, `rrf_fuse`, `excerpt_of`, `per_leg_limit`).

**Error Handling:**

FastAPI-default `{"detail": ...}` shape (PRD §10). Client errors via `HTTPException`: 422 blank query (JSON path — mirrors ingest's JSON-blank rule) and 422 Pydantic range violations (`top_k` outside 1..50, non-int chunk id); 404 unknown chunk id (`"chunk not found"`, mirroring `"artifact not found"`). Server faults with cause, never swallowed: `EmbeddingDimMismatchError` → 500 (mirror `ingest.py:106-110`), wrong-dim query vector `ValueError` → 500. FTS-hostile input (quotes, operators, `*`) is sanitized, NOT rejected — it returns 200 with whatever the legs find. Empty DB returns 200 `{results: []}`, never 404.

**Settings access:**

Routers call `get_settings()` inside the handler (mirror `health.py:43`); library modules (`chunks.py`, `search.py`, `embedder.py`) take explicit params and NEVER import `app.core.config`. No new env vars: RRF/excerpt/top-k bounds are module constants in `search.py`; the router imports `TOP_K_DEFAULT`/`TOP_K_MAX` from there for the Pydantic field (router→retrieval edge is fine — no cycle, since `search.py` never imports the router).

**DB access:**

`connect()` from `app.db.connection` is the only path; legs and hydrate each open exactly one connection per call, closed in `finally` (mirror `artifacts.py:97-120`). Mirror the vec query EXACTLY (`test_db_init.py:84-87`): `struct.pack(f"{len(vec)}f", *vec)` bound param, `WHERE embedding MATCH ? ORDER BY distance LIMIT ?`. BM25 leg: `SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?` — ascending (lower bm25 = better). Hydrate is ONE `SELECT ... WHERE id IN (...)` per search (never N connections for top_k rows); empty ID list short-circuits to `{}` without querying.

**Logging Pattern:**

Module `logger = logging.getLogger(__name__)`; `logger.info` one-line search summary (result count, top_k, per-leg hit counts — never the query text at info... actually the query is user input typed for search, low-sensitivity, but stay consistent with ingest's no-content rule: log lengths/ids only); `logger.warning` on hydrate drops (leg returned an ID with no chunk row — impossible without concurrent delete in MVP single-writer, so warn loudly) and on blank-query 422s. Mirror `connection.py:42-48` (no secrets/content in logs).

**Sync-endpoint rule:**

Search endpoints are sync `def` (not `async def`) because sqlite3 + fastembed are blocking/CPU-bound — FastAPI runs them in the threadpool. No `await` anywhere in the retrieval path.

**Test-injection rule:**

`hybrid_search` takes `embed_fn: QueryEmbedFn | None = None` (`QueryEmbedFn = Callable[[str], list[float]]`, single query → single vector — distinct from ingestion's list-based `EmbedFn`); default binds the real `embed_query` via `functools.partial` (mirror `pipeline.py:63`). The router imports `hybrid_search` BY NAME so API tests `monkeypatch.setattr("app.api.retrieval.hybrid_search", stub)` with a wrapper delegating to the real function but forcing a fake `embed_fn` (mirror `test_ingest_api.py:23-25`). One gated real-model recall test (`TB_REAL_EMBEDDINGS=1`, skip otherwise) proves true vague-query recall end to end.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

Query-side embedding plus the chunk read path — no ranking yet. `embed_query` completes the embedder's asymmetric pair (documents already embed via `passage_embed`); `db/chunks.py` adds the three read primitives every later phase builds on (BM25 IDs, vector IDs, batch hydrate). Both fully testable without ranking or HTTP.

**Tasks:**

- UPDATE `backend/app/retrieval/embedder.py` — `QueryEmbedFn` alias + `embed_query(text, model_name)` via `query_embed`, blank → `ValueError`
- CREATE `backend/app/db/chunks.py` — `ChunkDetail`, `get_chunks` batch hydrate, `search_bm25_ids`, `search_vector_ids`

### Phase 2: Core Implementation

Pure ranking core plus orchestration. The sanitizer makes arbitrary user text FTS-safe; RRF fuses two rank lists with textbook math; `hybrid_search` composes dim-guard → embed → legs → fuse → hydrate → excerpt. Pure units land with the module so fusion math is pinned before any HTTP exists.

**Tasks:**

- CREATE `backend/app/retrieval/search.py` — constants, `build_fts_match`, `per_leg_limit`, `rrf_fuse`, `excerpt_of`, `SearchHit`, `hybrid_search`
- CREATE `backend/tests/test_search.py` — sanitizer matrix, RRF exact-math/1-index/tie-break/truncation, excerpt boundaries, per-leg formula

### Phase 3: Integration

Thin HTTP surface plus app wiring. The router validates (`min_length=1` + strip check → 422; `top_k` 1..50) and maps domain errors to status codes; `main.py` mounts the router under `/api/v1`. No lifespan change — DB init and the boot-time dim guard already exist.

**Tasks:**

- CREATE `backend/app/api/retrieval.py` — Pydantic request/response models mirroring the PRD §10 citation shape + scores; two endpoints; domain-error → `HTTPException` mapping
- UPDATE `backend/app/main.py` — `include_router(retrieval_router, prefix="/api/v1")` next to the ingest mount; no other changes

### Phase 4: Testing & Validation

Contract + integration coverage with stubbed query vectors and real FTS, then full-gate validation. Every behavior gets a test: leg ordering, fusion, graceful degradation (empty DB, no-token query, FTS-miss), top_k enforcement, hydrate order/excerpts, dim-guard-before-embed, defensive hydrate-drop, endpoint shapes and the full status matrix, plus one gated real-model vague-recall test that previews the Phase 1 gate.

**Tasks:**

- CREATE `backend/tests/test_retrieval.py` — leg + hybrid integration over tmp DBs with one-hot stub vectors (deterministic nearest-neighbor), degradation cases, dim-guard/wrong-dim errors, hydrate-drop defense, gated vague-recall test
- CREATE `backend/tests/test_retrieval_api.py` — TestClient contracts with router-level `hybrid_search` stub wrapper (real search + legs + FTS, fake query vector): shapes, top_k default/boundaries, blank/injection queries, empty-DB `[]`, chunk round-trip, 404/422/500 matrix, OpenAPI presence
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

### UPDATE backend/app/retrieval/embedder.py

- **IMPLEMENT**: Step 0 (probe, read-only): run `uv run python -c "import inspect; from fastembed import TextEmbedding; print(inspect.signature(TextEmbedding.query_embed))"` and confirm it accepts a single `str` query — implement the call shape the INSTALLED fastembed 0.9.1 shows; if it takes only an iterable, wrap as `query_embed([text])`. Then ADD `QueryEmbedFn = Callable[[str], list[float]]` (single query → single vector; do NOT reuse list-based `EmbedFn`) and `embed_query(text: str, model_name: str = EMBEDDING_MODEL_DEFAULT) -> list[float]` — `text.strip() == ""` → `raise ValueError("query must not be blank")` (router rejects blank earlier with 422, so this is defense-in-depth); else `model = get_model(model_name)` and materialize the ONE yielded vector via `next(model.query_embed(text))` converted with `list(map(float, vec))`. Update the module docstring's deliverable-4 forward reference to state `embed_query` is now implemented. No other changes (singleton, `embed_passages`, constants untouched).
- **PATTERN**: MIRROR `embed_passages` (lines 38-45) — same singleton access, same `list(map(float, ...))` numpy→list conversion, same default-model param idiom
- **IMPORTS**: none new (`Callable` already imported for `EmbedFn`)
- **GOTCHA**: `query_embed` returns a GENERATOR — `next()` it, never `list(...)[0]`... either materializes, but `next()` documents single-vector intent; documents MUST stay on `passage_embed` and queries on `query_embed` (BGE asymmetric prefixes — mixing degrades recall); first real call downloads ~90 MB — unit tests must NEVER reach this (search tests always pass stubs); the call-shape probe result (str vs list) MUST be recorded in the execution report
- **VALIDATE**: `cd backend && uv run ruff check app/retrieval/embedder.py && uv run ruff format --check app/retrieval/embedder.py && uv run python -c "import app.retrieval.embedder; print('import ok')"`

### CREATE backend/app/db/chunks.py

- **IMPLEMENT**: `ChunkDetail` dataclass (`id: int`, `artifact_id: str`, `chunk_idx: int`, `span_start: int`, `span_end: int`, `text: str`); `get_chunks(db_path: str, ids: list[int]) -> dict[int, ChunkDetail` — `[]` in → `{}` out WITHOUT opening a connection; else one `connect(db_path)`, single `SELECT id, artifact_id, chunk_idx, span_start, span_end, text FROM chunks WHERE id IN ({placeholders})` with `?` bound params (placeholders built as `",".join("?" * len(ids))`, never f-string-interpolated IDs), dict keyed by `id`, close in `finally`; `search_bm25_ids(db_path: str, match_expr: str, limit: int) -> list[int]` — one connection, `SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?` with `(match_expr, limit)` bound, return `[r[0] for r in rows]` (best-first: lower bm25 sorts first ascending); `search_vector_ids(db_path: str, query_vec: list[float], limit: int) -> list[int]` — one connection, `SELECT rowid FROM chunks_vec WHERE embedding MATCH ? ORDER BY distance LIMIT ?` with `(struct.pack(f"{len(query_vec)}f", *query_vec), limit)` bound, return rowids best-first. All functions explicit-params, no settings import, no logging except none (repository stays quiet; orchestration logs).
- **PATTERN**: MIRROR `backend/app/db/artifacts.py:97-120` (SELECT-over-`connect()` + `finally: conn.close()` + dataclass row mapping); MIRROR `backend/tests/test_db_init.py:84-87` (vec KNN SQL verbatim — NO `k =` constraint) and `:106-112` (FTS MATCH SQL + `bm25()` ordering added per the FTS5 §5.1.1 doc reference)
- **IMPORTS**: `from __future__ import annotations`, `struct`, `dataclasses.dataclass`, `from app.db.connection import connect`
- **GOTCHA**: vec0 rowid == `chunks.id` AND FTS rowid == `chunks.id` by construction — return rowids as chunk IDs with NO join; `ORDER BY bm25(...)` MUST be ascending (default) — `DESC` silently inverts ranking (SQLite's lower-is-better convention); `LIMIT ?` as a bound param (SQLite supports bound LIMIT); `IN (...)` with zero IDs is a syntax error — hence the empty short-circuit; `struct.pack` format `f` = float32 MUST match vec0 `float[384]` (mirror `artifacts.py:89`); every connection closed in `finally`
- **VALIDATE**: `cd backend && uv run ruff check app/db/chunks.py && uv run ruff format --check app/db/chunks.py`

### CREATE backend/app/retrieval/search.py

- **IMPLEMENT**: constants `RRF_K = 60` (Cormack et al. SIGIR 2009 standard), `EXCERPT_CHARS = 300`, `TOP_K_DEFAULT = 8` (mirrors PRD §10 `POST /query top_k: 8`), `TOP_K_MAX = 50`, `PER_LEG_MULT = 5`, `PER_LEG_MIN = 50`; `RrfHit` dataclass (`chunk_id: int`, `score: float`, `bm25_rank: int | None`, `vector_rank: int | None`); `SearchHit` dataclass (`chunk_id: int`, `artifact_id: str`, `span_start: int`, `span_end: int`, `excerpt: str`, `rrf_score: float`, `bm25_rank: int | None`, `vector_rank: int | None`); `build_fts_match(query: str) -> str | None` — `tokens = [t for t in _TOKEN_RE.findall(query) if any(c.isalnum() for c in t)]` with `_TOKEN_RE = re.compile(r"\w+", re.UNICODE)`; `[]` → `None` (caller skips the BM25 leg); else `" OR ".join(f'"{t}"' for t in tokens)` — `\w` tokens cannot contain `"` so quoting is trivially injection-proof (document this invariant); OR (not AND) so vague multi-term queries degrade gracefully and BM25's own term-weighting does the ranking; `per_leg_limit(top_k: int) -> int` — `max(top_k * PER_LEG_MULT, PER_LEG_MIN)`; `rrf_fuse(bm25_ids: list[int], vector_ids: list[int], *, k: int = RRF_K, top_k: int) -> list[RrfHit]` — 1-indexed rank maps over each list (legs return unique IDs by construction), `score = Σ 1.0/(k + rank)` over legs containing the ID, `None` rank for the absent leg, sort by `(-score, chunk_id)` (deterministic tie-break), truncate to `top_k`; `excerpt_of(text: str, limit: int = EXCERPT_CHARS) -> str` — `text if len(text) <= limit else text[:limit] + "..."` (plain slice, `"..."` ASCII dots); `hybrid_search(*, db_path: str, query: str, top_k: int, embedding_model: str, embed_fn: QueryEmbedFn | None = None) -> list[SearchHit` — contract (docstring): non-blank `query`, `1 <= top_k <= TOP_K_MAX` (router enforces; library assumes valid); (1) `check_embedding_dim(db_path, embedding_model, EMBEDDING_DIM)` fail-fast BEFORE embedding; (2) `qvec = (embed_fn or functools.partial(embed_query, model_name=embedding_model))(query)`, `len(qvec) != EMBEDDING_DIM` → `raise ValueError` (server fault, router maps to 500); (3) `leg = per_leg_limit(top_k)`; (4) `match = build_fts_match(query)`; `bm25_ids = search_bm25_ids(db_path, match, leg) if match else []`; (5) `vector_ids = search_vector_ids(db_path, qvec, leg)`; (6) `fused = rrf_fuse(bm25_ids, vector_ids, top_k=top_k)`; (7) `hydrated = get_chunks(db_path, [h.chunk_id for h in fused])`, drop IDs with no row with `logger.warning` (defensive — impossible in single-writer MVP without concurrent delete); (8) build `SearchHit`s in fused order with `excerpt_of(detail.text)`; (9) `logger.info` one-line summary (counts only, no query text); return list.
- **PATTERN**: orchestration MIRROR `backend/app/ingest/pipeline.py:45-85` (kw-only explicit params, docstring contract, dim-guard-before-model, `functools.partial` default injection); pure-helper style MIRROR `backend/app/ingest/chunker.py` (stdlib-only, deterministic, no app imports for `build_fts_match`/`rrf_fuse`/`excerpt_of`/`per_leg_limit`)
- **IMPORTS**: `from __future__ import annotations`, `functools`, `logging`, `re`, `dataclasses.dataclass`, `from app.db.chunks import get_chunks, search_bm25_ids, search_vector_ids`, `from app.db.connection import check_embedding_dim`, `from app.retrieval.embedder import EMBEDDING_DIM, QueryEmbedFn, embed_query`
- **GOTCHA**: ranks are 1-INDEXED (first = rank 1 → `1/61`; 0-indexed would give `1/60` and silently reweight everything — pinned by an explicit regression test); RRF is rank-only — raw `bm25()`/`distance` values must NEVER enter the score (incomparable scales); every returned field hydrates from canonical `chunks` (vec/FTS supply ordering only — the derived-index principle); `functools.partial(embed_query, model_name=...)` binds the model name so stubs keep the `(str) -> vec` shape; `re.UNICODE` is default for `str` patterns but state it explicitly for readability; `logger.warning` (not silent skip) on hydrate drops
- **VALIDATE**: `cd backend && uv run ruff check app/retrieval/search.py && uv run ruff format --check app/retrieval/search.py`

### CREATE backend/tests/test_search.py

- **IMPLEMENT**: pure unit tests, no DB/model/settings imports — sanitizer: (1) `"lazy loading fix"` → `'"lazy" OR "loading" OR "fix"'` exact; (2) injection matrix — each of `cat AND dog`, `a OR b NOT c`, `"unbalanced quote`, `prefix*`, `col:term`, `NEAR(foo bar)`, `(a b)`, `^ sheer "quotes" \\ backslash` produces output containing NO bare FTS operator (assert every token occurrence is inside double quotes; assert output parses by feeding it to a real FTS `MATCH` on a 1-row tmp DB? NO — keep this file pure; FTS acceptance of sanitizer output is covered in `test_retrieval.py` test 6); (3) `""`, `"   "`, `"???"`, `"___"`, `"... !!!"` → `None`; (4) unicode `"café naïve 日本語"` → three quoted tokens preserved verbatim; (5) case preserved (`"SelectInLoad"` stays as-is — FTS folds at match time); RRF: (6) exact math — `rrf_fuse([1], [1], top_k=1)` → `[(1, 2/61, 1, 1)]` with `pytest.approx(2/61)`; (7) single-leg doc — `rrf_fuse([1], [], top_k=5)` → `[(1, 1/61, 1, None)]`; (8) 1-INDEX REGRESSION — first-position score equals `1/(60+1)`, explicitly assert `!= 1/60`; (9) both-legs-wins — `bm25=[1,2], vec=[2]` with k=60: doc 2 (`1/62+1/61`) outranks doc 1 (`1/61`)... wait compute: doc1 = 1/61 ≈ .01639, doc2 = 1/62+1/61 ≈ .03279 → order [2,1] — assert; (10) tie-break — `bm25=[1,2], vec=[2,1]` → identical scores → order `[1, 2]` (lower id first); (11) truncation — 5 fused docs, `top_k=2` → best 2 in order; (12) empties — `([],[])` → `[]`, one-empty ranks the other alone; (13) `k` param honored — `k=0`: rank-1 score `1.0`; excerpt: (14) short text unchanged; (15) exactly-300-char text unchanged (no dots); (16) 301-char text → `text[:300] + "..."` (303 chars total); per-leg: (17) `per_leg_limit(8) == 50`, `per_leg_limit(1) == 50`, `per_leg_limit(50) == 250`; (18) determinism — repeat `rrf_fuse` + `build_fts_match` calls identical.
- **PATTERN**: plain pytest functions — MIRROR `backend/tests/test_chunker.py` (small asserts, exact-value expectations, no fixtures, no I/O)
- **IMPORTS**: `pytest`, `from app.retrieval.search import (EXCERPT_CHARS, RRF_K, build_fts_match, excerpt_of, per_leg_limit, rrf_fuse)`
- **GOTCHA**: this file must run in milliseconds — NO `init_db`, NO `connect`, NO embedder import (dependency order: pure math only); float compares via `pytest.approx`; test 9's expected order MUST be hand-computed in a comment (reviewers check the arithmetic); injection test asserts quoting structure, NOT FTS acceptance (acceptance needs a DB → belongs in `test_retrieval.py`)
- **VALIDATE**: `cd backend && uv run pytest tests/test_search.py -q`

### CREATE backend/tests/test_retrieval.py

- **IMPLEMENT**: fixtures — `db_path(tmp_path)` with `init_db()` (MIRROR `test_ingest_pipeline.py:38-42`); passage stub `one_hot(texts)` mapping chunk index → unit vector (`vec[i % DIM] = 1.0`, zeros elsewhere — deterministic nearest-neighbor: query with chunk j's vector ranks chunk j first at distance 0); seed helper `seed(db_path, [(title, content), ...])` via REAL `ingest_source` + `one_hot` (MIRROR pipeline-test seeding); query stub factory `qmatch(j)` returning chunk j's one-hot vector; tests — legs: (1) BM25 orders exact-term chunk first (3 seeded notes with distinctive terms `selectinload`/`p99`/`sourdough`, `search_bm25_ids("selectinload", 10)[0]` == selectinload chunk); (2) vector orders stub-nearest first (`search_vector_ids(db, qmatch(1), 10)[0]` == chunk 1); (3) BM25 `LIMIT` honored (limit=1 → 1 row); (4) sanitizer output ACCEPTED by real FTS — every injection string from `test_search.py` test 2, passed through `build_fts_match` (or skipped when `None`), executes `search_bm25_ids` WITHOUT raising (`sqlite3.OperationalError` = failure); hybrid: (5) both-legs-agree wins — query `"selectinload"` + `qmatch(selectinload_idx)` → fused[0] is the selectinload chunk with both ranks non-`None`; (6) fusion math end-to-end — craft 2 chunks where chunk A is BM25-1st/vector-2nd and chunk B is BM25-miss/vector-1st, assert fused order matches hand-computed RRF (comment the arithmetic); (7) top_k truncation (`top_k=2` over 5 chunks → 2 hits, best first); (8) empty DB → `[]`; (9) FTS-miss degrades — query `"zzzqqq nonexistent terms"` (no corpus match) + valid stub vector → results carry `bm25_rank=None`, `vector_rank` set; (10) no-token query `"???"` → vector-only path, no exception, all `bm25_rank=None`; hydration: (11) fused order preserved + spans/excerpts exact (`detail.text[:300]` semantics incl. a >300-char chunk asserting `"..."` suffix); (12) per-leg over-fetch — graded (non-one-hot) stubs place the target deterministically at vector rank 4: seed 5 one-chunk notes where only the 4th contains the query term `selectinload`; passage stub is a stateful counter yielding `[[float(n)] + [0.0]*383]` per chunk in seed order (n = 0..4) and the query stub returns `[0.0]*384`, so vector distances ascend strictly with seed order and the target sits at vector rank 4; `top_k=2` must still return the target with `bm25_rank == 1` AND `vector_rank == 4` — a leg limit equal to `top_k` would truncate the vector leg to ranks 1-2, yielding `vector_rank=None` and failing the assertion (proves legs fetch deeper than top_k); errors: (13) tampered `meta.embedding_model` → `EmbeddingDimMismatchError` WITHOUT calling `embed_fn` (spy flag, MIRROR `test_ingest_pipeline.py:180-205`); (14) stub returning 128-dim vector → `ValueError` before any leg query; (15) hydrate-drop defense — monkeypatch `app.retrieval.search.search_vector_ids` to return `[999999]` (+ `search_bm25_ids` → `[]`) → `hybrid_search` returns `[]` (dropped with warning, no `KeyError`); gated: (16) `@pytest.mark.skipif(os.environ.get("TB_REAL_EMBEDDINGS") != "1")` REAL-model vague recall — seed 4 notes (SQLAlchemy lazy-loading fix via selectinload; Postgres index tuning p99; eight-step RAG explainer note; sourdough recipe), `embed_fn=None`, vague query `"my database query was slow because related rows loaded one by one — what was the fix"` → SQLAlchemy chunk in top 3 (assert on artifact title of a top-3 hit). ONE gated test only.
- **PATTERN**: tmp-DB + stub vectors — MIRROR `test_ingest_pipeline.py` (real SQLite incl. real FTS5, fake vectors); monkeypatch-namespace style MIRROR `test_ingest_api.py:54` (patch `app.retrieval.search.<name>` since `search.py` imports the leg functions BY NAME)
- **IMPORTS**: `os`, `struct` (only if asserting packed bytes — avoid; assert IDs), `pytest`, `from app.db.connection import connect, init_db`, `from app.db.chunks import search_bm25_ids, search_vector_ids`, `from app.ingest.pipeline import ingest_source`, `from app.retrieval.search import build_fts_match, hybrid_search`
- **GOTCHA**: one-hot stub needs `i % DIM` guard past 384 chunks (tests seed ≤ 60 — never hit, but no `IndexError`); seed contents MUST contain the BM25 probe terms verbatim (porter stems `loading`→`load` consistently on both sides — assert on distinctive un-stemmed nouns like `selectinload`/`sourdough` to avoid stemmer surprises); test 6's hand computation MUST appear as a comment; test 15 patches the names IN THE `search` NAMESPACE (by-name import — patching `app.db.chunks.search_vector_ids` would NOT intercept); gated test seeds via `embed_fn=None` (real `passage_embed`) AND queries via `embed_fn=None` (real `query_embed`) — full true path, slow, network + ~90 MB model on first run
- **VALIDATE**: `cd backend && uv run pytest tests/test_retrieval.py -q`

### CREATE backend/app/api/retrieval.py

- **IMPLEMENT**: `router = APIRouter(tags=["retrieval"])`; Pydantic models — `SearchRequest (query: str = Field(min_length=1), top_k: int = Field(default=TOP_K_DEFAULT, ge=1, le=TOP_K_MAX))`, `SearchHitOut (chunk_id: int, artifact_id: str, span: list[int], excerpt: str, rrf_score: float, bm25_rank: int | None, vector_rank: int | None)`, `SearchResponse (results: list[SearchHitOut])`, `ChunkOut (id: int, artifact_id: str, chunk_idx: int, span: list[int], text: str)`; `POST /retrieval/search` (status 200, sync `def`): `query.strip() == ""` → 422 `"query must not be blank"` (mirror ingest JSON-blank rule); `settings = get_settings()` → `hybrid_search(db_path=settings.database_path, query=body.query, top_k=body.top_k, embedding_model=settings.embedding_model, embed_fn=None)` mapping `EmbeddingDimMismatchError` AND `ValueError` (wrong-dim vectors — server fault) → 500 with cause; map hits to `SearchHitOut(span=[h.span_start, h.span_end])`; `GET /chunks/{chunk_id}` (status 200, sync `def`, `chunk_id: int`): `get_chunks(settings.database_path, [chunk_id]).get(chunk_id)` → `None` → 404 `"chunk not found"`; else `ChunkOut` with full `text`. Module docstring documents the test seam: `hybrid_search` imported BY NAME so tests `monkeypatch.setattr("app.api.retrieval.hybrid_search", stub)` (mirror `ingest.py` docstring lines 7-11).
- **PATTERN**: thin router — MIRROR `backend/app/api/ingest.py:84-110` (handler shape, `get_settings()` in handler, by-name import seam, 422/500 mapping); response models MIRROR PRD §10 citation shape `{chunk_id, artifact_id, span: [s, e], excerpt}` + score/rank fields; 404 body MIRROR `ingest.py:179` (`"artifact not found"` → `"chunk not found"`)
- **IMPORTS**: `from __future__ import annotations`, `logging`, `fastapi (APIRouter, HTTPException, status)`, `pydantic (BaseModel, Field)`, `from app.core.config import get_settings`, `from app.db.chunks import get_chunks`, `from app.db.connection import EmbeddingDimMismatchError`, `from app.retrieval.search import TOP_K_DEFAULT, TOP_K_MAX, hybrid_search`
- **GOTCHA**: `min_length=1` yields 422 for `""` (FastAPI default — accept); whitespace-only passes it — hence the explicit strip check → 422 (NOT 400: JSON path = schema problem, mirror ingest's 422-vs-400 split); `top_k` bounds enforced by Pydantic (`ge`/`le` → 422, no manual check); `ValueError` → 500 (a wrong-dim vector can only come from model/config drift, never from user input); response `span` is a `[s, e]` LIST (JSON-native, matches PRD §10 citation shape deliverable 5 reuses); NEVER log query text or excerpts — log counts/ids only; sync `def` (threadpool — no `await`)
- **VALIDATE**: `cd backend && uv run ruff check app/api/retrieval.py && uv run ruff format --check app/api/retrieval.py`

### UPDATE backend/app/main.py

- **IMPLEMENT**: ADD `from app.api.retrieval import router as retrieval_router` + `app.include_router(retrieval_router, prefix="/api/v1")` next to the ingest mount (order: health, ingest, retrieval — then liveness). NOTHING else: no lifespan change (DB init + boot dim-guard already cover retrieval), no middleware change, no settings change.
- **PATTERN**: MIRROR existing mount lines (`main.py:47-49`)
- **IMPORTS**: ADD `from app.api.retrieval import router as retrieval_router` only
- **GOTCHA**: circular-import check — `app.api.retrieval` → `search` → `db.chunks`/`embedder` must not import `app.main` (they don't — verify by the import in VALIDATE); bare `TestClient(create_app())` does NOT run lifespan (unchanged behavior — retrieval tests seed tmp DBs explicitly like ingest tests)
- **VALIDATE**: `cd backend && uv run ruff check app/main.py && uv run ruff format --check app/main.py && uv run pytest tests/test_app_boot.py -q`

### CREATE backend/tests/test_retrieval_api.py

- **IMPLEMENT**: fixtures — autouse `_isolated_settings` EXACT mirror of `test_ingest_api.py:28-42` (cache clear + env scrub, patching `app.api.retrieval.get_settings` AND `app.main.get_settings` to `Settings(_env_file=None)` so lifespan — if ever entered — also hits tmp); `_client(monkeypatch, tmp_path, seed: list[tuple[str, str]])` helper: `init_db(tmpdb)`, `DATABASE_PATH=tmpdb` env, seed DIRECTLY via real `ingest_source(..., embed_fn=one_hot)` (bypasses HTTP — keeps passage vectors stubbed; document why: POST-seeding would invoke real fastembed), monkeypatch `app.api.retrieval.hybrid_search` with `_stub` wrapper (`def _stub(*a, **k): k["embed_fn"] = fake_query; return real_hybrid_search(*a, **k)`, MIRROR `test_ingest_api.py:23-25`), return `TestClient(create_app())`; `fake_query(text)` returns one-hot vector for chunk index 0 (fixed target — ranking assertions live in `test_retrieval.py`; here assert shapes/counts/codes); tests — (1) POST search → 200, `results` list, first hit has EXACT keys `{chunk_id, artifact_id, span, excerpt, rrf_score, bm25_rank, vector_rank}` with `span` a 2-int list; (2) top_k default — seed 10 one-chunk notes → 8 results (TOP_K_DEFAULT); (3) explicit `top_k=2` → 2; (4) `top_k` 0 / 51 / -1 → 422; `top_k=50` → 200 (upper boundary); (5) `""` → 422 (Pydantic), `"   "` → 422 (strip rule); (6) injection queries (`'" OR "1"="1'`, `'*'`, `'AND NOT ('`) → 200 with a `results` list (never 500); (7) empty DB (seed=[]) → 200 `{results: []}`; (8) GET chunk round-trip — created id → 200, `text`/`span`/`chunk_idx`/`artifact_id` exact, all keys `{id, artifact_id, chunk_idx, span, text}`; (9) unknown chunk id → 404 `{"detail": "chunk not found"}` exact body; non-int id (`/chunks/abc`) → 422; (10) OpenAPI contains `/api/v1/retrieval/search` + `/api/v1/chunks/{chunk_id}`; (11) dim mismatch → 500 — tamper `meta.embedding_model` AFTER client creation, POST search → 500 with cause in `detail` (proves router mapping; search-level uncalled-embed proof lives in `test_retrieval.py` test 13).
- **PATTERN**: settings isolation + `_stub` wrapper + TestClient — MIRROR `test_ingest_api.py:23-56` line-for-line where applicable; 404-body exact-match MIRROR `test_ingest_api.py:218-222`
- **IMPORTS**: `pytest`, `fastapi.testclient.TestClient`, `from app.core.config import Settings, get_settings`, `from app.db.connection import connect, init_db`, `from app.main import create_app`, `import app.retrieval.search as search_mod` (real-function reference), `from app.ingest.pipeline import ingest_source` (direct seeding)
- **GOTCHA**: seed via DIRECT `ingest_source` call (stubbed), NOT via POST (real model) — the one deliberate HTTP bypass, documented in the helper; `_stub` signature MUST be `(*a, **k)` passthrough setting `k["embed_fn"]` (router's exact kwargs); lifespan never entered (bare TestClient) so test 11's post-creation tamper persists to request time; `fake_query` takes `str` (QueryEmbedFn shape) — NOT a list (EmbedFn shape) — the two aliases differ; NEVER let tests hit real fastembed (no-network guarantee) except the gated test in `test_retrieval.py`
- **VALIDATE**: `cd backend && uv run pytest tests/test_retrieval_api.py -q`

---

## TESTING STRATEGY

Backend `pytest` only (no frontend changes). Pure ranking math gets exact-value unit tests; SQL legs run against real SQLite (real FTS5 + real vec0, stub vectors); HTTP gets contract tests with a router-level stub wrapper. All tests offline-safe by default except one gated recall test.

### Unit Tests

`tests/test_search.py` — pure-function coverage, no fixtures: sanitizer exact-output (test 1), injection-structure matrix (test 2 — quoting, not FTS acceptance), blank/punctuation/underscore-only → `None` (test 3), unicode preservation (test 4), case preservation (test 5); RRF exact math incl. `2/61` two-leg and `1/61` single-leg scores (tests 6-7), 1-index regression (`1/61`, never `1/60` — test 8), both-legs-wins ordering with hand-computed arithmetic in comments (test 9), deterministic id-asc tie-break (test 10), truncation (test 11), empty inputs (test 12), `k` param (test 13); excerpt passthrough/exact-boundary/truncation (tests 14-16); per-leg formula boundaries (test 17); determinism (test 18). Must run in milliseconds.

### Integration Tests

`tests/test_retrieval.py` — real SQLite tmp DBs (real FTS5 + vec0), REAL `ingest_source` with one-hot stub passage vectors, stub query vectors: BM25 best-first + LIMIT (tests 1, 3), vector nearest-first (test 2), sanitizer-output FTS acceptance for every injection string (test 4 — `OperationalError` = failure), fused agreement (test 5), end-to-end fusion math with commented arithmetic (test 6), top_k truncation (test 7), empty DB (test 8), FTS-miss graceful degradation with `None` ranks (test 9), no-token vector-only path (test 10), hydrate order + span/excerpt exactness incl. `"..."` case (test 11), per-leg over-fetch via graded stubs asserting `bm25_rank == 1` and `vector_rank == 4` (test 12 — fails if legs were truncated to `top_k`), dim-guard-before-embed with uncalled spy (test 13), wrong-dim `ValueError` (test 14), bogus-ID hydrate drop (test 15). Gated real-model vague-recall test (test 16, `TB_REAL_EMBEDDINGS=1`) — the Phase 1 gate preview: vague description retrieves the SQLAlchemy passage in top 3.

`tests/test_retrieval_api.py` — TestClient over tmp DBs seeded in-process (stub passage vectors), router-level `hybrid_search` stub wrapper (real search + legs + FTS, fake query vector): result-shape exact keys (test 1), default/explicit/boundary top_k (tests 2-4), blank matrix (test 5), injection → 200 (test 6), empty-DB `[]` (test 7), chunk round-trip + key shape (test 8), 404 exact body + non-int 422 (test 9), OpenAPI paths (test 10), tampered-meta → 500 with cause (test 11).

### Edge Cases

- Blank vs whitespace-only query (search test 3 → `None`; API tests 5 → 422 both; embedder `ValueError` defense-in-depth)
- FTS-hostile input: operators/quotes/star/parens/colon/caret (search test 2 structure; retrieval test 4 acceptance; API test 6 → 200)
- No-token queries (`"???"`) → BM25 leg skipped, vector-only fusion (retrieval test 10)
- FTS total-miss (`"zzzqqq..."`) → `bm25_rank=None`, vector ranks carry (retrieval test 9)
- Empty database → `[]`, 200 (retrieval test 8; API test 7)
- `top_k` boundaries: 1, 8 (default), 50 (max → 200), 0/51/-1 (→ 422) (API tests 2-4; retrieval test 7)
- Excerpt exactly 300 chars (no dots) vs 301 (dots) (search tests 15-16; retrieval test 11)
- RRF ties across legs → lower chunk id first, deterministic (search test 10)
- 1-indexed ranks — `1/61` not `1/60` (search test 8 regression)
- Unicode queries (search test 4 — preserved tokens; retrieval degrades gracefully, no crash assertions on CJK recall — BGE-small + porter are English-biased, out of scope)
- Tampered `meta` → fail fast before embedding (retrieval test 13 spy; API test 11 → 500)
- Bogus leg IDs → warned + dropped, never `KeyError` (retrieval test 15)
- Unknown chunk id → 404 exact body; non-int → 422 (API test 9)

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
cd backend && uv run pytest tests/test_search.py -q
```
Expected: exit 0, `18 passed` (all pure-unit tests, zero failures/skips; if the executor splits/combines asserts, the signal is "every test in the file passes, zero skipped" — update this line with the final count)

### Level 3: Integration Tests

```bash
cd backend && uv run pytest tests/test_retrieval.py tests/test_retrieval_api.py -q
```
Expected: exit 0, `26 passed, 1 skipped` (15 non-gated `test_retrieval.py` tests + 11 `test_retrieval_api.py` tests; the skip is the `TB_REAL_EMBEDDINGS`-gated vague-recall test; if the executor splits/combines asserts, the signal is "every test in both files passes except the single gated skip" — update this line with the final count)

```bash
cd backend && uv run pytest -q
```
Expected: exit 0, full suite green — all 80 pre-existing tests still pass plus all new tests; zero failures, zero errors; exactly 2 skips (pre-existing ingest smoke + new recall test, both `TB_REAL_EMBEDDINGS`-gated)

Optional real-embedding proof (downloads ~90 MB model on first run; run once, then note the result):
```bash
cd backend && TB_REAL_EMBEDDINGS=1 uv run pytest tests/test_retrieval.py -q -k recall
```
Expected: exit 0, gated recall test passes — vague description retrieves the SQLAlchemy passage in top 3 (proves `query_embed` + pack + rowid + RRF path with true vectors; doubles as the Phase 1 gate preview)

### Level 4: Manual Validation

Performer: `agent` (all steps executable in this environment via dev server + curl — the executor MUST run them).

Setup (once):
1. `cd backend && uv sync` to ensure deps installed; expected: exit 0, environment ready
2. Start the server with a scratch DB: `DATABASE_PATH=/tmp/tb_retrieval_manual.db uv run uvicorn app.main:create_app --factory --port 8012 &` then `sleep 5`; expected: log line shows uvicorn startup without traceback; `curl -s localhost:8012/health` returns `{"status":"ok","db":true,...}` proving lifespan init created the DB. NOTE: seeding + search below use the REAL fastembed model (~90 MB download on first use — requires network; if offline, run the stubbed L2/L3 suites instead and record L4 server-flow as blocked-on-network with the suite as evidence, mirroring the ingestion plan's offline rule)

Step 1 — seed three notes:
1. `curl -s -X POST localhost:8012/api/v1/artifacts -H 'Content-Type: application/json' -d '{"source_type":"note","title":"SQLAlchemy fix","content":"Fixed the lazy loading problem by adding selectinload to the query. The N+1 queries are gone."}'`; expected: HTTP 201, body `{"artifact_id":"<32-hex>","chunks":1}` — record id as A1
2. `curl -s -X POST localhost:8012/api/v1/artifacts -H 'Content-Type: application/json' -d '{"source_type":"note","title":"Postgres tuning","content":"Postgres index tuning cut p99 response time in half after analyzing slow queries."}'`; expected: HTTP 201 — record id as A2
3. `curl -s -X POST localhost:8012/api/v1/artifacts -H 'Content-Type: application/json' -d '{"source_type":"note","title":"Sourdough","content":"My sourdough starter finally doubled after feeding it rye flour twice a day."}'`; expected: HTTP 201 — record id as A3

Step 2 — vague-query retrieval (Phase 1 gate preview):
1. `curl -s -X POST localhost:8012/api/v1/retrieval/search -H 'Content-Type: application/json' -d '{"query":"my database query was slow because related objects loaded one by one, what did I do","top_k":3}' | python3 -m json.tool`; expected: HTTP 200, `results[0].artifact_id == A1` (SQLAlchemy passage first despite zero shared keywords — vector leg carries), every hit has keys `chunk_id, artifact_id, span, excerpt, rrf_score, bm25_rank, vector_rank`, `excerpt` non-empty, `rrf_score` descending
2. `curl -s -X POST localhost:8012/api/v1/retrieval/search -H 'Content-Type: application/json' -d '{"query":"selectinload"}' | python3 -c "import json,sys; r=json.load(sys.stdin)['results']; print(r[0]['artifact_id'], r[0]['bm25_rank'], r[0]['vector_rank'])"`; expected: prints `<A1> 1 <int-or-null>` — exact-term query ranks A1 first with `bm25_rank: 1`
3. `curl -s -X POST localhost:8012/api/v1/retrieval/search -H 'Content-Type: application/json' -d '{"query":"sourdough starter","top_k":1}'`; expected: HTTP 200, exactly 1 result with `artifact_id == A3` (top_k honored)

Step 3 — chunk citation target:
1. `curl -s localhost:8012/api/v1/chunks/1`; expected: HTTP 200, body has `id: 1`, `artifact_id: A1`, `chunk_idx: 0`, `span: [0, <len>]`, `text` exactly the SQLAlchemy content
2. `curl -s -o /dev/null -w "%{http_code}" localhost:8012/api/v1/chunks/999999`; expected: `404`
3. `curl -s localhost:8012/api/v1/chunks/999999`; expected: body `{"detail": "..."}` (FastAPI default shape)

Step 4 — hostile + invalid input:
1. `curl -s -X POST localhost:8012/api/v1/retrieval/search -H 'Content-Type: application/json' -d '{"query":"\" OR \"1\"=\"1"}'`; expected: HTTP 200 with a `results` list (injection string sanitized, never 500)
2. `curl -s -o /dev/null -w "%{http_code}" -X POST localhost:8012/api/v1/retrieval/search -H 'Content-Type: application/json' -d '{"query":"* AND NOT ("}'`; expected: `200`
3. `curl -s -o /dev/null -w "%{http_code}" -X POST localhost:8012/api/v1/retrieval/search -H 'Content-Type: application/json' -d '{"query":"   "}'`; expected: `422`
4. `curl -s -o /dev/null -w "%{http_code}" -X POST localhost:8012/api/v1/retrieval/search -H 'Content-Type: application/json' -d '{"query":"hi","top_k":0}'`; expected: `422`
5. `curl -s -o /dev/null -w "%{http_code}" -X POST localhost:8012/api/v1/retrieval/search -H 'Content-Type: application/json' -d '{"query":"hi","top_k":51}'`; expected: `422`

Step 5 — teardown:
1. Stop the server (`kill %1` or the recorded PID); expected: process exits, no traceback in server log
2. `rm -f /tmp/tb_retrieval_manual.db*`; expected: scratch DB removed

### Level 5: Additional Validation (Optional)

None required — no MCP servers, browser flows, or extra CLIs apply to this backend-only deliverable. If the executor has the `sqlite3` CLI available, running the BM25-leg SQL by hand against the manual DB (before teardown) with an UPSANITIZED injection string — observing the `OperationalError` — is a free extra proof that the sanitizer is load-bearing (not a gate).

---

## MANUAL VERIFICATION CHECKLIST

Label each item `agent` or `human` (same performer rule as Level 4). Each item MUST give numbered steps and the exact expected observable result — never a bare "verify X works."

- [ ] [agent] vague-query retrieval: 1. seed the 3 L4 notes; 2. POST the no-shared-keywords vague query with `top_k: 3`; expected: 200, `results[0].artifact_id` is the SQLAlchemy artifact, all 7 keys present per hit, `rrf_score` descending
- [ ] [agent] exact-term retrieval: 1. POST `{"query":"selectinload"}`; expected: 200, first hit is the SQLAlchemy chunk with `bm25_rank: 1`
- [ ] [agent] top_k enforcement: 1. POST with `top_k: 1` over 3 seeded notes; expected: exactly 1 result (the best match)
- [ ] [agent] chunk round-trip: 1. GET `/api/v1/chunks/1`; 2. GET `/api/v1/chunks/999999`; expected: 200 with byte-exact `text` + `span [0,len]` → 404 `{"detail": ...}`
- [ ] [agent] injection safety: 1. POST `" OR "1"="1` query; 2. POST `* AND NOT (` query; expected: `200` both, each with a `results` list (proves sanitizer, never 500)
- [ ] [agent] rejection matrix: 1. POST blank query; 2. POST `top_k: 0`; 3. POST `top_k: 51`; expected: `422` all three (proves Pydantic bounds + strip rule)
- [ ] [agent] empty-DB behavior: 1. restart server on a fresh `DATABASE_PATH`; 2. POST any search; expected: 200 `{results: []}` (no seed needed — proves graceful empty handling)
- [ ] [agent] real-model recall (one-time, network): 1. run `TB_REAL_EMBEDDINGS=1 uv run pytest tests/test_retrieval.py -q -k recall`; expected: pass; if the sandbox has no network, record `SKIPPED (no network)` as a coverage gap instead of failing the gate

## ROLLBACK CONSIDERATIONS

- Code rollback is a clean `git checkout` of the new files (`db/chunks.py`, `retrieval/search.py`, `api/retrieval.py`, 3 test files) + `main.py` (one mount line) + `embedder.py` (`embed_query` addition only). No migration to reverse: `schema.sql` is UNCHANGED by this deliverable.
- Data rollback: retrieval writes NOTHING (pure read path — legs are SELECTs, no tables touched). Manual-validation artifacts live in scratch DBs (`/tmp/tb_retrieval_manual.db*`) — delete the files. If the executor seeded the real `./data/thoughtbridge.db` during L4, those rows are ordinary artifacts (delete the DB file and let lifespan re-init, or leave them — they are valid ingest rows, not retrieval residue).
- Model cache: the real-model paths reuse the ingestion-cached fastembed download — no new cache, no rollback needed.

## ACCEPTANCE CRITERIA

Each criterion MUST name the check that proves it: the validation level/command, the test file, or the manual-checklist item — plus the exact expected result. A criterion with no verification named is an incomplete plan.

- [ ] `POST /retrieval/search` returns ranked `{results: [{chunk_id, artifact_id, span, excerpt, rrf_score, bm25_rank, vector_rank}]}` honoring `top_k` (L3 `test_retrieval_api.py` shape/top_k tests 1-4; L4 manual Step 2.1 → SQLAlchemy first with all keys)
- [ ] Vague no-keyword query retrieves the right passage first (L3 gated `test_retrieval.py` recall test 16 → SQLAlchemy in top 3; L4 manual Step 2.1 → SQLAlchemy `results[0]`; manual vague-query checklist item)
- [ ] Exact-term query ranks the term's chunk first with `bm25_rank: 1` (L3 `test_retrieval.py` leg test 1 + API-exact check; L4 manual Step 2.2)
- [ ] RRF math is textbook: 1-indexed ranks, k=60, rank-only, deterministic id-asc tie-break (L2 `test_search.py` RRF tests 6-13; L3 `test_retrieval.py` fusion test 6 with commented arithmetic)
- [ ] FTS-hostile input never errors: injection strings return 200 (L2 structure test 2; L3 acceptance test 4 executing every injection string; L3 API test 6; L4 manual Step 4.1-4.2 → 200)
- [ ] Blank query → 422, `top_k` outside 1..50 → 422 (L3 API tests 4-5; L4 manual Step 4.3-4.5 → 422)
- [ ] Empty database → 200 `{results: []}` (L3 retrieval test 8 + API test 7; manual empty-DB checklist item)
- [ ] `GET /chunks/{id}` returns full text + artifact link, 404 on unknown id (L3 API tests 8-9; L4 manual Step 3.1-3.3 → byte-exact text, `span [0,len]`, 404 + `{"detail"}` body)
- [ ] Every returned field hydrates from canonical `chunks` (vec/FTS supply ordering only); bogus leg IDs are warned + dropped, never crash (L3 retrieval hydrate tests 11-12 + drop test 15)
- [ ] Dim/config drift fails fast before embedding (L3 retrieval dim-guard test 13 asserting embed_fn uncalled; L3 API tamper test 11 → 500 with cause)
- [ ] Query embedding uses `query_embed`, documents stay on `passage_embed` (L3 gated recall test 16 exercises the true asymmetric path; Task 1 probe result recorded in execution report)
- [ ] All validation commands pass with zero errors (L1 ruff + format + mypy; L2 pure units; L3 new integration + full `pytest -q` green incl. all 80 pre-existing tests)
- [ ] Test coverage: new modules covered per TESTING STRATEGY; no stated repo threshold exists (AGENTS.md sets none), so the bar is every behavior above asserted, not a percentage
- [ ] Code follows project conventions and patterns (thin router, explicit-params modules, no settings imports outside router/main, sync endpoints, logging without content — reviewer checks against CONTEXT REFERENCES)
- [ ] No regressions in existing functionality (L3 full-suite run: boot/config/health/db-init/meta-client/ingest tests all still pass; `main.py` change is one mount line)
- [ ] No answer generation, no reranker, no HyDE, no rebuild surface (acceptance: `git status` shows no new symbols/endpoints beyond this plan's file list; reviewer greps for `rerank|hyde|generate` in new code → zero hits)
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

- **Design decision — POST `/retrieval/search` (not GET `/search?q=`):** mirrors PRD §10 `POST /query`'s POST+JSON shape so deliverable 5 reuses `hybrid_search` unchanged; no URL length limits on long queries; Pydantic validates `top_k` bounds. Considered `GET /api/v1/search?q=&top_k=` (marginally more curl-convenient) — rejected: query-in-URL caps length and splits validation idioms from `/query`. The inspection endpoint is permanent (doubles as the debug surface for retrieval issues in every later phase), not throwaway.
- **Design decision — `GET /chunks/{id}` in this deliverable:** PRD §10's citation target; the ingestion plan explicitly deferred it here ("deliverable 4, retrieval inspection"). Inspection returns truncated excerpts; full text is always one hop away — the same division deliverable 5's citations will use.
- **Design decision — RRF k=60, 1-indexed, rank-only:** textbook Cormack/Clarke/Buettcher values. Raw `bm25()` (lower-better, unbounded negative-ish) and vec `distance` (lower-better, 0..2 cosine-ish) live on incomparable scales — any score mixing would need normalization tuning with no eval set; rank fusion needs none. 1-indexing is load-bearing (`1/61` vs `1/60`) and pinned by a dedicated regression test.
- **Design decision — FTS OR-join (not AND):** vague queries ("database slow related rows") would AND themselves into empty sets; OR + BM25 term-weighting rewards multi-term matches while tolerating missing ones. Recall-first is the correct bias for US-1; precision comes from RRF agreement between legs.
- **Design decision — per-leg `max(top_k*5, 50)`:** RRF needs deeper candidate lists than `top_k` to fuse meaningfully; 50/leg at default `top_k=8` gives 6x headroom for pennies (ID-only rows, indexed lookups). Pure function + unit test so the formula stays honest.
- **Design decision — excerpt 300 chars + `"..."`:** readable preview, bounded payload, prompt-economy forward-compat for `/query` citations. Plain slice (no word-boundary snapping — deterministic, trivially testable). Full text via `GET /chunks/{id}`.
- **Design decision — batch hydrate, one connection:** top_k ≤ 50 rows in one `SELECT ... WHERE id IN (...)`. Per-hit connections would open 50 connections per search — the N+1 to avoid.
- **Design decision — no new env vars:** RRF_K/excerpt/top-k bounds are code constants. PRD §9's config surface stays untouched; tuning these needs an eval set that doesn't exist yet, not runtime knobs.
- **Trade-off — uniform truncation instead of FTS `snippet()`:** `snippet()` highlights only FTS-matched terms, but fused vector-only hits have no FTS context — per-hit highlighting would be inconsistent (some hits highlighted, others not). Uniform excerpts keep every hit comparable; revisit if a future UI wants keyword highlighting on the BM25 leg only.
- **Trade-off — legs run sequentially, not in parallel:** two indexed SELECTs over a single-user DB take single-digit ms; threading adds nothing measurable. Revisit only with profiling evidence.
- **Risk — fastembed `query_embed` call shape:** Task 1's signature probe resolves str-vs-list before any implementation. If the installed 0.9.1 differs from the documented `query_embed(str)` shape, the executor adapts the one call line + records the actual shape in the execution report. The gated recall test then proves the true path regardless.
- **Risk — L4 manual flows need network:** seeding + search via the dev server invoke real fastembed (~90 MB first download). If the sandbox is offline, the executor runs the stubbed L2/L3 suites as the evidence and records L4 server-flow as blocked-on-network (same rule as the ingestion plan — do not fake it).
- **Risk — `bm25()` direction:** the single most likely silent bug (ranking inverted with all tests green IF tests asserted weakly). Mitigated by best-first assertions on real FTS rows (leg test 1, hybrid tests 5-6, API tests, L4) — never assert "returns N rows" where "returns X first" is meant.
- **Out-of-scope guard:** if execution tempts toward answer text, `/query`, reranking, HyDE, a rebuild endpoint, DELETE, or any `frontend/` edit — stop. Those belong to deliverable 5, Phase 3 stretch, Phase 3 cascade, and deliverable 5's UI respectively. The plan is retrieval-reads-only by build-list authority.
- **Forward-compat:** deliverable 5 imports `hybrid_search` + `SearchHit` unchanged and reuses the citation shape (`chunk_id/artifact_id/span/excerpt`); `search_bm25_ids`/`search_vector_ids` are independently reusable for teaching-mode retrieval variants; the inspection endpoint stays as the permanent retrieval debugger.
- **Open follow-up — Capture UI scheduling (unchanged, non-blocking):** still undecided per the ingestion plan's NOTES; this deliverable stays backend-only and assigns nothing.

---

## Revision History

### Cycle 1

Findings addressed (from `.agents/plans/reviews/hybrid-retrieval-plan-review.md`, review 1 — the only open items; all structure checks and all other assessments PASS, no escalations):

1. "`test_retrieval.py` test 12 does not prove per-leg over-fetch: with one-hot stubs, every non-target chunk is equidistant, so vector rank 4 is uncontrollable, and a BM25-rank-1 chunk would surface in `top_k=2` even at limit 2; use graded stub vectors and assert the hit's `vector_rank == 4` (which would be `None` without over-fetch)." Rewrote test 12 with graded stubs: a stateful counter passage stub (`[[float(n)] + [0.0]*383]` in seed order) plus a zero query vector yields strictly ascending distances, placing the BM25-matching 4th chunk deterministically at vector rank 4; the test asserts `bm25_rank == 1` AND `vector_rank == 4`, and the description states a `top_k`-truncated leg would yield `vector_rank=None` and fail. TESTING STRATEGY's test-12 phrase updated to match.
2. "The L3 Expected line says `27 passed, 1 skipped`, but the plan enumerates 15 non-gated `test_retrieval.py` tests plus 11 API tests (26), so correct the count to match the enumerated tests." Corrected to `26 passed, 1 skipped` with the 15+11 decomposition stated inline.

Not done / open: nothing — review 1's corrections are fully applied.

