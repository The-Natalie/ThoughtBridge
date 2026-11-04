# Feature: tb-conversation-memory-adapter

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Automatic conversation memory (PRD F-12): every in-app conversation (grounded Q&A, learning, interview practice) is indexed into the standard retrieval pipeline through a `tb_conversation` source adapter, so a follow-up like "what did we decide about the retrieval architecture?" retrieves the earlier discussion with role labels intact. Each turn-append (one `POST /query`, `/practice/question`, or `/practice/answer` call) becomes one `tb_conversation` SourceArtifact whose content is the role-tagged transcript (`User:` / `Assistant:` prefixes), chunked and embedded through the existing `ingest_source` pipeline. Retrieval results and citations carry a `source_type` so the UI can render "from a ThoughtBridge conversation" labels. Work extraction, evidence-mode Q&A, and interview-experience evaluation gain a role-asymmetric grounding rule (user turns are candidate evidence like pasted notes; assistant turns are conversational context only, never evidence of the user's actions or accomplishments; completion needs explicit user statements). `DELETE /conversations/{id}` removes the conversation, its turns, its artifacts, and all derived rows left with no remaining support, reusing a connection-level artifact-cascade helper that deliverable 4's `DELETE /artifacts/{id}` will reuse. `GET /conversations` and `GET /conversations/{id}` already exist and are unchanged.

## User Story

As a user who discusses decisions inside ThoughtBridge
I want past in-app conversations to be automatically saved and retrievable with role labels
So that decisions and insights from those discussions stay available without manual importing

## Problem Statement

Turn persistence exists (every query/practice call stores ordered, role-labeled turns), and the conversation read endpoints exist — but turns are invisible to retrieval: hybrid search never sees them, extraction cannot treat user statements as evidence, nothing labels conversation-derived content, and conversations cannot be deleted. The Phase 3 validation gate ("an in-app discussion is retrievable by a follow-up question with role labels intact") cannot pass.

## Scope

- In scope: `adapt_conversation` adapter + `index_conversation_turns` helper; synchronous indexing hooks in the query router (1 path) and practice router (3 paths: question, answer, NULL-conversation recovery); `source_type` on `CitationOut`/`SearchHitOut`/`ChunkOut` via a batched chunk→artifact lookup; role-asymmetry prompt rule on extraction + evidence-mode Q&A + interview-experience evaluation, plus the `extract-v1`→`extract-v2` version bump; `DELETE /conversations/{id}` with full derived cascade; ChatView "from a ThoughtBridge conversation" citation badge; disclosure line added to LearnView/WorkView (Chat/Practice/Interview already have it); all tests listed below.
- Out of scope: `DELETE /artifacts/{id}` endpoint (deliverable 4 — but this plan builds the reusable cascade core it will call); delete-then-query residue tests and the mandatory no-evidence-mining test (deliverable 4 — this plan adds deterministic contract tests only); checkpoint-prompt button + cross-view provenance/visibility unification (deliverable 5 — this plan renders the conversation label verbatim in ChatView only); rerank/HyDE (deliverable 6, default skip); backfill indexing of pre-existing conversations (documented limitation, fresh conversations only); scored career ranking; editing/redaction; automated scheduling.

## Solution Statement

Mirror the established adapter→pipeline→repository slice: a pure `adapt_conversation` function in `ingest/adapters.py` (no I/O, like `adapt_text`) producing an `AdaptedSource` with `source_type="tb_conversation"` and role-tagged content; a thin `index_conversation_turns` helper in a new `ingest/conversation_memory.py` that delegates to the unchanged `ingest_source` pipeline; one artifact per turn-append recorded in `origin` JSON (`adapter`, `conversation_id`, `kind`, turn idx range) so no schema migration is needed and chunk IDs stay stable forever (no re-indexing, no churn for fact/attempt references). Routers call the helper by name after turn persistence (stub seam for API tests). Retrieval labeling is additive: a new `get_chunk_source_types` batched JOIN fills a new `source_type` field on the three citation/hit shapes. One shared role-asymmetry paragraph keys the extraction, evidence-Q&A, and experience-evaluation prompts on the literal role tags, with an `extract-v2` prompt-version bump (QA/practice prompts are unversioned — only extraction records a prompt version). Deletion is a single-transaction repository cascade (`delete_conversation_cascade`) built on a connection-level artifact-cascade helper (`_delete_artifacts_cascade_conn`) that deliverable 4 reuses verbatim for `DELETE /artifacts/{id}`.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: Medium
**Primary Systems Affected**: backend `ingest/`, `db/`, `api/query.py`, `api/practice.py`, `api/retrieval.py`, `core/grounding.py`; frontend `api/types.ts`, `api/query.ts`, `views/ChatView.tsx`, `views/LearnView.tsx`, `views/WorkView.tsx`
**Dependencies**: none (all tables, routers, and pipeline pieces exist; `sqlite3` `json_extract` verified on the backend venv SQLite 3.54.1)
**Assumptions**: conversations table is append-only with stable IDs (TS-4, holds); `origin` JSON shape is free-form per adapter (holds — `adapt_upload` already varies keys); synchronous indexing latency (one local fastembed call over ~2 turns) is acceptable inside the request; pre-existing conversations stay unindexed (no backfill — stated limitation)

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `backend/app/ingest/adapters.py` (lines 34-61) - Why: `AdaptedSource` shape + `adapt_text` pure-function pattern that `adapt_conversation` mirrors; `SourceAdapter` protocol (line 44-49) already names `tb_conversation` as the expected plug-in
- `backend/app/ingest/pipeline.py` (lines 50-90) - Why: `ingest_source` contract (cap → chunk → dim-guard → embed → persist) that the memory helper delegates to unchanged; `IngestResult` return shape
- `backend/app/ingest/chunker.py` (lines 49-84) - Why: paragraph-aware packing — blank-line-separated turns usually chunk separately; overlap may mix adjacent turns (accepted, tags are inline)
- `backend/app/db/conversations.py` (lines 60-144) - Why: `append_turns` / `create_conversation_with_turns` signatures + "persist AFTER successful generation" rule; `list_conversations` (lines 183-199) for the lookup-side read style
- `backend/app/db/artifacts.py` (lines 50-94) - Why: `store_artifact` single-transaction persist (+ FTS-via-trigger, vec-row insert) that indexing inherits; `find_missing_artifact_ids` (lines 123-144) for the one-connection lookup style
- `backend/app/db/chunks.py` (lines 21-44) - Why: `get_chunks` batched-hydration style that `get_chunk_source_types` mirrors
- `backend/app/db/schema.sql` (lines 16-36, 45-54, 62-85, 136-152) - Why: artifacts/chunks DDL + FTS sync triggers + fact join tables + conversations/turns DDL with the exact FK cascade graph the deletion cascade relies on (`chunks.artifact_id` CASCADE, `turns.conversation_id` CASCADE, `attempts.conversation_id` SET NULL, `fact_chunks` double-CASCADE)
- `backend/app/api/query.py` (lines 96-210) - Why: `post_query` flow — turn tuple shape + persist block (lines 185-198) where the indexing hook slots in; conversation endpoints (lines 213-246) where DELETE joins them; exception ordering (validation 502 BEFORE generic ValueError 500)
- `backend/app/api/practice.py` (lines 216-247, 300-313) - Why: question-path turn persist + attempt creation order; answer-path persist + NULL-conversation recovery (line 304-310) whose discarded fresh id must now be captured for the indexing origin
- `backend/app/api/retrieval.py` (lines 31-50, 53-104) - Why: `SearchHitOut`/`ChunkOut` shapes gaining `source_type`; endpoint hydration style to extend
- `backend/app/core/grounding.py` (lines 19-51, 365-420) - Why: framing-constant style + `NumberedPassage` + extraction contract block where the role-asymmetry rule lands; module stays pure (no settings/DB/network imports)
- `backend/app/llm/extraction.py` (lines 178-216) - Why: passage assembly from `get_chunks_by_artifacts` (conversation artifacts flow through unchanged — NO code change here, prompt-only)
- `backend/tests/test_conversations.py` (lines 17-22) - Why: tmp-DB `init_db` fixture style for repository tests
- `backend/tests/test_adapters.py` (lines 1-34) - Why: pure no-I/O adapter test style
- `backend/tests/test_retrieval.py` (lines 50-88, 155-162) - Why: fake `embed_fn` unit-vector stub + `seed` helper + `hybrid_search` call shape for the retrieval round-trip test
- `backend/tests/test_learn_api.py` (lines 41-110) - Why: settings-isolation fixture + TestClient(tmp DB) + by-name stub pattern for ALL API tests
- `backend/tests/test_extraction.py` (line 191) - Why: the ONE `extract-v1` version assert that the prompt bump must update (other `extract-v1` strings are historical fixture data and stay)
- `frontend/src/api/query.ts` + `frontend/src/api/query.test.ts` (full, both short) - Why: api-module + vitest mockFetch contract-test style to mirror for `deleteConversation`
- `frontend/src/api/types.ts` (lines 1-58) - Why: "field names mirror backend Pydantic JSON exactly" rule for the `source_type` additions
- `frontend/src/views/ChatView.tsx` (lines 90-128) - Why: citation button + active-citation panel where the conversation badge renders
- `frontend/src/views/ChatView.test.tsx` (lines 20-60) - Why: `mockFetchSequence` + findByText view-test style

### New Files to Create

- `backend/app/ingest/conversation_memory.py` - `index_conversation_turns` helper (adapt + delegate to `ingest_source`)
- `backend/tests/test_conversation_memory.py` - Adapter-output-to-retrieval round-trip + cascade repository tests (index → hybrid_search finds it; delete removes everything)

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [SQLite JSON1 json_extract](https://www.sqlite.org/json1.html#jextract)
  - Specific section: `json_extract` path access on TEXT columns
  - Why: conversation→artifact lookup filters `origin` JSON in SQL with no migration (`json_extract(origin, '$.conversation_id')`); verified working on the backend venv SQLite 3.54.1
- No new libraries, no new SDK calls: `ingest_source`, `hybrid_search`, `TestClient`, `monkeypatch`, `vitest`, and `sqlite3` are all established in-repo patterns. Do NOT add dependencies for this deliverable.

### Patterns to Follow

**Naming Conventions:** `snake_case` backend modules/functions, `PascalCase` Pydantic models/classes/dataclasses, `PascalCase.tsx` components. Error classes end `Error` and live in the raising module. Adapter functions are `adapt_<source>` in `ingest/adapters.py`.

**Router seams (by-name imports for monkeypatch):** every collaborator the router touches is imported BY NAME and named in the module docstring (e.g. `app/api/query.py:8-10`). This plan adds ONE seam to each of `api/query.py` and `api/practice.py`: `index_conversation_turns`.

**Persist-after-validate:** no DB write until generation validates. Indexing runs after turn persistence (turns first, then index) — a failed generation persists nothing and indexes nothing.

**Exception ordering:** validation-error subclasses of ValueError are caught BEFORE generic ValueError (502 for model failures, 500 for code bugs — `query.py:164-174`). Indexing failures propagate as 500 with cause (honest; the lifespan dim-check already guards environment failure).

**Single-transaction writes:** repository write functions wrap all statements in `with conn:` (`conversations.py:49-56`, `artifacts.py:74-90`). The deletion cascade is ONE transaction.

**Frontend api module:** one function per endpoint over `apiGet`/`apiPost`, JSDoc one-liner (`query.ts:10-28`). Types mirror backend JSON exactly (`types.ts:1`).

**Frontend view:** `useState` for input/loading/error, `role="alert"` error box with Dismiss button, disclosure line (`ChatView.tsx`).

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

Adapter + indexing helper + cascade repositories + extraction contract. No router changes, no UI. After this phase, conversations can be adapted, indexed, retrieved, role-governed at extraction, and deleted — all covered by repository/contract tests.

**Key design decisions (locked):**

1. **One artifact per turn-append.** Each `POST /query`, `/practice/question`, `/practice/answer` call indexes exactly its newly persisted turns as one artifact. Never re-index old turns: chunk IDs stay stable forever, so fact `chunk_ids` and attempt `reference_json` never churn. `origin` records `adapter="tb_conversation"`, `conversation_id`, `kind`, `turn_start`, `turn_end` (turn `idx` values, inclusive).
2. **Title is deterministic from content:** first user turn truncated to 60 chars, falling back to `f"{kind} conversation"` when there is no user turn (defensive — all current call sites persist a user turn first).
3. **Role tags are literal prefixes:** `ROLE_TAGS = {"user": "User:", "assistant": "Assistant:"}` in `adapters.py`; turns joined with `\n\n`. Tags travel inside chunk text, so they appear in excerpts, extraction passages, and citation panels with no plumbing.
4. **Synchronous indexing after turn persistence.** Router order: generate → validate → persist turns → `index_conversation_turns` → respond. Any indexing exception propagates as 500 with cause (uniform rule — no special mapping, including `ArtifactTooLargeError`: a within-cap request that overflows the artifact cap is a server-side data problem, and the pre-existing request caps make it near-impossible). Retry-after-500 may duplicate turns — a pre-existing property of the non-idempotent API, not introduced here.
5. **`source_type` is additive on three shapes:** `CitationOut`, `SearchHitOut`, `ChunkOut` each gain `source_type: str`, hydrated via a batched `get_chunk_source_types(db_path, ids) -> dict[int, str]` JOIN (`chunks` → `artifacts`). No change to `ChunkDetail` or `SearchHit` internals. Frontend renders "from a ThoughtBridge conversation" when `source_type == "tb_conversation"`.
6. **Role-asymmetry change is prompt-only, on three prompts.** `llm/extraction.py`, `llm/qa.py`, and `llm/practice.py` are untouched: conversation chunks flow through existing passage assembly like any other chunks. One shared `CONVERSATION_ROLE_RULE` paragraph keys on the literal `User:`/`Assistant:` tags and is appended to `EXTRACTION_SYSTEM_PROMPT`, `EVIDENCE_SYSTEM_PROMPT`, and the `("interview", "experience")` branch of `EVALUATION_SYSTEM_PROMPTS` (this generalizes the existing `HISTORY_NOT_EVIDENCE` principle from live dialogue history to retrieved conversation history). Rule content: user-tagged text is candidate evidence (same status as a pasted note); assistant-tagged text is conversational context only — never cite it as support for claims about what the user did, decided, accomplished, or knows, and never mine facts from it even as `proposed`; recall of what was SAID (by either role, e.g. "what did you suggest about X?") may draw on assistant-tagged text but must be framed as prior assistant output, never as user action; `completed` still requires an explicit user statement of done/shipped/fixed/merged; when a passage mixes both tags, cite it only for claims fully supported by its user-tagged sentences. Teaching/learning/technical prompts are unchanged (open-world; personal-fact invention is already barred there). Version bump `extract-v1` → `extract-v2`; stored v1 facts keep v1 (correct provenance). No version bump for QA/practice — those prompts are unversioned (only extraction records a prompt version).
7. **Deletion is one transaction with a reusable core.** `db/artifacts.py` gains conn-level `_delete_artifacts_cascade_conn(conn, artifact_ids) -> dict` (vec rows explicit; artifacts delete cascades chunks via FK; FTS rows follow via the schema triggers; `fact_chunks` rows cascade via FK; zero-support facts deleted; `fact_links`/`interpretations` cascade via FK) plus a self-connecting wrapper `delete_artifacts_cascade(db_path, ids)`. `db/conversations.py::delete_conversation_cascade` opens ONE connection, resolves artifact ids via `json_extract(origin, ...)` lookup, calls the conn-level helper, deletes the conversation row (turns cascade, attempts SET NULL), and returns counts. Deliverable 4's `DELETE /artifacts/{id}` calls the wrapper verbatim. Attempts `reference_json` staleness needs no handling here: the existing stale-fact 409 and missing-chunk drop already cover it. Attempt rows themselves are KEPT with `conversation_id` NULLed (owner-confirmed: practice history stays independently available; the NULL-conversation answer path already handles that state).
8. **DELETE response mirrors the F-10 shape:** `{"deleted": {"conversations": 1, "turns": N, "artifacts": A, "chunks": C, "facts": M}, "unlinked": {"facts": K}}` where K = affected facts that retain other support. (The `conversations` key is this endpoint's additive extra; deliverable 4 uses the F-10-exact subset.)
9. **Practice NULL-conversation path captures the fresh id** (today it discards the return value) so the indexing origin records the real conversation. One-line fix, in scope.
10. **No migration, no backfill, no new view.** Lookup is `json_extract` on `origin` (verified SQLite 3.54.1); pre-existing conversations stay unindexed (documented limitation); role-label polish across all views is deliverable 5's pass.

**Tasks:**

- ADD `adapt_conversation` to `ingest/adapters.py`
- CREATE `ingest/conversation_memory.py` (`index_conversation_turns`)
- ADD cascade helpers to `db/artifacts.py` + `db/conversations.py` + `get_chunk_source_types` to `db/chunks.py`
- UPDATE `core/grounding.py` contracts (shared role rule on extraction + evidence-Q&A + experience-evaluation prompts; `extract-v2` bump)

### Phase 2: Core Implementation

Router hooks + DELETE endpoint + `source_type` hydration. After this phase the three write paths index, deletion works end-to-end, and citations carry labels.

**Tasks:**

- UPDATE `api/query.py` (index hook in `post_query`, DELETE endpoint, `source_type` on `CitationOut`)
- UPDATE `api/practice.py` (index hooks on question + answer paths incl. fresh-id capture)
- UPDATE `api/retrieval.py` (`source_type` on `SearchHitOut`/`ChunkOut`)

### Phase 3: Integration

Frontend type + client + label + disclosure lines. After this phase ChatView badges conversation citations and every main view discloses persistence.

**Tasks:**

- UPDATE `api/types.ts` (`source_type` on `Citation`/`ChunkDetail`; `ConversationDeleteResponse`)
- ADD `deleteConversation` to `api/query.ts`
- UPDATE `ChatView.tsx` (conversation badge on citation buttons + citation panel)
- ADD disclosure line to `LearnView.tsx` + `WorkView.tsx`

### Phase 4: Testing & Validation

- Backend: adapter cases in `test_adapters.py`, new `test_conversation_memory.py`, grounding/extraction contract updates, API tests for hooks + DELETE + `source_type`
- Frontend: `query.test.ts` delete case, `ChatView.test.tsx` badge cases, Learn/Work disclosure assertions
- Full validation ladder (§VALIDATION COMMANDS) + redeploy + Playwright-against-deployed per AGENTS.md environment constraints

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

### ADD backend/app/ingest/adapters.py::adapt_conversation

- **IMPLEMENT**: ADD `TB_CONVERSATION_SOURCE_TYPE = "tb_conversation"` and `ROLE_TAGS = {"user": "User:", "assistant": "Assistant:"}` module constants, plus `def adapt_conversation(conversation_id: str, kind: str, turns: list[tuple[str, str]], turn_start: int) -> AdaptedSource` where each turn is `(role, content)` with role in `{"user", "assistant"}` (unknown role → ValueError; empty turns → ValueError). Content = `"\n\n".join(f"{ROLE_TAGS[role]} {content}")` with content used verbatim (no strip — spans must match the stored artifact exactly; chunker strips per-chunk). Title = first user-turn content truncated to 60 chars (plain slice, no ellipsis), or `f"{kind} conversation"` when no user turn exists. Origin = `{"adapter": "tb_conversation", "conversation_id": ..., "kind": ..., "turn_start": str(turn_start), "turn_end": str(turn_start + len(turns) - 1)}`.
- **PATTERN**: `adapters.py:52-61` (`adapt_text` pure shape + origin dict)
- **IMPORTS**: none new (`dataclass` block already present)
- **GOTCHA**: this module never interprets content beyond validation (header contract) — role validation is structural (allowed keys), not semantic. Do NOT skip blank turn contents: turn count and `turn_end` math must stay exact.
- **VALIDATE**: `cd backend && uv run pytest tests/test_adapters.py -q`

### CREATE backend/app/ingest/conversation_memory.py

- **IMPLEMENT**: CREATE module with `def index_conversation_turns(*, db_path: str, conversation_id: str, kind: str, turns: list[tuple[str, str]], turn_start: int, max_artifact_chars: int, embedding_model: str, embed_fn: EmbedFn | None = None) -> IngestResult`: call `adapt_conversation`, then delegate to `ingest_source` with the adapted fields (re-export `IngestResult` in the import for the return annotation). Docstring states the one-artifact-per-append contract and that routers call this AFTER turn persistence.
- **PATTERN**: `pipeline.py:50-90` (delegate target — do not duplicate its cap/chunk/embed logic)
- **IMPORTS**: `app.ingest.adapters.adapt_conversation`, `app.ingest.pipeline.IngestResult/ingest_source`, `app.retrieval.embedder.EmbedFn`
- **GOTCHA**: `turn_start` is the FIRST appended turn's `idx` — the router must compute it from the conversation BEFORE appending (existing turn count) or from `append_turns` ordering; new-conversation path starts at 0. An off-by-one here corrupts only the origin label, not retrieval — but get it right anyway (Task: query/practice routers).
- **VALIDATE**: `cd backend && uv run pytest tests/test_conversation_memory.py -q`

### ADD backend/app/db/chunks.py::get_chunk_source_types

- **IMPLEMENT**: ADD `def get_chunk_source_types(db_path: str, ids: list[int]) -> dict[int, str]`: one connection, `SELECT c.id, a.source_type FROM chunks c JOIN artifacts a ON a.id = c.artifact_id WHERE c.id IN (...)`; empty input → `{}` without querying. Every returned id maps to its artifact's `source_type`.
- **PATTERN**: `chunks.py:21-44` (`get_chunks` batched style, early `{}` return)
- **IMPORTS**: none new
- **GOTCHA**: do NOT extend `ChunkDetail` — the JOIN reader stays separate so no existing hydration call changes shape.
- **VALIDATE**: `cd backend && uv run pytest tests/test_conversation_memory.py tests/test_retrieval.py -q`

### ADD backend/app/db/artifacts.py cascade helpers

- **IMPLEMENT**: ADD `def find_conversation_artifacts(db_path: str, conversation_id: str) -> list[str]`: one connection, `SELECT id FROM artifacts WHERE json_extract(origin, '$.adapter') = 'tb_conversation' AND json_extract(origin, '$.conversation_id') = ? ORDER BY created_at, id`. ADD `def _delete_artifacts_cascade_conn(conn, artifact_ids: list[str]) -> dict[str, int]` operating on the CALLER's open connection (no commit — caller owns the transaction): dedupe ids preserving order; collect `chunk_ids` (`SELECT id FROM chunks WHERE artifact_id IN (...)`); `affected_fact_ids` (distinct `fact_id` from `fact_chunks` for those chunks); `DELETE FROM chunks_vec WHERE rowid IN (chunk_ids)`; `DELETE FROM artifacts WHERE id IN (...)` (chunks + `fact_chunks` rows + `fact_links` + artifact-linked `interpretations` cascade via FK; FTS rows follow via triggers); delete facts left with zero support (`DELETE FROM facts WHERE id IN (affected) AND NOT EXISTS (SELECT 1 FROM fact_chunks WHERE fact_id = facts.id)`); `unlinked = affected facts still existing` (count). Return `{"artifacts": A, "chunks": C, "facts": M, "unlinked_facts": K}` where A/C count actual deleted rows (`cursor.rowcount`), M = deleted facts, K = affected-minus-deleted. Empty input → all-zero dict without querying. ADD public `def delete_artifacts_cascade(db_path: str, artifact_ids: list[str]) -> dict[str, int]`: `connect`, `with conn: return _delete_artifacts_cascade_conn(...)`, close. Docstring on the wrapper: "Deliverable 4's DELETE /artifacts/{id} calls this verbatim."
- **PATTERN**: `artifacts.py:123-144` (lookup style); `conversations.py:60-96` (single-transaction writes); `schema.sql:45-54` (FTS trigger reliance — never touch `chunks_fts` directly)
- **IMPORTS**: none new (`connect` already imported)
- **GOTCHA**: `cursor.rowcount` must be read per-statement before the next execute. `json_extract` on a malformed `origin` returns NULL (row simply not matched) — never raises, so no defensive parse needed. Vec0 has no FK — forgetting `chunks_vec` leaves ghost vectors that hydrate-drop with warnings; the round-trip delete test must assert vec cleanup (query `chunks_vec` rowids directly).
- **VALIDATE**: `cd backend && uv run pytest tests/test_conversation_memory.py -q`

### ADD backend/app/db/conversations.py::delete_conversation_cascade

- **IMPLEMENT**: ADD `@dataclass ConversationDeleteCounts(conversation_id: str, turns: int, artifacts: int, chunks: int, facts: int, unlinked_facts: int)` and `def delete_conversation_cascade(db_path: str, conversation_id: str) -> ConversationDeleteCounts | None`: return None when the conversation does not exist (router maps to 404); else ONE connection + `with conn:`: count turns, resolve artifact ids via `find_conversation_artifacts`-equivalent SQL on THIS connection (do not call the self-connecting wrapper — same-connection atomicity), call `_delete_artifacts_cascade_conn(conn, ids)` (import from `app.db.artifacts`), `DELETE FROM conversations WHERE id = ?` (turns cascade, attempts SET NULL). Log `deleted conversation: id=%s ...` at info with counts.
- **PATTERN**: `conversations.py:99-144` (single-transaction multi-statement shape)
- **IMPORTS**: `app.db.artifacts._delete_artifacts_cascade_conn` (private cross-module import is deliberate — document it in the docstring as the shared cascade core)
- **GOTCHA**: importing a private name across modules is unusual here — alternative is duplicating the SQL; the shared core is worth it and deliverable 4 depends on it. Do NOT delete `explanations`/`explanation_markers` (no conversation linkage exists). Do NOT touch `attempts.reference_json` (existing stale-409/drop logic governs).
- **VALIDATE**: `cd backend && uv run pytest tests/test_conversation_memory.py tests/test_conversations.py -q`

### UPDATE backend/app/core/grounding.py role-rule contracts

- **IMPLEMENT**: ADD one shared `CONVERSATION_ROLE_RULE` paragraph constant (place it directly above the extraction contract block): user-tagged (`User:`) passage text is candidate evidence with the same status as a pasted note; assistant-tagged (`Assistant:`) passage text is conversational context only — never cite it as support for claims about what the user did, decided, accomplished, or knows, and never mine facts from it even as `proposed`; recall of what was said (by either role) may draw on assistant-tagged text but must be framed as prior assistant output, never as user action; `completed` requires an explicit user statement (done/shipped/fixed/merged) in user-tagged or untagged note text; when a passage mixes both tags, cite it only for claims fully supported by its user-tagged sentences. Append the paragraph to THREE prompts: `EXTRACTION_SYSTEM_PROMPT` (before the JSON/framing tail), `EVIDENCE_SYSTEM_PROMPT` (before the JSON/framing tail), and the `("interview", "experience")` branch of `EVALUATION_SYSTEM_PROMPTS` (before its tail). Leave `TEACHING_SYSTEM_PROMPT`, the learning/technical evaluation branches, and all question-gen prompts unchanged. Bump `EXTRACTION_PROMPT_VERSION` `"extract-v1"` → `"extract-v2"` (only extraction is versioned — no QA/practice version constant exists, so none is added).
- **PATTERN**: `grounding.py:26-35` (evidence prompt style), `grounding.py:367-390` (extraction contract style), `grounding.py:519-527` (experience evaluation branch); `HISTORY_NOT_EVIDENCE` (`grounding.py:47-51`) is the live-history analogue this generalizes to retrieved history
- **IMPORTS**: none new
- **GOTCHA**: module stays pure — no imports. The tag literals `User:`/`Assistant:` MUST match `adapters.ROLE_TAGS` values exactly — the grounding test asserts equality against the imported constants (not a retyped copy) so drift fails loudly. (grounding.py importing adapters.py is a new edge: adapters imports docx/pypdf — heavy for a pure contract module. To avoid it, the TEST imports both and asserts equality; grounding.py keeps plain string literals.)
- **VALIDATE**: `cd backend && uv run pytest tests/test_grounding.py tests/test_extraction.py -q`

### UPDATE backend/app/api/query.py (index hook + DELETE + source_type)

- **IMPLEMENT**: (a) Import `index_conversation_turns` BY NAME from `app.ingest.conversation_memory` + `get_chunk_source_types` BY NAME from `app.db.chunks` + `delete_conversation_cascade` BY NAME from `app.db.conversations`; extend the module docstring seam list. (b) `CitationOut` gains `source_type: str`; hydrate in `post_query` via one `get_chunk_source_types` call over the result citation ids (missing id → "unknown" is impossible — citations come from existing chunks; use direct index and let KeyError 500 loudly rather than masking). (c) After the turn-persist block (lines 194-198) and BEFORE the return, call `index_conversation_turns(db_path=db_path, conversation_id=conversation_id, kind="qa", turns=[(role, content) for the two persisted turns], turn_start=(0 if existing is None else len(existing.turns)), max_artifact_chars=settings.max_artifact_chars, embedding_model=settings.embedding_model, embed_fn=None)` — inside the existing try? NO: place it after the try/except (turns already persisted), letting exceptions propagate as 500 via FastAPI's default handler like other post-generation persistence errors. (d) ADD `DELETE /conversations/{conversation_id}` returning `ConversationDeleteOut(deleted: dict[str, int], unlinked: dict[str, int])`: `delete_conversation_cascade(...)` → None → 404; else `{"deleted": {"conversations": 1, "turns": ..., "artifacts": ..., "chunks": ..., "facts": ...}, "unlinked": {"facts": ...}}`.
- **PATTERN**: `query.py:185-210` (turn persist + response build); `ingest.py:105-111` (cap-error mapping — NOT followed here: indexing errors propagate as 500 per decision 4)
- **IMPORTS**: `app.ingest.conversation_memory.index_conversation_turns`, `app.db.chunks.get_chunk_source_types`, `app.db.conversations.delete_conversation_cascade`
- **GOTCHA**: `turn_start` for the continue-path is `len(existing.turns)` — `existing` was fetched BEFORE this call's append, so its length is exactly the next idx. The assistant-turn citations JSON is persisted in the turn row but NOT indexed into the artifact (artifact content is role+content only — citations stay queryable via GET /conversations/{id}).
- **VALIDATE**: `cd backend && uv run pytest tests/test_query_api.py -q`

### UPDATE backend/app/api/practice.py (index hooks + fresh-id capture)

- **IMPLEMENT**: (a) Import `index_conversation_turns` BY NAME; extend the module docstring seam list (Task: seams named at `practice.py:11-15`). (b) Question path: after `create_attempt` (line 225-233), call `index_conversation_turns(... kind=("learning" if body.mode == "learning" else "interview"), turns=[(t[0], t[1]) for t in turns], turn_start=(0 if existing is None else len(existing.turns)), ...)` with `embed_fn=None`. (c) Answer path: after the persist block, call `index_conversation_turns` with the attempt's mode-derived kind and `turn_start` = pre-append turn count — requires fetching the conversation BEFORE appending (mirror the question path's `existing` check: `get_conversation` first; None → fresh-id path). (d) NULL-conversation recovery (line 304-310): capture the return — `conversation_id, _ = create_conversation_with_turns(...)`, `turn_start=0` — instead of discarding it. (e) Indexing exceptions propagate as 500 (same rule as query — no new except branches).
- **PATTERN**: `practice.py:216-247` (question persist order); `query.py` hook from the previous task (same call shape, kind differs)
- **IMPORTS**: `app.ingest.conversation_memory.index_conversation_turns`
- **GOTCHA**: the answer path currently appends without a pre-fetch — adding the `get_conversation` pre-fetch ALSO fixes a latent crash (appending to a deleted conversation id raises FK IntegrityError → 500; after this change it takes the fresh-conversation path). Keep that behavior change minimal and covered by one test (answer on deleted conversation creates fresh conversation + indexes).
- **VALIDATE**: `cd backend && uv run pytest tests/test_practice_api.py -q`

### UPDATE backend/app/api/retrieval.py (source_type hydration)

- **IMPLEMENT**: `SearchHitOut` and `ChunkOut` gain `source_type: str`. Import `get_chunk_source_types` BY NAME; extend the module docstring seam list. `POST /retrieval/search`: one batched call over hit ids, fill per-hit (direct index — hits hydrate from existing chunks). `GET /chunks/{id}`: single-id call, fill from the one-entry dict.
- **PATTERN**: `retrieval.py:76-104` (hydration loops)
- **IMPORTS**: `app.db.chunks.get_chunk_source_types`
- **GOTCHA**: response_model additions are additive — old clients ignore the field. Frontend types MUST still be updated (exact-mirror rule) in the frontend task.
- **VALIDATE**: `cd backend && uv run pytest tests/test_retrieval_api.py tests/test_search.py -q`

### UPDATE backend/tests/test_extraction.py version assert

- **IMPLEMENT**: Update the ONE prompt-version assert (`test_extraction.py:191`) `== "extract-v1"` → `== "extract-v2"`. No other `extract-v1` string changes: fixture data in `test_accomplishments.py` / `test_work_api.py` / `test_extraction.py:451` represents historically stored v1 facts and stays v1.
- **PATTERN**: none (one-line bump)
- **IMPORTS**: none new
- **GOTCHA**: if any OTHER test asserts on extraction prompt text snapshots, update those too — grep for `EXTRACTION_SYSTEM_PROMPT` in tests first.
- **VALIDATE**: `cd backend && uv run pytest tests/test_extraction.py tests/test_work_api.py tests/test_accomplishments.py -q`

### ADD backend/tests/test_adapters.py conversation cases

- **IMPLEMENT**: ADD cases: two-turn adapt (content exactly `"User: <q>\n\nAssistant: <a>"`, source_type `tb_conversation`, title = first user turn sliced to 60 chars, origin keys exact incl. `turn_start`/`turn_end` strings); title fallback (`f"{kind} conversation"`) when no user turn; unknown role → ValueError; empty turns → ValueError; origin JSON round-trips (`json.loads(json.dumps(...))`).
- **PATTERN**: `test_adapters.py:22-60` (pure assert style, no I/O)
- **IMPORTS**: `adapt_conversation`, `ROLE_TAGS`, `TB_CONVERSATION_SOURCE_TYPE` from `app.ingest.adapters`
- **GOTCHA**: assert the title slice is a PLAIN 60-char slice (build the expected as `text[:60]` in the test, not a retyped string) so truncation-rule drift fails loudly.
- **VALIDATE**: `cd backend && uv run pytest tests/test_adapters.py -q`

### ADD backend/tests/test_grounding.py role-rule cases

- **IMPLEMENT**: ADD cases: `CONVERSATION_ROLE_RULE` text contains the `ROLE_TAGS` values imported from `app.ingest.adapters` (equality, not retyped literals); `EXTRACTION_SYSTEM_PROMPT`, `EVIDENCE_SYSTEM_PROMPT`, and `EVALUATION_SYSTEM_PROMPTS[("interview", "experience")]` each contain the full `CONVERSATION_ROLE_RULE` constant; `TEACHING_SYSTEM_PROMPT`, the learning/technical evaluation branches, and all `QUESTION_SYSTEM_PROMPTS` branches do NOT contain it (branch-exclusion lock); `EXTRACTION_PROMPT_VERSION == "extract-v2"`; `build_extraction_messages` with a role-tagged passage renders the tags verbatim in the user message; `build_messages(mode_used="evidence", ...)` output contains the rule in the system message while `mode_used="teaching"` output does not (mirror the `test_build_question_messages_branch_prompts` marker style at `test_grounding.py:140-147`).
- **PATTERN**: existing `test_grounding.py` builder assertions (output strings, not constant names)
- **IMPORTS**: new grounding names + `ROLE_TAGS` from `app.ingest.adapters`
- **GOTCHA**: the adapters import in a grounding test is new but fine (tests already import both modules elsewhere); production `grounding.py` keeps zero app imports.
- **VALIDATE**: `cd backend && uv run pytest tests/test_grounding.py -q`

### CREATE backend/tests/test_conversation_memory.py

- **IMPLEMENT**: tmp-DB tests with the fake unit-vector `embed_fn` (mirror `test_retrieval.py:50-67`): (a) `index_conversation_turns` creates one artifact with `source_type == "tb_conversation"`, chunk text starts with `User:`/`Assistant:` tags, origin round-trips; (b) retrieval round-trip — index then `hybrid_search` with a distinctive term from the USER turn returns the conversation chunk (proves "what did we decide" retrieval); role tags present in the returned excerpt; (c) `get_chunk_source_types` maps mixed note + conversation chunks correctly + `{}` on empty input; (d) `find_conversation_artifacts` returns only the conversation's artifacts (seed a note artifact + two conversation artifacts across two conversations); (e) `delete_conversation_cascade` on unknown id → None; happy path removes conversation + turns + artifacts + chunks + vec rows (assert `chunks_vec` rowids gone via direct SQL) + FTS rows (assert `search_bm25_ids` no longer matches) while a seeded note artifact + its fact survive; multi-append conversation deletes ALL its artifacts; fact supported ONLY by conversation chunks is deleted; fact supported by conversation + note chunks survives with only the conversation `fact_chunks` rows removed (`unlinked_facts` counts it); linked attempt row survives with `conversation_id` NULL; (f) `delete_artifacts_cascade` wrapper happy path on a note artifact (deliverable-4 smoke: same counts shape).
- **PATTERN**: `test_retrieval.py` (fake embed + seed + hybrid_search asserts); `test_conversations.py:17-22` (tmp-DB fixture); `create_facts` for fact fixtures (see `test_accomplishments.py` usage)
- **IMPORTS**: `app.ingest.conversation_memory.index_conversation_turns`, `app.db.artifacts.(delete_artifacts_cascade, find_conversation_artifacts)`, `app.db.chunks.get_chunk_source_types`, `app.db.conversations.(create_conversation_with_turns, delete_conversation_cascade)`, `app.db.facts.create_facts`, `app.retrieval.search.hybrid_search`
- **GOTCHA**: `create_facts` needs real chunk ids — index or ingest first, then read chunk ids from the DB. Vec-row assertion needs `connect()` + raw `SELECT rowid FROM chunks_vec` (no repository reader exists — that is fine in a test). FTS assertion uses `search_bm25_ids` with a `build_fts_match` expression.
- **VALIDATE**: `cd backend && uv run pytest tests/test_conversation_memory.py -q`

### ADD backend/tests/test_query_api.py hook + DELETE + source_type cases

- **IMPLEMENT**: TestClient(tmp DB) + settings-isolation fixture (existing file pattern): stub `app.api.query.index_conversation_turns` (by-name seam) and assert it is called once per `POST /query` with the question + answer contents, correct `conversation_id`, `kind == "qa"`, and `turn_start` 0 on new / N on continue (two sequential posts); `source_type` present on every citation in `POST /query` and `GET /chunks/{id}` responses (stub `hybrid_search` returning a real chunk id seeded via the real pipeline with fake `embed_fn` — mirror how the file seeds chunks today, or assert the field key exists with the seeded artifact's type); DELETE happy path (seed via real `create_conversation_with_turns` + real `index_conversation_turns` with fake embed, DELETE, assert F-10-mirror shape keys/values exact, GET conversation → 404, `GET /artifacts` no longer lists the conversation artifact); DELETE unknown → 404; indexing stub raising → 500 (propagate rule).
- **PATTERN**: `test_learn_api.py:41-110` (fixture + client + by-name stubs); `test_query_api.py` existing turn-persistence assertions
- **IMPORTS**: existing file imports + `app.ingest.conversation_memory` (for the real seed path), `app.db.conversations.get_conversation`
- **GOTCHA**: stub at `app.api.query.<name>` — stubbing `app.ingest.conversation_memory.*` directly does NOT affect the router. The 500-propagation test asserts turns WERE persisted despite the failed response (documents the retry-duplication property).
- **VALIDATE**: `cd backend && uv run pytest tests/test_query_api.py -q`

### ADD backend/tests/test_practice_api.py hook cases

- **IMPLEMENT**: Stub `app.api.practice.index_conversation_turns`; assert called on question (kind `learning`/`interview` per mode, `turn_start` 0/continue) AND on answer (same conversation, `turn_start` = pre-answer turn count); NULL-conversation answer path (delete the question's conversation via SQL between calls... simpler: craft an attempt with `conversation_id=None` via real `create_attempt`) creates a fresh conversation AND indexes with `turn_start == 0`; indexing stub raising on answer → 500 with the attempt still recorded (record happens before turns+index? NO — check the implemented order: evaluate → record_answer → append turns → index; assert attempt recorded + turns persisted + 500).
- **PATTERN**: `test_practice_api.py` existing by-name stub + `create_attempt` seeding style
- **IMPORTS**: existing file imports only
- **GOTCHA**: the answer-path `turn_start` assertion needs the pre-answer turn count — fetch via `get_conversation` BEFORE posting the answer.
- **VALIDATE**: `cd backend && uv run pytest tests/test_practice_api.py -q`

### ADD backend/tests/test_retrieval_api.py source_type cases

- **IMPLEMENT**: TestClient(tmp DB) + settings-isolation fixture (existing file pattern): seed one note artifact (via `adapt_text` + real `ingest_source` with fake unit-vector `embed_fn`, mirroring `test_retrieval.py:50-88`) and one conversation artifact (via real `index_conversation_turns` with the same fake embed); `POST /retrieval/search` with a term matching both, assert EVERY hit carries `source_type` with the note hit reading `"note"` and the conversation hit `"tb_conversation"`; `GET /chunks/{id}` on each hit's chunk asserts the same values (locks the ChunkOut hydration path independently of the query-API task's coverage).
- **PATTERN**: `test_retrieval_api.py` existing TestClient style; `test_retrieval.py:50-88` (fake embed + seed)
- **IMPORTS**: existing file imports + `app.ingest.conversation_memory.index_conversation_turns`, `app.ingest.pipeline.ingest_source` (real, fake embed_fn only)
- **GOTCHA**: use `embed_fn` fakes that return DISTINCT unit vectors per passage (the `test_retrieval.py` counter stub) so both artifacts surface in one search; a constant-vector stub also works (BM25 leg carries recall) but assert on the term match, not vector order.
- **VALIDATE**: `cd backend && uv run pytest tests/test_retrieval_api.py -q`

### UPDATE frontend/src/api/types.ts + query.ts + query.test.ts

- **IMPLEMENT**: `Citation` and `ChunkDetail` gain `source_type: string`; ADD `ConversationDeleteResponse {deleted: Record<string, number>; unlinked: Record<string, number>}`. `query.ts` ADDs `deleteConversation(id): Promise<ConversationDeleteResponse>` → `apiDelete`? — check `client.ts` for a delete helper; if none exists, ADD `apiDelete` mirroring `apiGet` (same error propagation) and use it. Test: URL+method assertions for `deleteConversation`, non-OK rejection.
- **PATTERN**: `query.ts:10-28` (one function per endpoint); `query.test.ts` (mockFetch contract style); `client.ts:16-30` (`apiGet`/`apiPost`)
- **IMPORTS**: `./client`, `./types`
- **GOTCHA**: existing frontend fixtures constructing `Citation`/`ChunkDetail` objects (ChatView tests, WorkView tests?) will fail typecheck until they add `source_type` — grep for object literals and fix them in this task (expected fallout, not a separate task).
- **VALIDATE**: `cd frontend && npm test -- --run src/api/query.test.ts && npm run build`

### UPDATE frontend/src/views/ChatView.tsx + test (conversation badge)

- **IMPLEMENT**: Citation buttons and the active-citation panel render a "from a ThoughtBridge conversation" badge (`<span aria-label="Conversation source">`) when `source_type === "tb_conversation"` (exact backend string — no remapping). Neutral border styling (Tailwind only; deliverable 5 unifies grounding visuals). Tests: assistant message with a conversation citation shows the badge; note citation shows none; citation panel shows the badge for conversation chunks.
- **PATTERN**: `ChatView.tsx:90-128` (citation render block); `ChatView.test.tsx` (mockFetchSequence + findByText)
- **IMPORTS**: none new (types flow through existing imports)
- **GOTCHA**: fixtures in the test file need `source_type` on every citation/chunk object (see previous task GOTCHA). Badge text is verbatim — assert full string.
- **VALIDATE**: `cd frontend && npm test -- --run src/views/ChatView.test.tsx`

### UPDATE frontend/src/views/LearnView.tsx + WorkView.tsx (disclosure line)

- **IMPLEMENT**: ADD `<p className="text-xs">Conversations are saved and retrievable.</p>` to both views (same placement as ChatView: bottom of the view root). ADD one assertion per view test that the line renders.
- **PATTERN**: `ChatView.tsx:153` (verbatim line — copy the exact string and classes)
- **IMPORTS**: none
- **GOTCHA**: exact-string match — the same sentence in all five views (Capture stub has no view file; deliverable scope is the four real views + Practice/Interview already done).
- **VALIDATE**: `cd frontend && npm test -- --run src/views/LearnView.test.tsx src/views/WorkView.test.tsx`

---

## TESTING STRATEGY

Backend: `pytest` over tmp-DB `TestClient`s with by-name monkeypatch stubs (never network, never fastembed) for API tests; direct repository/helper calls with fake unit-vector `embed_fn` for memory tests; raw-`connect` tmp DBs for cascade assertions (vec/FTS row checks). Frontend: `vitest` + Testing Library; `mockFetch`/`mockFetchSequence` for all network; no real backend.

### Unit Tests

- `test_adapters.py` additions: exact transcript format, title slice/fallback, origin keys, both ValueErrors, origin JSON round-trip.
- `test_grounding.py` additions: role paragraph present in system prompt, tag-constant equality (no drift), version bump, verbatim tag rendering in extraction messages.
- `test_conversation_memory.py`: index shape + origin, `get_chunk_source_types` mapping, `find_conversation_artifacts` filtering, cascade counts, vec/FTS cleanup, multi-append deletion, zero-support vs shared-support facts, attempt NULL-ing, unknown-id None, wrapper smoke.
- `test_extraction.py`: version assert bump (contract: stored facts now record `extract-v2`).
- `query.test.ts` + `ChatView.test.tsx` + Learn/Work tests: delete contract, badge render/no-badge, disclosure lines.

### Integration Tests

- `test_query_api.py` additions: full `POST /query` → stubbed-index assert (turn contents, kind, turn_start new/continue) → DELETE → 404 + artifact gone; `source_type` on citations and chunk reads; 500-propagation with turns persisted.
- `test_practice_api.py` additions: index hooks on question + answer with kinds and turn_starts; fresh-conversation recovery path indexes at 0; 500-propagation with attempt recorded.
- `test_conversation_memory.py` retrieval round-trip: real `index_conversation_turns` + real `hybrid_search` (fake embed only) proves a user-turn term retrieves the conversation chunk with tags in the excerpt.
- `test_retrieval_api.py` source_type cases: `POST /retrieval/search` hits and `GET /chunks/{id}` read back the exact `source_type` for note vs conversation chunks (locks the inspection-endpoint hydration path).
- Live smoke (Level 4 agent steps): real-key TestClient + scratch `/tmp` DB proving end-to-end indexing → follow-up retrieval → extraction role behavior against the Meta API (isolated DB per working-notes rule).

### Edge Cases

- Continue-path `turn_start` off-by-one → asserted exact on second and third posts (query + practice).
- Answer posted after its conversation was deleted → fresh conversation + index at 0, no 500.
- Conversation with zero indexed artifacts (pre-backfill rows) → DELETE still removes conversation + turns, counts show zeros.
- Fact supported by conversation + note chunks → survives with conversation links removed, counted in `unlinked`.
- Attempt referencing the deleted conversation → row survives, `conversation_id` NULL (FK SET NULL), history still renders (owner-confirmed: practice history stays independently available).
- "What did you suggest about X?" recall → answerable from assistant-tagged text framed as prior assistant output; "what did I decide/ship" → user-tagged text only (recall-vs-evidence boundary, enforced by the shared rule paragraph).
- `source_type` hydration on citations for chunks whose artifact still exists → always present (direct index, never "unknown").
- Long first user turn → title is exactly `text[:60]`.
- Pre-existing (never-indexed) conversations → untouched by indexing, deletable, documented as unretrievable until re-discussed.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

```bash
cd backend && uv run ruff check . && uv run ruff format --check .
```
Expected: exit 0, `All checks passed!` + `N files already formatted` (no `would reformat`).

```bash
cd backend && uv run mypy app
```
Expected: exit 0, `Success: no issues found`.

```bash
cd frontend && npx oxlint
```
Expected: exit 0, no errors or warnings.

### Level 2: Unit Tests

```bash
cd backend && uv run pytest tests/test_conversation_memory.py tests/test_adapters.py tests/test_grounding.py tests/test_conversations.py -q
```
Expected: exit 0, all passed (no failures/errors/skips).

```bash
cd frontend && npm test -- --run src/api/query.test.ts src/views/ChatView.test.tsx
```
Expected: exit 0, all passed.

### Level 3: Integration Tests

```bash
cd backend && uv run pytest -q
```
Expected: exit 0, full suite green (new + existing, zero regressions).

```bash
cd frontend && npm test -- --run && npm run build
```
Expected: exit 0, full vitest suite green + `tsc -b` + vite build succeed (proves types + production bundle).

### Level 4: Manual Validation

Performer `agent` = executable in this environment (executor MUST run); `human` = real browser/judgment.

**L4-1 [agent] Live index → follow-up retrieval round-trip (real key, scratch DB):**

1. `cd backend && DATABASE_PATH=/tmp/conv_memory_smoke.db MODEL_API_KEY="$MODEL_API_KEY" uv run python /tmp/conv_memory_smoke.py` where the script (write to `/tmp`, NOT committed): TestClients `create_app()` as context manager; `POST /api/v1/query {"question": "We decided the session cache lives in Redis with a 5-minute TTL because Memcached lacked the eviction policy we need. Remember this decision."}` (evidence mode over an empty DB will refuse — that is fine, the TURNS still persist and index); then `POST /api/v1/query {"question": "What did we decide about the session cache?", "conversation_id": <fresh id>}`; asserts the second answer's citations include a `tb_conversation` chunk (via `source_type`) whose excerpt contains `User:` and `Redis`.
2. Expected: exit 0, conversation chunk cited with `source_type == "tb_conversation"`, role tags visible in excerpt; then delete `/tmp/conv_memory_smoke.db*`.
3. Same script continues (observational): ask "What suggestions did you make about the session cache?" in the same conversation; executor judges that the answer frames suggestions as prior assistant output rather than user actions, and pastes the output into the report. Expected: exit 0 + judged framing (recall-vs-evidence boundary spot-check).

**L4-2 [agent] Live extraction role-asymmetry spot-check (real key, scratch DB):**

1. Same harness, fresh `/tmp/conv_extract_smoke.db`: two-turn conversation via `POST /query` (user: "I shipped the Redis session-cache fix today, merged PR 42."; follow-up in the SAME conversation so both appends index); resolve the conversation's artifacts via `GET /artifacts` (filter `source_type == "tb_conversation"`); `POST /work/extract {"artifact_ids": [...]}`; assert every returned fact's `chunk_ids` resolve (via `GET /chunks/{id}`) to chunks whose text contains a `User:`-tagged sentence supporting the claim, and print the facts for human inspection that no assistant suggestion became a fact.
2. Expected: exit 0 with the chunk-tag assertion passing; printed facts reference only user-stated content (executor judges + pastes the output into the report); then delete the scratch DB files.

**L4-3 [human] Deployed UI walkthrough (after redeploy per AGENTS.md):**

1. Open the deployed app URL (from `backend/README.md` Live URL line); hard-refresh; confirm the bundle is fresh (ChatView citation buttons render for a cited answer).
2. Chat tab: ask a question answerable from seeded notes, then ask a follow-up referencing the earlier exchange ("what did you just tell me about X?") — expected: second answer cites a chunk badged "from a ThoughtBridge conversation"; clicking it shows the citation panel with role tags (`User:`/`Assistant:`) in the text and the same badge.
3. Learn + Work tabs: scroll to the bottom — expected: "Conversations are saved and retrievable." line visible in both.
4. Delete flow (via API docs or curl against the deployed URL): `DELETE /api/v1/conversations/{id}` for the test conversation — expected: F-10-mirror counts shape; re-asking the follow-up no longer cites the deleted exchange.

### Level 5: Additional Validation (Optional)

Playwright MCP browser E2E against the DEPLOYED URL (never localhost — sandboxed sessions deny local sockets):

1. Verify deployment freshness FIRST (new bundle hash + `DELETE /api/v1/conversations/nonexistent` returns 404 JSON, proving the new route is live) — an outdated deployment never validates new code.
2. Script: open Chat tab → ask a seeded-notes question → assert citation button visible → ask a follow-up referencing the exchange → assert "from a ThoughtBridge conversation" badge visible → click the citation → assert panel shows role tags.
3. Expected: all assertions pass; console shows no errors (`browser_console_messages` level error empty).
4. If deployment is impossible (missing credentials/blocked deploy), mark browser E2E `NOT_PERFORMED` with reason and L4-3 `UNVERIFIED` pending deployment with the manual steps above — never a failure, never a pass.

---

## MANUAL VERIFICATION CHECKLIST

- [ ] [agent] Backend ladder green: run Level 1–3 backend commands in order; expected: exact Expected outputs above, zero failures.
- [ ] [agent] Frontend ladder green: run Level 1 (oxlint) + Level 2–3 frontend commands; expected: exact Expected outputs above, zero failures.
- [ ] [agent] Live round-trip + extraction spot-check: run L4-1 and L4-2; expected: exit 0 each, conversation chunk cited with tags, facts cite user-tagged chunks only, scratch DBs deleted after.
- [ ] [human] Deployed UI walkthrough: perform L4-3 steps 1–4 on the fresh deployment; expected: per-step observations above (badge, role tags, disclosure lines, delete-then-requery).
- [ ] [agent] Cascade proof: run `cd backend && uv run pytest tests/test_conversation_memory.py -q -k "delete or cascade"`; expected: exit 0, all selected passed — plus confirm `delete_artifacts_cascade` wrapper exists for deliverable 4 (`grep -n "def delete_artifacts_cascade" backend/app/db/artifacts.py` prints the def line).
- [ ] [agent] No leftover scratch: `ls /tmp/conv_*smoke*` shows no files; `git status --short` shows only intended new/modified files (no `.env`, no `conversation-log/`, no scratch scripts in repo).

## ROLLBACK CONSIDERATIONS

- Code rollback: `git revert` the single deliverable commit — all changes are additive (new adapter function, new module, new repository functions, new endpoint, new response fields, badge, disclosure lines) except the extraction prompt paragraph + version bump and the practice fresh-id capture. Reverting restores `extract-v1` prompts; facts stored as `extract-v2` keep that label (harmless provenance string).
- Data rollback: no migration ran (schema untouched). `tb_conversation` artifacts are identifiable (`source_type` + `origin.adapter`) and removable via the new DELETE endpoint per conversation, or in bulk via `DELETE FROM artifacts WHERE source_type = 'tb_conversation'` + vec cleanup through `delete_artifacts_cascade` (never raw SQL on a live DB — write a `/tmp` script using the repository function).
- Deployed volume DB: no boot-time migration involved; redeploy is behavior-only. Pre-existing conversations were never indexed, so rollback loses no index state.

## ACCEPTANCE CRITERIA

- [ ] `adapt_conversation` produces exact role-tagged transcripts with correct origin/title (L2 `test_adapters.py` conversation cases; expected: pass)
- [ ] Index → hybrid_search round-trip retrieves the conversation chunk with tags in the excerpt (L2 `test_conversation_memory.py` round-trip test; expected: pass)
- [ ] All three write paths index exactly their new turns with correct kind + turn_start (L3 `test_query_api.py` + `test_practice_api.py` hook tests incl. continue-path counts; expected: pass)
- [ ] Extraction, evidence-Q&A, and experience-evaluation prompts carry the shared role-asymmetry rule keyed on the exact `ROLE_TAGS` literals, with teaching/learning/technical branches excluded; version `extract-v2` (L2 `test_grounding.py` role cases + `test_extraction.py` version assert; expected: pass)
- [ ] `source_type` present on all citation/hit/chunk shapes (L3 `test_query_api.py` citation cases + `test_retrieval_api.py` search-hit cases + `GET /chunks/{id}` cases in both files; expected: pass)
- [ ] `DELETE /conversations/{id}` removes conversation + turns + all its artifacts + chunks/vec/FTS rows, deletes only zero-support facts, unlinks shared facts, NULLs attempt links, 404s unknown ids (L2 `test_conversation_memory.py` cascade tests + L3 `test_query_api.py` DELETE tests; expected: pass)
- [ ] `delete_artifacts_cascade` wrapper exists with the documented counts shape for deliverable 4 (manual checklist cascade-proof item: grep prints the def + wrapper test passes)
- [ ] ChatView badges conversation citations + panel; Learn/Work show the disclosure line (L3 frontend suite: `ChatView`/`LearnView`/`WorkView` tests; expected: pass)
- [ ] Full backend + frontend suites green with zero regressions (L3 `pytest -q`, `npm test`, `npm run build`; expected: exit 0 throughout)
- [ ] Lint/type gates pass (L1 ruff + mypy + oxlint; expected: exit 0 throughout)
- [ ] Live index→retrieve→extract exchanges against the Meta API succeed on scratch DBs (L4-1/L4-2 agent steps; expected: exit 0 + asserted citation/tag values, facts cite user-tagged chunks)
- [ ] No new dependencies added (`git diff backend/pyproject.toml frontend/package.json` empty of new deps; `uv.lock`/`package-lock.json` unchanged — checklist item, verified by `git status`)
- [ ] No schema change (`git diff backend/app/db/schema.sql backend/app/db/connection.py` empty of DDL/migration changes — checklist item)
- [ ] Code follows project conventions (thin routers, pure grounding contracts, by-name seams, exact-JSON types, single-transaction writes — reviewer judgment at `/review-plan` + execution review)

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

- **Why one artifact per append (not one per conversation):** the turn log is append-only and chunk IDs are cited by facts and attempts. Re-indexing a growing transcript on every call would churn chunk IDs (breaking references) and re-embed old turns every round. Per-append artifacts keep every chunk ID stable forever at the cost of more artifact rows — correct tradeoff at single-user scale. `GET /artifacts` will show multiple rows per conversation; grouping by `origin.conversation_id` is a display concern for later.
- **Why synchronous, not async:** PRD §12 allows async indexing, but sync keeps "reliably retrievable" trivially true (no queue, no worker, no lag window for the demo's ask-then-recall flow) and the cost is one local fastembed call over ~2 turns. Modal `max_containers=1` single-writer is unaffected.
- **Why the role-asymmetry change is prompt-only:** passages already carry full chunk text including role tags, so the model sees everything it needs. A structural change (e.g. splitting user/assistant passages, code-side citation filtering, or excluding assistant chunks from retrieval) would complicate three modules for no MVP gain — and excluding assistant chunks would break "what did you suggest" recall, which must stay answerable. The mandatory no-evidence-mining test in deliverable 4 is the backstop that proves the prompt rule holds. One shared paragraph (not three copies) keeps the three governed prompts in sync; the branch-exclusion test locks which prompts carry it.
- **Deliverable 4 handoff (explicit):** `delete_artifacts_cascade(db_path, ids)` + its counts dict are the reusable core; deliverable 4 wires `DELETE /artifacts/{id}` to it, adds the delete-then-query residue test + mandatory no-evidence-mining test, and decides nothing new about cascade semantics. `find_conversation_artifacts` stays conversation-specific.
- **Known limitation — no backfill:** conversations created before this deploy (including the deployed volume's existing rows) are never indexed and stay unretrievable until re-discussed. Documented in the L4-3 walkthrough (use fresh exchanges) and in scope boundaries — not a bug.
- **Fallback check (PRD §12):** this plan implements the FULL deliverable (adapter + retrieval + labels + role rule + DELETE), not the fallback — turns already persist with role tags, so nothing needs deferring. If execution slips, the first cut is the ChatView badge (backend labels stay; deliverable 5 renders them), never the adapter or cascade.
- **Deadline pressure:** this plan is deliberately additive with zero migration risk; the riskiest item is the cascade SQL, which is covered by direct vec/FTS row assertions rather than prompt behavior.

---

## Revision History

### Cycle 1

Owner decisions on the two Cycle-0 review escalations, plus the reviewer's routine test-coverage finding:

1. Finding (escalation, owner-decided): "Decide whether deleting a conversation should keep its practice attempts with conversation_id NULLed, as planned (they still hold the user's answer text), or delete them as records 'left with no remaining support' under F-10/US-8." Owner decision: KEEP attempts with the conversation link removed — practice history stays independently available. This confirms the plan as written (FK SET NULL); no design change. What changed: decision 7, the attempts edge case, and this entry now record the confirmation explicitly.
2. Finding (escalation, owner-decided): "Decide whether the role-asymmetry rule (assistant turns never evidence) must also govern evidence-mode Q&A and interview-experience evaluation; as planned, prior assistant answers can be retrieved and cited as support for claims about the user's work." Owner decision: APPLY role-asymmetric grounding to evidence-mode Q&A and interview-experience evaluation too — assistant turns are conversational context only, never evidence of the user's actions or accomplishments. What changed: `EXTRACTION_CONVERSATION_ROLES` became one shared `CONVERSATION_ROLE_RULE` appended to three prompts (extraction, evidence Q&A, experience evaluation); teaching/learning/technical branches explicitly excluded with a branch-exclusion test lock; feature description, scope, solution statement, decision 6, both grounding tasks, the role acceptance criterion, edge cases, L4-1 (observational recall-framing spot-check), and NOTES updated. Interpretation encoded (owner to confirm at plan approval): recall of what was SAID by either role stays answerable (framed as prior assistant output); only user-action/accomplishment claims are restricted to user-tagged text. No QA/practice prompt-version bump — verified only extraction records a prompt version.
3. Finding (routine): "Add an API test in test_retrieval_api.py asserting that `source_type` is present and correct on POST /retrieval/search hits (SearchHitOut), so the 'all citation/hit/chunk shapes' acceptance criterion is actually verified." What changed: new step-by-step task `ADD backend/tests/test_retrieval_api.py source_type cases` (note + conversation seeds, every-hit asserts, ChunkOut lock); Integration Tests section and the `source_type` acceptance criterion now cite it.

Not done: nothing — all three items applied. `llm/qa.py` and `llm/practice.py` remain untouched by design (prompt flows through existing builders).


