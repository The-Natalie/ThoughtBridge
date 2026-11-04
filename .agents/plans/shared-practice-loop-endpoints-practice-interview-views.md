# Feature: shared-practice-loop-endpoints-practice-interview-views

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

The shared Practice Loop (PRD F-7/F-8): one mode-parameterized question → answer → evaluated-feedback loop serving Learning mode (explain-back against a stored lesson) and Interview mode (experience questions judged against accomplishment facts in evidence mode; technical questions judged for conceptual accuracy in teaching mode). Backend: `POST /practice/question`, `POST /practice/answer`, `GET /practice/attempts`, attempt persistence with stored evaluation references, per-branch rubrics, code-computed grounding labels, and turn persistence inheriting the attempt's conversation. Frontend: Practice and Interview views replacing the `App.tsx` stubs, sharing `FeedbackCard` + `AttemptHistory` components.

This plan covers Phase 3 build-list deliverables **1 and 2 as one functional slice** — `POST /practice/answer` cannot exist without the rubric/grounding-label contract, and the build list explicitly permits "plan 1+2 together". After this plan, deliverable 2 has no remaining separate work.

## User Story

As a learner preparing for interviews
I want to answer practice questions and get specific feedback grounded in my real knowledge
So that I move from supported understanding toward independent, interview-ready recall

## Problem Statement

Learn (lessons) and Work (extracted facts) exist, but there is no closed feedback loop: nothing asks the user to explain back, nothing evaluates interview answers against stored evidence, and no attempt log exists to feed re-queue display. The Practice/Interview tabs are placeholder stubs.

## Scope

- In scope: practice router + `llm/practice.py` orchestration + `db/attempts.py` repository + grounding-contract additions + attempts-table migration (v1→v2) + `get_facts_by_ids` + frontend `api/practice.ts`, `FeedbackCard`, `AttemptHistory`, `PracticeView`, `InterviewView`, `App.tsx` wiring + all tests listed below.
- Out of scope: `tb_conversation` pipeline ingestion (deliverable 3); deletion cascade incl. conversation deletion (deliverable 4 — but this plan stores explicit reference edges + `conversation_id` so F-10 support-checking is implementable there); checkpoint-prompt button + visibility unification pass (deliverable 5 — practice views render the backend grounding label verbatim until then); rerank/HyDE (deliverable 6, default skip); scored career ranking; editing/redaction; automated scheduling (only the deterministic `needs_retry` field + re-queue display).

## Solution Statement

Mirror the established learn/query/work vertical slice: thin `api/practice.py` router over generation-only `llm/practice.py` with injected `chat_fn`/`search_fn`/`career_fn` seams (persistence lives in the router via repository calls, qa-style), prompt contracts as pure builders in `core/grounding.py`, and a per-table repository. Question generation assembles references per (mode, kind) branch, persists them ON the attempt (`reference_json` + `explanation_id`), and evaluation rehydrates those stored references — the evaluator is literally constrained to question-time references, never re-derivation. Grounding labels are computed in code from reference buckets, never model-guessed. Frontend mirrors the `ChatView` useState/fetch/test style with two shared presentational components.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: High
**Primary Systems Affected**: backend `api/`, `llm/`, `db/`, `core/grounding.py`; frontend `api/`, `views/`, `components/`, `App.tsx`
**Dependencies**: none (all tables except the two new attempt columns exist; `list_accomplishments`, `get_explanation`, `build_explanation_context`, `hybrid_search`, conversation persistence all exist)
**Assumptions**: attempts table is empty in all environments (endpoints never existed, so the v1→v2 migration touches schema only, verified by test); `meta.schema_version` has no value-asserting consumers (only presence is asserted — `backend/tests/test_ingest_api.py:349`); Spark hidden-reasoning token behavior from prior deliverables still holds (generous budgets required)

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `backend/app/api/query.py` (lines 96-210) - Why: question/answer endpoint shape to mirror — 404-on-unknown-conversation, `create_conversation_with_turns` vs `append_turns`, turn tuple shape `(role, content, mode, citations_json)`, exception-ordering (validation BEFORE generic ValueError)
- `backend/app/api/learn.py` (lines 134-203) - Why: `_make_chat_fn(settings, model_wanted)` (messages, budget) closure + missing-key 502 + `functools.partial` seam wiring to copy
- `backend/app/api/work.py` (lines 83-161) - Why: `career_fn=functools.partial(read_career_context, db_path)` wiring + full error-mapping matrix (422/404/413/502/500) to extend with 409
- `backend/app/llm/qa.py` (lines 36-59, 72-137) - Why: orchestration contract — injected seams, `strip_fences` + `model_validate_json` boundary validation, dropped-leg warnings, refusal-as-result
- `backend/app/llm/explainer.py` (lines 1-60) - Why: `(messages, max_tokens)` ChatFn arity with per-call budgets + persist AFTER all validation succeeds (no partial rows)
- `backend/app/core/grounding.py` (lines 140-151, 350-457) - Why: contract-block style (STEP_KEYS, EXTRACTION_* tuples, JSON-instruction strings, pure `build_*_messages`); lines 442-445 hold the Phase 3 career-block composition recipe to follow exactly
- `backend/app/db/conversations.py` (lines 60-144) - Why: `append_turns` / `create_conversation_with_turns` signatures + "persist AFTER successful generation" rule
- `backend/app/db/explanations.py` (lines 238-242) - Why: answered-attempt counting (`answer` non-blank) that the attempt lifecycle must preserve
- `backend/app/db/facts.py` (lines 119-200) - Why: `_clean_skills` + chunk/link hydration pattern that `get_facts_by_ids` must mirror
- `backend/app/db/connection.py` (lines 33-50) - Why: `init_db` executes schema.sql idempotently; the `_migrate` step slots in after `executescript`
- `backend/app/db/schema.sql` (lines 6-12, 120-130) - Why: meta version row + attempts DDL to extend
- `backend/app/db/chunks.py` (lines 12-46) - Why: `ChunkDetail` + `get_chunks` / `get_chunks_by_artifacts` for reference rehydration
- `backend/app/core/meta_client.py` (lines 112-137) - Why: `chat_completion` keyword-only signature + MetaAPIError contract
- `backend/app/retrieval/search.py` (lines 26-27, 105-112) - Why: `TOP_K_DEFAULT`/`TOP_K_MAX` + `hybrid_search(db_path, query, top_k, embedding_model, embed_fn)` signature
- `backend/app/llm/extraction.py` (lines 163-175) - Why: `read_career_context` seam filler + `CareerContext`/`CareerFn`/`no_career` types to reuse (import, do not duplicate)
- `backend/app/main.py` (lines 43-61) - Why: router import + `include_router(prefix="/api/v1")` registration to extend
- `backend/tests/test_learn_api.py` (lines 41-110) - Why: settings-isolation fixture + TestClient(tmp DB) + by-name stub pattern for ALL API tests
- `backend/tests/test_db_init.py` (lines 23-28) - Why: idempotent-init fixture style for the migration test
- `frontend/src/api/query.ts` + `frontend/src/api/query.test.ts` (full, both short) - Why: api-module + vitest mockFetch contract-test style to mirror exactly
- `frontend/src/api/client.ts` (lines 16-30) - Why: `apiGet`/`apiPost` — all practice calls go through these
- `frontend/src/api/types.ts` (lines 1-26) - Why: "field names mirror backend Pydantic JSON exactly" rule for new practice types
- `frontend/src/views/ChatView.tsx` (lines 13-60, 130-153) - Why: view pattern — `conversationId` state, loading/error/dismiss, `role="alert"`, disclosure line, Enter-to-send
- `frontend/src/views/ChatView.test.tsx` (lines 20-60) - Why: `mockFetchSequence` + fireEvent + findByText view-test style
- `frontend/src/App.tsx` (lines 8-14, 42-44) - Why: stub entries to replace with real views

### New Files to Create

