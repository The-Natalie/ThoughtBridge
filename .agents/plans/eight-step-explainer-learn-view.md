# Feature: Interactive Eight-Step Explainer Endpoint + Learn View

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Implement PRD F-3 (interactive eight-step explainer) as Phase 2 deliverable 1: a multi-stage LLM generation pipeline that teaches a concept through the founder's eight-step sequence (definition → familiar-system connection → complete-system analogy → component mapping → interaction walkthrough → larger-process placement → interview-ready explanation → analogy limitations), persists each lesson as a versioned `Explanation` record, and serves it through a stepwise, interruptible Learn view. Interruptions (ask-a-question mid-lesson) reuse the existing `POST /query` contract by finally honoring its `context.explanation_id` field (accepted-but-ignored since Phase 1); step regeneration persists a new version; resume is positional state over the stored explanation.

This is the first of three mutually dependent learning deliverables (explainer + explanation memory + learner profile). It is planned to be implementable standalone: profile and memory inputs arrive through injected seams with documented contracts and working defaults, which deliverables 2–3 will later fill with real reads.

## User Story

As a learner who understands systems through familiar analogies
I want new concepts explained in eight connected steps that I can interrupt with questions and resume
So that the knowledge connects to how I actually think instead of evaporating after one reading

## Problem Statement

US-2/US-3 require analogy-based learning with explanation reuse, but the current product only offers grounded Q&A: single-shot answers with no pedagogical structure, no persistence of what was taught, and no way to explore confusion mid-explanation. Without the explainer, the Learn surface (currently a placeholder stub) cannot function, and the Practice Loop (Phase 3) has no taught explanations to evaluate against.

## Scope

