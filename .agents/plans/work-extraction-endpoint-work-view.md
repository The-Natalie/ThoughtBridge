# Feature: Work Extraction Endpoint + Work View

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Implement PRD F-5 (work extraction, reasoning chains & accomplishment recognition) as Phase 2 deliverable 4: a structured LLM extraction pipeline that turns raw work artifacts (notes, pastes, session summaries) into grounded `facts` — problems, decisions + reasoning, accomplishments, demonstrated skills — each with evidence links (chunk IDs), per-item status (proposed / rejected / completed), and typed reasoning links (`constrained_by`, `considered`, `rejected_because`, `decided`, `implemented_by`, `resulted_in`) forming traversable Problem → constraints → approaches → rejection reasons → decision → implementation → outcome chains. A new Work view renders extraction results reviewably with provenance (chunk drill-down) and clickable reasoning links.

This is the first deliverable to write Layer 3 of the four-layer store (`facts`, `fact_chunks`, `fact_links` tables exist in schema since scaffolding but have zero writers). Anti-invention rules are load-bearing: extraction never upgrades discussion into accomplishment, never invents steps or outcomes, completion requires explicit user statements, and every fact keeps its own chunk evidence. Career-profile prompt injection arrives through a seam with a working empty default, which deliverable 5 will fill with real reads (same pattern deliverable 1 used for profile/memory seams).

## User Story

As an engineer who pastes raw notes without judging their importance
I want my work sessions extracted into problems, decisions, accomplishments, and skills with evidence and proposed/rejected/completed status
So that my real contributions get recognized without me needing self-promotion skills, and my record never claims work I only considered

## Problem Statement

US-5/US-6 require work documentation with accomplishment recognition and a strict proposed-vs-done distinction, but the current product only ingests artifacts into searchable chunks: there is no structured understanding of what the user did, decided, or completed. The `facts`/`fact_chunks`/`fact_links` schema has sat writerless since Phase 1, the Work surface is a placeholder stub (`App.tsx` line 10), and interview prep (Phase 3) will have no accomplishment facts to ground experience questions against. Without extraction, pasted assistant conversations remain undifferentiated text and rejected approaches (evidence of engineering judgment) stay invisible.

## Scope

- In scope:
  - `POST /work/extract` exactly per PRD §10 (`{artifact_ids[...]}` → `{facts[{fact_id, kind, status, summary, skills, confidence, chunk_ids, links[{to_fact, relation}]}]}`), single LLM call over numbered chunks, JSON-schema-validated at the boundary, persisted atomically.
  - Extraction prompt contracts in `core/grounding.py` (evidence-mode closed world + anti-invention rules + link-relation semantics), with `EXTRACTION_PROMPT_VERSION` recorded per fact row.
  - `app/db/facts.py` repository (single-transaction `facts` + `fact_chunks` + `fact_links` writes) plus two small read helpers: chunk-fetch-by-artifacts (`db/chunks.py`) and missing-artifact detection (`db/artifacts.py`).
  - Career-profile input seam (`CareerContext` / `CareerFn` / `no_career()` default / `render_career_block()`) — D5 handoff point, explicitly named.
  - Input guards: empty `artifact_ids` → 422, unknown ids → 404, zero-chunk artifacts → 422, over-char-cap → 413, malformed/hallucinated model output → 502 with nothing persisted.
  - Work view: artifact multi-select (via existing `GET /artifacts`) → extract → reviewable results with status filter (client-side), provenance drill-down (via existing `GET /chunks/{id}`), traversable reasoning links.
  - Frontend API clients (`artifacts.ts`, `work.ts`) + types, App view wiring, backend + frontend tests.
- Out of scope:
  - `GET /work/accomplishments` (list/filter) and `GET /PUT /profile` career-profile CRUD (deliverable 5 — the seam default keeps this deliverable standalone).
  - Deduplication/merging of equivalent facts across extraction calls (documented MVP limitation per PRD F-10 — each call produces per-call fact records).
  - Editing, redaction, or correction workflows (deferred per PRD).
  - `tb_conversation` ingestion, deletion cascade, Practice Loop (Phase 3).
  - PDF/Word adapters (deliverable 6, Preferred).
  - Rerank, HyDE, scored relevance ranking (deferred/Preferred per PRD).

## Solution Statement