- `backend/app/db/attempts.py` - Attempt repository (create/record/get/list + deterministic `needs_retry`)
- `backend/app/llm/practice.py` - Question-gen + evaluation orchestration over injected seams
- `backend/app/api/practice.py` - Thin router: question/answer/attempts endpoints
- `backend/tests/test_attempts.py` - Repository unit tests (lifecycle, filters, retry rule, NULL normalization)
- `backend/tests/test_practice.py` - Orchestration contract tests (branches, stale refs, grounding, validation)
- `backend/tests/test_practice_api.py` - Router contract tests (shapes, status matrix, turn persistence, inheritance)
- `frontend/src/api/practice.ts` - Typed practice client (`postPracticeQuestion`, `postPracticeAnswer`, `listAttempts`)
- `frontend/src/api/practice.test.ts` - Client contract tests (mirror `query.test.ts`)
- `frontend/src/components/FeedbackCard.tsx` - Shared feedback display (5 sections + grounding badge)
- `frontend/src/components/FeedbackCard.test.tsx` - FeedbackCard render tests
- `frontend/src/components/AttemptHistory.tsx` - Shared history + retry-queue display with retry callback
- `frontend/src/components/AttemptHistory.test.tsx` - AttemptHistory render/callback tests
- `frontend/src/views/PracticeView.tsx` - Learning-mode loop (explanation picker → question → answer → feedback)
- `frontend/src/views/PracticeView.test.tsx` - PracticeView flow tests
- `frontend/src/views/InterviewView.tsx` - Interview-mode loop (kind toggle + focus → question → answer → feedback)
- `frontend/src/views/InterviewView.test.tsx` - InterviewView flow tests

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [Pydantic model_validate_json](https://docs.pydantic.dev/latest/api/base_model/#pydantic.BaseModel.model_validate_json)
  - Specific section: `model_validate_json` classmethod
  - Why: Boundary-validation call already used by `qa.py`/`explainer.py`; practice uses it identically for question + feedback schemas.
- [FastAPI handling errors](https://fastapi.tiangolo.com/tutorial/handling-errors/)
  - Specific section: `HTTPException` with `status_code`
  - Why: Router error-mapping pattern already established; this plan extends the matrix with 409 (stale reference) only.
- [FastAPI query parameters](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/)
  - Specific section: Optional query parameters with defaults
  - Why: `GET /practice/attempts` filter params (`mode`, `explanation_id`, `retry_only`) follow the `GET /work/accomplishments` `q`/`skill` precedent.
- No new libraries, no new SDK calls: the Meta client (`chat_completion`), test doubles (`TestClient`, `monkeypatch`, `vitest`), and SQLite access (`connect`) are all established in-repo patterns. Do not add dependencies for this deliverable.

### Patterns to Follow

**Naming Conventions:** `snake_case` backend modules/functions, `PascalCase` Pydantic models/classes/dataclasses, `PascalCase.tsx` components, `camelCase.ts` api utils. Error classes end `Error` and live in the raising module (`QaValidationError` in `llm/qa.py` → `PracticeValidationError`, `UnknownReferenceError`, `StaleReferenceError`, `NoEvidenceError` in `llm/practice.py`).

**Router seams (by-name imports for monkeypatch):** every collaborator the router touches is imported BY NAME and named in the module docstring, e.g. `app/api/learn.py:8-14`. Practice router seams: `generate_question`, `evaluate_answer`, `chat_completion`, `hybrid_search`, `read_career_context`, `create_attempt`, `record_answer`, `get_attempt`, `list_attempts`, `get_conversation`, `create_conversation_with_turns`, `append_turns`, `get_settings`. `llm/practice.py` is generation-only — all persistence flows through these router seams.

**Orchestration seams (injected callables):** `llm/practice.py` takes `chat_fn`/`search_fn`/`career_fn` and is generation-only — it takes NO `persist_fn`; the router persists via `db/attempts` + conversation repositories after successful generation (qa-precedent: turns + attempt must persist in router order). Unit tests stub the three seams; the router passes `functools.partial`s. ChatFn arity is `(messages, max_tokens)` (explainer/extraction convention — budget travels with the call), NOT qa's `(messages)`.

**Persist-after-validate:** no DB write until generation validates (`explainer.py` header: "Any stage failure raises BEFORE persisting — no partial lessons, no orphan rows"). Question flow: generate → validate → `create_attempt` → persist turns. Answer flow: evaluate → validate → `record_answer` → append turns.

**Exception ordering:** validation-error subclasses of ValueError are caught BEFORE generic ValueError → 502 for model failures, 500 for code bugs (`query.py:164-174`). Practice adds: `NoEvidenceError` → 422, `UnknownReferenceError` → 404, `StaleReferenceError` → 409.

**Logging:** `logger = logging.getLogger(__name__)`; `warning` for rejections/failures with `key=value` params, `info` for served summaries (`query.py:199-204`).

**Frontend api module:** one function per endpoint over `apiGet`/`apiPost`, JSDoc one-liner (`query.ts:10-28`). Types mirror backend JSON exactly (`types.ts:1`).

**Frontend view:** `useState` for input/loading/error + `conversationId`, `role="alert"` error box with Dismiss button, Enter-to-send, disclosure line (`ChatView.tsx`).

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

Schema migration + repository + grounding contracts. No router, no UI. After this phase, attempts persist with conversation linkage and stored references, and all prompt builders are pure and unit-tested.

**Key design decisions (locked):**

1. **Migration v1→v2** adds two NULLABLE columns to `attempts`: `conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL` (PRD §10: answer "inherits its conversation from the attempt") and `reference_json TEXT` (NULL ≡ `{}`; stores `{"fact_ids": [...]}` for experience, `{"chunk_ids": [...]}` for technical; learning uses the existing `explanation_id` column). Fresh DBs get the columns from updated `schema.sql`; existing DBs via idempotent `_migrate()` in `init_db` guarded by `PRAGMA table_info`. `meta.schema_version` becomes `'2'` (default row + migration UPDATE). Deletion-cascade consumption of these edges is deliverable 4's work, not this plan's.
2. **`reference_kind` is a deterministic 1:1 map, not model output:** learning → `"explanation"`, interview/experience → `"facts"`, interview/technical → `"general"`. It names what the rubric judges against.
3. **Grounding labels computed in code** via `resolve_grounding(mode, kind, personal_refs: bool)` in `grounding.py`: experience → always `"from your notes"`; technical → `"both"` if `chunk_ids` non-empty else `"general explanation"`; learning → `"both"` if the explanation carries personal shaping (`reused_from IS NOT NULL` OR memory context resolves to a DIFFERENT explanation id, i.e. `mem is not None and mem.reused_from != explanation_id` — the self-exclusion guards against `build_memory_context` matching the lesson itself) else `"general explanation"`.
4. **Learning mode REQUIRES `context.explanation_id`** (422 `PracticeInputError` otherwise) — explain-back needs the taught lesson. Interview mode REQUIRES `question_kind` (422 if missing); learning REJECTS `question_kind` (422 if present). `focus` is optional everywhere, `max_length=2000` (422 beyond).
5. **Experience grounding is strict:** zero total accomplishment facts → 422 ("no accomplishment facts stored — extract work first"); focus matching zero of N stored → 422 naming the focus and N. No silent fallback (anti-invention). Facts included newest-first, capped at `MAX_PRACTICE_FACTS=10` and `MAX_REFERENCE_CHARS=12000` (deterministic truncation; `reference_json` records exactly the included IDs).
6. **Re-answer overwrites:** answering the same `attempt_id` twice UPDATEs answer/feedback/grounding and appends new turns (supports "retry the full explanation" on one question). New questions create new attempts.
7. **`needs_retry`** (deterministic, repository-computed): answered AND (`missing` non-empty OR `inaccurate` non-empty), parsed defensively (malformed → False). Unanswered attempts are pending, not retry.
8. **Stale references:** experience facts deleted between question and answer → `StaleReferenceError` → 409 ("request a new question"). Technical chunks deleted → dropped with warning (qa.py dropped-leg precedent); all-gone degrades to general-only evaluation. (Deletion itself lands in deliverable 4; the behavior is specified and tested now.)
9. **Turn contents:** question call persists `(user: synthesized request turn, assistant: question)`; answer call persists `(user: answer text, assistant: rendered feedback)`. Synthesized user-turn text via `build_practice_request_turn(mode, kind, descriptor)` in `grounding.py` (deterministic, e.g. `Practice (learning): explain back the lesson on 'RAG'`); feedback rendering via `render_feedback_text(feedback)` in `grounding.py`. Turn `mode` column stores `"learning"` / `"interview:experience"` / `"interview:technical"`. Conversation `kind` is `"learning"`/`"interview"` at creation, unchanged when continuing (continuing a foreign-kind conversation is allowed — kind is an origin label). Citations `"[]"` for practice turns (no chunk citations in MVP feedback).
10. **NULL conversation guard:** if `attempt.conversation_id` is NULL (conversation deleted — possible once deliverable 4 lands), the answer call creates a fresh conversation for its turns instead of failing.

**Tasks:**

- Extend `schema.sql` attempts DDL + version default; add `_migrate()` to `connection.init_db`
- CREATE `db/attempts.py` (+ ADD `get_facts_by_ids` to `db/facts.py`)
- ADD practice contract block to `core/grounding.py`
- CREATE `llm/practice.py`

### Phase 2: Core Implementation

Router + registration. After this phase the three endpoints work end-to-end over stubbed or real chat.

**Tasks:**

- CREATE `api/practice.py` (models mirror PRD §10 exactly; 200 on POSTs like explain/query siblings, NOT 201)
- UPDATE `main.py` router registration

### Phase 3: Integration

Frontend client + shared components + views + App wiring. After this phase both tabs run the full loop against the backend.

**Tasks:**

- ADD practice types to `api/types.ts`; CREATE `api/practice.ts`
- CREATE `FeedbackCard` + `AttemptHistory` (shared presentation; per-view loop state — matches the codebase's no-custom-hooks precedent)
- CREATE `PracticeView` (explanation picker via existing `listExplanations`) + `InterviewView` (kind radio + focus input)
- UPDATE `App.tsx` (replace practice/interview stubs; keep capture stub)

### Phase 4: Testing & Validation

- Backend: `test_attempts.py`, `test_practice.py`, `test_practice_api.py` (new); ADD migration test to `test_db_init.py`, grounding cases to `test_grounding.py`
- Frontend: `practice.test.ts`, `FeedbackCard.test.tsx`, `AttemptHistory.test.tsx`, `PracticeView.test.tsx`, `InterviewView.test.tsx` (new)
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

### UPDATE backend/app/db/schema.sql

- **IMPLEMENT**: attempts DDL gains `conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL` and `reference_json TEXT` (both nullable, after `grounding`); meta default `schema_version` `'1'` → `'2'`. Update the header comment (`schema v1` → `schema v2`, noting the additive attempts migration).
- **PATTERN**: `schema.sql:6-12` (meta rows), `schema.sql:120-130` (attempts DDL)
- **IMPORTS**: none (SQL only)
- **GOTCHA**: `CREATE TABLE IF NOT EXISTS` never alters existing DBs — the `_migrate()` in Task 2 is what upgrades them; schema.sql alone only serves fresh DBs. Do NOT backfill or set defaults: NULL is meaningful (pre-migration rows).
- **VALIDATE**: `cd backend && uv run pytest tests/test_db_init.py -q`

### UPDATE backend/app/db/connection.py

- **IMPLEMENT**: ADD `_migrate(conn)` called at the end of `init_db` (after `executescript`, before the summary log so the log reflects post-migration state): for each of (`conversation_id`, `reference_json`) on `attempts`, `PRAGMA table_info(attempts)` check → `ALTER TABLE attempts ADD COLUMN ...` when missing (exact DDL strings shared with schema.sql); when any column was added, `UPDATE meta SET value='2' WHERE key='schema_version'`. Idempotent: re-running on a v2 DB is a no-op. Log `db migrate: ...` at info when a change applies.
- **PATTERN**: `connection.py:33-50` (`init_db` structure/log line)
- **IMPORTS**: none new (sqlite3 already imported)
- **GOTCHA**: `executescript` auto-commits; run migration statements inside `with conn:` for atomicity. Never gate on the meta version value alone — the `PRAGMA table_info` column check is the real guard (a v1-labeled DB could theoretically already have the columns).
- **VALIDATE**: `cd backend && uv run pytest tests/test_db_init.py -q`

### CREATE backend/app/db/attempts.py

- **IMPLEMENT**: `AttemptDetail` dataclass (`id, mode, question_kind|None, explanation_id|None, concept|None, question, answer|None, feedback|None (parsed dict), grounding|None, needs_retry: bool, conversation_id|None, reference: dict (parsed `reference_json`, NULL→{}), created_at`); `create_attempt(db_path, *, mode, question_kind, explanation_id, question, conversation_id, reference_json: dict)` (single transaction, `reference_json` dumped, returns id); `record_answer(db_path, attempt_id, *, answer, feedback: dict, grounding)` (UPDATE, returns False when attempt missing); `get_attempt(db_path, attempt_id)` (None when missing; LEFT JOIN explanations for `concept`; NULL reference→`{}` normalization happens at read for forward-compat); `list_attempts(db_path, *, mode=None, explanation_id=None, retry_only=False)` (newest-first; `retry_only` filters to `needs_retry` in Python). `feedback` TEXT parsed defensively at read: malformed JSON or non-dict → None (never raises — listing must survive bad stored rows). `needs_retry`: answered AND (`missing`/`inaccurate` non-empty lists; None/malformed/missing → False). Unanswered → False.
- **PATTERN**: `db/explanations.py:17-100` (Detail dataclass + create/get shape, `uuid.uuid4().hex`, `datetime.now(UTC).isoformat()`, `with conn:`); `db/conversations.py:60-96` (single-transaction writes); `db/facts.py:119-128` (defensive JSON parse)
- **IMPORTS**: `json, logging, uuid, datetime (UTC), dataclasses.dataclass, app.db.connection.connect`
- **GOTCHA**: `record_answer` overwrite (not insert) is the specified re-answer semantic — do NOT reject already-answered attempts. `list_attempts` mode filter validates nothing (router owns 422s); unknown mode strings just match zero rows.
- **VALIDATE**: `cd backend && uv run pytest tests/test_attempts.py -q`

### ADD backend/app/db/facts.py::get_facts_by_ids

- **IMPLEMENT**: ADD `get_facts_by_ids(db_path, ids: list[str]) -> dict[str, FactRead]` mirroring `list_accomplishments` hydration (`_clean_skills`, chunk/link maps) but with `WHERE id IN (...)` (parameterized, any kind — experience references are accomplishments but the reader stays general). Empty `ids` → `{}` without querying.
- **PATTERN**: `db/facts.py:142-200` (read + hydrate structure)
- **IMPORTS**: none new
- **GOTCHA**: preserve input-ID lookup by returning a dict keyed by fact id (caller detects missing IDs for the 409 path). Do NOT refactor `list_accomplishments` to share code — mirror it; a shared-hydration refactor is out of scope.
- **VALIDATE**: `cd backend && uv run pytest tests/test_attempts.py tests/test_accomplishments.py -q`

### ADD backend/app/core/grounding.py practice block

- **IMPLEMENT**: ADD after the extraction block: `PRACTICE_MODES=("learning","interview")`, `QUESTION_KINDS=("experience","technical")`, `REFERENCE_KINDS=("explanation","facts","general")`, `GROUNDING_LABELS=("from your notes","general explanation","both")`; `QUESTION_SYSTEM_PROMPTS: dict[tuple[str,str|None], str]` keyed `("learning",None)`, `("interview","experience")`, `("interview","technical")` (experience = closed-world over provided facts, refuse-when-silent does not apply to question-gen — instead the NoEvidence 422 fires before the call; technical/learning = open-world with personalization); `EVALUATION_SYSTEM_PROMPTS` same keys with per-branch rubric (learning: judge ONLY against the lesson, quote step names; experience: judge claims ONLY against the provided facts AND their cited source excerpts (both are rendered into `reference_block` by the caller), flag claims unsupported by either as inaccurate; technical: judge conceptual accuracy, credit personal examples when present); `QUESTION_JSON_INSTRUCTIONS` (`{"question": "<single question>"}`); `EVALUATION_JSON_INSTRUCTIONS` (`{"feedback": {"correct": [...], "missing": [...], "inaccurate": [...], "terminology": [...], "next_step": "<one concrete next step>"}}` — `next_step` is a STRING per PRD §10 example); `build_question_messages(*, mode, kind, reference_block, career_block, focus)` and `build_evaluation_messages(*, mode, kind, reference_block, answer)` pure builders (focus + answer framed as UNTRUSTED data via existing framing constants — the user answer is judged as data, never followed as instructions); `resolve_grounding(mode, kind, personal_refs) -> GroundingLabel` (decision 3); `build_practice_request_turn(mode, kind, descriptor) -> str`; `render_feedback_text(feedback: Mapping) -> str` (deterministic sections: Correct/Missing/Inaccurate/Terminology/Next step, `"(none)"` for empty lists). Career block composes per the recipe at `grounding.py:442-445` (header + `CAREER_LINES_FRAMING` + `render_career_profile_lines`, `""` when empty).
- **PATTERN**: `grounding.py:350-420` (extraction contract block style); `grounding.py:429-457` (career lines renderer + Phase 3 recipe)
- **IMPORTS**: none new (`json, re, dataclasses, typing.Literal, collections.abc.Mapping` already present)
- **GOTCHA**: this module stays pure — no settings/DB/network imports (header contract `grounding.py:1-6`). `render_feedback_text` must never raise on odd shapes (defensive `.get` + str() coercion) — it runs on the turn-persist path.
- **VALIDATE**: `cd backend && uv run pytest tests/test_grounding.py -q`

### CREATE backend/app/llm/practice.py

- **IMPLEMENT**: `PracticeChatFn = Callable[[list[dict[str,str]], int], Awaitable[str]]`; `PracticeSearchFn = Callable[[str, int], list[SearchHit]]` (mirror `qa.SearchFn`); reuse `CareerFn`/`CareerContext`/`no_career` from `app.llm.extraction` (import, do not redefine); `QUESTION_MAX_TOKENS=8192`, `EVALUATION_MAX_TOKENS=8192`, `MAX_PRACTICE_FACTS=10`, `MAX_REFERENCE_CHARS=12000`. Errors: `PracticeInputError(ValueError)` → 422, `UnknownReferenceError(ValueError)` → 404, `NoEvidenceError(ValueError)` → 422, `StaleReferenceError(ValueError)` → 409, `PracticeValidationError(ValueError)` → 502. `QuestionModelOut(BaseModel): question: str` (non-blank enforced post-parse); `FeedbackModelOut`/`PracticeFeedbackOut` models for the 5-key feedback shape. `QuestionResult(question, question_kind|None, reference_kind, reference_json: dict, explanation_id|None)`; `EvaluationResult(feedback: dict, grounding: str)`. `async generate_question(*, mode, question_kind, explanation_id, focus, db_path, chat_fn, search_fn, career_fn)`: validate mode/kind matrix (decision 4) → assemble reference per branch (learning: `get_explanation` + `build_explanation_context`, 404 when missing; experience: `list_accomplishments(q=focus or None)`, 422s per decision 5, newest-first inclusion within `MAX_PRACTICE_FACTS`/`MAX_REFERENCE_CHARS` (block built fact-by-fact — each fact's summary + status + skills + its supporting chunk excerpts via `get_chunks` over the fact's `chunk_ids` rendered with `excerpt_of` — stopping before the cap would break; `reference_json={"fact_ids": [...]}` records exactly the included facts); technical: `hybrid_search` via `search_fn(focus or "technical interview concepts", TOP_K_DEFAULT)` (empty hits legal → `chunk_ids: []`), `reference_json={"chunk_ids": [...]}`) → career block (all branches) → `build_question_messages` → `chat_fn(messages, QUESTION_MAX_TOKENS)` → `strip_fences` + `model_validate_json` (import `strip_fences` from `app.llm.qa`) → non-blank check → return. `async evaluate_answer(*, mode, question_kind, explanation_id, reference_json, question, answer, db_path, chat_fn)`: non-blank answer assumed (router 422s blanks); rehydrate STORED reference (learning: `get_explanation` → 404-flavored `UnknownReferenceError` when gone; experience: `get_facts_by_ids` → `StaleReferenceError` when ANY id missing, then `get_chunks` over the facts' `chunk_ids` (missing chunks dropped with warning — the fact summary stays, only its excerpt is lost); technical: `get_chunks` → drop missing with warning, possibly empty) → `build_evaluation_messages` → `chat_fn(messages, EVALUATION_MAX_TOKENS)` → validate → `resolve_grounding` in code (learning `personal_refs` = `reused_from is not None or (mem is not None and mem.reused_from != explanation_id)` where `mem = build_memory_context(db_path, concept)` (self-exclusion: a lone lesson matching only itself still yields `"general explanation"`); import `build_memory_context` from `app.llm.memory`) → return. Persistence stays in the ROUTER via repository calls (qa-style: `llm/` is generation-only; `db/attempts` writes happen in `api/practice.py` after success) — NOTE this differs from explainer's `persist_fn`; qa is the closer precedent because turns + attempt must persist in router order.
- **PATTERN**: `llm/qa.py:72-137` (seam orchestration + validate + dropped-leg warnings); `llm/explainer.py` (ChatFn arity, token-budget constants); `llm/extraction.py:163-175` (career seam)
- **IMPORTS**: `app.core.grounding` (builders, `resolve_grounding`, tuples), `app.db.explanations.get_explanation`, `app.db.facts.get_facts_by_ids/list_accomplishments`, `app.db.chunks.get_chunks`, `app.llm.qa.strip_fences`, `app.llm.memory.build_memory_context`, `app.llm.extraction` (`CareerFn`, `no_career`), `app.retrieval.search` (`SearchHit`, `TOP_K_DEFAULT`, `excerpt_of`)
- **GOTCHA**: NEVER re-derive experience/technical references at answer time — rehydrate `reference_json` only (drift + the AND-semantics `_matches_q` trap make re-derivation wrong). `build_memory_context` needs the concept string — from the joined explanation, NOT from user input. Circular-import check: `llm/practice.py` imports `llm/{qa,memory,extraction}` — none of them may import `llm/practice`.
- **VALIDATE**: `cd backend && uv run pytest tests/test_practice.py -q`

### CREATE backend/app/api/practice.py

- **IMPLEMENT**: Models (PRD §10 exact): `PracticeQuestionContext(explanation_id|None=None, focus|None=Field(default=None, max_length=2000))`; `QuestionRequest(mode: Literal["learning","interview"], question_kind: Literal["experience","technical"]|None=None, context: PracticeQuestionContext|None=None, conversation_id|None=None)`; `QuestionResponse(attempt_id, question, question_kind|None, reference_kind, conversation_id)`; `AnswerRequest(attempt_id, answer)`; `FeedbackOut(correct/missing/inaccurate/terminology: list[str], next_step: str)`; `AnswerResponse(feedback: FeedbackOut, grounding: str)`; `AttemptOut(id, mode, question_kind|None, explanation_id|None, concept|None, question, answer|None, feedback: FeedbackOut|None, grounding|None, needs_retry: bool, created_at)`. `POST /practice/question` (200): normalize `context or PracticeQuestionContext()`; blank-focus → None; existing-conversation check (404 like `query.py:107-114`); `generate_question` with `_make_chat_fn` + `search_fn` closure (`hybrid_search(db_path, query, top_k, embedding_model, None)` like `query.py:135-142`) + `career_fn=functools.partial(read_career_context, db_path)`; on success `create_attempt(...)` then `create_conversation_with_turns(kind="learning"|"interview", turns)` or `append_turns` (turns per decision 9); map `PracticeInputError/NoEvidenceError`→422, `UnknownReferenceError`→404, `MetaAPIError/PracticeValidationError`→502, `(EmbeddingDimMismatchError, ValueError)`→500. `POST /practice/answer` (200): blank answer → 422; `get_attempt` → 404 when missing; `evaluate_answer` with stored reference (pass `reference_json` — repository exposes it; see Task 3 note) → `record_answer` → append turns to `attempt.conversation_id` (NULL → create fresh conversation per decision 10); `StaleReferenceError`→409. `GET /practice/attempts` (200): optional `mode` (Literal incl. validation → 422 on garbage via FastAPI), `explanation_id` (blank → 422 like `q`/`skill` precedent), `retry_only: bool=False` → `list_attempts`. Attempt `feedback` conversion is defensive at BOTH layers and never raises: the repository returns `feedback` as parsed-dict-or-None (malformed JSON → None); the router maps each dict → `FeedbackOut` inside try/except (`ValidationError` → None, e.g. partial shapes missing keys), so `AttemptOut.feedback` is `FeedbackOut`-or-null and listing never 500s on bad stored data. Module docstring lists by-name seams (Task: `generate_question, evaluate_answer, chat_completion, hybrid_search, read_career_context, create_attempt, record_answer, get_attempt, list_attempts, get_conversation, create_conversation_with_turns, append_turns, get_settings`).
- **PATTERN**: `api/query.py:96-210` (endpoint flow + turn persist + exception order); `api/learn.py:134-148` (`_make_chat_fn`); `api/work.py:205-235` (query-param filters + blank rejection)
- **IMPORTS**: `functools, json, logging, fastapi (APIRouter, HTTPException, Query, status), pydantic (BaseModel, Field, Literal→typing)`, `app.core.config.get_settings`, `app.core.grounding (build_practice_request_turn, render_feedback_text)`, `app.core.meta_client (DEFAULT_META_MODEL, MetaAPIError, chat_completion)`, `app.db.attempts (...)`, `app.db.connection.EmbeddingDimMismatchError`, `app.db.conversations (...)`, `app.llm.extraction.read_career_context`, `app.llm.practice (...)`, `app.retrieval.search (TOP_K_DEFAULT, TOP_K_MAX?, hybrid_search)`
- **GOTCHA**: `get_attempt` must ALSO return `reference_json` + `conversation_id` (add both fields to `AttemptDetail` in Task 3 — the router needs them). POSTs return 200 (sibling precedent), not 201. Attempt `mode` turn-label: `"learning"` or `f"interview:{kind}"`. Descriptor for the request turn: learning → concept (`f"explain back the lesson on '{concept}'"` — concept from the explanation row, fetched post-generation), interview → focus or kind (`f"answer an experience question about '{focus}'"` / `"answer a technical question"`).
- **VALIDATE**: `cd backend && uv run pytest tests/test_practice_api.py -q`

### UPDATE backend/app/main.py

- **IMPLEMENT**: ADD `from app.api.practice import router as practice_router` + `app.include_router(practice_router, prefix="/api/v1")` after the work line.
- **PATTERN**: `main.py:14-60`
- **IMPORTS**: `app.api.practice`
- **GOTCHA**: none — one import + one line. Verify no route collisions (`/practice/*` is a fresh prefix).
- **VALIDATE**: `cd backend && uv run pytest tests/test_app_boot.py tests/test_practice_api.py -q`

### ADD backend/tests/test_db_init.py migration test

- **IMPLEMENT**: ADD `test_attempts_v1_to_v2_migration`: build a synthetic v1 DB (raw sqlite3: `CREATE TABLE attempts (id TEXT PRIMARY KEY, mode TEXT NOT NULL, question_kind TEXT, explanation_id TEXT, question TEXT NOT NULL, answer TEXT, feedback TEXT, grounding TEXT, created_at TEXT NOT NULL)` + one row + `meta(schema_version='1', embedding_model/dim)` + minimal companion tables? NO — simpler: `init_db` on a DB where ONLY `meta`+v1-`attempts` exist: `executescript` creates all missing tables, `_migrate` adds the two columns. Assert: both columns in `PRAGMA table_info`, `schema_version=='2'`, the v1 row intact with NULL new columns, second `init_db` is a no-op (idempotency).
- **PATTERN**: `test_db_init.py:23-28` (fixture style); raw-SQL style of `test_fact_chunks_supports_f10_counting`
- **IMPORTS**: existing (`connect, init_db`) only
- **GOTCHA**: the synthetic DB must include `embedding_model`/`embedding_dim` meta rows or nothing breaks (init only INSERT OR IGNOREs). Do NOT hand-write the full schema — let `init_db` create everything except the pre-existing v1 `attempts`.
- **VALIDATE**: `cd backend && uv run pytest tests/test_db_init.py -q`

### ADD backend/tests/test_grounding.py practice cases

- **IMPLEMENT**: ADD cases: `build_question_messages` per branch (system prompt selection, career block present/absent, focus framing as data); `build_evaluation_messages` per branch (rubric keywords present: learning→lesson-only, experience→facts-only/unsupported-claims, technical→conceptual accuracy); `resolve_grounding` truth table (all mode/kind/personal_refs combos); `build_practice_request_turn` format; `render_feedback_text` (full + empty-lists + odd-shape-never-raises).
- **PATTERN**: existing `test_grounding.py` builder assertions (read the file first)
- **IMPORTS**: new grounding names only
- **GOTCHA**: assert on builder OUTPUT strings, not on the constant names — constants may be reworded, semantics must hold.
- **VALIDATE**: `cd backend && uv run pytest tests/test_grounding.py -q`

### CREATE backend/tests/test_attempts.py

- **IMPLEMENT**: tmp-DB repository tests: create→get round-trip (all fields incl. `reference_json`/`conversation_id`); `record_answer` fills + overwrite-on-re-answer; `get_attempt` None-on-missing + concept join (explanation-linked vs NULL); `list_attempts` newest-first + `mode`/`explanation_id` filters + `retry_only` (needs_retry TRUE iff answered AND missing-or-inaccurate non-empty; unanswered → False; malformed feedback JSON → False); NULL `reference_json` reads as `{}`.
- **PATTERN**: `test_db_init.py` raw-SQL fixtures; `test_learn_api.py:60-65` (`init_db` on tmp path)
- **IMPORTS**: `app.db.attempts`, `app.db.connection.init_db`, `app.db.explanations.create_explanation` (for concept join), `app.db.conversations.create_conversation` (for FK linkage)
- **GOTCHA**: FKs enforced — `conversation_id`/`explanation_id` used in tests must reference real rows (or NULL). `create_attempt` with bogus FK ids must raise IntegrityError — assert it (contract, not just behavior).
- **VALIDATE**: `cd backend && uv run pytest tests/test_attempts.py -q`

### CREATE backend/tests/test_practice.py

- **IMPLEMENT**: orchestration tests with stubbed `chat_fn`/`search_fn`/`career_fn` over tmp DBs: learning branch (explanation context in messages, `reference_kind=="explanation"`, missing explanation_id → `PracticeInputError`, unknown id → `UnknownReferenceError`); experience branch (facts in prompt newest-first + supporting chunk excerpts present, caps applied, `reference_json` ids match included facts, zero-facts → `NoEvidenceError`, focus-miss → `NoEvidenceError` naming focus+N); experience evaluation messages contain a supporting chunk excerpt verbatim (seed fact + chunk, capture `chat_fn` messages, assert excerpt substring); technical branch (passages woven, empty-hits legal with `chunk_ids==[]`); kind/matrix violations (learning+kind, interview-kindless → `PracticeInputError`); malformed/blank model output → `PracticeValidationError`; `evaluate_answer` per branch (stored-reference rehydration — prove NO search call happens for experience via strict stub; stale fact id → `StaleReferenceError`; technical missing chunks dropped; grounding labels per truth table incl. learning personal-shaping via `reused_from`/memory AND the self-match guard (single explanation with `reused_from` NULL and no other versions → `"general explanation"`, proving `build_memory_context` matching the lesson itself cannot flip the label to `"both"`)).
- **PATTERN**: `test_qa.py`/`test_extraction.py` stub-seam style (read one first for the stub shapes)
- **IMPORTS**: `app.llm.practice`, repo builders for fixtures (`create_explanation`, `create_facts`, `create_conversation`), `app.llm.extraction.no_career`
- **GOTCHA**: the "no search call for experience evaluation" test is the anti-re-derivation lock — use a `search_fn` that raises. `build_memory_context` needs real explanation rows for the learning-`both` case (seed two versions with `reused_from`).
- **VALIDATE**: `cd backend && uv run pytest tests/test_practice.py -q`

### CREATE backend/tests/test_practice_api.py

- **IMPLEMENT**: TestClient(tmp DB) + settings-isolation fixture (copy `test_learn_api.py:41-65`, retargeting `app.api.practice.get_settings`): question happy-path shape per PRD (`attempt_id/question/question_kind/reference_kind/conversation_id` keys exact); answer happy-path shape (`feedback.{correct,missing,inaccurate,terminology,next_step}` + `grounding` keys exact); attempts list shape; status matrix (blank answer 422, overlong focus 422, learning+kind 422, interview-kindless 422, unknown explanation/conversation/attempt 404, stale 409, Meta/validation 502 via raising stubs); malformed-feedback resilience (seed one attempt with garbage `feedback` TEXT and one with a partial-dict `feedback` via raw SQL, assert `GET /practice/attempts` returns 200 with `feedback: null` on both rows and history still renders); conversation inheritance (answer turns land in the QUESTION's conversation — prove via `get_conversation` turn count/order/roles); new-question/new-conversation vs continue-conversation; re-answer overwrite (second answer UPDATEs + appends turns); NULL-conversation answer creates fresh conversation; `retry_only`/`mode`/`explanation_id` filters; blank `explanation_id` filter 422.
- **PATTERN**: `test_learn_api.py:41-110` (fixture + client + happy-path + 422 cases); `test_query_api.py` turn-persistence assertions (read for the conversation-proof style)
- **IMPORTS**: `app.main.create_app`, `app.core.config.Settings/get_settings`, `app.db.connection.init_db`, `app.db.conversations.get_conversation`, `app.llm.practice` result types, `MetaAPIError`
- **GOTCHA**: stub at `app.api.practice.<name>` (by-name seams) — stubbing `app.llm.practice.*` directly does NOT affect the router. Seed attempt rows via the real `create_attempt` (not SQL) for answer-path tests, with real conversation rows for FK.
- **VALIDATE**: `cd backend && uv run pytest tests/test_practice_api.py -q`

### ADD frontend/src/api/types.ts practice types

- **IMPLEMENT**: ADD `PracticeMode='learning'|'interview'`, `QuestionKind='experience'|'technical'`, `ReferenceKind='explanation'|'facts'|'general'`, `GroundingLabel='from your notes'|'general explanation'|'both'`, `PracticeQuestionContext{explanation_id?: string|null; focus?: string|null}`, `PracticeQuestionRequest{mode: PracticeMode; question_kind?: QuestionKind|null; context?: PracticeQuestionContext; conversation_id?: string|null}`, `PracticeQuestionResponse{attempt_id: string; question: string; question_kind: QuestionKind|null; reference_kind: ReferenceKind; conversation_id: string}`, `PracticeAnswerRequest{attempt_id: string; answer: string}`, `PracticeFeedback{correct: string[]; missing: string[]; inaccurate: string[]; terminology: string[]; next_step: string}`, `PracticeAnswerResponse{feedback: PracticeFeedback; grounding: GroundingLabel}`, `PracticeAttempt{id: string; mode: PracticeMode; question_kind: QuestionKind|null; explanation_id: string|null; concept: string|null; question: string; answer: string|null; feedback: PracticeFeedback|null; grounding: GroundingLabel|null; needs_retry: boolean; created_at: string}`.
- **PATTERN**: `types.ts:1-26` (exact backend-JSON mirroring)
- **IMPORTS**: none
- **GOTCHA**: `question_kind: QuestionKind | null` (backend sends explicit null for learning, not undefined) — the distinction matters for `JSON.parse` round-trips in tests.
- **VALIDATE**: `cd frontend && npm run build`

### CREATE frontend/src/api/practice.ts + practice.test.ts

- **IMPLEMENT**: `postPracticeQuestion(req) → POST /api/v1/practice/question`; `postPracticeAnswer(req) → POST /api/v1/practice/answer`; `listAttempts(filters?: {mode?, explanation_id?, retry_only?}) → GET /api/v1/practice/attempts?...` (URLSearchParams; `retry_only` only when true). Tests mirror `query.test.ts`: URL+method+body assertions per function, query-string encoding, non-OK rejection, `VITE_API_URL` honor.
- **PATTERN**: `api/query.ts` (full); `api/query.test.ts` (full)
- **IMPORTS**: `./client` (`apiGet, apiPost`), `./types`
- **GOTCHA**: `retry_only=false` must OMIT the param (backend default False) — assert the bare URL in that case.
- **VALIDATE**: `cd frontend && npm test -- --run src/api/practice.test.ts`

### CREATE frontend/src/components/FeedbackCard.tsx + test

- **IMPLEMENT**: Props `{feedback: PracticeFeedback; grounding: GroundingLabel}`. Sections in fixed order Correct/Missing/Inaccurate/Terminology help/Next step (`<h4>` labels); empty lists render `(none)`; `next_step` emphasized; grounding badge `<p aria-label="Grounding">` rendering the label VERBATIM with distinct styling per value (`from your notes` = green-ish border, `general explanation` = neutral, `both` = blue-ish — Tailwind classes only, deliverable 5 unifies). Test: full feedback renders all sections + verbatim badge; empty-lists render `(none)`; each grounding value renders its badge.
- **PATTERN**: `ChatView.tsx:80-105` (assistant bubble + grounding line); `FactCard.tsx` (read for component+test shape precedent)
- **IMPORTS**: `../api/types`
- **GOTCHA**: no fetching in this component — pure presentational (props only), so tests need no fetch stub.
- **VALIDATE**: `cd frontend && npm test -- --run src/components/FeedbackCard.test.tsx`

### CREATE frontend/src/components/AttemptHistory.tsx + test

- **IMPLEMENT**: Props `{attempts: PracticeAttempt[]; onRetry: (a: PracticeAttempt) => void}`. Header `Practice history (N)` + `Retry queue (M)` count line; retry-queue section FIRST (needs_retry, oldest-first, `Retry` button per item `aria-label={`Retry ${id}`}`), then full list newest-first with per-item mode/kind/concept/question/grounding + `Retry` badge text on needs_retry items. Empty → `No attempts yet.`. Test: counts, ordering, retry callback fires with the attempt, empty state. No fetching (props only).
- **PATTERN**: `FeedbackCard` (sibling just built); ChatView test style for queries
- **IMPORTS**: `../api/types`
- **GOTCHA**: `onRetry` passes the WHOLE attempt (view needs `attempt_id` + `question` + `conversation_id`? — NO: backend `AttemptOut` carries no conversation_id; retry re-answers the same attempt_id and the BACKEND resolves the conversation. View must not need it.)
- **VALIDATE**: `cd frontend && npm test -- --run src/components/AttemptHistory.test.tsx`

### CREATE frontend/src/views/PracticeView.tsx + test

- **IMPLEMENT**: Learning loop. State (ChatView style): `explanations` (loaded on mount via existing `listExplanations`), `explanationId` select (`aria-label="Lesson"`), `question/attemptId`, `answerInput`, `feedback/grounding`, `attempts`, `conversationId`, loading/error. Flow: pick lesson → `Get question` (`postPracticeQuestion({mode:'learning', context:{explanation_id}, conversation_id})`) → question card → answer textarea (`aria-label="Your answer"`) → `Submit answer` → `FeedbackCard` → `Next question` (same lesson, same conversation) + `Start new session` (resets conversation/question/feedback, keeps history). History via `listAttempts({mode:'learning'})` on mount + after each answer; `onRetry` loads attempt question+id into answer state. Error box + Dismiss + `Conversations are saved and retrievable.` disclosure (ChatView mirror). Tests (`mockFetchSequence`): mount loads explanations+attempts; full question→answer→feedback flow with URL/body assertions; retry loads prior question; error dismiss; empty-explanations state disables `Get question` with hint text.
- **PATTERN**: `ChatView.tsx` (state/error/conversation flow); `LearnView.tsx` (explanation-list loading); `ChatView.test.tsx` (mockFetchSequence + flow assertions)
- **IMPORTS**: `../api/practice`, `../api/learn` (`listExplanations`), `../components/FeedbackCard`, `../components/AttemptHistory`
- **GOTCHA**: mount fires TWO fetches (explanations + attempts) — tests must queue both payloads in order. `Get question` disabled until a lesson is chosen AND not loading. After `Start new session`, next question omits `conversation_id` (pass null).
- **VALIDATE**: `cd frontend && npm test -- --run src/views/PracticeView.test.tsx`

### CREATE frontend/src/views/InterviewView.tsx + test

- **IMPLEMENT**: Interview loop. Same loop skeleton as PracticeView, but context controls are: kind radio (`Experience`/`Technical`, `name="question-kind"`, default experience) + focus input (`aria-label="Focus (optional)"`, blank → omit). `postPracticeQuestion({mode:'interview', question_kind, context:{focus?}, conversation_id})`. History via `listAttempts({mode:'interview'})`. Per-question `question_kind` chip on the question card (`aria-label="Question kind"`). Tests mirror PracticeView: default-kind flow, kind switch changes request body, blank focus omits context key assertions, retry, error dismiss.
- **PATTERN**: `PracticeView` (sibling just built — same skeleton, different context controls)
- **IMPORTS**: `../api/practice`, `../components/FeedbackCard`, `../components/AttemptHistory`
- **GOTCHA**: do NOT abstract a shared loop hook/component — two thin views + shared presentational components is the specified shape (matches the no-custom-hooks precedent; deliverable 5 may unify). Radio change must reset current question state (a stale experience question under the technical radio is a real confusion bug — test it).
- **VALIDATE**: `cd frontend && npm test -- --run src/views/InterviewView.test.tsx`

### UPDATE frontend/src/App.tsx

- **IMPLEMENT**: Import `PracticeView`/`InterviewView`; replace the practice/interview stub blurbs with the views (`view==='practice' ? <PracticeView/> : view==='interview' ? <InterviewView/> : ...`). Keep the capture stub untouched.
- **PATTERN**: `App.tsx:8-14, 42-44`
- **IMPORTS**: `./views/PracticeView`, `./views/InterviewView`
- **GOTCHA**: the `VIEWS` array `blurb` for practice/interview becomes `''` (rendered views need no blurb) — keep the entries (tab order/labels unchanged).
- **VALIDATE**: `cd frontend && npm test -- --run && npm run build`

---

## TESTING STRATEGY

Backend: `pytest` over tmp-DB `TestClient`s with by-name monkeypatch stubs (never network, never fastembed) for API tests; direct orchestration calls with stubbed seams for `llm/` tests; raw-`connect` tmp DBs for repository tests. Frontend: `vitest` + Testing Library; `mockFetch`/`mockFetchSequence` for all network; no real backend.

### Unit Tests

- `test_attempts.py`: lifecycle round-trip, re-answer overwrite, concept join, filters, `retry_only`, `needs_retry` truth table (answered+missing, answered+inaccurate, answered-clean, unanswered, malformed-feedback), NULL-reference normalization, FK IntegrityError contract.
- `test_practice.py`: all three reference-assembly branches, cap/truncation exactness (`reference_json` IDs == included facts/chunks), every error type, no-re-derivation lock (raising `search_fn` in experience evaluation), grounding truth table, blank/model-malformed outputs.
- `test_grounding.py` additions: builder branch selection, rubric keywords, `resolve_grounding` table, turn/request text formats, never-raises renderer.
- `test_db_init.py` addition: v1→v2 migration (columns, version bump, data preserved, idempotent re-run).
- `practice.test.ts`, `FeedbackCard.test.tsx`, `AttemptHistory.test.tsx`: contract + render + callback coverage per task specs.

### Integration Tests

- `test_practice_api.py`: full question→answer→attempts flow per mode/kind with REAL repositories (only `generate_question`/`evaluate_answer` or deeper seams stubbed — prefer stubbing `chat_completion`+`hybrid_search` so the real orchestration runs); turn order/roles/contents proven via `get_conversation`; conversation inheritance + NULL-conversation recovery; re-answer end-to-end.
- `PracticeView.test.tsx` / `InterviewView.test.tsx`: full UI flows with sequenced fetch mocks incl. history refresh after answer.
- Live smoke (Level 4 agent step): real-key TestClient + scratch `/tmp` DB proving one learning + one interview exchange against the Meta API (documents the demo path; uses an isolated DB per working-notes rule).

### Edge Cases

- Answer before question's conversation exists (NULL conversation) → fresh conversation, no 500.
- All experience facts deleted between Q&A → 409 with actionable detail.
- All technical chunks deleted between Q&A → general-only evaluation, grounding `"general explanation"`.
- Re-answer storm (5 answers, one attempt) → latest wins, 10 new turns appended in order.
- `focus` of 2000 chars ok / 2001 → 422.
- `retry_only=true` with zero retries → `[]` (not 404).
- Malformed stored feedback → `needs_retry` False, history still renders.
- Interview kind radio switched mid-question → stale question cleared.
- Practice with zero stored explanations → picker empty state, `Get question` disabled.

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
cd backend && uv run pytest tests/test_attempts.py tests/test_practice.py tests/test_grounding.py tests/test_db_init.py -q
```
Expected: exit 0, all passed (no failures/errors/skips).

```bash
cd frontend && npm test -- --run src/api/practice.test.ts src/components/FeedbackCard.test.tsx src/components/AttemptHistory.test.tsx
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

**L4-1 [agent] Live learning exchange (real key, scratch DB):**

1. `cd backend && DATABASE_PATH=/tmp/practice_smoke.db MODEL_API_KEY="$MODEL_API_KEY" uv run python /tmp/practice_live_smoke.py` where the script (write to `/tmp`, NOT committed): TestClients `create_app()` as context manager; seeds one artifact+chunks via the ingest pipeline helpers and one explanation row via `create_explanation`; `POST /api/v1/practice/question {mode:'learning', context:{explanation_id}}`; asserts a non-empty `question` + `reference_kind=='explanation'`; `POST /api/v1/practice/answer {attempt_id, answer:'RAG retrieves passages then generates.'}`; asserts 5-key `feedback` + `grounding in ('general explanation','both')`.
2. Expected: exit 0, both questions non-blank, feedback has exactly `correct/missing/inaccurate/terminology/next_step`, grounding label one of the two teaching values, then delete `/tmp/practice_smoke.db*`.

**L4-2 [agent] Live interview exchange (real key, scratch DB):**

1. Same harness, fresh `/tmp/practice_smoke2.db`: seed artifact → `POST /work/extract` (real extraction) → `POST /api/v1/practice/question {mode:'interview', question_kind:'experience', context:{}}` asserts `reference_kind=='facts'`; answer it, assert 5-key `feedback` + `grounding=='from your notes'`; then `question_kind:'technical'` with `focus:'APIs'` asserts `reference_kind=='general'`, answer it, assert 5-key `feedback` + `grounding in ('general explanation','both')`.
2. Expected: exit 0 with all five asserted values (experience reference+feedback+grounding, technical reference+feedback+grounding); then delete the scratch DB files.

**L4-3 [human] Deployed UI walkthrough (after redeploy per AGENTS.md):**

1. Open the deployed app URL (from `backend/README.md` Live URL line); hard-refresh; confirm the bundle is fresh (page shows Practice + Interview tabs rendering real views, not stub blurbs).
2. Practice tab: pick a lesson, Get question, answer briefly, Submit — expected: question card, then FeedbackCard with all five sections + a grounding badge, history entry appears.
3. Interview tab: Experience kind, empty focus, Get question — expected: a question naming your documented work (seeded demo has accomplishments) OR an honest 422 message; answer it — expected: feedback with `from your notes` badge.
4. Switch kind to Technical mid-question — expected: stale question cleared; new question is conceptual.
5. Retry queue: submit a deliberately thin answer — expected: attempt gains a Retry badge and the Retry queue count increments; Retry reloads the question.

### Level 5: Additional Validation (Optional)

Playwright MCP browser E2E against the DEPLOYED URL (never localhost — sandboxed sessions deny local sockets):

1. Verify deployment freshness FIRST (new bundle hash + `/api/v1/practice/question` reachable) — an outdated deployment never validates new code.
2. Script: open Practice tab → select lesson → Get question → assert question card visible → answer → assert FeedbackCard sections + grounding badge → open Interview tab → assert kind radios + focus input.
3. Expected: all assertions pass; console shows no errors (`browser_console_messages` level error empty).
4. If deployment is impossible (missing credentials/blocked deploy), mark browser E2E `NOT_PERFORMED` with reason and L4-3 `UNVERIFIED` pending deployment with the manual steps above — never a failure, never a pass.

---

## MANUAL VERIFICATION CHECKLIST

- [ ] [agent] Backend ladder green: run Level 1–3 backend commands in order; expected: exact Expected outputs above, zero failures.
- [ ] [agent] Frontend ladder green: run Level 1 (oxlint) + Level 2–3 frontend commands; expected: exact Expected outputs above, zero failures.
- [ ] [agent] Live learning + interview exchanges: run L4-1 and L4-2; expected: exit 0 each, asserted reference/grounding values observed, scratch DBs deleted after.
- [ ] [human] Deployed UI walkthrough: perform L4-3 steps 1–5 on the fresh deployment; expected: per-step observations above (FeedbackCard sections, grounding badges, retry queue behavior).
- [ ] [agent] Migration proof: run `cd backend && uv run pytest tests/test_db_init.py::test_attempts_v1_to_v2_migration -q`; expected: exit 0, `1 passed` — plus confirm the deployed volume DB migrates on next boot (redeploy + boot log shows `db migrate` line OR version already 2).
- [ ] [agent] No leftover scratch: `ls /tmp/practice_smoke*` shows no files; `git status --short` shows only intended new/modified files (no `.env`, no `conversation-log/`, no scratch scripts in repo).

## ROLLBACK CONSIDERATIONS

- Code rollback: `git revert` the single deliverable commit — all changes are additive (new modules, new routes, new columns, stub replacements). No existing endpoint, table semantic, or UI flow is altered except `schema_version` 1→2 and the additive attempts columns.
- Data rollback: v2 columns are NULLABLE and ignored by old code — a v1 binary reads a v2 DB safely (extra columns invisible). Downgrade path: none needed; to fully revert, drop the columns (`ALTER TABLE attempts DROP COLUMN ...` — SQLite 3.35+) and reset `meta.schema_version='1'`.
- Deployed volume DB: migration runs inside `init_db` at boot (idempotent, additive, no backfill) — safe on the live volume; failed boot leaves data untouched (migration is one transaction).

## ACCEPTANCE CRITERIA

- [ ] `POST /practice/question` learning/experience/technical each return PRD-§10-exact shapes with correct `reference_kind` (L3 `test_practice_api.py` question-shape tests; expected: pass)
- [ ] `POST /practice/answer` returns 5-key feedback + code-computed grounding label; feedback JSON never model-guessed labels (L3 `test_practice_api.py` + L2 `test_practice.py` grounding table; expected: pass)
- [ ] Evaluator constrained to stored references: experience evaluation performs zero retrieval (L2 `test_practice.py` raising-`search_fn` test; expected: pass)
- [ ] Conversation inheritance: answer turns land in the question's conversation in order with roles (L3 `test_practice_api.py` inheritance test via `get_conversation`; expected: pass)
- [ ] Status matrix: 422/404/409/502 paths per spec (L3 `test_practice_api.py` matrix; expected: pass)
- [ ] v1→v2 migration idempotent, data-preserving, version-bumping (L2 `test_db_init.py::test_attempts_v1_to_v2_migration`; expected: `1 passed`)
- [ ] Practice + Interview views run the full loop with shared FeedbackCard/AttemptHistory, history + retry queue, error/dismiss/disclosure (L3 frontend suite + L4-3 human walkthrough; expected: pass + observed)
- [ ] Kind-switch clears stale question; empty-explanations disables Get-question (L3 `InterviewView`/`PracticeView` tests; expected: pass)
- [ ] Full backend + frontend suites green with zero regressions (L3 `pytest -q`, `npm test`, `npm run build`; expected: exit 0 throughout)
- [ ] Lint/type gates pass (L1 ruff + mypy + oxlint; expected: exit 0 throughout)
- [ ] Live exchanges against the Meta API succeed on scratch DBs (L4-1/L4-2 agent steps; expected: exit 0 + asserted values, incl. 5-key feedback + grounding label for BOTH experience and technical questions)
- [ ] No new dependencies added (`git diff backend/pyproject.toml frontend/package.json` empty of new deps; `uv.lock`/`package-lock.json` unchanged — checklist item, verified by `git status`)
- [ ] Code follows project conventions (thin router, shared grounding contracts, by-name seams, exact-JSON types — reviewer judgment at `/review-plan` + execution review)

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

- **Why stored references instead of re-derivation:** re-deriving experience facts at answer time would need full-question-text search, but `_matches_q` is AND-semantics over whitespace terms (a question sentence matches nothing); re-derivation also drifts when the DB changes between Q&A. Stored `reference_json` + `explanation_id` are explicit derivation edges (TS-4) and give deliverable 4 the support graph F-10 needs for attempts.
- **Why the router (not `llm/`) persists:** qa-precedent — turn persistence order (attempt row, then turns) is a router concern; keeping `llm/practice.py` generation-only preserves the injected-seam unit-test story.
- **Why 200 on POSTs:** sibling precedent (`/learn/explain`, `/query`, `/work/extract` all 200); only `/markers` uses 201. Consistency beats REST-purity here.
- **Why two views, not one parameterized component:** the loop skeleton is shared informally (same state shape, same shared children), but context controls differ enough that a parameterized mega-component would be harder to test; matches the codebase's no-custom-hooks precedent. Deliverable 5 may unify during its visibility pass.
- **Why `resolve_grounding` lives in `grounding.py`:** the grounding label is a shared contract (backend computes, frontend renders verbatim, tests assert the table) — the exact "shared, never copy-pasted" case.
- **Token budgets:** 8192/8192 follow the STAGE_* precedent (Spark hidden reasoning burns `max_tokens`); question-gen is single-shot short output but the reasoning overhead dominates.
- **Deadline pressure valve:** if execution slips, cut in this order: (1) Level 5 browser E2E → human L4-3 only; (2) `retry_only` filter + Retry-queue UI section (keep `needs_retry` field + badge — the field is load-bearing for Phase 4 demo narrative); (3) technical-mode passage weaving (ship `chunk_ids: []` always-general first, add weaving if time). Never cut: the three endpoints, both views, stored references, 409 path, migration test.

---

## Revision History

### Cycle 1

Review: `.agents/plans/reviews/shared-practice-loop-endpoints-practice-interview-views-plan-review.md` (Overall: NEEDS_REVISION, 4 failing checks, 5 findings). All 5 corrections applied; nothing escalated.

1. "Remove the contradictory text claiming llm/practice.py takes injected persist_fns and the garbled 'create_attempt(via persist fns? no…)' seam entry" — changed: Solution Statement now says "generation-only `llm/practice.py`"; Router-seams pattern lists `create_attempt` plainly with an explicit generation-only sentence; Orchestration-seams pattern states NO `persist_fn` and that the router persists via repositories. Every section now consistently places persistence in the router.
2. "Specify how the router converts stored attempt feedback to FeedbackOut when it is malformed or partial … and add an API test proving GET /practice/attempts still returns 200" — changed: `api/practice.py` task now specifies two-layer defensive conversion (repository: malformed JSON → None; router: dict → `FeedbackOut` in try/except → None), listing never 500s; `db/attempts.py` task states the repository half of the rule; `test_practice_api.py` task gains the garbage-TEXT + partial-dict seeding test asserting 200 with `feedback: null`. Consistent with the "history still renders" edge case.
3. "Extend L4-2 to answer the technical question and assert its grounding label" — changed: L4-2 step 1 now answers the technical question and asserts 5-key feedback + `grounding in ('general explanation','both')`; Expected line counts all five asserted values; the live-exchange acceptance criterion now requires feedback + label for BOTH interview kinds.
4. "Add a test_practice.py evaluate_answer case where a single explanation with reused_from NULL yields 'general explanation'" — changed: `test_practice.py` task gains the lone-lesson self-match-guard test next to the existing `both` case; the `personal_refs` rule (decision 3 + `llm/practice.py` task) now self-excludes (`mem.reused_from != explanation_id`) so the rule is robust whether or not `build_memory_context` matches the lesson itself.
5. "Define the experience reference block to include supporting source chunk excerpts alongside fact summaries … and add a test that the evaluation messages contain them" — changed: experience rubric now judges against "facts AND their cited source excerpts"; `llm/practice.py` task specifies fact-by-fact block building (summary + status + skills + `get_chunks`/`excerpt_of` excerpts) within the caps at question time, and drop-with-warning (summary stays) for chunks missing at evaluation time; `test_practice.py` task asserts a supporting excerpt appears verbatim in captured evaluation messages. Rendering stays in `llm/` (it owns the db types) rather than `grounding.py`, keeping that module free of fact shapes per its no-app-imports contract.

Limitations: none — all findings were routine technical tightenings inside the confirmed deliverable scope; no requirement conflicts or ambiguities surfaced.