- In scope:
  - `POST /learn/explain` exactly per PRD §10 (`{concept, familiar_system_hint?}` → `{explanation_id, reused_from, steps{8 keys}}`), multi-stage generation (3 sequential LLM calls), versioned persistence.
  - `GET /learn/explanations/{id}` single-fetch (PRD §10 contract) — required for interrupt context, regeneration, and resume. NOTE (owner-approved Nov 3): the Phase 2 build list assigns both learning GETs to deliverable 2, but single-fetch is a hard dependency of this deliverable's interactive Learn view, so it is built here. Explanation-listing and memory-reuse functionality stay in deliverable 2.
  - `POST /learn/explanations/{id}/regenerate` (`{step}` → new version with that step regenerated) — additive contract, not in PRD §10 (owner-approved Nov 3: implements the PRD's existing regenerate-steps-and-save-new-versions requirement); does not alter any specified contract.
  - `POST /query` honors `context.explanation_id`: loads the explanation, injects its steps as teaching-mode context, forces teaching mode, persists turns as today (unknown id → 404).
  - Profile/memory input seams with working defaults (`LearnerContext` all-emphasis-on + empty free text; memory returns `None`).
  - Learn view: concept form → stepwise lesson (prev/next) → per-step ask-a-question (via `/query` + conversation threading) → per-step regenerate → positional resume.
  - Router registration, frontend API client + types, App view wiring, backend + frontend tests.
- Out of scope:
  - `GET /learn/explanations` (list), `POST .../markers`, reuse-offer/injection behavior, attempt-outcome linkage (deliverable 2).
  - `learner_profile` table reads/writes, profile UI (deliverable 3 — the seam default matches the schema defaults).
  - Career profile, work extraction (deliverables 4–5), PDF/Word adapters (deliverable 6).
  - Practice Loop, `tb_conversation` ingestion, deletion cascade (Phase 3).
  - User-notes hybrid retrieval inside the explainer (teaching-mode generation + profile + memory seams only; related-experience retrieval may ride the memory seam later).
  - Rerank, HyDE, scored ranking, editing/redaction (deferred per PRD).

## Solution Statement

Follow the proven `llm/qa.py` + thin-router architecture: add `app/llm/explainer.py` (pure orchestration over injected `chat_fn`/`profile_fn`/`memory_fn` seams, Pydantic validation at every LLM boundary via a `strip_fences` reuse), `app/db/explanations.py` (create/get/version-count repository over the existing schema), and `app/api/learn.py` (thin router mapping `ExplainerValidationError`/`MetaAPIError` → 502 exactly like `query.py`). Generation runs as 3 chained teaching-mode stages (A: definition+familiar_system, B: analogy+mapping+walkthrough, C: placement+interview_ready+limitations), each schema-validated; the Explanation row is written only after all stages succeed (no partial lessons). Prompts live in `core/grounding.py` alongside the existing mode contracts. The frontend mirrors `ChatView` conventions in a new `LearnView` with positional step state.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: High
**Primary Systems Affected**: `backend/app/llm/` (new explainer), `backend/app/api/` (new learn router, query-context wiring), `backend/app/db/` (new explanations repository), `backend/app/core/` (explainer prompt contracts), `frontend/src/views/` (LearnView), `frontend/src/api/` (learn client)
**Dependencies**: None outside this plan (profile/memory arrive via seams with working defaults; deliverables 2–3 fill them later). Runtime dep: Meta Model API via existing `meta_client.chat_completion` (no new packages).
**Assumptions**:
1. Deliverables 2 (memory) and 3 (profile) are NOT yet built; this plan's seam contracts (`ProfileFn`, `MemoryFn`, `LearnerContext`, `MemoryContext`) are the interface they must fill — validate these names survive into those plans.
2. DECIDED (owner-approved Nov 3): `GET /learn/explanations/{id}` is built here because the interactive Learn view depends on it; explanation-listing and memory-reuse stay in deliverable 2.
3. DECIDED (owner-approved Nov 3): `POST /learn/explanations/{id}/regenerate` is accepted as an additive endpoint implementing the PRD's existing regen-and-new-version requirement.
4. When `context.explanation_id` is present, `/query` forces teaching mode (PRD F-3: interruptions "answered in teaching mode with the in-progress explanation as context").
5. Generous per-stage token budgets (Stage B 8192, others 4096) suffice despite Spark hidden-reasoning burn — validate with one live call during implementation.
6. Repeat `POST /learn/explain` for the same concept always generates fresh at version max+1 (no reuse-offer until deliverable 2).

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `backend/app/llm/qa.py` (lines 32-42) - Why: seam-type + schema-validation pattern to MIRROR (`SearchFn`/`ChatFn` aliases, `QaValidationError`, `QaModelOut`); explainer defines `ProfileFn`/`MemoryFn` the same way.
- `backend/app/llm/qa.py` (lines 61-70) - Why: `strip_fences` — IMPORT and reuse directly; do not copy fence-stripping logic.
- `backend/app/llm/qa.py` (lines 72-111) - Why: orchestration shape to MIRROR (inject seams → call chat → validate → map to result dataclasses → log); teaching-mode validation failure raises (→ 502), never degrades.
- `backend/app/core/grounding.py` (lines 1-6) - Why: module purity contract (prompts only; no settings, DB, or network) — explainer prompts MUST live here, not in `llm/` or `api/`.
- `backend/app/core/grounding.py` (lines 35-56) - Why: teaching-mode system prompt + JSON-instruction style to MIRROR for stage prompts (JSON-only, untrusted-data framing).
- `backend/app/core/grounding.py` (lines 114-130) - Why: `build_messages` message-assembly pattern to MIRROR for stage message builders.
- `backend/app/api/query.py` (lines 4-11) - Why: docstring documents the `context.explanation_id` forward-compat hook this plan implements + the by-name seam convention (`monkeypatch.setattr("app.api.learn.hybrid_search", ...)`).
- `backend/app/api/query.py` (lines 39-63) - Why: Pydantic request/response model style to MIRROR (`QueryContext` already defines `explanation_id: str | None`).
- `backend/app/api/query.py` (lines 89-191) - Why: `post_query` flow to MIRROR — blank-input 422 (92-94), unknown-conversation 404 (100-107), `chat_fn` closure with missing-key 502 (126-133), exception mapping `QaValidationError`→502 BEFORE `ValueError`→500 (145-155), turn persistence only after successful generation (166-179).
- `backend/app/api/query.py` (lines 108-115) - Why: history hydration + `select_history` — interrupt questions reuse this unchanged.
- `backend/app/db/conversations.py` (lines 60-96, 99-144) - Why: `append_turns` / `create_conversation_with_turns` atomic patterns to MIRROR in the explanations repository (single-transaction writes, `connect(db_path)` + `finally: conn.close()`).
- `backend/app/db/schema.sql` (lines 98-117) - Why: `explanations` + `explanation_markers` DDL — the repository MUST match these columns exactly (`steps`/`mapping` JSON TEXT, `limitations` TEXT, `reused_from` FK, `version` INT).
- `backend/app/core/meta_client.py` (lines 110-120) - Why: `chat_completion` signature — accepts per-call `max_tokens`/`temperature`; the router passes stage budgets explicitly (defaults `QA_MAX_TOKENS=4096`, lines 21-23, are Q&A-sized, not explainer-sized).
- `backend/app/main.py` (lines 41-56) - Why: `create_app` router registration — ADD `app.include_router(learn_router, prefix="/api/v1")` beside the existing four.
- `backend/app/retrieval/search.py` (lines 100-103) - Why: `excerpt_of` truncation helper — reuse if interrupt answers need excerpts (likely not; listed to prevent reimplementation).
- `frontend/src/views/ChatView.tsx` (lines 1-60) - Why: view conventions to MIRROR — `useState` slices, typed API calls, `conversationId` threading, `loading`/`error` states.
- `frontend/src/views/ChatView.tsx` (lines 61-70, 130-153) - Why: error-alert with `role="alert"` + Dismiss, labeled input + Send button — same a11y contract for tests.
- `frontend/src/api/query.ts` (whole file) - Why: thin typed wrappers over `apiGet`/`apiPost` — MIRROR exactly in `api/learn.ts`.
- `frontend/src/api/types.ts` (lines 1-26) - Why: "Field names mirror backend Pydantic JSON exactly" — Learn types MUST follow (snake_case preserved).
- `frontend/src/api/client.ts` (lines 4-29) - Why: `apiUrl`/`apiGet`/`apiPost` — reuse; no new client helpers needed (all learn calls are GET/POST JSON).
- `frontend/src/App.tsx` (lines 6-12, 16-43) - Why: `VIEWS` table + view-switch state — replace the `learn` stub blurb with `<LearnView />` (mirror the `chat` branch, line 40).
- `backend/tests/test_qa.py` (lines 41-76) - Why: `_run`/`_chat` stub-helper + happy-path test shape to MIRROR in `test_explainer.py` (stub `chat_fn`, `asyncio.run`, no DB/network).
- `frontend/src/views/ChatView.test.tsx` (lines 7-62) - Why: `mockFetchSequence` + response factory + submit-flow test to MIRROR in `LearnView.test.tsx`.
- `PRD.md` (§7 F-3, lines 233-235) - Why: authoritative eight-step order and stage contents; interrupt/regenerate/resume/version requirements.
- `PRD.md` (§10 Learning, lines 335-339) - Why: authoritative `POST /learn/explain` request/response shape — all eight step keys verbatim.
- `.agents/plans/phase-2-build-list.md` (deliverable 1 + build-order note) - Why: phase scope boundaries; this plan implements deliverable 1 with the 1-first/seams assumption.

### New Files to Create

- `backend/app/db/explanations.py` - Repository: `create_explanation`, `get_explanation`, `max_version_for_concept` over existing `explanations` table.
- `backend/app/llm/explainer.py` - Orchestration: seam types, stage Pydantic models, 3-stage `generate_explanation`, single-step `regenerate_step`, seam defaults.
- `backend/app/api/learn.py` - Router: `POST /learn/explain`, `GET /learn/explanations/{id}`, `POST /learn/explanations/{id}/regenerate`.
- `backend/tests/test_explainer.py` - Unit tests: stage chaining, validation failures, versioning, seam defaults (stubbed `chat_fn`, no network).
- `backend/tests/test_learn_api.py` - Router tests: status codes, response shapes, 404/422/502 mapping (monkeypatched seams).
- `frontend/src/api/learn.ts` - Typed wrappers: `postExplain`, `getExplanation`, `postRegenerate`.
- `frontend/src/api/learn.test.ts` - Client tests: URL + body assertions (mirror `query.test.ts`).
- `frontend/src/views/LearnView.tsx` - Learn view: concept form, stepwise lesson, per-step ask + regenerate.
- `frontend/src/views/LearnView.test.tsx` - View tests: full teach → interrupt → resume → regenerate flows (mocked fetch).

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

No new libraries, no external docs. Every pattern this feature needs already exists in-repo (listed above). Specifically NOT needed: any LLM-framework docs (direct `chat_completion` calls only), any state-management docs (plain `useState` like `ChatView`), any migration docs (schema tables already exist — no DDL changes).

- [PRD §7 F-3 — Eight-step explainer](PRD.md) — Specific section: lines 233-235 (stage order, interrupt/resume/regenerate/version rules). Why: acceptance source for step contents.
- [PRD §10 — Learning contracts](PRD.md) — Specific section: lines 335-339 (`POST /learn/explain` shape with all eight step keys). Why: response-shape conformance.
- [PRD §6 — Teaching mode](PRD.md) — Specific section: lines 191-195 (open-world contract: general knowledge + stored material when retrieved, never blocked by empty KB). Why: explainer grounding rules.

### Patterns to Follow

**Naming Conventions:**

- Backend: `snake_case` modules/functions (`explainer.py`, `generate_explanation`, `get_explanation`); `PascalCase` Pydantic models/dataclasses (`ExplainRequest`, `ExplanationDetail`, `StageBOut`).
- Step keys (canonical, PRD §10 order): `definition`, `familiar_system`, `analogy`, `mapping`, `walkthrough`, `placement`, `interview_ready`, `limitations`. Use this exact order everywhere (prompts, models, UI stepper).
- Frontend: `PascalCase.tsx` views (`LearnView.tsx`), `camelCase.ts` API modules (`learn.ts`); JSON field names stay `snake_case` in TS interfaces (mirror rule).

**Error Handling:**

- Mirror `query.py` mapping exactly: `ExplainerValidationError` → 502 (BEFORE the `ValueError` branch — it subclasses `ValueError`, see `query.py:145-148` gotcha), `MetaAPIError` → 502 with cause, blank concept → 422, unknown explanation id → 404, `EmbeddingDimMismatchError`/`ValueError` → 500.
- Missing `MODEL_API_KEY` → 502 `"MODEL_API_KEY not configured"` from the router `chat_fn` closure (mirror `query.py:126-133`).
- Stage failure at ANY stage → whole explain fails with 502 and persists NOTHING (no partial lessons, no orphan rows).
- Teaching-mode validation failure raises (mirror `qa.py:110-111`) — never a refusal (refusals are evidence-mode-only).

**Logging Pattern:**

- `logger = logging.getLogger(__name__)` per module; `logger.info` on success with key counts (`"explainer generated: concept=%s version=%d stages=3"`), `logger.warning` on validation failures with stage + detail (mirror `qa.py:110`). Never log prompt contents or API keys.

**Other Relevant Patterns:**

- Test seams imported BY NAME in routers so tests monkeypatch `app.api.learn.chat_completion` / `app.api.learn.<repo fn>` (mirror `query.py:8-11` docstring convention — include the same docstring note).
- `llm/` orchestration takes injected async `chat_fn` + sync seam fns; unit tests stub all three (mirror `test_qa.py:41-60`).
- Repository functions take `db_path: str` first, use `connect(db_path)` + `with conn:` + `finally: conn.close()` (mirror `conversations.py:60-96`).
- Frontend errors: `role="alert"` div with Dismiss button; all interactive elements get `aria-label`s (mirror `ChatView.tsx:63-70`).

---

## IMPLEMENTATION PLAN

### Design Decisions (read before tasking)

**D1 — Three chained stages, not 1 or 8 calls.** Steps that must stay mutually consistent (analogy ↔ mapping ↔ walkthrough) generate in ONE call (Stage B) so they cannot drift; loosely coupled steps split so a failure retries cheaply and each stage's JSON stays small enough to validate reliably. Chain: Stage A output → Stage B context → Stage C context.
- Stage A `definition + familiar_system` — budget 4096 tokens.
- Stage B `analogy + mapping[{familiar, technical, note}] + walkthrough` — budget 8192 tokens (largest, most constrained).
- Stage C `placement + interview_ready + limitations` — budget 4096 tokens.
- All stages `temperature=0.0` (deterministic teaching; mirror `QA_TEMPERATURE`).

**D2 — Seams with working defaults (deliverables 2–3 fill later).** `generate_explanation` takes `profile_fn: ProfileFn` and `memory_fn: MemoryFn` (sync, mirror `SearchFn`):
- `ProfileFn = Callable[[], LearnerContext]`; default `default_learner_context()` returns all five emphasis flags `True` + `how_i_learn=""` (matches schema/PRD defaults). Deliverable 3 replaces the router wiring with a `learner_profile` read; the dataclass shape is the contract.
- `MemoryFn = Callable[[str], MemoryContext | None]` (arg = concept); default `no_memory()` returns `None`. Deliverable 2 implements same-concept retrieval returning `MemoryContext(reused_from, prior_steps, framing_note)`; `reused_from` flows into the response + row.
- Prompts render profile emphasis as instruction lines and memory as "a prior explanation that worked" context ONLY when present (teaching mode is never blocked by absence).

**D3 — Atomic persistence.** The `explanations` row is inserted only after all stages validate. Version = `max_version_for_concept(concept) + 1` computed inside the same write path. Repeat explains for one concept produce v1, v2, … (no reuse-offer until deliverable 2).

**D4 — Regenerate = new version, one call.** `POST /learn/explanations/{id}/regenerate {step}` loads the source, runs ONE teaching-mode call with the full explanation as context + `{"step": ..., "content": ...}` JSON validation (`content` is `str`, except `mapping` which is the mapping-item array), copies all other steps verbatim, derives the top-level `mapping`/`limitations` columns from the merged steps (column sync), and inserts version max+1 with `reused_from = NULL` (D8 — regen is lineage, not memory reuse, and never a success signal). Invalid step name → 422 with the eight valid keys listed.

**D5 — Interrupt forces teaching mode.** When `context.explanation_id` is present on `POST /query`: 404 if unknown; else inject a compact rendering of all eight steps as an additional system message (via a new `build_explanation_context(explanation) -> str` pure helper in `grounding.py`), set `mode_used="teaching"` regardless of the `mode` field, and persist turns exactly as today (same conversation threading, same citations JSON column — citations from passages still recorded when passages exist).

**D6 — Response shapes.** `POST /learn/explain` returns PRD §10 exactly: `{explanation_id, reused_from, steps{definition, familiar_system, analogy, mapping[], walkthrough, placement, interview_ready, limitations}}`. `GET /learn/explanations/{id}` returns `{id, concept, version, steps{…8}, mapping, limitations, reused_from, created_at}`. `POST .../regenerate` returns the same shape as `POST /learn/explain` (new `explanation_id`, `reused_from=null` per D8).

**D7 — Frontend state.** `LearnView` holds: `explanation` (full `ExplanationDetail`, fetched via `getExplanation(explanation_id)` after every explain/regenerate POST since those responses lack concept/version), `stepIndex` (0–7 positional resume), `conversationId` (interrupt threading, mirror `ChatView`), per-step interrupt thread `[{question, answer}]` keyed by step, `loading`/`error`. Stepper shows all eight step names with the current highlighted; Next/Back move `stepIndex` without network; Ask submits `postQuery({question, mode:"teaching", context:{explanation_id}, conversation_id})`; Regenerate submits `postRegenerate`, GETs the new id, then replaces `explanation` and keeps `stepIndex`.

**D8 — `reused_from` reserved for memory reuse; regen writes NULL, no schema change.** (Owner-decided Nov 3.) The `reused_from` column carries exactly one meaning: "generated using prior explanation X as context" — written only by the deliverable-2 memory path, never by regeneration. A regenerated explanation is not a successful explanation: regen rows write `reused_from = NULL` and never inherit the source's value, so naive F-4 reuse-count queries (`COUNT(*) WHERE reused_from=X`) stay unpolluted and PRD's saved-vs-marked distinction holds. Regen lineage is not persisted as an explicit edge; the (concept, version) sequence (shared by fresh re-explains and regens) is the only ordering. No DDL in this deliverable. If deliverable 2 needs explicit regen edges (e.g., for marker inheritance), it owns that migration.

### Phase 1: Foundation

Shared contracts first: grounding prompt helpers + stage JSON models + repository + seam dataclasses. No routers, no UI. Everything in this phase is importable and unit-testable without a network key.

**Tasks:**

- ADD explainer prompt constants + builders to `core/grounding.py` (pure functions only).
- CREATE `db/explanations.py` repository (create/get/max-version + `ExplanationDetail` dataclass).
- CREATE `llm/explainer.py` seam types + defaults + stage Pydantic models (no orchestration yet).

### Phase 2: Core Implementation

Orchestration + routers + query-context wiring. Backend complete and curl-testable.

**Tasks:**

- ADD `generate_explanation` + `regenerate_step` orchestration to `llm/explainer.py` (3-stage chain, per-stage validation, atomic persist via repository).
- CREATE `api/learn.py` router (three endpoints, exception mapping mirroring `query.py`).
- UPDATE `api/query.py` to honor `context.explanation_id` (404/force-teaching/context-injection per D5).

### Phase 3: Integration

Wire the backend into the app surface and build the frontend slice.

**Tasks:**

- UPDATE `app/main.py` to register the learn router under `/api/v1`.
- UPDATE `frontend/src/api/types.ts` with Learn types (mirror Pydantic JSON exactly).
- CREATE `frontend/src/api/learn.ts` typed wrappers.
- CREATE `frontend/src/views/LearnView.tsx` + UPDATE `frontend/src/App.tsx` to render it for the `learn` view.

### Phase 4: Testing & Validation

Mirror both test suites' conventions; then run the five validation levels.

**Tasks:**

- CREATE `backend/tests/test_explainer.py` (stubbed `chat_fn`, no network/DB-files — `:memory:` via tmp repo or monkeypatched repo fns).
- CREATE `backend/tests/test_learn_api.py` (TestClient + monkeypatched module seams).
- CREATE `frontend/src/api/learn.test.ts` + `frontend/src/views/LearnView.test.tsx` (mocked fetch).
- Run Levels 1–5 validation; live-call check with the real key for token-budget assumption A5.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### ADD backend/app/core/grounding.py — explainer prompt contracts

- **IMPLEMENT**: Add `EXPLAINER_SYSTEM_PROMPT` (teaching-mode, eight-step aware: JSON-only, untrusted-data framing via existing `UNTRUSTED_PASSAGE_FRAMING`, "never invent personal facts" line mirrored from `TEACHING_SYSTEM_PROMPT`); `STEP_KEYS: tuple[str, ...]` canonical eight keys in PRD order; `build_stage_messages(stage: Literal["A","B","C"], concept, hint, profile_block, memory_block, prior_json) -> list[dict[str,str]]` chaining prior stage JSON as context; `build_regenerate_messages(explanation_steps, step) -> list[dict[str,str]]`; `build_explanation_context(explanation: Mapping[str, object]) -> str` compact eight-step rendering for interrupt injection (pure, takes a plain mapping — NOT the db dataclass, keeping this module DB-free per its header contract).
- **PATTERN**: `backend/app/core/grounding.py:35-56` (prompt-string style), `backend/app/core/grounding.py:114-130` (`build_messages` assembly).
- **IMPORTS**: `typing.Literal`, `collections.abc.Mapping` (new); reuse `UNTRUSTED_PASSAGE_FRAMING` in-module.
- **GOTCHA**: This module must NOT import db models, settings, or httpx (header contract lines 1-6) — `build_explanation_context` takes `Mapping`, and `api/query.py` adapts the dataclass at the call site.
- **VALIDATE**: `cd backend && uv run ruff check app/core/grounding.py && uv run ruff format --check app/core/grounding.py`

### CREATE backend/app/db/explanations.py — explanations repository

- **IMPLEMENT**: `ExplanationDetail` dataclass (`id, concept, version, steps: dict, mapping: list, limitations: str, reused_from: str | None, created_at: str`); `create_explanation(db_path, concept, version, steps, mapping, limitations, reused_from) -> ExplanationDetail` (single `with conn:` insert, `uuid4().hex` id, UTC isoformat timestamp, `json.dumps` for `steps`/`mapping`); `get_explanation(db_path, explanation_id) -> ExplanationDetail | None` (`json.loads` on read, `None` when missing); `max_version_for_concept(db_path, concept) -> int` (`COALESCE(MAX(version),0)`).
- **PATTERN**: `backend/app/db/conversations.py:60-96` (connect/with/finally-close shape, logging on write).
- **IMPORTS**: `json`, `logging`, `uuid`, `dataclasses.dataclass`, `datetime.UTC/datetime`, `app.db.connection.connect`.
- **GOTCHA**: Column order/types MUST match `db/schema.sql:98-107` (`steps`/`mapping` TEXT JSON, `limitations` TEXT, `reused_from` nullable FK). Concept match is exact-string (no normalization — deliverable 2 owns fuzzy same-concept logic).
- **VALIDATE**: `cd backend && uv run python -c "import app.db.explanations; print('ok')"`

### CREATE backend/app/llm/explainer.py — seams, models, orchestration

- **IMPLEMENT**: Seam types `ProfileFn = Callable[[], LearnerContext]`, `MemoryFn = Callable[[str], MemoryContext | None]`, reuse `ChatFn` via `from app.llm.qa import ChatFn, strip_fences`; dataclasses `LearnerContext(emphasis: dict[str,bool], how_i_learn: str)`, `MemoryContext(reused_from: str, prior_steps: dict, framing_note: str)`; defaults `default_learner_context()` (all five PRD F-13 flags True, `how_i_learn=""`) and `no_memory(concept) -> None`; Pydantic `StageAOut(definition, familiar_system)`, `MappingItem(familiar, technical, note)`, `StageBOut(analogy, mapping: list[MappingItem], walkthrough)`, `StageCOut(placement, interview_ready, limitations)`, `RegenOut(step, content)` with `content: str | list[MappingItem]`; `ExplainerValidationError(ValueError)`; `async generate_explanation(*, concept, hint, db_path, chat_fn, profile_fn, memory_fn, persist_fn=None) -> ExplainedResult(explanation_id, reused_from, steps)` running A→B→C with per-stage `strip_fences` + `model_validate_json`, raising `ExplainerValidationError` naming the stage on ANY failure BEFORE persisting; `async regenerate_step(*, source: ExplanationDetail, step, db_path, chat_fn) -> ExplainedResult` (validates `step in STEP_KEYS` else `ValueError`, one call, copies other steps verbatim, writes `reused_from=None` per D8, derives the top-level `mapping`/`limitations` columns from the merged steps dict so GET stays consistent). Token budgets as module constants `STAGE_A_MAX_TOKENS=4096`, `STAGE_B_MAX_TOKENS=8192`, `STAGE_C_MAX_TOKENS=4096`, `REGEN_MAX_TOKENS=4096`; pass `max_tokens` per call — orchestration calls `chat_fn(messages, max_tokens)` so extend the call signature: define local `ExplainerChatFn = Callable[[list[dict[str,str]], int], Awaitable[str]]` (messages + budget) and adapt `meta_client.chat_completion` at the router.
- **PATTERN**: `backend/app/llm/qa.py:32-42` (seam aliases + error + models), `backend/app/llm/qa.py:103-111` (validate-or-raise teaching behavior).
- **IMPORTS**: `logging`, `dataclasses.dataclass`, `collections.abc.{Awaitable, Callable}`, `pydantic.{BaseModel, ValidationError}`, `app.core.grounding.{STEP_KEYS, build_stage_messages, build_regenerate_messages}`, `app.db.explanations.{ExplanationDetail, create_explanation, max_version_for_concept}`, `app.llm.qa.strip_fences`.
- **GOTCHA**: (1) `chat_fn` here takes `(messages, max_tokens)` — DIFFERENT arity from `qa.py`'s `ChatFn`; use the local `ExplainerChatFn` alias everywhere in this module and adapt at the router. (2) Persist LAST: compute `max_version_for_concept` + `create_explanation` only after Stage C validates (D3 atomicity). (3) `persist_fn` injection seam exists so unit tests can skip the DB (`persist_fn(steps, reused_from) -> tuple[id, version]`); router passes `None` → real repository path, which builds the merged steps first and then passes `steps` plus the extracted `mapping`/`limitations` columns to `create_explanation`.
- **VALIDATE**: `cd backend && uv run ruff check app/llm/explainer.py app/db/explanations.py && uv run ruff format --check app/llm/explainer.py app/db/explanations.py`

### CREATE backend/app/api/learn.py — learn router

- **IMPLEMENT**: `router = APIRouter(tags=["learn"])`; models `ExplainRequest(concept: str min_length=1, familiar_system_hint: str | None = None)`, `ExplainResponse(explanation_id, reused_from: str | None, steps: dict)`, `ExplanationOut(id, concept, version, steps: dict, mapping: list, limitations: str, reused_from, created_at)`, `RegenerateRequest(step: str)`, `RegenerateResponse = ExplainResponse` shape; `POST /learn/explain` (blank-concept 422 incl. whitespace-only; `chat_fn` closure adapting `(messages, budget) -> chat_completion(api_key, model, messages, max_tokens=budget)` with missing-key 502; `profile_fn=default_learner_context`, `memory_fn=no_memory`; map `ExplainerValidationError`→502 BEFORE `ValueError`→500, `MetaAPIError`→502); `GET /learn/explanations/{id}` (`get_explanation`, missing → 404); `POST /learn/explanations/{id}/regenerate` (missing source → 404; bad step → 422 listing valid keys; same chat/exception wiring as explain). Import `chat_completion`, `get_explanation`, `create_explanation`, `max_version_for_concept` BY NAME for monkeypatch seams; include the seam docstring note mirroring `query.py:8-11`.
- **PATTERN**: `backend/app/api/query.py:89-191` (full endpoint flow incl. closure seams + exception order + logging).
- **IMPORTS**: `logging`, `fastapi.{APIRouter, HTTPException, status}`, `pydantic.{BaseModel, Field}`, `app.core.config.get_settings`, `app.core.grounding.STEP_KEYS`, `app.core.meta_client.{DEFAULT_META_MODEL, MetaAPIError, chat_completion}`, `app.db.explanations.{get_explanation}`, `app.llm.explainer.{ExplainerValidationError, default_learner_context, generate_explanation, no_memory, regenerate_step}`.
- **GOTCHA**: (1) Exception order: `except ExplainerValidationError` MUST precede `except ValueError` (subclass — see `query.py:145-148`). (2) `steps: dict` in responses (PRD shape has mixed str/array values — no stricter model). (3) Router paths are relative (`/learn/explain`) — the `/api/v1` prefix is applied in `main.py`.
- **VALIDATE**: `cd backend && uv run ruff check app/api/learn.py && uv run ruff format --check app/api/learn.py`

### UPDATE backend/app/api/query.py — honor context.explanation_id

- **IMPLEMENT**: In `post_query`, after the conversation lookup: if `body.context and body.context.explanation_id`: `get_explanation(db_path, id)` → 404 `"explanation not found"` when missing; else build `explanation_block = build_explanation_context(source.steps)` and append `{"role": "system", "content": explanation_block}` to the message list (extend `llm/qa.answer_question` with an optional `extra_system: str | None = None` param prepended after the mode system prompt — small, backward-compatible; history/passages flow unchanged), and force `mode_override="teaching"` (pass `mode="teaching"` into `answer_question` regardless of `body.mode`). Update the module docstring lines 4-6 to state Phase 2 implements the hook. Import `get_explanation` and `build_explanation_context` BY NAME for seams.
- **PATTERN**: `backend/app/api/query.py:100-107` (404 lookup shape), `backend/app/llm/qa.py:72-81` (`answer_question` signature to extend).
- **IMPORTS**: ADD `from app.core.grounding import build_explanation_context` (extend existing import), `from app.db.explanations import get_explanation`.
- **GOTCHA**: (1) Forcing teaching mode changes `mode_used` in the response + persisted turns — intended per D5; do NOT preserve the caller's `mode` for the record. (2) `answer_question`'s `extra_system` default `None` keeps all existing `test_qa.py` tests passing unmodified. (3) Keep the existing `history`/`select_history` flow untouched — explanation context is ADDITIONAL, not a replacement.
- **VALIDATE**: `cd backend && uv run pytest tests/test_query_api.py tests/test_qa.py -q`

### UPDATE backend/app/llm/qa.py — extra_system injection point

- **IMPLEMENT**: Add keyword-only `extra_system: str | None = None` to `answer_question`; when set, insert `{"role": "system", "content": extra_system}` immediately after the mode system prompt in the `build_messages(...)` result (i.e. `messages = build_messages(...); if extra_system: messages.insert(1, ...)` before `chat_fn`). No other behavior change.
- **PATTERN**: `backend/app/llm/qa.py:103` (the single `chat_fn(build_messages(...))` call site).
- **IMPORTS**: none new.
- **GOTCHA**: Insert at index 1 (after mode prompt, before history marker) so the mode contract keeps precedence. Existing tests must pass unmodified — verify in VALIDATE.
- **VALIDATE**: `cd backend && uv run pytest tests/test_qa.py -q`

### UPDATE backend/app/main.py — register learn router

- **IMPLEMENT**: ADD `from app.api.learn import router as learn_router` + `app.include_router(learn_router, prefix="/api/v1")` beside the existing router lines.
- **PATTERN**: `backend/app/main.py:14-18, 53-56` (import + include block).
- **IMPORTS**: `app.api.learn.router`.
- **GOTCHA**: Keep alphabetical-ish grouping (health, ingest, learn, query, retrieval) — insert learn between ingest and query.
- **VALIDATE**: `cd backend && DATABASE_PATH=/tmp/tb-prime-check.db uv run python -c "from app.main import create_app; r=[x.path for x in create_app().routes]; assert '/api/v1/learn/explain' in r, r; assert '/api/v1/learn/explanations/{explanation_id}' in r, r; print('routes ok')"`

### UPDATE frontend/src/api/types.ts — Learn types

- **IMPLEMENT**: ADD `ExplainRequest {concept: string; familiar_system_hint?: string | null}`, `ExplanationSteps {definition: string; familiar_system: string; analogy: string; mapping: MappingItem[]; walkthrough: string; placement: string; interview_ready: string; limitations: string}`, `MappingItem {familiar: string; technical: string; note: string}`, `ExplainResponse {explanation_id: string; reused_from: string | null; steps: ExplanationSteps}`, `ExplanationDetail {id: string; concept: string; version: number; steps: ExplanationSteps; mapping: MappingItem[]; limitations: string; reused_from: string | null; created_at: string}`, `RegenerateRequest {step: string}`. `RegenerateResponse` = `ExplainResponse` (type alias).
- **PATTERN**: `frontend/src/api/types.ts:1-26` (mirror-backend-JSON rule, `snake_case` preserved).
- **IMPORTS**: none.
- **GOTCHA**: `mapping` appears BOTH inside `steps` (PRD explain shape) and top-level (detail shape) — type both positions.
- **VALIDATE**: `cd frontend && npx tsc -b --dry 2>/dev/null; npx tsc --noEmit -p tsconfig.app.json`

### CREATE frontend/src/api/learn.ts — learn client wrappers

- **IMPLEMENT**: `postExplain(req: ExplainRequest): Promise<ExplainResponse>` → `apiPost('/api/v1/learn/explain', req)`; `getExplanation(id: string): Promise<ExplanationDetail>` → `apiGet('/api/v1/learn/explanations/${id}')`; `postRegenerate(id: string, req: RegenerateRequest): Promise<ExplainResponse>` → `apiPost('/api/v1/learn/explanations/${id}/regenerate', req)`.
- **PATTERN**: `frontend/src/api/query.ts:1-28` (one-line typed wrappers + doc comments).
- **IMPORTS**: `./client` (`apiGet`, `apiPost`), `./types` (new Learn types).
- **GOTCHA**: Path param `id` is a hex string — no `encodeURIComponent` needed (matches `getChunk`/`getConversation` precedent of direct interpolation).
- **VALIDATE**: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`

### CREATE frontend/src/views/LearnView.tsx — Learn view

- **IMPLEMENT**: States per D7 (`explanation: ExplanationDetail | null`, `stepIndex`, `conversationId`, `threads: Record<string, {question, answer}[]>`, `input`s, `loading`, `error`). Sections: (1) concept form (`aria-label="Concept"`, `aria-label="Familiar system hint (optional)"`, `aria-label="Teach me"`) shown when no explanation; `Teach me` runs `postExplain` then `getExplanation(response.explanation_id)` and stores the Detail (POST responses lack concept/version); (2) stepper (`aria-label="Lesson steps"`, eight buttons `aria-label="Step: definition"` etc., current `aria-current="step"`); (3) current step panel (`mapping` renders as a definition list of familiar→technical + note; other steps as paragraphs split on `\n\n`); (4) Back/Next buttons (`aria-label="Previous step"`/`"Next step"`, bounded 0–7, no network); (5) per-step Ask box (`aria-label="Ask about this step"`, `aria-label="Ask"`) → `postQuery({question, mode:'teaching', context:{explanation_id}, conversation_id})`, threads `conversation_id` from response, appends to `threads[step]`; (6) per-step Regenerate (`aria-label="Regenerate this step"`, confirm-free, `postRegenerate` then `getExplanation(new_id)`, replaces `explanation`, keeps `stepIndex`); (7) error alert mirroring `ChatView` (`role="alert"` + Dismiss); (8) header line showing concept + `v{version}` + `explanation {id.slice(0,8)}…`; (9) "Start over" button (`aria-label="Start over"`) resetting to the concept form. Disclosure line: "Lessons are saved and reusable." Step display names: Definition, Familiar system, Analogy, Mapping, Walkthrough, Placement, Interview-ready, Limitations.
- **PATTERN**: `frontend/src/views/ChatView.tsx:18-60` (state + send flow), `frontend/src/views/ChatView.tsx:63-70` (error alert).
- **IMPORTS**: `react` (`useState`), `../api/learn` (`postExplain`, `postRegenerate`), `../api/query` (`postQuery`), `../api/types` (Learn types).
- **GOTCHA**: (1) Ask while a regenerate is in flight (or vice versa): single `loading` flag disables ALL action buttons (mirror `ChatView`'s `if (!question || loading) return`). (2) Regenerate replaces the whole `explanation` object — threads keyed by step name survive (intended: old Q&A stays visible under the new step text). (3) Enter-key submits for both inputs (mirror `ChatView:135-137`).
- **VALIDATE**: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`

### UPDATE frontend/src/App.tsx — render LearnView

- **IMPLEMENT**: Import `LearnView`; change the `learn` VIEWS entry blurb to `''`; extend the main branch to `{view === 'chat' ? <ChatView /> : view === 'learn' ? <LearnView /> : <p>{active.blurb}</p>}`.
- **PATTERN**: `frontend/src/App.tsx:1-12, 40` (VIEWS table + chat branch).
- **IMPORTS**: `./views/LearnView`.
- **GOTCHA**: Keep the remaining four stubs untouched (capture/work/practice/interview are later deliverables).
- **VALIDATE**: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`

### CREATE backend/tests/test_explainer.py — explainer unit tests

- **IMPLEMENT**: Mirror `test_qa.py` helpers: `_stage_payloads()` returning valid JSON for A/B/C; `_chat_for(payloads: list[str], record=None)` popping one payload per call (assert call count == 3); stub `profile_fn`/`memory_fn`; `persist_fn` capturing args. Tests: (1) happy path returns all 8 steps + calls chat exactly 3× with chained context (assert Stage B messages contain Stage A definition text); (2) Stage B malformed JSON → `ExplainerValidationError` naming "B", `persist_fn` NOT called; (3) `memory_fn` returning context flows `reused_from` into result + Stage A messages contain the framing note; (4) profile emphasis renders into Stage A messages (e.g. `how_i_learn` text present); (5) `regenerate_step` happy path: one chat call, other 7 steps byte-identical, `reused_from is None` (D8 — regen never writes lineage into the memory column); (6) `regenerate_step` invalid step → `ValueError` mentioning valid keys, chat NOT called; (7) `regenerate_step` for `mapping` validates array content; non-mapping step with array content → `ExplainerValidationError`; (8) real-repository atomicity: `generate_explanation` with `persist_fn=None` against tmp `db_path` (init via `init_db`) writes v1 then v2 on repeat concept; failed run writes zero rows; (9) column sync: regen of `mapping` then `limitations` on tmp DB yields top-level columns equal to in-steps values (assert via `get_explanation` after each regen). Use `tmp_path` + `app.db.connection.init_db` for the repository-backed tests (mirror `test_conversations.py` if it uses tmp DBs — check that file first).
- **PATTERN**: `backend/tests/test_qa.py:41-76` (stub helpers + happy path + refusal-shape assertions).
- **IMPORTS**: `asyncio`, `json`, `pytest`, `app.core.grounding.STEP_KEYS`, `app.db.connection.init_db`, `app.db.explanations.{ExplanationDetail, get_explanation}`, `app.llm.explainer.{...}`.
- **GOTCHA**: (1) No network, no embedding model, no real Meta key in ANY test — all `chat_fn`s are stubs. (2) `asyncio.run(...)` per test (mirror `test_qa.py:51`), not async test functions (no anyio/asyncio plugin configured — verify by checking `pyproject.toml`, which lists no async plugin).
- **VALIDATE**: `cd backend && uv run pytest tests/test_explainer.py -q`

### CREATE backend/tests/test_learn_api.py — learn router tests

- **IMPLEMENT**: TestClient tests with `monkeypatch.setattr("app.api.learn.<name>", stub)` seams: (1) `POST /api/v1/learn/explain` happy path (stub `generate_explanation` async fake) → 200 + PRD-shaped body (all 8 step keys present); (2) blank concept (whitespace) → 422; (3) `generate_explanation` raising `ExplainerValidationError` → 502; (4) raising `MetaAPIError` → 502; (5) `GET /api/v1/learn/explanations/{id}` happy path (stub `get_explanation`) → 200 detail shape; (6) unknown id (stub returns None) → 404; (7) `POST .../regenerate` happy path → 200 explain-shaped body with `reused_from is None` (D8); (8) unknown source → 404; (9) invalid step → 422 with valid keys in `detail`. Plus `POST /api/v1/query` with `context.explanation_id`: (10) unknown explanation → 404 (stub `app.api.query.get_explanation` → None); (11) known → 200 with `mode_used == "teaching"` even when `mode: "evidence"` requested (stub `get_explanation` + stub `hybrid_search` + stub `chat_completion` returning valid Q&A JSON). Mirror the TestClient + lifespan pattern from `test_query_api.py` / `test_ingest_api.py` (read one before writing).
- **PATTERN**: `backend/tests/test_qa.py` (stub style) + whichever of `test_query_api.py`/`test_ingest_api.py` shows the TestClient pattern.
- **IMPORTS**: `json`, `fastapi.testclient.TestClient`, `pytest`, `app.main.create_app`, `app.core.meta_client.MetaAPIError`, `app.llm.explainer.ExplainerValidationError`.
- **GOTCHA**: (1) Monkeypatch the BY-NAME imports (`app.api.learn.generate_explanation` must be imported by name in `learn.py` for this to work — if the router calls `explainer.generate_explanation`, patch `app.llm.explainer.generate_explanation` instead; keep router and tests consistent). (2) TestClient must run inside lifespan (`with TestClient(app)`) if the app factory requires DB init — mirror the existing API test files.
- **VALIDATE**: `cd backend && uv run pytest tests/test_learn_api.py tests/test_query_api.py -q`

### CREATE frontend/src/api/learn.test.ts + frontend/src/views/LearnView.test.tsx — frontend tests

- **IMPLEMENT**: `learn.test.ts`: stub `fetch` (mirror `query.test.ts` — read it first), assert `postExplain` URL `http://localhost:8000/api/v1/learn/explain` + JSON body passthrough; `getExplanation` URL interpolation; `postRegenerate` URL + body. `LearnView.test.tsx`: `explainResponse()` factory (8 steps, `explanation_id: 'exp-1'`, `reused_from: null`); `mockFetchSequence` mirror from `ChatView.test.tsx:20-32`. Tests: (1) renders concept form + no stepper initially; (2) submit → POST-then-GET fetch sequence, stepper with 8 steps appears, step 1 content shown, header shows concept + `v1` from the GET payload; (3) Next/Back move without fetch calls (assert `fetch.mock.calls.length` unchanged); (4) Ask flow posts to `/api/v1/query` with `{question, mode:'teaching', context:{explanation_id:'exp-1'}, conversation_id:null}` and renders the answer under the step; second Ask threads `conversation_id`; (5) Regenerate posts to `/api/v1/learn/explanations/exp-1/regenerate` with `{step:'analogy'}` then GETs the new id and swaps content keeping position (assert both fetch URLs in order); (6) failed explain renders `role="alert"` with Dismiss; (7) mapping step renders familiar→technical pairs.
- **PATTERN**: `frontend/src/views/ChatView.test.tsx:7-62` (factory + fetch-sequence + submit assertions), `frontend/src/api/query.test.ts` (client-test shape — read before writing).
- **IMPORTS**: `vitest`, `@testing-library/react`, `../api/types` (factories), `./LearnView`.
- **GOTCHA**: (1) `afterEach`: `cleanup(); vi.unstubAllGlobals(); vi.unstubAllEnvs()` (mirror line 34-39). (2) Async assertions need `findBy*` (mirror line 56). (3) Step-button labels must match `LearnView` exactly (`Step: analogy` etc.) — keep view and tests consistent.
- **VALIDATE**: `cd frontend && npm test -- --run src/api/learn.test.ts src/views/LearnView.test.tsx`

---

## TESTING STRATEGY

Backend mirrors `test_qa.py` (stubbed seams, no network) + existing TestClient router tests; frontend mirrors `ChatView.test.tsx`/`query.test.ts` (mocked `fetch`). No new frameworks, no async plugins.

### Unit Tests

`tests/test_explainer.py`: orchestration fully stubbed (`chat_fn` pops canned stage JSON; `profile_fn`/`memory_fn`/`persist_fn` fakes). Covers: 3-call chaining with context propagation, per-stage validation failure naming the stage, atomicity (no persist on failure), seam rendering (profile/memory content reaches Stage A messages), regenerate copy-verbatim + `reused_from`, invalid-step `ValueError` without a call, mapping/non-mapping content-type validation. Repository-backed subset uses `tmp_path` + `init_db` for version-increment + zero-rows-on-failure.

### Integration Tests

`tests/test_learn_api.py`: TestClient over the real app with module-seam monkeypatches. Covers: PRD-shaped 200s, 422/404/502 mapping per endpoint, `/query` + `context.explanation_id` forcing `mode_used == "teaching"`, unknown-explanation 404. Existing `test_query_api.py` + `test_qa.py` must pass unmodified (regression proof for the `extra_system` extension).

### Edge Cases

- Whitespace-only concept → 422 (not a 3-call burn).
- Unknown explanation id in `/query` context → 404; unknown id in GET/regenerate → 404.
- Invalid regenerate step → 422 listing the eight valid keys.
- Malformed JSON at Stage B (middle) → 502, zero DB rows.
- Fenced (```json) stage output accepted via `strip_fences` (mirror `qa.py` tolerance).
- Empty KB (no artifacts, no memory, default profile) → explain still succeeds (teaching mode never blocked).
- Repeat concept → version increments (v1, v2), distinct ids.
- Mapping step with empty array → valid (model allows `list`, possibly empty); mapping item missing `note` → 502.
- Frontend: Next on step 8 / Back on step 1 are no-ops; Ask/Regenerate disabled while `loading`; second Ask threads `conversation_id`.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

- `cd backend && uv run ruff check . && uv run ruff format --check .`
  - Expected: exit 0, `All checks passed!` + `N files would be left unchanged` (no failures).
- `cd backend && uv run mypy app`
  - Expected: exit 0, `Success: no issues found` (non-strict config in `pyproject.toml`).
- `cd frontend && npm run lint`
  - Expected: exit 0, no warnings/errors (oxlint).
- `cd frontend && npx tsc --noEmit -p tsconfig.app.json`
  - Expected: exit 0, no output.

### Level 2: Unit Tests

- `cd backend && uv run pytest tests/test_explainer.py tests/test_learn_api.py tests/test_qa.py tests/test_query_api.py -q`
  - Expected: exit 0, `N passed` with zero failures (new + regression-adjacent suites).
- `cd frontend && npm test -- --run src/api/learn.test.ts src/views/LearnView.test.tsx src/api/query.test.ts src/views/ChatView.test.tsx`
  - Expected: exit 0, `Test Files 4 passed`, all tests passed.

### Level 3: Integration Tests

- `cd backend && uv run pytest -q`
  - Expected: exit 0, full suite passes (new + all pre-existing, zero regressions).
- `cd frontend && npm test -- --run`
  - Expected: exit 0, all test files pass.
- `cd frontend && npm run build`
  - Expected: exit 0, `tsc -b` + `vite build` succeed, `dist/` emitted.

### Level 4: Manual Validation

Performer `agent` steps run in this environment (executor MUST run them); `human` steps need a real browser.

**Setup (agent):** start the backend with a scratch DB:
1. `cd backend && DATABASE_PATH=/tmp/tb-explainer-manual.db uv run uvicorn app.main:create_app --factory --port 8000 &` then `sleep 4; curl -s http://localhost:8000/api/v1/health | head -c 300`
   - Expected: HTTP 200 JSON containing `"status": "ok"` (proves the app boots with the learn router registered).

**A1 — Explain round-trip (agent):**
1. `curl -s -X POST http://localhost:8000/api/v1/learn/explain -H 'Content-Type: application/json' -d '{"concept": "RAG", "familiar_system_hint": "library"}' | uv run python -c "import json,sys; d=json.load(sys.stdin); print(sorted(d['steps'].keys())); print(d['explanation_id'], d['reused_from'])"`
   - Expected: all eight step keys printed in sorted order + a hex `explanation_id` and `None` for `reused_from` (live Meta call; takes ~30–90s for 3 stages; proves A5 token budgets hold and multi-stage chaining works end to end).

**A2 — Single-fetch + version increment (agent):**
1. Repeat the A1 curl with the same concept; capture both ids as `$E1`, `$E2`.
2. `curl -s http://localhost:8000/api/v1/learn/explanations/$E2 | uv run python -c "import json,sys; d=json.load(sys.stdin); print(d['concept'], d['version'], d['reused_from'])"`
   - Expected: `RAG 2 None` (proves versioning; repeat generates fresh per assumption A6).

**A3 — Regenerate one step (agent):**
1. `E3=$(curl -s -X POST http://localhost:8000/api/v1/learn/explanations/$E1/regenerate -H 'Content-Type: application/json' -d '{"step": "analogy"}' | uv run python -c "import json,sys; d=json.load(sys.stdin); print(d['explanation_id'])"); echo "E3=$E3"`
   - Expected: a new hex id distinct from `$E1` (proves a new version row was created).
2. `curl -s http://localhost:8000/api/v1/learn/explanations/$E3 | uv run python -c "import json,sys; d=json.load(sys.stdin); print(d['version'], d['reused_from'])"`
   - Expected: `3 None` (version max+1; `reused_from` NULL per D8 — regen is not memory reuse).
3. `curl -s http://localhost:8000/api/v1/learn/explanations/$E1 > /tmp/e1.json; curl -s http://localhost:8000/api/v1/learn/explanations/$E3 > /tmp/e3.json; uv run python -c "import json; a=json.load(open('/tmp/e1.json'))['steps']; b=json.load(open('/tmp/e3.json'))['steps']; print([k for k in a if a[k]!=b[k]])"`
   - Expected: `['analogy']` (only the target step changed; the other 7 are copied verbatim by code, so this is deterministic).
4. `curl -s -X POST http://localhost:8000/api/v1/learn/explanations/$E1/regenerate -H 'Content-Type: application/json' -d '{"step": "bogus"}' -w '\n%{http_code}\n'`
   - Expected: HTTP 422 with the eight valid keys named in `detail`.

**A4 — Interrupt forces teaching (agent):**
1. `curl -s -X POST http://localhost:8000/api/v1/query -H 'Content-Type: application/json' -d '{"question": "What did I accomplish?", "mode": "evidence", "context": {"explanation_id": "'$E1'"}}' | uv run python -c "import json,sys; d=json.load(sys.stdin); print(d['mode_used'], d['conversation_id'][:8])"`
   - Expected: `mode_used` is `teaching` (forced despite `mode: evidence`) + a hex conversation id (proves D5).
2. `curl -s -X POST http://localhost:8000/api/v1/query -H 'Content-Type: application/json' -d '{"question": "hi", "context": {"explanation_id": "deadbeef"}}' -w '\n%{http_code}\n'`
   - Expected: HTTP 404 `explanation not found`.

**H1 — Learn view round-trip (human):** needs `cd frontend && VITE_API_URL=http://localhost:8000 npm run dev` running + backend from Setup on :8000.
1. Open `http://localhost:5173`, click the `Learn` tab; expected: concept form visible ("Concept", "Familiar system hint (optional)", "Teach me").
2. Type concept `Vector indexes` (distinct from the `RAG` rows A1–A3 created, so versions start at v1), click `Teach me`; expected: after generation, stepper shows 8 steps with Definition current + header `Vector indexes v1 explanation <id…>`.
3. Click `Next` twice; expected: Analogy step content shown, no loading flash (no network).
4. Type `why a librarian?` in "Ask about this step", click `Ask`; expected: answer appears under the step.
5. Click `Next` (Mapping); expected: familiar→technical pairs listed; the Analogy Q&A stays under Analogy when navigating back (positional resume).
6. Click `Regenerate this step`; expected: Mapping content swaps, header now `Vector indexes v2`, position stays on Mapping.
7. Click `Start over`; expected: concept form returns, empty.

**Teardown (agent):** `pkill -f 'uvicorn app.main:create_app.*port 8000'; rm -f /tmp/tb-explainer-manual.db`
   - Expected: exit 0, processes stopped, scratch DB removed.

### Level 5: Additional Validation (Optional)

None required. If the agent-browser skill is available, it may drive H1 mechanically, but the human readability judgment (step quality, mapping sensibility) still needs a human eye — do not mark H1 agent-complete on DOM presence alone.

---

## MANUAL VERIFICATION CHECKLIST

- [ ] [agent] Backend boots with learn routes: run the L4 Setup curl; expected: `200` + `"status": "ok"`.
- [ ] [agent] Live 3-stage explain: run L4 A1; expected: eight step keys + hex id + `reused_from None`.
- [ ] [agent] Versioning: run L4 A2; expected: second explain for `RAG` reads back `version 2`.
- [ ] [agent] Regenerate + bad-step 422: run L4 A3; expected: new id, version `3` with `reused_from None`, diff `['analogy']`; `bogus` → 422 naming valid keys.
- [ ] [agent] Interrupt forces teaching + unknown-id 404: run L4 A4; expected: `mode_used teaching` despite `mode: evidence`; `deadbeef` → 404.
- [ ] [human] Learn view teach → interrupt → resume → regenerate: run L4 H1 steps 1–7; expected: each step's stated observation, ending with `Vector indexes v2` header and working Start over.
- [ ] [agent] No partial lessons: after A1–A4, `cd backend && DATABASE_PATH=/tmp/tb-explainer-manual.db uv run python -c "import sqlite3; c=sqlite3.connect('/tmp/tb-explainer-manual.db'); q=\"SELECT COUNT(*), COUNT(DISTINCT version) FROM explanations WHERE concept='RAG'\"; print(c.execute(q).fetchone())"`; expected: `(3, 3)` — A1 v1, A2 v2, one successful regenerate v3; the bogus step created no row (H1 uses concept 'Vector indexes', excluded by the WHERE clause).
- [ ] [agent] Docs reflection: `grep -c 'learn' backend/README.md` is informational only; expected: no README change required (no new routes documented there — health/deploy only).

## ROLLBACK CONSIDERATIONS

- Revert is a clean `git revert`: new files delete, `query.py`/`qa.py`/`main.py`/`App.tsx`/`types.ts` restore. No DDL runs (tables pre-exist), no migrations, no config changes.
- Data: `explanations` rows created by testing are inert JSON (no FK consumers yet — markers/attempts arrive in deliverable 2/Phase 3). Scratch-DB rows vanish with the file; dev-DB rows can stay (version counters are per-concept, harmless).
- Deploy: this plan does NOT redeploy (CHECKPOINT 2 freshness rule) — redeploy happens at the next deploy action with rebuilt `dist/`. State this in the execution report.

## ACCEPTANCE CRITERIA

- [ ] `POST /learn/explain` returns PRD §10 shape with all eight step keys (L4 A1 agent curl; expected: eight keys + hex id).
- [ ] Generation is multi-stage, not single-shot (L2 `test_explainer.py` chaining test; expected: exactly 3 chat calls, Stage B input contains Stage A output).
- [ ] Lessons persist versioned; repeats increment (L4 A2; expected: `RAG 2 None`).
- [ ] Step regeneration persists version max+1 with `reused_from` NULL and only the target step changed (L4 A3; expected: version `3`, `reused_from None`, diff `['analogy']`).
- [ ] Interrupt via `/query` + `context.explanation_id` forces teaching mode (L4 A4; expected: `mode_used teaching`).
- [ ] Unknown explanation ids 404 on all three read paths (L2 `test_learn_api.py` + L4 A4; expected: 404 `explanation not found` / `conversation`-style detail).
- [ ] Malformed stage output → 502 with zero rows persisted (L2 atomicity test; expected: `ExplainerValidationError`, persist never called).
- [ ] Learn view completes teach → interrupt → resume → regenerate (H1 human check; expected: all 7 observations incl. `v2` header).
- [ ] All validation commands pass with zero errors (L1–L3; expected: each `Expected:` line holds).
- [ ] No coverage threshold is set in CLAUDE.md/AGENTS.md — noted; new modules carry dedicated unit + router/view tests (L2 files exist and pass).
- [ ] Integration tests verify end-to-end workflows (L3 full suites green; L4 live curls A1–A4 green).
- [ ] Code follows project conventions (seam docstrings, thin routers, prompts in `core/`, L1 lint clean).
- [ ] No regressions in existing functionality (L2–L3: `test_qa.py`/`test_query_api.py`/`ChatView`/`query.test` pass unmodified).
- [ ] Owner decisions on single-fetch assignment, additive regenerate contract, and `reused_from` reservation recorded in `## Revision History` (read plan tail; expected: Cycle 1 entry quoting all three decisions).
- [ ] Performance: live explain completes in < 3 min on the dev key (L4 A1 wall-clock observation).
- [ ] Security: untrusted hint/concept text framed as data in prompts; no keys logged (code inspection during review — prompts built only via `grounding.py` helpers).

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

- **Why 3 stages (D1):** 8 calls would be slow/expensive and risk cross-step drift; 1 call risks unparseable mega-JSON and violates PRD's explicit "multi-stage generation (not single-shot)". The A/B/C split groups the consistency-critical triple (analogy+mapping+walkthrough) while keeping each JSON payload validatable.
- **Why `(messages, budget)` chat arity:** stage budgets differ (B needs 2× A/C); threading the budget through the seam keeps `llm/` testable without settings and the router as the single place that knows Meta. The arity differs from `qa.py`'s `ChatFn` deliberately — aliased separately, never confused.
- **Why force teaching on interrupt (D5):** PRD F-3 mandates teaching mode for interruptions with the explanation as context. An evidence-mode interrupt ("what did I say…") is better served by plain `/query` without context — the UI always sends `mode: "teaching"` for Ask anyway; forcing is belt-and-braces.
- **Why no retrieval in the explainer:** simplest rung that holds. Teaching mode permits general knowledge; personalization arrives via profile + memory seams. If demo review shows generic-feeling lessons, the memory seam (deliverable 2) is the designed inlet for retrieved personalization — no explainer rework needed.
- **Trade-off — exact-string versioning:** `max_version_for_concept` matches exact concept strings ("RAG" ≠ "rag"). Fuzzy same-concept grouping is deliverable 2's explicitly owned logic; normalizing here would preempt it.
- **Reviewer attention (resolved Nov 3):** assumptions A2 (single-fetch assignment) and A3 (additive regenerate contract) plus `reused_from` semantics were escalated and owner-decided — see `## Revision History` Cycle 1. Alternatives considered and rejected: (i) move single-fetch to deliverable 2 with client-side explanation state (rejected: resume/regenerate need server state anyway); (ii) fold regenerate into `POST /learn/explain` via a `regenerate:` field (rejected: mutates the specified PRD contract instead of adding beside it); (iii) new `regenerated_from` column for regen lineage (rejected: this deliverable's first migration for an edge no PRD-required behavior consumes — deliverable 2 owns it if needed).

---

## VALIDATION OUTPUT REFERENCE — EXACT OUTPUTS TO CHECK (DO NOT SKIP)

The executor fills this section during `/execute` with the exact full command + exact full output per check. Each check appears EXACTLY once. Template entries (executor replaces `⟨…⟩` with observed output — never truncates, never summarizes):

- Item to check:
  `cd backend && uv run ruff check . && uv run ruff format --check .`
  Expected output or result:
  ⟨exact full output, e.g. `All checks passed!` + format summary⟩

- Item to check:
  `cd backend && uv run mypy app`
  Expected output or result:
  ⟨exact full output, e.g. `Success: no issues found in N source files`⟩

- Item to check:
  `cd frontend && npm run lint`
  Expected output or result:
  ⟨exact full oxlint output⟩

- Item to check:
  `cd frontend && npx tsc --noEmit -p tsconfig.app.json`
  Expected output or result:
  ⟨empty output⟩

- Item to check:
  `cd backend && uv run pytest tests/test_explainer.py tests/test_learn_api.py tests/test_qa.py tests/test_query_api.py -q`
  Expected output or result:
  ⟨exact full output ending `N passed`⟩

- Item to check:
  `cd frontend && npm test -- --run src/api/learn.test.ts src/views/LearnView.test.tsx src/api/query.test.ts src/views/ChatView.test.tsx`
  Expected output or result:
  ⟨exact full output ending `Test Files 4 passed`⟩

- Item to check:
  `cd backend && uv run pytest -q`
  Expected output or result:
  ⟨exact full output ending `N passed`⟩

- Item to check:
  `cd frontend && npm test -- --run`
  Expected output or result:
  ⟨exact full output, all files passed⟩

- Item to check:
  `cd frontend && npm run build`
  Expected output or result:
  ⟨exact full `tsc -b` + `vite build` output ending with `dist/` summary⟩

- Item to check:
  L4 Setup curl — backend boots with learn routes
  Expected output or result:
  ⟨exact JSON containing `"status": "ok"`⟩

- Item to check:
  L4 A1 curl — live 3-stage explain for `RAG`
  Expected output or result:
  ⟨exact eight sorted step keys + hex id + `None`⟩

- Item to check:
  L4 A2 curl — repeat explain reads back version 2
  Expected output or result:
  ⟨exact `RAG 2 None`⟩

- Item to check:
  L4 A3 curls — new id + version 3 / reused_from None + single-step diff + bad-step 422
  Expected output or result:
  ⟨exact new hex id; exact `3 None`; exact `['analogy']`; exact 422 body naming valid keys⟩

- Item to check:
  L4 A4 curls — interrupt forces teaching + unknown-id 404
  Expected output or result:
  ⟨exact `teaching` + conversation prefix; exact 404 body⟩

- Item to check:
  H1 human Learn view round-trip steps 1–7
  Expected output or result:
  ⟨human confirms each of the 7 stated observations, ending with `Vector indexes v2` header + working Start over⟩

- Item to check:
  RAG-scoped orphan-row count query after A1–A4
  Expected output or result:
  ⟨exact `(3, 3)`⟩

- Item to check:
  Files created: `backend/app/db/explanations.py`, `backend/app/llm/explainer.py`, `backend/app/api/learn.py`, `backend/tests/test_explainer.py`, `backend/tests/test_learn_api.py`, `frontend/src/api/learn.ts`, `frontend/src/api/learn.test.ts`, `frontend/src/views/LearnView.tsx`, `frontend/src/views/LearnView.test.tsx`
  Expected output or result:
  ⟨`ls` evidence that each file exists⟩

- Item to check:
  Files modified: `backend/app/core/grounding.py`, `backend/app/api/query.py`, `backend/app/llm/qa.py`, `backend/app/main.py`, `frontend/src/api/types.ts`, `frontend/src/App.tsx`
  Expected output or result:
  ⟨`git status --short` showing exactly these modifications (plus the new files)⟩

---

## Revision History

### Cycle 1

**Trigger:** independent review `NEEDS_DECISION` (`.agents/plans/reviews/eight-step-explainer-learn-view-plan-review.md`) + owner decisions on all three escalations (Nov 3).

**Owner decisions applied:**
1. "Single-fetch endpoint: Approved. Implement `GET /learn/explanations/{id}` in Deliverable 1 because the interactive Learn view depends on it. Keep the explanation-listing and memory-reuse functionality in Deliverable 2." → Scope NOTE and assumption A2 marked owner-approved; no structural change (was already the plan's position).
2. "Regeneration endpoint: Approved. `POST /learn/explanations/{id}/regenerate` implements the PRD's existing requirement to regenerate explanation steps and save new versions." → Scope bullet and assumption A3 marked owner-approved; no structural change.
3. "`reused_from` semantics: Do not conflate regeneration lineage with explanation-memory reuse or success signals. ... Determine the smallest solution compatible with the existing schema and upcoming explanation-memory deliverable." → Resolved as new design decision D8 with no further product decision needed: the column carries exactly one meaning ("generated using prior explanation X as context", written only by the deliverable-2 memory path); regen writes `reused_from = NULL` and never inherits the source's value; no schema change; the (concept, version) sequence is the only ordering. A `regenerated_from` column was considered and rejected (first migration for an edge no PRD-required behavior consumes). D4/D6, `regenerate_step` spec, regen unit/router tests, L4 A3, and the regen acceptance criterion updated to `reused_from None` + version/diff verification.

**Routine corrections applied (all four):**
1. "LearnView needs concept and version for its header, but POST /learn/explain and /regenerate return only explanation_id/reused_from/steps..." → D7 + LearnView task specify `getExplanation` after every explain/regenerate POST; frontend test task sequences assert the POST-then-GET order.
2. "H1 runs against the scratch DB already holding RAG v1–v3 from A1–A3, so its expected 'RAG v1' and 'v2' headers are unreachable..." → H1 uses distinct concept "Vector indexes" with v1-then-v2 expectations.
3. "The orphan-row checklist item expects (3, 2) while its own note says regenerate creates v3..." → definite `(3, 3)` scoped with `WHERE concept='RAG'` (H1's rows excluded deterministically); hedging note removed; validation-reference entry mirrored.
4. "Regenerating mapping or limitations must also update the top-level mapping/limitations columns..." → `regenerate_step`/persist spec derives columns from merged steps; new unit test (9) asserts top-level == in-steps via `get_explanation`.

**Also updated for consistency:** manual checklist A3/H1 items, sign-off acceptance criterion (now: decisions recorded in this Cycle 1 entry), NOTES reviewer-attention paragraph.

**Not done:** nothing — all review findings addressed or owner-decided. Re-verification via `/review-plan` rerun is the owner's call (not run in this pass).