Follow the proven `llm/qa.py` + `llm/explainer.py` + thin-router architecture: add `app/llm/extraction.py` (pure orchestration over injected `chat_fn`/`career_fn` seams, Pydantic validation at the LLM boundary reusing `strip_fences` from `qa.py`), `app/db/facts.py` (atomic multi-table repository mirroring `artifacts.store_artifact`), and `app/api/work.py` (thin router mapping `ExtractionValidationError`/`MetaAPIError` → 502 exactly like `learn.py`, with `_make_chat_fn` carrying the per-call token budget). Generation is ONE evidence-mode LLM call over numbered chunk passages (not per-chunk calls — reasoning links span chunks and per-chunk calls would fragment chains and multiply cost); the model returns facts with ephemeral 0-based link indices and real chunk IDs, code validates every reference (unknown chunk → 502, dangling/self link → 502, ungrounded fact → 502) and translates indices to uuid fact IDs before a single-transaction persist. Prompts live in `core/grounding.py` alongside the existing mode contracts. The frontend mirrors `ChatView` citation conventions and `LearnView` state conventions in a new `WorkView`.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: High
**Primary Systems Affected**: `backend/app/llm/` (new extraction), `backend/app/api/` (new work router), `backend/app/db/` (new facts repository + 2 read helpers), `backend/app/core/` (extraction prompt contracts), `frontend/src/views/` (WorkView), `frontend/src/api/` (work + artifacts clients)
**Dependencies**: None outside this plan (career profile arrives via seam with working empty default; deliverable 5 fills it). Runtime dep: Meta Model API via existing `meta_client.chat_completion` (no new packages).
**Assumptions**:
1. Deliverable 5 (career profile) is NOT yet built; this plan's seam contract (`CareerFn`, `CareerContext`, `no_career`, `render_career_block`) is the interface it must fill — validate these names survive into that plan.
2. Single-call extraction suffices for MVP-sized inputs; inputs over `MAX_EXTRACTION_CHARS` (30,000) are rejected with 413 rather than silently truncated or multi-called. Multi-call/chunked extraction is deferred until a measured failure (mirrors the rerank/HyDE posture).
3. `EXTRACTION_MAX_TOKENS = 16384` suffices despite Spark hidden-reasoning burn (matches Stage B, which also emits long structured JSON) — validate with one live call during implementation.
4. Empty extraction result (`{"facts": []}`) is a legitimate 200 outcome (nothing extractable), not a model failure — validate the executor preserves this distinction.
5. Every fact requires ≥1 valid chunk ID; any ungrounded fact, unknown chunk ID, or invalid link fails the WHOLE call (502, nothing persisted) — fail-closed, no partial facts, matching the explainer's atomicity.
6. Repeat `POST /work/extract` over the same artifacts always creates fresh per-call fact records (no dedup — the documented F-10 MVP limitation).

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `backend/app/llm/qa.py` (lines 32-42) - Why: error-class + Pydantic-output pattern to MIRROR (`QaValidationError(ValueError)`, `QaModelOut`); extraction defines `ExtractionValidationError` + `ExtractionModelOut` the same way.
- `backend/app/llm/qa.py` (lines 61-70) - Why: `strip_fences` — IMPORT and reuse directly; do not copy fence-stripping logic.
- `backend/app/llm/qa.py` (lines 72-115) - Why: orchestration shape to MIRROR (inject seams → call chat → validate → map to result dataclasses → log); validation failure handling at the boundary.
- `backend/app/llm/explainer.py` (lines 40-64) - Why: budgeted chat-fn seam (`ExplainerChatFn` takes `(messages, max_tokens)`) + `ExplainerValidationError` — extraction uses the same budgeted arity since its budget differs from Q&A's.
- `backend/app/llm/explainer.py` (lines 108-124) - Why: seam-default + DB-backed filler pattern (`default_learner_context` / `read_learner_context`) to MIRROR for `no_career()` (the `read_career_context` filler is deliverable 5's work — do NOT build it here).
- `backend/app/llm/explainer.py` (lines 127-156) - Why: `render_profile_block` / `render_memory_block` pure renderers to MIRROR for `render_career_block` (empty input → empty string, no prompt change).
- `backend/app/llm/explainer.py` (lines 166-232) - Why: atomic persist-after-all-validation pattern (`persist_fn` seam, no partial writes) — extraction persists only after every fact and link validates.
- `backend/app/core/grounding.py` (lines 1-6) - Why: module purity contract (prompts only; no settings, DB, or network) — extraction prompts MUST live here, not in `llm/` or `api/`.
- `backend/app/core/grounding.py` (lines 19-35) - Why: `UNTRUSTED_PASSAGE_FRAMING` + evidence-mode system prompt to MIRROR/REUSE — extraction is closed-world evidence mode; reuse the framing constant verbatim.
- `backend/app/core/grounding.py` (lines 142-151) - Why: `STEP_KEYS` vocabulary-tuple pattern — extraction vocabularies (`EXTRACTION_KINDS`, `EXTRACTION_STATUSES`, `LINK_RELATIONS`) are defined here as the single owner.
- `backend/app/core/grounding.py` (lines 241-270) - Why: `build_stage_messages` assembly pattern (pre-rendered context blocks + JSON instructions) to MIRROR for `build_extraction_messages`.
- `backend/app/api/learn.py` (lines 124-138) - Why: `_make_chat_fn(settings, model)` closure carrying per-call budget + missing-key 502 — COPY this shape for `app/api/work.py` (extraction budget ≠ Q&A default).
- `backend/app/api/learn.py` (lines 141-175) - Why: `post_explain` flow to MIRROR — blank-input 422, `ExplainerValidationError`→502 BEFORE `ValueError`→500, `MetaAPIError`→502.
- `backend/app/api/query.py` (lines 144-174) - Why: `chat_fn` closure + exception-mapping order (`QaValidationError`→502 before generic `ValueError`→500) — same ordering requirement applies to `ExtractionValidationError`.
- `backend/app/api/ingest.py` (lines 158-171) - Why: list-endpoint response-mapping style (`list_artifacts` → Pydantic items); frontend artifact picker consumes this existing endpoint.
- `backend/app/db/schema.sql` (lines 60-83) - Why: `facts` / `fact_chunks` / `fact_links` DDL — the repository MUST match these columns exactly (`skills` JSON TEXT, `confidence` REAL, `model`/`prompt_version` TEXT, link PK `(from_fact_id, to_fact_id, relation)`).
- `backend/app/db/artifacts.py` (lines 50-94) - Why: single-transaction multi-table write pattern (`with conn:` + `lastrowid`) to MIRROR in `facts.create_facts`.
- `backend/app/db/artifacts.py` (lines 97-120) - Why: `list_artifacts` single-connection aggregate query pattern; ADD `find_missing_artifact_ids` in this file beside it.
- `backend/app/db/chunks.py` (lines 21-44) - Why: `get_chunks` batch-hydration pattern (`connect` + `finally: conn.close()`, parameterized IN clause); ADD `get_chunks_by_artifacts` in this file following it.
- `backend/app/db/explanations.py` (lines 29-75) - Why: `create_explanation` id/timestamp generation (`uuid.uuid4().hex`, `datetime.now(UTC).isoformat()`) to MIRROR in `create_facts`.
- `backend/app/db/connection.py` (lines 21-30) - Why: `connect` is the ONLY sanctioned DB path (WAL + FK + vec0 + Row factory) — every repository function uses it.
- `backend/app/core/meta_client.py` (lines 110-120) - Why: `chat_completion` signature — accepts per-call `max_tokens`; router passes `EXTRACTION_MAX_TOKENS` explicitly (the `QA_MAX_TOKENS=4096` default is Q&A-sized, too small here).
- `backend/app/main.py` (lines 42-58) - Why: `create_app` router registration — ADD `app.include_router(work_router, prefix="/api/v1")` beside the existing five.
- `backend/tests/test_explainer.py` (lines 42-50) - Why: `_chat_for` stub factory (payload queue + call record) to MIRROR in `test_extraction.py`.
- `backend/tests/test_explainer.py` (lines 240-269) - Why: tmp-DB atomic-failure test (success writes versions, failure writes nothing) to MIRROR for facts persistence.
- `backend/tests/test_learn_api.py` (lines 42-67) - Why: `_isolated_settings` fixture + `_client` helper (settings isolation, tmp DB, TestClient) to MIRROR in `test_work_api.py`.
- `backend/tests/test_learn_api.py` (lines 256-270) - Why: `_seeded_client` real-repo seeding pattern for API tests needing pre-existing rows (artifacts + chunks here).
- `frontend/src/api/query.ts` (lines 15-18) - Why: `getChunk` — IMPORT and reuse for provenance drill-down; do not create a second chunk fetcher.
- `frontend/src/api/learn.ts` (whole file) - Why: client-module pattern to MIRROR (`apiGet`/`apiPost` wrappers, one function per endpoint, JSDoc line) for `artifacts.ts` + `work.ts`.
- `frontend/src/api/learn.test.ts` (lines 14-21, 29-38) - Why: `mockFetch` helper + URL/body assertion pattern to MIRROR in `work.test.ts` / `artifacts.test.ts`.
- `frontend/src/api/types.ts` (lines 1-11) - Why: "Field names mirror backend Pydantic JSON exactly" contract — new work/artifact types MUST match backend key names (`fact_id`, `chunk_ids`, `to_fact`, `chunk_count`, `fact_count`).
- `frontend/src/views/ChatView.tsx` (lines 52-59, 90-128) - Why: `openCitation` + citation-chip + chunk-panel rendering to MIRROR for per-fact provenance drill-down.
- `frontend/src/views/LearnView.tsx` (lines 72-110, 262-271) - Why: async-action shape (`loading`/`error`, try/catch/finally) + `role="alert"` error-with-Dismiss pattern to MIRROR in `WorkView`.
- `frontend/src/views/LearnView.test.tsx` (lines 1-60) - Why: factory helpers (`explainResponse`, `explanationDetail`) + `mockFetchSequence` pattern to MIRROR in `WorkView.test.tsx`.
- `frontend/src/App.tsx` (lines 1-13, 41-43) - Why: view registration — ADD `WorkView` import, clear the `work` blurb, extend the ternary in `main`.

### New Files to Create

- `backend/app/llm/extraction.py` - Extraction orchestration over injected `chat_fn`/`career_fn` seams: validate → translate indices to uuids → atomic persist.
- `backend/app/db/facts.py` - Facts repository: single-transaction `create_facts` over `facts` + `fact_chunks` + `fact_links`.
- `backend/app/api/work.py` - Thin work router: `POST /work/extract` with input guards + exception mapping.
- `backend/tests/test_extraction.py` - Orchestration unit tests: happy path, every validation failure, career injection, tmp-DB atomicity.
- `backend/tests/test_work_api.py` - API contract tests: shape, 404/413/422/502 matrix, persistence round-trip with stubbed chat.
- `frontend/src/api/artifacts.ts` - Artifact list client (`listArtifacts`, consumed by the WorkView picker).
- `frontend/src/api/artifacts.test.ts` - Client test for the artifact list call.
- `frontend/src/api/work.ts` - Work client (`postExtract`).
- `frontend/src/api/work.test.ts` - Client test for the extract call.
- `frontend/src/views/WorkView.tsx` - Work view: artifact picker → extract → filterable results with provenance + reasoning links.
- `frontend/src/views/WorkView.test.tsx` - View tests: select → extract → render → filter → provenance open.

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [Pydantic model_validate_json](https://docs.pydantic.dev/latest/api/base_model/#pydantic.BaseModel.model_validate_json)
  - Specific section: `model_validate_json` classmethod
  - Why: Boundary-validation call already used by `qa.py`/`explainer.py`; extraction uses it identically for the model-output schema.
- [FastAPI handling errors](https://fastapi.tiangolo.com/tutorial/handling-errors/)
  - Specific section: `HTTPException` with `status_code`
  - Why: Router error-mapping pattern (`422`/`404`/`413`/`502`) already established in `learn.py`/`query.py`; no new error shape.
- No new libraries, no new SDK calls: the Meta client (`chat_completion`), test doubles (`TestClient`, `monkeypatch`, `vitest`), and SQLite access (`connect`) are all established in-repo patterns. Do not add dependencies for this deliverable.

### Patterns to Follow

**Naming Conventions:**

- Backend: `snake_case` modules/functions (`extraction.py`, `create_facts`, `post_extract`); `PascalCase` Pydantic models/dataclasses (`ExtractRequest`, `FactOut`, `ExtractionValidationError`); router function names mirror endpoint purpose (`post_extract`, like `post_explain`/`post_query`).
- DB tables already fixed: `facts`, `fact_chunks`, `fact_links` (plural `snake_case`).
- Frontend: `PascalCase.tsx` views (`WorkView.tsx`), `camelCase.ts` clients (`work.ts`, `artifacts.ts`); client functions are verbs (`postExtract`, `listArtifacts`, like `postExplain`/`getChunk`).

**Error Handling:**

Exception-mapping ORDER matters — the validation-error branch must precede the generic `ValueError` branch because the custom error subclasses it (from `backend/app/api/learn.py` lines 159-169):

```python
except ExplainerValidationError as exc:
    # BEFORE the generic ValueError branch: ExplainerValidationError subclasses it.
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
except MetaAPIError as exc:
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
except ValueError as exc:
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
```

`POST /work/extract` status matrix: 200 (facts, possibly `[]`), 201? No — 200: extraction is a computation returning persisted facts, and PRD §10 shows no 201 for it (unlike artifact creation). 422 empty/blank input or zero-chunk artifacts, 404 unknown artifact ids, 413 over char cap, 502 Meta failure / malformed or hallucinated model output / missing API key.

**Budgeted chat closure (from `backend/app/api/learn.py` lines 124-138):**

```python
def _make_chat_fn(settings, model_wanted: str):
    async def chat_fn(messages: list[dict[str, str]], max_tokens: int) -> str:
        key = settings.model_api_key.get_secret_value()
        if not key:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="MODEL_API_KEY not configured")
        return await chat_completion(api_key=key, model=model_wanted, messages=messages, max_tokens=max_tokens)
    return chat_fn
```

COPY this shape into `app/api/work.py` (extraction needs its own budget constant, not the Q&A default).

**By-name seam imports (from `backend/app/api/learn.py` lines 7-13 docstring):** router modules import `chat_completion`, orchestration entry points, and repository functions BY NAME so tests stub via `monkeypatch.setattr("app.api.work.<name>", stub)`. The work router MUST follow this: `from app.llm.extraction import run_extraction` (by name), `from app.core.meta_client import chat_completion` (by name).

**Atomic repository write (from `backend/app/db/artifacts.py` lines 74-90):** one `connect(db_path)`, one `with conn:` block covering all inserts, `finally: conn.close()`. `create_facts` inserts `facts` rows, then `fact_chunks` rows, then `fact_links` rows inside the same transaction — a link-table FK failure rolls back everything.

**Frontend error alert (from `frontend/src/views/LearnView.tsx` lines 263-271):**

```tsx
{error && (
  <div role="alert" className="rounded border border-red-500 px-3 py-2 text-sm">
    <span>{error}</span>{' '}
    <button type="button" aria-label="Dismiss error" onClick={() => setError(null)} className="underline">
      Dismiss
    </button>
  </div>
)}
```

COPY this block into `WorkView` (same roles/labels/classes so tests and styling stay consistent).

**Other Relevant Patterns:**

- Vocabulary tuples live in `core/grounding.py` as the single owner (`STEP_KEYS` precedent); `llm/` modules import them for Pydantic `Literal` types and prompt text. Never redeclare the enum strings in a second module.
- Untrusted-data framing: artifact content is untrusted user data — reuse `UNTRUSTED_PASSAGE_FRAMING` verbatim in the extraction system prompt and number passages as `Passage [n] (chunk_id=...)` exactly like `build_messages` (`grounding.py` lines 129-130), so chunk-ID citation has one visual format across the product.
- Frontend types mirror backend Pydantic JSON keys exactly (`fact_id`, `chunk_ids`, `to_fact`) — no camelCase translation layer exists; do not introduce one.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

Shared contracts and read helpers that everything else builds on. Add the extraction vocabularies, system prompt, JSON instructions, prompt-version constant, and message builder to `core/grounding.py` (pure functions only — no settings/DB/network per the module contract). Add `get_chunks_by_artifacts` to `db/chunks.py` (ordered chunk hydration for a set of artifacts, one connection) and `find_missing_artifact_ids` to `db/artifacts.py` (single-query existence check for the router's 404).

**Tasks:**

- Define `EXTRACTION_KINDS`, `EXTRACTION_STATUSES`, `LINK_RELATIONS` tuples + `EXTRACTION_PROMPT_VERSION = "extract-v1"` in `grounding.py`.
- Write `EXTRACTION_SYSTEM_PROMPT` (closed-world evidence mode + anti-invention rules + status semantics + relation-direction semantics) reusing `UNTRUSTED_PASSAGE_FRAMING` verbatim, plus `EXTRACTION_JSON_INSTRUCTIONS` and `build_extraction_messages(passages, career_block)`.
- Add the two repository read helpers with `connect`/`finally: conn.close()` discipline.

### Phase 2: Core Implementation

The extraction orchestrator and facts repository. `app/llm/extraction.py` defines the model-output Pydantic schema (facts with ephemeral 0-based link indices + real chunk IDs), the `CareerContext`/`CareerFn`/`no_career()`/`render_career_block()` seam (D5 handoff), and `run_extraction()` — fetch chunks → guard char cap → build messages → chat → `strip_fences` + `model_validate_json` → validate every chunk ID against the fetched set and every link index against the facts array → translate indices to uuid fact IDs → atomic persist via `persist_fn` seam (default: real repository path). `app/db/facts.py` implements `create_facts` (one transaction over all three tables) and the `FactCreate`/`FactLinkCreate` input dataclasses.

**Tasks:**

- CREATE `app/db/facts.py` with input dataclasses + single-transaction `create_facts`.
- CREATE `app/llm/extraction.py` with schema models, career seam, `EXTRACTION_MAX_TOKENS`/`MAX_EXTRACTION_CHARS`/`MAX_EXTRACTION_ARTIFACTS` constants, and `run_extraction`.
- Every validation failure raises `ExtractionValidationError` BEFORE any write; `{"facts": []}` is a valid 200 outcome that persists nothing.

### Phase 3: Integration

Wire the feature into the app's entry points. CREATE `app/api/work.py` (thin `POST /work/extract` router: Pydantic models mirroring PRD §10 keys exactly, input guards, `_make_chat_fn` budgeted closure, ordered exception mapping, by-name seam imports) and register it in `create_app`. Frontend: extend `api/types.ts`, CREATE `api/artifacts.ts` + `api/work.ts`, CREATE `views/WorkView.tsx`, wire the `work` view in `App.tsx` (import + blank blurb + ternary branch).

**Tasks:**

- CREATE the work router + register in `main.py`.
- Extend types + CREATE the two API clients.
- CREATE `WorkView` (picker → extract → status filter → fact cards with provenance + links) + wire `App.tsx`.

### Phase 4: Testing & Validation

Backend: `tests/test_extraction.py` (stubbed `chat_fn`/`career_fn`/`persist_fn` — no network, no embedding model; tmp-DB subset via `init_db`) and `tests/test_work_api.py` (TestClient over tmp DBs, `run_extraction`/`chat_completion` stubbed per-test, real-repo seeding for guard tests). Frontend: `artifacts.test.ts` + `work.test.ts` (URL/body assertions) + `WorkView.test.tsx` (fetch-sequence interaction tests). Then the full validation ladder (ruff + mypy + full pytest + vitest + build) and the manual verification checklist, including one live extraction over a real pasted dev log (Phase 2 gate item 3).

**Tasks:**

- CREATE the two backend test files + three frontend test files.
- Run L1–L4 validation; record the live-extraction inspection for the phase gate.
- L5 browser E2E is `NOT_PERFORMED` (deployment out of scope) with manual steps documented.

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

### UPDATE backend/app/core/grounding.py

- **IMPLEMENT**: Append an extraction-contracts section: `EXTRACTION_KINDS = ("problem", "decision", "accomplishment", "skill")`, `EXTRACTION_STATUSES = ("proposed", "rejected", "completed")`, `LINK_RELATIONS = ("constrained_by", "considered", "rejected_because", "decided", "implemented_by", "resulted_in")`, `EXTRACTION_PROMPT_VERSION = "extract-v1"`, `EXTRACTION_SYSTEM_PROMPT` (closed world: use ONLY numbered passages; every fact cites ≥1 chunk_id; status semantics — completed requires explicit user statements of done/shipped/fixed/merged, rejected = considered-then-discarded WITH reason, proposed = everything else incl. assistant suggestions; anti-invention — discussion never upgrades to accomplishment, never invent steps/outcomes, rejected approaches are first-class records; relation directions — `constrained_by`: fact → its constraint, `considered`: problem → approach, `rejected_because`: approach → reason, `decided`: problem → decision, `implemented_by`: decision → accomplishment, `resulted_in`: decision/accomplishment → outcome; plus `UNTRUSTED_PASSAGE_FRAMING` verbatim), `EXTRACTION_JSON_INSTRUCTIONS` (single JSON object `{"facts": [...]}`; per-fact `kind`, `status`, `summary` non-empty string, `skills` string array, `confidence` 0.0–1.0, `chunk_ids` non-empty integer array of cited chunk IDs, `links` array of `{"to": <0-based fact index>, "relation": <one of six>}`; `to` must reference another fact in the same array, never self; empty `facts` array allowed when nothing is extractable), `build_extraction_messages(passages: list[NumberedPassage], career_block: str) -> list[dict[str, str]]` (system prompt + optional career block as second system message when non-empty + user message with `Passage [n] (chunk_id=...)` blocks reusing the `build_messages` format + JSON instructions).
- **PATTERN**: MIRROR `STEP_KEYS` + `build_stage_messages` (grounding.py:142-151, 241-270); REUSE `NumberedPassage`, `UNTRUSTED_PASSAGE_FRAMING`.
- **IMPORTS**: None new (same module; `NumberedPassage` already defined above).
- **GOTCHA**: This module must stay pure — no settings/DB/network reads (module docstring contract, grounding.py:1-6). The career block arrives pre-rendered; this builder never fetches the profile.
- **VALIDATE**: `cd backend && uv run ruff check app/core/grounding.py && uv run ruff format --check app/core/grounding.py`

### UPDATE backend/app/db/chunks.py

- **IMPLEMENT**: ADD `get_chunks_by_artifacts(db_path: str, artifact_ids: list[str]) -> dict[str, list[ChunkDetail]]` — one connection, one parameterized query (`WHERE artifact_id IN (...) ORDER BY artifact_id, chunk_idx`), returns mapping artifact_id → ordered chunks (artifacts with no chunks map to `[]`; unknown ids simply absent — existence is the caller's job).
- **PATTERN**: MIRROR `get_chunks` (chunks.py:21-44) — `connect` + `finally: conn.close()`, `ChunkDetail` construction.
- **IMPORTS**: None new.
- **GOTCHA**: Empty `artifact_ids` must return `{}` without issuing an `IN ()` query (invalid SQL) — early-return like `get_chunks` does for empty ids.
- **VALIDATE**: `cd backend && uv run ruff check app/db/chunks.py && uv run pytest tests/test_search.py -q`

### UPDATE backend/app/db/artifacts.py

- **IMPLEMENT**: ADD `find_missing_artifact_ids(db_path: str, artifact_ids: list[str]) -> list[str]` — one connection, one `SELECT id FROM artifacts WHERE id IN (...)` query, returns the requested ids NOT present (order-preserving, deduped).
- **PATTERN**: MIRROR `list_artifacts` query discipline (artifacts.py:97-120) — single connection, `finally: conn.close()`.
- **IMPORTS**: None new.
- **GOTCHA**: Empty input returns `[]` without querying (same `IN ()` hazard as above).
- **VALIDATE**: `cd backend && uv run ruff check app/db/artifacts.py && uv run pytest tests/test_ingest_api.py -q`

### CREATE backend/app/db/facts.py

- **IMPLEMENT**: Facts repository. The repository takes FINAL ids only (the orchestrator owns id generation so link translation and response assembly use one id set). Define `@dataclass FactCreate(kind, status, summary, skills: list[str], confidence: float, chunk_ids: list[int])` and `@dataclass FactLinkCreate(from_fact_id: str, to_fact_id: str, relation: str)`; `create_facts(*, db_path, items: list[tuple[str, FactCreate, list[FactLinkCreate]]], model: str, prompt_version: str) -> list[str]` where each tuple is `(pre-assigned fact id, fact, outgoing links)` — single transaction: for each item generate `datetime.now(UTC).isoformat()`, INSERT into `facts` (skills as `json.dumps`), INSERT `fact_chunks` rows, collect link rows and INSERT into `fact_links` after all facts exist (satisfies self-join FKs); returns fact ids in input order. Empty `items` list is a no-op returning `[]` (one connection, no writes).
- **PATTERN**: MIRROR `store_artifact` transaction shape (artifacts.py:50-94) + `create_explanation` id/timestamp generation (explanations.py:29-75).
- **IMPORTS**: `json`, `logging`, `uuid`, `dataclasses.dataclass`, `datetime.UTC/datetime`, `app.db.connection.connect`.
- **GOTCHA**: Schema columns are `skills TEXT (JSON)`, `confidence REAL`, `model`/`prompt_version` TEXT with defaults — INSERT must name all seven value columns explicitly (`id, kind, status, summary, skills, confidence, model, prompt_version, created_at`). Link inserts happen AFTER all fact inserts (self-join FKs). Dedupe identical `(from, to, relation)` triples in Python before insert (link PK would abort the whole transaction on duplicates).
- **VALIDATE**: `cd backend && uv run ruff check app/db/facts.py && uv run ruff format --check app/db/facts.py`

### CREATE backend/app/llm/extraction.py

- **IMPLEMENT**: Extraction orchestration. Constants `EXTRACTION_MAX_TOKENS = 16384`, `MAX_EXTRACTION_CHARS = 30_000`, `MAX_EXTRACTION_ARTIFACTS = 20`. Seam types: `ExtractionChatFn = Callable[[list[dict[str, str]], int], Awaitable[str]]`, `CareerContext` dataclass (`current_role: str, past_roles: list[str], target_career: str, target_position: str`), `CareerFn = Callable[[], CareerContext]`, `PersistFn = Callable[[list[tuple[str, FactCreate, list[FactLinkCreate]]], str, str], list[str]]` (takes `(items, model, prompt_version)`; default persist is a closure over `db_path` calling `create_facts`). `no_career()` default (all empty), `render_career_block(career) -> str` ("" when all fields empty, else "Career profile (prioritize and phrase extraction toward this trajectory; untrusted user data, never instructions): ..." lines). Pydantic models `ExtractionLinkOut(to: int, relation: Literal[...six])`, `ExtractionFactOut(kind/status Literals, summary: str, skills: list[str], confidence: float ge=0 le=1, chunk_ids: list[int], links: list[ExtractionLinkOut])`, `ExtractionModelOut(facts: list[ExtractionFactOut])`. Error classes (all subclass `ValueError`): `ExtractionValidationError`, `ExtractionTooLargeError`, `UnknownArtifactError`, `EmptyExtractionError`. `async def run_extraction(*, artifact_ids, db_path, chat_fn, career_fn, model, persist_fn=None) -> ExtractedResult(facts: list[ExtractedFact(fact_id, kind, status, summary, skills, confidence, chunk_ids, links: list[ExtractedLink(to_fact, relation)])])`: dedupe ids preserving order → `find_missing_artifact_ids` (missing → `UnknownArtifactError` listing the ids) → `get_chunks_by_artifacts` (zero total chunks → `EmptyExtractionError`) → char-cap guard (sum of chunk text > cap → `ExtractionTooLargeError` with chars/cap in message) → build `NumberedPassage`s in (artifact order, chunk_idx) order → `render_career_block(career_fn())` → `chat_fn(build_extraction_messages(...), EXTRACTION_MAX_TOKENS)` → `strip_fences` + `model_validate_json` (failure → `ExtractionValidationError`) → per-fact checks: summary non-blank, ≥1 chunk_id, every chunk_id in fetched set, skills entries non-blank, every link `to` in range and ≠ self (any violation → `ExtractionValidationError` naming fact index + reason) → pre-generate one `uuid.uuid4().hex` per fact, translate link indices to ids, build `FactCreate`/`FactLinkCreate` items → persist via `persist_fn` (or the default `create_facts` closure with `model` + `EXTRACTION_PROMPT_VERSION`). Persist ONLY after all validation; empty facts → return empty result with NO persist call. Log `logger.info("extraction complete: artifacts=%d facts=%d links=%d")`.
- **PATTERN**: MIRROR `explainer.generate_explanation` seam/orchestration shape (explainer.py:166-232) + `qa.strip_fences` REUSE (qa.py:61-70) + budgeted `ExplainerChatFn` arity (explainer.py:42).
- **IMPORTS**: `json`? no — Pydantic handles; `logging`, `uuid`, `dataclasses`, `collections.abc (Awaitable, Callable)`, `typing.Literal`, `pydantic (BaseModel, Field, ValidationError)`, `app.core.grounding (EXTRACTION_KINDS, EXTRACTION_STATUSES, LINK_RELATIONS, EXTRACTION_PROMPT_VERSION, NumberedPassage, build_extraction_messages)`, `app.db.artifacts.find_missing_artifact_ids`, `app.db.chunks.get_chunks_by_artifacts`, `app.db.facts (FactCreate, FactLinkCreate, create_facts)`, `app.llm.qa.strip_fences`.
- **GOTCHA**: (1) The orchestrator pre-generates fact ids and the repository inserts the GIVEN ids (same signature as the CREATE-facts task above) — response assembly, link translation, and stored rows share one id set; never let the repository mint a second set. (2) `Literal` types must derive from the grounding tuples (`Literal["problem", ...]` written out, with an import-time assert `set(...) == set(EXTRACTION_KINDS)` to catch drift — MIRROR `EMPHASIS_LABELS` drift-guard in explainer.py:96-105). (3) All four error classes subclass `ValueError` — the router catches them BEFORE the generic `ValueError` branch.
- **VALIDATE**: `cd backend && uv run ruff check app/llm/extraction.py && uv run mypy app/llm/extraction.py`

### CREATE backend/app/api/work.py

- **IMPLEMENT**: Thin work router. Docstring documents by-name seams (`run_extraction`, `chat_completion`, `no_career` — stubbed via `monkeypatch.setattr("app.api.work.<name>", ...)`). Pydantic: `ExtractRequest(artifact_ids: list[str])`, `FactLinkOut(to_fact: str, relation: str)`, `FactOut(fact_id, kind, status, summary, skills, confidence, chunk_ids, links)`, `ExtractResponse(facts: list[FactOut])`. `_make_chat_fn(settings, model_wanted)` COPY from learn.py:124-138. `@router.post("/work/extract", response_model=ExtractResponse)` → `post_extract`: blank/whitespace-only ids filtered → empty after filtering → 422 "artifact_ids must not be empty"; `> MAX_EXTRACTION_ARTIFACTS` → 422; call `run_extraction(artifact_ids=..., db_path=..., chat_fn=..., career_fn=no_career, model=model_wanted)` with the comment `# D5 handoff: deliverable 5 replaces no_career with the read_career_context(db_path) filler`; map `ExtractionValidationError`→502, `ExtractionTooLargeError`→413, `UnknownArtifactError`→404, `EmptyExtractionError`→422, `MetaAPIError`→502, generic `ValueError`→500 — in exactly this order (all four orchestrator errors subclass `ValueError`, so their branches precede the generic one). Response maps dataclasses to Pydantic outs preserving fact order.
- **PATTERN**: MIRROR `post_explain` (learn.py:141-175) + `post_query` mapping order (query.py:164-174).
- **IMPORTS**: `functools`? no — direct `no_career` reference; `logging`, `fastapi (APIRouter, HTTPException, status)`, `pydantic (BaseModel)`, `app.core.config.get_settings`, `app.core.meta_client (DEFAULT_META_MODEL, MetaAPIError, chat_completion)`, `app.llm.extraction (EmptyExtractionError, ExtractionTooLargeError, ExtractionValidationError, MAX_EXTRACTION_ARTIFACTS, UnknownArtifactError, no_career, run_extraction)`.
- **GOTCHA**: (1) Orchestrator error types (`UnknownArtifactError`, `EmptyExtractionError`, `ExtractionTooLargeError`, `ExtractionValidationError`) must ALL be defined in `llm/extraction.py` and ALL subclass `ValueError` — router orders branches most-specific-first: `ExtractionValidationError`→502, `ExtractionTooLargeError`→413, `UnknownArtifactError`→404, `EmptyExtractionError`→422, `MetaAPIError`→502, `ValueError`→500. (2) PRD §10 response keys are `fact_id`/`chunk_ids`/`to_fact` — Pydantic field names must match EXACTLY (no aliases). (3) Status code is 200, not 201 (PRD shows no 201 for this endpoint).
- **VALIDATE**: `cd backend && uv run ruff check app/api/work.py && uv run ruff format --check app/api/work.py`

### UPDATE backend/app/main.py

- **IMPLEMENT**: ADD `from app.api.work import router as work_router` + `app.include_router(work_router, prefix="/api/v1")` beside the existing five registrations.
- **PATTERN**: MIRROR lines 14-19 + 54-58 (import block + registration block).
- **IMPORTS**: `app.api.work.router`.
- **GOTCHA**: Keep alphabetical-ish grouping (health, ingest, learn, query, retrieval, work) — append after retrieval.
- **VALIDATE**: `cd backend && uv run pytest tests/test_app_boot.py -q`

### UPDATE frontend/src/api/types.ts

- **IMPLEMENT**: ADD `ArtifactSummary { id, title, source_type, created_at, chunk_count, fact_count }`, `ExtractRequest { artifact_ids: string[] }`, `ExtractLink { to_fact: string, relation: string }`, `ExtractFact { fact_id: string, kind: string, status: string, summary: string, skills: string[], confidence: number, chunk_ids: number[], links: ExtractLink[] }`, `ExtractResponse { facts: ExtractFact[] }`. Keep the file's "mirror backend Pydantic JSON exactly" contract — snake_case keys verbatim.
- **PATTERN**: MIRROR existing interfaces (types.ts:1-26) — no methods, no transformation.
- **IMPORTS**: None.
- **GOTCHA**: `kind`/`status`/`relation` stay `string` (not union literals) — backend owns the vocabularies; frontend unions would drift. Do NOT add camelCase aliases.
- **VALIDATE**: `cd frontend && npx tsc -b`

### CREATE frontend/src/api/artifacts.ts

- **IMPLEMENT**: `listArtifacts(): Promise<ArtifactSummary[]>` via `apiGet('/api/v1/artifacts')` with JSDoc line. (Single function — the WorkView picker needs only the list; detail fetching stays with the future Capture view.)
- **PATTERN**: MIRROR `learn.ts` `listExplanations` (bare-path GET).
- **IMPORTS**: `apiGet` from `./client`, `ArtifactSummary` type from `./types`.
- **GOTCHA**: Path is `/api/v1/artifacts` (ingest router under the `/api/v1` prefix — verify in main.py:54-58 + ingest.py:158).
- **VALIDATE**: `cd frontend && npx tsc -b`

### CREATE frontend/src/api/work.ts

- **IMPLEMENT**: `postExtract(req: ExtractRequest): Promise<ExtractResponse>` via `apiPost('/api/v1/work/extract', req)` with JSDoc line.
- **PATTERN**: MIRROR `learn.ts` `postExplain`.
- **IMPORTS**: `apiPost` from `./client`, `ExtractRequest/ExtractResponse` types from `./types`.
- **GOTCHA**: POST (not PUT) — matches the new router's method.
- **VALIDATE**: `cd frontend && npx tsc -b`

### CREATE frontend/src/views/WorkView.tsx

- **IMPLEMENT**: Work view. State: `artifacts` (list from `listArtifacts` on mount via `useEffect`), `selected: Record<string, boolean>` (checkbox set), `result: ExtractResponse | null`, `statusFilter: 'all' | 'proposed' | 'rejected' | 'completed'`, `activeCitation: ChunkDetail | null`, `highlightedFact: string | null`, `loading`, `error`. Layout: (1) artifact picker fieldset (checkbox per artifact: title + source_type + chunk/fact counts; empty list → "No artifacts yet — capture notes first."); (2) "Extract" button (disabled when none selected or loading) calling `postExtract({artifact_ids: selectedIds})`; (3) results: status-filter chips (`aria-label="Filter: all|proposed|..."`, `aria-pressed`), fact cards each with kind badge, status badge, summary, skills chips, confidence (`Math.round(c*100)%`), chunk chips (`aria-label="Evidence chunk ${id}"` → `openCitation` via imported `getChunk`, MIRROR ChatView:52-59) + reasoning links (`aria-label="Reasoning link ${relation} to ${to_fact.slice(0,8)}"` → sets `highlightedFact` + scrolls via `document.getElementById('fact-${to_fact}')?.scrollIntoView()`); when the active status filter matches zero facts show the plain-text status line "No facts with this status." (never the error alert); (4) chunk panel MIRROR ChatView:110-128 (chunk id · artifact · span + text + Close); (5) error alert COPY LearnView:263-271; (6) empty-facts result → "Nothing extractable found in the selected artifacts." status line (200-with-[] is success, not error).
- **PATTERN**: MIRROR ChatView citation panel + LearnView async/error patterns; fact cards keyed by `fact_id` with `id={'fact-' + fact_id}` anchors for link navigation.
- **IMPORTS**: `react (useEffect, useState)`, `../api/artifacts (listArtifacts)`, `../api/work (postExtract)`, `../api/query (getChunk)`, types `ArtifactSummary, ChunkDetail, ExtractFact, ExtractResponse`.
- **GOTCHA**: (1) Fetch artifacts once on mount; the extract POST must send ids in STABLE order (sort selected ids) so repeated extractions are comparable. (2) `highlightedFact` styling must be additive (ring/bold class), never hiding other cards. (3) Loading disables ALL action buttons (extract, filters stay enabled — filtering is local).
- **VALIDATE**: `cd frontend && npx tsc -b`

### UPDATE frontend/src/App.tsx

- **IMPLEMENT**: ADD `import WorkView from './views/WorkView'`; set the `work` blurb to `''`; extend the main ternary to `view === 'chat' ? <ChatView /> : view === 'learn' ? <LearnView /> : view === 'work' ? <WorkView /> : <p>{active.blurb}</p>`.
- **PATTERN**: MIRROR the existing `learn` wiring (App.tsx:4, 9, 42).
- **IMPORTS**: `./views/WorkView`.
- **GOTCHA**: Keep the `VIEWS` array order unchanged (nav order is a UX contract now); only the blurb + branch change.
- **VALIDATE**: `cd frontend && npx tsc -b && npm test -- --run src/App.test.tsx 2>/dev/null || npm test -- --run`

### CREATE backend/tests/test_extraction.py

- **IMPLEMENT**: Orchestration tests over stubbed seams + tmp DBs. Helpers: `_chat_for(payloads, record)` MIRROR test_explainer.py:42-50 (budget-aware arity `(messages, max_tokens)`); `_seed_artifacts(db) -> tuple[artifact_ids, chunk_ids]` seeding two artifacts with known chunks via the REAL `ingest_source` with `embed_fn=lambda texts: [[0.0]*384 ...]`? NO — simpler: seed via `store_artifact` directly with zero-vectors (MIRROR how test_ingest_pipeline seeds; avoids embedder import entirely). Tests: (1) happy path — 2 artifacts → canned `{"facts": [...]}` with 3 facts + 2 links → assert fact ids are 32-hex uuids, chunk_ids echoed, links translated to `to_fact` ids, budgets recorded `[16384]`, single chat call, career block absent from prompt when `no_career`; (2) `persist_fn` stub captures items (assert model + `extract-v1` prompt_version passed); (3) malformed JSON → `ExtractionValidationError`, persist NOT called; (4) unknown chunk_id → raises naming the id; (5) fact with empty `chunk_ids` → raises; (6) blank summary → raises; (7) confidence out of range → raises (Pydantic); (8) bad kind/status/relation → raises; (9) dangling link index → raises; (10) self-link → raises; (11) `{"facts": []}` → empty result, persist NOT called, no error; (12) unknown artifact id → `UnknownArtifactError` WITHOUT calling chat; (13) over-char-cap (seed a >30k-char artifact) → `ExtractionTooLargeError` without calling chat; (14) career injection — `career_fn` returning filled `CareerContext` → assert target-position text present in the system messages; (15) tmp-DB atomicity MIRROR test_explainer.py:240-269 — success persists facts+fact_chunks+fact_links rows (assert join counts), subsequent failing call persists nothing new (row counts unchanged); (16) repository rollback — call `create_facts` DIRECTLY on a tmp DB with one item whose `FactLinkCreate.to_fact_id` does not exist → assert the call raises (FK violation) and `facts`, `fact_chunks`, `fact_links` all hold zero rows (proves in-transaction rollback, not just pre-write validation); (17) duplicate ids processed once — `run_extraction` with `[a, a, b]` → single chat call whose recorded user message contains a's chunk passages exactly once; (18) cap boundary — chunks totaling exactly `MAX_EXTRACTION_CHARS` (import the constant) → chat called with canned valid JSON; one char more → `ExtractionTooLargeError`, chat not called; (19) duplicate link triples — model output repeating one `(from, to, relation)` triple through the real-persist tmp-DB path → exactly one `fact_links` row; (20) zero-chunk artifact through the real path — `store_artifact` with empty chunks/embeddings lists, real `run_extraction` → `EmptyExtractionError`, chat not called.
- **PATTERN**: MIRROR test_explainer.py structure (stub factories, `asyncio.run`, tmp-DB via `init_db`).
- **IMPORTS**: `asyncio`, `json`, `pathlib.Path`, `pytest`, `app.db.connection (connect, init_db)`, `app.db.artifacts.store_artifact`, `app.ingest.chunker.chunk_text`, `app.llm.extraction (...)`.
- **GOTCHA**: (1) `store_artifact` needs embeddings dim 384 — pass `[[0.0]*384 for _ in chunks]`; never import the real embedder (no model download in tests). (2) `chunk_text` on the seed content gives spans — reuse its output for `store_artifact(chunks=...)`. (3) Assert the recorded budget equals `EXTRACTION_MAX_TOKENS`, not a hardcoded number (import the constant).
- **VALIDATE**: `cd backend && uv run pytest tests/test_extraction.py -q`

### CREATE backend/tests/test_work_api.py

- **IMPLEMENT**: API contract tests MIRRORING test_learn_api.py: `_isolated_settings` autouse fixture (patch `app.api.work.get_settings` + `app.main.get_settings`), `_client` (tmp DB + TestClient), `_seeded_client(seed_fn)` seeding artifacts via `store_artifact` + zero-vectors. Tests: (1) happy path — stub `app.api.work.run_extraction` to return an `ExtractedResult` with 2 facts/1 link → assert 200 + exact key sets (`fact_id/kind/status/summary/skills/confidence/chunk_ids/links`, link keys `to_fact/relation`); (2) `artifact_ids: []` → 422; missing body → 422; (3) `run_extraction` raising `UnknownArtifactError` → 404; (4) raising `EmptyExtractionError` → 422; (5) raising `ExtractionTooLargeError` → 413; (6) raising `ExtractionValidationError` → 502; (7) raising `MetaAPIError` → 502; (8) real-`run_extraction` + stubbed `app.api.work.chat_completion` round-trip — seed one artifact with a dev-log paragraph, canned extraction JSON with proposed/rejected/completed split → assert 200, facts persisted in DB (query `facts`/`fact_links` counts via `connect`), response `fact_id`s match stored rows; (9) missing `MODEL_API_KEY` (env deleted) with REAL chat path → 502 (MIRROR the missing-key closure behavior — requires unstubbed `_make_chat_fn`, so seed + call without stubbing `chat_completion`); (10) whitespace-only ids — `{"artifact_ids": ["   ", ""]}` with `run_extraction` stubbed to raise AssertionError if called → 422 "artifact_ids must not be empty" (proves router-side blank filtering, orchestrator never reached).
- **PATTERN**: MIRROR test_learn_api.py:42-67 + 256-270 fixtures; stub-by-name convention from the router docstring.
- **IMPORTS**: `json`, `pathlib.Path`, `pytest`, `fastapi.testclient.TestClient`, `app.core.config.Settings/get_settings`, `app.core.meta_client.MetaAPIError`, `app.db.connection (connect, init_db)`, `app.db.artifacts.store_artifact`, `app.ingest.chunker.chunk_text`, `app.llm.extraction (ExtractedFact, ExtractedLink, ExtractedResult, ...)`, `app.main.create_app`.
- **GOTCHA**: (1) The `_isolated_settings` fixture MUST patch `app.api.work.get_settings` (new module path) or tests hit the real DB path. (2) Test 9 needs `monkeypatch.delenv("MODEL_API_KEY")` AFTER `_client` sets it — order matters. (3) `store_artifact` requires `content_hash`/`origin_json`/`created_at` — pass `"h"`, `"{}"`, `"2026-11-03T00:00:00+00:00"`.
- **VALIDATE**: `cd backend && uv run pytest tests/test_work_api.py -q`

### CREATE frontend/src/api/artifacts.test.ts + frontend/src/api/work.test.ts

- **IMPLEMENT**: `artifacts.test.ts`: `listArtifacts` GETs `http://localhost:8000/api/v1/artifacts` (MIRROR learn.test.ts:63-68). `work.test.ts`: `postExtract` POSTs `{artifact_ids: [...]}` to `http://localhost:8000/api/v1/work/extract` with method/body assertions (MIRROR learn.test.ts:29-38) + non-OK rejection test (MIRROR learn.test.ts:56-61). Both files use the `mockFetch` + `afterEach(vi.unstubAllGlobals/vi.unstubAllEnvs)` shape.
- **PATTERN**: MIRROR learn.test.ts:14-21 helpers + citation URLs `http://localhost:8000` (default `VITE_API_URL` absent in tests).
- **IMPORTS**: `vitest`, the client under test.
- **GOTCHA**: `vi.stubGlobal('fetch', ...)` per test + `afterEach` un-stub — missing the unstub leaks mocks across files in the same worker.
- **VALIDATE**: `cd frontend && npm test -- --run src/api/work.test.ts src/api/artifacts.test.ts`

### CREATE frontend/src/views/WorkView.test.tsx

- **IMPLEMENT**: View tests MIRRORING LearnView.test.tsx factories + `mockFetchSequence` (mount fetch → `listArtifacts` payload; extract click → `postExtract` payload; chunk-chip click → `getChunk` payload). Factories: `artifactSummary(overrides)`, `extractFact(overrides)` (3 facts: proposed/rejected/completed + 1 link), `extractResponse(overrides)`, `chunkDetail(overrides)`. Tests: (1) mount lists artifacts with checkboxes; (2) extract disabled with none selected; (3) select two + Extract → POST body `{artifact_ids: [sorted ids]}` + fact cards render (kind/status/summary/skills/confidence); (4) status filter chips narrow the cards (`Filter: completed` shows 1 card; `Filter: all` restores 3); (5) evidence chip opens the chunk panel with full text + Close dismisses; (6) reasoning-link click highlights the target card (`fact-<id>` element gains the highlight class); (7) extract returning `{facts: []}` shows the nothing-extractable status line (not an error); (8) failed extract shows `role="alert"` + Dismiss clears it; (9) empty artifact list shows the capture-first hint; (10) zero-match filter — extract payload containing only `completed` facts, apply the `proposed` filter → the "No facts with this status." line renders, zero fact cards render, no error alert appears.
- **PATTERN**: MIRROR LearnView.test.tsx (factories, fetch queue, `fireEvent`/`screen` queries by aria-label).
- **IMPORTS**: `vitest`, `@testing-library/react`, types, `WorkView`.
- **GOTCHA**: (1) `listArtifacts` fires on mount — EVERY test's fetch queue must start with the artifacts payload (even error-path tests). (2) Query chips/cards by `aria-label`/`role`, never by CSS class (classes are styling, labels are contract). (3) `scrollIntoView` is unimplemented in jsdom — assert the highlight class only, do not call or stub `scrollIntoView` in tests (the view guards the call with `?.` optional chaining so jsdom never throws).
- **VALIDATE**: `cd frontend && npm test -- --run src/views/WorkView.test.tsx`

---

## TESTING STRATEGY

Backend uses pytest (`testpaths = ["tests"]`, `pythonpath = ["."]`); frontend uses vitest + Testing Library. No test may touch the network or download the fastembed model: LLM calls are stubbed (`_chat_for` queues, `monkeypatch.setattr` on by-name seams), embeddings are zero-vectors passed to `store_artifact` directly.

### Unit Tests

`tests/test_extraction.py` (20 tests, see task spec): orchestration over stubbed `chat_fn`/`career_fn`/`persist_fn` — happy-path shape + single-call + budget assertion, `persist_fn` capture of model + `extract-v1`, all eight validation failures (malformed JSON, unknown chunk, empty chunk_ids, blank summary, bad confidence, bad enum, dangling link, self-link), empty-facts legitimacy, pre-chat guards (unknown artifact, over-cap), career-block injection, the tmp-DB atomicity pair (success writes all three tables, failure writes nothing), the direct-`create_facts` rollback test (bad link → raises, all three tables zero rows), duplicate-id dedupe, exact-cap boundary, duplicate-link dedupe, and the zero-chunk real-path test. `tests/test_work_api.py` unit-ish half: stubbed-`run_extraction` status-matrix tests (200 shape, 422/404/413/502 mapping) plus the whitespace-only-ids 422 test.

Design fixtures after `test_explainer.py` (`_chat_for` queue+record, `asyncio.run`) and `test_learn_api.py` (`_isolated_settings`, `_client`, `_seeded_client`).

### Integration Tests

`tests/test_work_api.py` round-trip tests: real `run_extraction` + stubbed `chat_completion` over a seeded artifact — assert the 200 body AND the stored `facts`/`fact_chunks`/`fact_links` rows agree (response `fact_id`s present in DB, link endpoints resolve). The missing-key test exercises the real `_make_chat_fn` closure end-to-end (→ 502). Frontend `WorkView.test.tsx`: full mount → select → extract → filter → provenance → link-highlight flows over a `mockFetchSequence` queue.

### Edge Cases

- `artifact_ids: []`, whitespace-only ids, duplicate ids (dedupe, single processing), >20 ids (422).
- Unknown artifact id mixed with known ones (404 naming the missing ids, nothing persisted, chat never called).
- Artifact with zero chunks (422 — defensive; ingest normally guarantees ≥1).
- Total chars exactly at cap (allowed) vs. one over (413).
- Model returns `{"facts": []}` (200, persist never called) vs. model returns non-JSON (502).
- Fact citing a chunk from an artifact NOT in the request (502 — cross-request evidence smuggling).
- Duplicate `(from, to, relation)` triples (deduped, single link row).
- Repeat extraction over the same artifacts (fresh fact ids, no dedup — assert row count doubles).
- Frontend: empty artifact list, empty facts result, failed extract + dismiss, filter with zero matches (shows "no facts with this status", not an error).

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

Every command or block MUST state its exact pass signal on an `Expected:` line (exit code plus the key output, count, or observation that proves success — e.g. `Expected: exit 0, "11 passed"`, `Expected: exit 0, docs:200`). A check whose passing output is not specified cannot confirm anything; do not write checks you cannot describe passing.

### Level 1: Syntax & Style

```bash
cd backend && uv run ruff check . && uv run ruff format --check .
```
Expected: exit 0, `All checks passed!` + `N files already formatted` (ruff prints the checked file count; zero errors).

```bash
cd backend && uv run mypy app
```
Expected: exit 0, `Success: no issues found in M files` (non-strict config; M grows by 3 new modules: extraction, facts, work).

```bash
cd frontend && npm run lint
```
Expected: exit 0, oxlint reports 0 errors and 0 warnings.

### Level 2: Unit Tests

```bash
cd backend && uv run pytest tests/test_extraction.py tests/test_work_api.py -q
```
Expected: exit 0, `NN passed` (NN = 20 extraction + 10 API = 30 tests; exact count asserted by the executor against the files).

```bash
cd frontend && npm test -- --run src/api/work.test.ts src/api/artifacts.test.ts src/views/WorkView.test.tsx
```
Expected: exit 0, `Test Files 3 passed`, `Tests NN passed` (2–3 client tests per file + 10 view tests; zero failures).

### Level 3: Integration Tests

```bash
cd backend && uv run pytest -q
```
Expected: exit 0, full suite passes (pre-existing ~150+ tests plus the 30 new ones; zero failures, zero regressions in learn/query/ingest suites).

```bash
cd frontend && npm test -- --run
```
Expected: exit 0, all test files pass (pre-existing ChatView/LearnView/client suites plus the 3 new files; zero failures).

```bash
cd frontend && npm run build
```
Expected: exit 0, `tsc -b` clean + `vite build` emits `dist/` (proves the WorkView/App wiring typechecks and bundles).

### Level 4: Manual Validation

Performer rule: `agent` = executable in this environment via in-process `TestClient` with a scratch DB (the sanctioned equivalent procedure — sandboxed sessions deny local-server sockets, so `uvicorn`/`vite` dev servers cannot run here); `human` = requires a real browser/device/account. The executor MUST run every `agent` step.

**L4-1 [agent] Stubbed end-to-end extract over a scratch DB.** Steps: (1) write `/tmp/extract_probe.py`: `init_db` a scratch DB, `store_artifact` one dev-log artifact (3 approaches discussed, 1 implemented — reuse the PRD US-6 shape) with zero-vector embeddings, (2) `TestClient(create_app())` with `DATABASE_PATH` pointed at the scratch DB, stub `app.api.work.chat_completion` with a canned valid extraction JSON (1 completed, 1 rejected with `rejected_because` link, 1 proposed), `POST /api/v1/work/extract`, (3) assert 200 + fact/link counts + query `facts`/`fact_links` row counts via `connect`. Expected: 200, `len(facts) == 3`, link `to_fact` resolves to a returned `fact_id`, DB holds exactly 3 facts / ≥3 fact_chunks / 1 fact_link.

**L4-2 [agent] Live extraction over a real pasted dev log (Phase 2 gate item 3).** Steps: (1) same harness as L4-1 but with the REAL `MODEL_API_KEY` from the repo `.env` and NO chat stub, (2) seed artifact content = a ~600-word realistic dev log with at least one completed fix, one rejected approach with an explicit reason, and one open idea (write it fresh for the probe — no employer/client data), (3) `POST /api/v1/work/extract` and inspect the returned facts. Expected: 200 within ~60s; at least one fact of each status with the completed fix matching the log's explicit completion statement, the rejected approach carrying its stated reason, NO invented outcomes (every summary traceable to a cited chunk — spot-check 2 facts by fetching their chunk_ids via `GET /api/v1/chunks/{id}` and confirming the text supports the summary); record the JSON + inspection notes in the execution report as the gate evidence.

**L4-3 [agent] Guard matrix probe.** Steps: same stubbed harness; send (a) `{"artifact_ids": []}` → 422, (b) unknown id → 404 with the id in `detail`, (c) 21 ids → 422, (d) stub chat returning a fact with an unknown chunk_id → 502 + `facts` table still empty. Expected: all four statuses exact; (d) leaves zero rows (atomicity).

**L4-4 [agent] Char-cap probe.** Steps: seed one artifact with >30,000 chars of repetitive dev-log text; stub chat with a boom function (raises if called); `POST /api/v1/work/extract`. Expected: 413 with chars/cap in `detail`; boom never called.

**L4-5 [human] Work view click-through (requires a running deployment or local dev servers).** Steps: (1) start backend (`uv run uvicorn app.main:create_app --factory --reload`, from `backend/`) and frontend (`npm run dev`, from `frontend/`), open `http://localhost:5173`, (2) capture or seed ≥1 artifact (via API `POST /api/v1/artifacts` if Capture view is still a stub), (3) click Work → check two artifacts → Extract, (4) click each status filter chip, (5) click one evidence chip → read the chunk panel → Close, (6) click one reasoning link → confirm the target card highlights and scrolls into view. Expected: picker lists artifacts with counts; results render as kind/status-badged cards; filters narrow without refetching; chunk panel shows full chunk text with artifact + span; link click highlights the referenced card.

**Local-server block confirmation (sandbox rule):** the executor attempts ONE blocked local-server launch per deliverable to confirm the sandbox block and records the exact error (e.g. `uv run uvicorn ...` → socket/bind denial); never retry it. L4-1–L4-4 are the equivalent in-process procedures.

### Level 5: Additional Validation (Optional)

**Browser E2E via Playwright MCP: `NOT_PERFORMED`.** Reason: the sanctioned browser procedure targets the deployed app URL, and deployment is out of this deliverable's scope (no deploy step, no freshness to verify — an outdated deployment would validate nothing). Criterion: `UNVERIFIED` pending deployment. Manual steps for the deploy owner: after the next deploy, (1) verify freshness (fetch `/api/v1/health` + confirm the Work nav renders), (2) run the L4-5 click-through against the deployed URL, (3) record a screenshot of one extracted fact card with its provenance panel open.

---

## MANUAL VERIFICATION CHECKLIST

Label each item `agent` or `human` (same performer rule as Level 4). Each item MUST give numbered steps and the exact expected observable result — never a bare "verify X works."

- [ ] [agent] Stubbed extract persists correctly: (1) run `/tmp/extract_probe.py` from L4-1; expected: exit 0, prints `200 facts=3 links=1 db_facts=3 db_links=1`.
- [ ] [agent] Live extract splits statuses correctly (gate item 3): (1) run the L4-2 live probe; (2) fetch 2 cited chunks via `GET /api/v1/chunks/{id}`; expected: 200 with ≥1 proposed + ≥1 rejected + ≥1 completed fact, each spot-checked summary supported by its chunk text, no invented outcomes; JSON + notes recorded in the execution report.
- [ ] [agent] Guard matrix + atomicity: (1) run the L4-3 probe; expected: 422/404/422/502 in order, `SELECT COUNT(*) FROM facts` == 0 after the 502 case.
- [ ] [agent] Char cap enforced pre-chat: (1) run the L4-4 probe; expected: 413 mentioning chars and cap; chat stub never invoked.
- [ ] [agent] Career seam is inert by default: (1) in the L4-1 harness, record the chat messages; expected: exactly 1 system message (no career block) when `career_fn=no_career`; (2) unit test 14 covers the filled-career case — expected: `pytest tests/test_extraction.py -q -k career` passes.
- [ ] [agent] No-dedup documented behavior: (1) in the L4-1 harness, POST the same `artifact_ids` twice with the same canned JSON; expected: both 200, second response has all-new `fact_id`s, `facts` row count doubles.
- [ ] [human] Work view click-through: (1)–(6) run the L4-5 steps; expected: picker → extract → filter → provenance → link-highlight all behave as specified, no console errors.
- [ ] [agent] Docs/config reflection: (1) `grep -rn "no_career" backend/app/api/work.py` shows the `# D5 handoff` comment; (2) `grep -c "extract-v1" backend/app/core/grounding.py` is ≥1; expected: both greps hit, proving the D5 handoff and prompt-version wiring are in place.

## ROLLBACK CONSIDERATIONS

- Revert safely: the deliverable is purely additive (3 new backend modules, 1 new router registration line, 2 read-helper functions, 5 new frontend files, 1 App.tsx branch). Rollback = `git revert` the merge (or delete the new files + drop the `main.py`/`App.tsx`/`types.ts` hunks) — no migration to undo (the `facts`/`fact_chunks`/`fact_links` tables already exist in schema v1 and stay empty).
- Data handling: extracted facts are derived data. A rollback after live use leaves orphaned fact rows referencing valid chunks — harmless (no reader outside the Work view yet), but a `DELETE FROM fact_links; DELETE FROM fact_chunks; DELETE FROM facts;` cleanup is one statement if a pristine DB is wanted. No artifact/chunk data is ever mutated by extraction.
- Config: no new env vars, no dependency changes — nothing to un-configure.

## ACCEPTANCE CRITERIA

Each criterion MUST name the check that proves it: the validation level/command, the test file, or the manual-checklist item — plus the exact expected result. A criterion with no verification named is an incomplete plan.

- [ ] `POST /work/extract` returns the PRD §10 shape (`fact_id/kind/status/summary/skills/confidence/chunk_ids/links[{to_fact, relation}]`) — proven by L2 `test_work_api.py` happy-path test asserting exact key sets + 200.
- [ ] Extraction persists facts + evidence + links atomically in one transaction — proven by L2 `test_extraction.py` tmp-DB atomicity test (success writes all three tables; failure writes nothing) + the direct-`create_facts` rollback test (bad link → raises, all three tables zero rows) + L4-1 probe (`db_facts=3 db_links=1`).
- [ ] Every fact is grounded (≥1 valid chunk) and every link resolves; any violation fails the whole call with 502 and persists nothing — proven by L2 `test_extraction.py` validation-failure tests (8 cases) + L4-3 probe case (d).
- [ ] Input guards return the specified statuses (422 empty/whitespace/over-count/zero-chunk, 404 unknown ids, 413 over-cap) without calling the model — proven by L2 `test_work_api.py` matrix tests (incl. the whitespace-only-ids test) + L2 `test_extraction.py` dedupe/boundary/zero-chunk tests + L4-3/L4-4 probes.
- [ ] Empty extraction (`{"facts": []}`) is a 200 success persisting nothing, distinct from model failure — proven by L2 `test_extraction.py` empty-facts test + WorkView test 7 (status line, not error).
- [ ] Live extraction over a real dev log shows a correct proposed/rejected/completed split and a traversable reasoning chain with no invented outcomes (Phase 2 gate item 3) — proven by the L4-2 live probe + manual-checklist live-extract item (JSON + inspection notes in the execution report).
- [ ] Repeat extraction creates fresh per-call records (no dedup, the documented F-10 limitation) — proven by the manual-checklist no-dedup item (ids differ, row count doubles).
- [ ] Career seam is inert by default and injects when filled (D5 handoff ready) — proven by L2 `test_extraction.py` career tests (default absent + filled present) + manual-checklist seam item (`# D5 handoff` comment present).
- [ ] Work view renders picker → extract → status filter → provenance drill-down → link navigation — proven by L2 `WorkView.test.tsx` (10 tests, incl. the zero-match filter test) + the [human] click-through checklist item (L4-5).
- [ ] All validation commands pass with zero errors — proven by L1 (ruff + mypy + oxlint), L2 (new suites), L3 (full pytest + vitest + build) each meeting its `Expected:` line.
- [ ] No regressions in existing functionality — proven by L3 full-suite runs (learn/query/ingest/retrieval suites green alongside the 30 new backend + new frontend tests).
- [ ] Code follows project conventions (thin router, grounding contracts shared, by-name seams, frontend types mirroring Pydantic keys) — proven by L1 lint/typecheck + reviewer spot-check of the CONTEXT REFERENCES pattern list during `/review-plan` and execution review.

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

**Design decisions and rationale:**

1. **Single LLM call, not per-chunk.** Reasoning links (`decided`, `implemented_by`, `resulted_in`) inherently span chunks — per-chunk calls would fragment chains at chunk boundaries and multiply Meta API cost/latency. The 30k-char cap keeps the single prompt inside a comfortable context window; chunked extraction is deferred until a measured failure (same posture as rerank/HyDE).
2. **Ephemeral link indices in model output, uuids assigned in code.** The model must never invent database IDs (it would hallucinate plausible-but-wrong ids). `{"to": 2}` indices are trivially validatable (`0 <= to < len(facts)`, `to != self`) and the orchestrator translates them to pre-generated uuids in one pass.
3. **Fail-closed validation.** Any ungrounded fact, unknown chunk ID, or invalid link aborts the whole call (502, zero rows) rather than dropping bad items and returning partial results. Rationale: silent dropping would hide model failures and produce fact sets whose completeness the user cannot trust; the explainer's no-partial-lessons atomicity is the precedent. The one exception is the honest empty result (`{"facts": []}` → 200), which is a complete answer, not a failure.
4. **413 over cap, not truncation.** Silently truncating a dev log could drop the one completed fix the user cares about. Rejection with counts + a split-across-calls hint is honest and keeps the PRD response shape unchanged (no `truncated` flag leaking into the contract).
5. **Status 200, not 201.** Extraction is a computation that returns persisted facts (like `/query` returning persisted turns with 200), not a resource creation with a Location-style semantic; PRD §10 shows no 201 for it.
6. **Career seam mirrors the deliverable-1 profile/memory seams** (`no_career()` default + pre-rendered block + router one-line handoff) so deliverable 5 lands as a filler + one-line rewire with zero extraction-logic changes.
7. **`kind: skill` facts vs. per-fact `skills` arrays.** Both exist per PRD §10: the array captures demonstrated skills on any fact; a `skill`-kind fact reifies a standalone demonstrated capability (summary names it, array repeats it). The prompt defines this so the model fills both consistently.
8. **Frontend `artifacts.ts` is list-only.** The WorkView picker needs just the list; artifact detail fetching belongs to the future Capture view. Kept minimal per YAGNI, but placed in its own module so Capture can extend it without touching `work.ts`.

**Trade-offs accepted:**

- Single-call cap (30k chars / 20 artifacts) rejects very large extractions instead of handling them — acceptable for MVP pasted logs (typically 2–10k chars); revisit only on measured failure.
- No extraction re-run detection: accidental double-clicks create duplicate fact sets (documented F-10 limitation). The Work view disables Extract while loading to prevent the common case; true dedup is out of scope.
- Relation-direction semantics are prompt-defined, not code-enforced beyond enum membership — code cannot cheaply verify that a `decided` link points from a problem to a decision. Mitigated by explicit prompt definitions + the live-inspection gate (L4-2).

**Confidence score: 8/10 for one-pass execution success.** The architecture is the third instance of a proven pattern (qa → explainer → extraction), all seams and fixtures have exact precedents with line numbers, and the riskiest unknowns (prompt quality on real logs, Spark token burn) are isolated to one live probe with a generous budget. The two residual risks are model-output strictness causing live 502s on messy logs (mitigated by explicit JSON instructions + temp 0.0) and the 30k cap proving too small for real pastes (mitigated by the honest 413 + easy constant bump).

---

## Revision History

### Cycle 1

Findings addressed (from `.agents/plans/reviews/work-extraction-endpoint-work-view-plan-review.md`, review 1):

1. "Add a repository-level test in `test_extraction.py` that calls `create_facts` with an item whose link targets a nonexistent fact id and asserts zero rows in `facts`/`fact_chunks`/`fact_links`, and cite it in the atomicity acceptance criterion."
2. "Add test tasks for the listed edge cases that currently lack one: whitespace-only and duplicate artifact ids (dedupe), total chars exactly at cap (allowed) vs. cap+1 (413), duplicate `(from,to,relation)` link triples (single row), and a zero-chunk artifact through real `run_extraction` (`EmptyExtractionError`)."
3. "Add the 'no facts with this status' zero-match message to the WorkView IMPLEMENT spec and a WorkView test for it, since the edge-case list claims it but neither task includes it."

What changed:

- `CREATE backend/tests/test_extraction.py`: added tests (16) direct-`create_facts` rollback, (17) duplicate-id dedupe, (18) exact-cap vs cap+1 boundary, (19) duplicate-link-triple dedupe, (20) zero-chunk artifact through real `run_extraction`. Suite is now 20 tests.
- `CREATE backend/tests/test_work_api.py`: added test (10) whitespace-only ids → 422 with orchestrator-never-called proof. Suite is now 10 tests.
- `CREATE frontend/src/views/WorkView.tsx`: IMPLEMENT now specifies the plain-text "No facts with this status." line when the active filter matches zero facts (never the error alert).
- `CREATE frontend/src/views/WorkView.test.tsx`: added test (10) zero-match filter. Suite is now 10 tests.
- Counts updated everywhere they appear: TESTING STRATEGY unit-tests paragraph, L2 backend Expected (20 + 10 = 30), L2 frontend Expected (10 view tests), L3 full-suite Expected (30 new backend tests), and four acceptance criteria (atomicity now cites the rollback test; guards cite the new matrix/boundary tests; WorkView cites 10 tests; no-regressions cites 30 new backend tests). Verified via grep that no stale counts (15/24/9) remain.
- Not done: nothing — all three corrections applied in full. No escalations, no requirement redefinitions.


