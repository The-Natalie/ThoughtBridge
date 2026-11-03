# Feature: explanation-memory-retrieval-markers

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

Phase 2 deliverable 2 of 6. Deliverable 1 (eight-step explainer + Learn view, commit `95667d2`) is committed and left explicit seams for this plan: `MemoryFn`/`MemoryContext` in `app/llm/explainer.py`, `memory_fn=no_memory` wiring in `POST /learn/explain`, and `reused_from` reserved exclusively for the memory path (D1-plan D8). This plan fills those seams. It assumes deliverable 1 as committed; it does NOT assume deliverable 3 (learner profile — the `default_learner_context` default stands).

## Feature Description

Before generating a new lesson, the explainer retrieves past Explanations for the same concept (and related ones by similarity) and injects the winner as context so the successful analogy family is reused. Reuse is governed by explicit success signals: the authoritative signal is the user's "This clicked" marker (whole explanation or individual step); secondary signals are reuse count and linked practice-attempt outcomes. This deliverable adds the marker write/read endpoints, the explanation-list endpoint with success signals, the deterministic memory-selection cascade wired into `POST /learn/explain`, and the marker/reuse UI in LearnView. No new generation contracts, no schema changes, no Practice Loop.

## User Story

As a returning learner
I want ThoughtBridge to remember the explanation that made a concept click
So that I don't start over with a new analogy every time.

## Problem Statement

Every `POST /learn/explain` currently generates from scratch (`memory_fn=no_memory`, `reused_from` always null): repeat requests for one concept produce disconnected v1, v2, … with no reuse of the analogy family that worked. There is no way to record that an explanation clicked and no listing of stored explanations, so PRD F-4 (explanation memory, success markers, reuse) and US-3 ("Reuse what worked") are unmet, and the Phase 2 gate criterion "marked explanation reused on repeat concept request" cannot pass.

## Scope

- In scope:
  - `POST /learn/explanations/{id}/markers` (201) + `GET /learn/explanations/{id}/markers` (additive read path; see D7) + `GET /learn/explanations` (list with success signals + `?concept` filter).
  - Repository functions for markers, explanation summaries with aggregate signals, and memory-candidate reads (no DDL — `explanations`, `explanation_markers`, `attempts` tables already exist in schema v1).
  - Deterministic memory selection (`normalize_concept`, tiered same/related matching, success-signal cascade, framing templates) in a new `app/llm/memory.py`, wired into `POST /learn/explain` by replacing `no_memory`.
  - LearnView marker UI (whole-explanation + per-step "clicked" buttons with optional note), reuse notice banner, lazy concept-history strip.
  - Backend + frontend tests, including the marked-preferred-over-unmarked reuse proof and the preservation-vs-classification boundary.
- Out of scope:
  - Learner profile (deliverable 3), work extraction (4), career profile (5), PDF/Word adapters (6).
  - Practice Loop, question-gen/evaluation, attempt scoring (Phase 3) — `attempts` is read as answered-counts only.
  - Marker deletion/unmarking (no PRD endpoint), marker inheritance across versions, regen-lineage edges, any DDL/migration.
  - Changes to `ExplanationOut` shape, `app/llm/explainer.py`, `app/core/grounding.py` (seams already exist; framing is free text).
  - Chunk/note hybrid retrieval inside the memory path (concept-text similarity only — see D2).
  - Interactive reuse-offer choice flow (injection satisfies PRD's "offered first … or injected as context" — see D4).

## Solution Statement

Add marker + summary reads to `app/db/explanations.py`; implement pure, deterministic memory selection in a new `app/llm/memory.py` (normalized same-concept match → substring → token-overlap tiers; within/across tiers order by marker rank → reuse count → answered-attempt count → recency → id); wire it into the existing `memory_fn` seam so `generate_explanation` injects the winner's steps with a "this worked for you before" framing note and persists `reused_from`; expose the three router endpoints following the `ingest.py` 201/list patterns; extend the frontend learn client + LearnView with lazy marker/history fetching that adds zero requests to the existing teach/regenerate flows (existing tests pass unmodified).

## Feature Metadata

**Feature Type**: Enhancement
**Estimated Complexity**: Medium
**Primary Systems Affected**: `backend/app/db/explanations.py` (repo additions), `backend/app/llm/memory.py` (new), `backend/app/api/learn.py` (wiring + 3 endpoints), `frontend/src/api/` (learn client + types), `frontend/src/views/LearnView.tsx` (marker/reuse UI)
**Dependencies**: Phase 2 deliverable 1 (committed as `95667d2` — seam contracts `MemoryFn`/`MemoryContext`, `reused_from` semantics). No deliverable-3 dependency. No new packages. Runtime dep: Meta Model API via existing `meta_client.chat_completion` (live L4 check only).
**Assumptions**:
1. D1 seam names (`MemoryFn`, `MemoryContext(reused_from, prior_steps, framing_note)`, `no_memory`) are as committed — validate by reading `app/llm/explainer.py:44-60,109-110` before coding.
2. `MODEL_API_KEY` (live key in repo-root `.env`, gitignored) is available for the L4 live reuse proof; all pytest/vitest suites stay offline/stubbed.
3. `attempts` rows exist only when seeded by hand/SQL until Phase 3 — the attempt-count tiebreak is unit-tested with seeded rows, not live data.
4. Single-user scale (tens–hundreds of explanations): full-table candidate scan + Python ranking is acceptable; the scaling cliff is documented, not engineered (see D2).
5. Prior-step injection adds ~1–2 KB (~500 tokens) per stage — existing stage budgets (8192/16384/8192) absorb it with no change.

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `backend/app/llm/explainer.py` (lines 44-60) - Why: `MemoryContext`/`MemoryFn` seam contracts this plan fills; `reused_from`/`prior_steps`/`framing_note` field names are fixed.
- `backend/app/llm/explainer.py` (lines 109-134) - Why: `no_memory` default being replaced; `render_memory_block` framing format ("{framing_note}" + "Prior explanation that worked (JSON…)" + steps JSON).
- `backend/app/llm/explainer.py` (lines 145-211) - Why: `generate_explanation` calls `memory_fn(concept)` (line 157), flows `reused_from` into the result + row (lines 159, 194-207); atomic persist-last behavior to preserve.
- `backend/app/api/learn.py` (lines 1-11) - Why: by-name import seam convention (`monkeypatch.setattr("app.api.learn.<name>", …)`) — new imports must follow it.
- `backend/app/api/learn.py` (lines 83-117) - Why: `post_explain` wiring; line 99 (`memory_fn=no_memory`) is the exact line this plan changes; exception-order pattern (502-before-500) to mirror.
- `backend/app/api/learn.py` (lines 120-135) - Why: `GET /learn/explanations/{id}` shape is FROZEN — do not add keys (existing exact-keys test); the reason D7 adds a separate markers endpoint.
- `backend/app/api/learn.py` (lines 150-155) - Why: invalid-step 422 message pattern (lists all valid keys) to mirror for step-scope marker validation.
- `backend/app/db/schema.sql` (lines 97-117) - Why: `explanations` + `explanation_markers` columns (no DDL needed); `reused_from` + `ON DELETE CASCADE` semantics.
- `backend/app/db/schema.sql` (lines 119-130) - Why: `attempts` columns for the answered-count tiebreak (`explanation_id`, nullable `answer`).
- `backend/app/db/explanations.py` (lines 28-112) - Why: repository idioms to extend — `uuid4().hex` ids (line 38), UTC isoformat (line 39), one-connection-per-function, `connect`/`close` in try/finally.
- `backend/app/api/ingest.py` (lines 84, 113) - Why: 201-create decorator pattern (`response_model=…`, `status_code=status.HTTP_201_CREATED`) for the markers POST.
- `backend/app/api/ingest.py` (lines 158-171) - Why: list-endpoint pattern (`response_model=list[…]`, dataclass→Pydantic mapping) for `GET /learn/explanations`; note list registers before detail.
- `backend/app/api/ingest.py` (lines 87-89) - Why: blank-input 422 in the router (not the repo) — mirror for blank `?concept` handling.
- `backend/app/core/grounding.py` (lines 142-151) - Why: canonical `STEP_KEYS` for step-scope validation (import, never redefine).
- `backend/app/retrieval/search.py` (line 31) - Why: `_TOKEN_RE = re.compile(r"\w+", re.UNICODE)` tokenization idiom to mirror for concept token-overlap.
- `backend/app/db/chunks.py` (lines 21-44) - Why: one-connection batch-read pattern for the aggregate-count queries.
- `backend/tests/test_learn_api.py` (lines 35-59) - Why: settings-isolation fixture + `_client`/`_detail` helpers to reuse for all new router tests.
- `backend/tests/test_learn_api.py` (lines 87-103, 134-152) - Why: response-shape assertion style (`set(body.keys()) == …`) to mirror; the detail-keys test that must keep passing unmodified.
- `backend/tests/test_explainer.py` (lines 123-144) - Why: memory-flow test style (`MemoryContext` stub → `reused_from` + framing-note-in-prompt assertions).
- `backend/tests/test_explainer.py` (lines 240-243) - Why: `tmp_path` + `init_db` repository-backed test pattern for `test_memory.py`.
- `frontend/src/api/learn.ts` (all) - Why: client-function style (`apiGet`/`apiPost` wrappers + docstrings) for the 3 new functions.
- `frontend/src/api/types.ts` (lines 60-104) - Why: type style ("Field names mirror backend Pydantic JSON exactly") for `MarkerOut`/`ExplanationSummary`.
- `frontend/src/api/client.ts` (lines 16-30) - Why: `apiGet`/`apiPost` helpers (all reads/writes go through them).
- `frontend/src/views/LearnView.tsx` (lines 57-120) - Why: `teach`/`ask`/`regenerate` async patterns (loading/error/threading) new handlers must mirror.
- `frontend/src/views/LearnView.test.tsx` (lines 54-74) - Why: `mockFetchSequence` + `teach` helpers for all new view tests.
- `.agents/plans/phase-2-build-list.md` (lines 17-21) - Why: authoritative deliverable-2 scope + boundaries ("attempt-outcome linkage reads the attempts table", "no new generation contracts").
- `.agents/plans/eight-step-explainer-learn-view.md` (D2, D8) - Why: seam contracts + "`reused_from` written ONLY by the deliverable-2 memory path; regen writes NULL" (keeps `COUNT(*) WHERE reused_from=X` pure).

### New Files to Create

- `backend/app/llm/memory.py` - Deterministic memory selection: normalization, tiered matching, success cascade, framing templates, `build_memory_context(db_path, concept)`.
- `backend/tests/test_memory.py` - Unit tests for normalization/tiers/cascade/framing + repo round-trips on tmp DBs (15 tests, enumerated in Testing Strategy).

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

No new external dependencies are required, so no external library research was needed — every pattern below is sourced from the cited in-repo files above (do not invent external doc links). The authoritative requirement sources, in precedence order:

- `PRD.md` §7 F-4 (explanation memory, success markers & reuse) — Why: authoritative reuse/signal semantics ("authoritative signal is the user's marker"; "secondary signals are reuse count and linked practice-attempt outcomes"; preservation ≠ classification).
- `PRD.md` §10 Learning contracts — Why: exact endpoint shapes (`GET /learn/explanations`, `GET /learn/explanations/{id}`, `POST …/markers` body `{"scope": "explanation|step", "step": …, "note": …}` → 201).
- `PRD.md` §11 (success criteria: "Stored explanation is offered/reused on repeat concept request, marked explanations preferred"; "'This clicked' markers stored at explanation and step level") — Why: acceptance wording the tests must prove.
- `.agents/plans/phase-2-build-list.md` deliverable 2 + validation gate — Why: scope boundaries and the "marked explanation is reused" gate.
- `AGENTS.md` Environment Constraints — Why: sandboxed sessions deny local servers — L4 live checks MUST use in-process `TestClient` (never `curl localhost`), and browser E2E is `NOT_PERFORMED`/`UNVERIFIED` pending deployment (deployment is out of this deliverable's scope).

### Patterns to Follow

**Naming Conventions:** `snake_case` modules/functions/tables (`explanation_markers`, `build_memory_context`); `PascalCase` Pydantic models/dataclasses (`MarkerOut`, `MemoryContext`); frontend `camelCase` client fns (`listExplanations`, `createMarker`), `PascalCase` components/types.

**Repository idiom (mirror `app/db/explanations.py:28-74`):**

```python
explanation_id = uuid.uuid4().hex          # ids: hex, no dashes
created_at = datetime.now(UTC).isoformat() # timestamps: UTC ISO-8601 TEXT
conn = connect(db_path)                    # one connection per function…
try:
    with conn:                             # …transaction for writes…
        conn.execute(...)
finally:
    conn.close()
```

**201-create endpoint (mirror `app/api/ingest.py:84`):**

```python
@router.post("/learn/explanations/{explanation_id}/markers",
             response_model=MarkerCreated, status_code=status.HTTP_201_CREATED)
```

**List endpoint (mirror `app/api/ingest.py:158-171`):** `response_model=list[ExplanationSummaryOut]`, repo dataclasses mapped to Pydantic in the router, list route registered before `/{id}` detail.

**Router validation (mirror `app/api/learn.py:150-155` + `app/api/ingest.py:87-89`):** input validation lives in the router with 422 details that list valid values, e.g. `f"invalid step {step!r}: must be one of {', '.join(STEP_KEYS)}"`; blank-input 422 with `logger.warning`.

**Seam imports (mirror `app/api/learn.py:7-11`):** new callables (`build_memory_context`, repo fns) imported BY NAME so tests `monkeypatch.setattr("app.api.learn.<name>", stub)`; extend the module docstring seam note.

**Frontend client (mirror `frontend/src/api/learn.ts`):**

```ts
/** Set a "clicked" marker on an explanation or one of its steps. */
export function createMarker(id: string, body: MarkerCreate): Promise<MarkerOut> {
  return apiPost<MarkerOut>(`/api/v1/learn/explanations/${id}/markers`, body)
}
```

**Frontend tests (mirror `frontend/src/views/LearnView.test.tsx:54-74`):** `mockFetchSequence([...])` queues + `teach(fetch)` helper; assert request URLs/bodies via `fetch.mock.calls[i]`.

**Async tests:** `asyncio.run(…)` per test (no async plugin — mirror `test_explainer.py`); never the network, never the fastembed model, never the real Meta key in pytest/vitest.

---

## DESIGN DECISIONS

**D1 — Concept normalization owned here (D1-plan-deferred fuzzy grouping).** `normalize_concept(s) = re.sub(r"\s+", " ", s.strip()).casefold()`. Same-concept = normalized equality, so `"  PHOTOSYNTHESIS "` retrieves `"Photosynthesis"`. `max_version_for_concept` stays exact-string (D1 behavior + tests untouched); only memory retrieval normalizes. Rationale: recall where it matters (retrieval) without perturbing tested versioning semantics.

**D2 — Related-concept similarity WITHOUT embeddings (simplest rung).** Tier function `concept_tier(query_norm, cand_norm) -> int | None`: 0 = normalized-equal; 1 = substring containment either direction (guard: shorter string ≥ 3 chars, so `"AI"` never matches `"air"`); 2 = word-token overlap (`\w+` tokens len ≥ 2, mirroring `retrieval/search.py:31`; requires `|Q ∩ C| / |Q| ≥ 0.5`); else `None` (unrelated, excluded). No fastembed in the memory path: zero model load on explain, flat latency, fully deterministic unit tests. Candidate scan is a full-table lightweight `SELECT id, concept, version, created_at` + Python ranking — acceptable at single-user scale (tens–hundreds of rows); documented cliff: past ~10k explanations, add a normalized-concept column/index (not MVP). Rejected: embedding concepts with fastembed + in-Python cosine (model load per explain, nondeterministic thresholds, heavier tests for no MVP benefit); reusing the chunk vec0 table (explanations are not chunks — polluting it breaks the layer model).

**D3 — Tier-first, then the success cascade (total deterministic order).** Ordering key: `(tier ASC, marked_rank ASC, reuse_count DESC, attempt_count DESC, created_at DESC, id ASC)`. `marked_rank`: 0 = has explanation-scope marker, 1 = step-scope marker(s) only, 2 = unmarked. `reuse_count` = `COUNT(*) WHERE reused_from = X` (pure per D1-plan D8 — regen writes NULL). `attempt_count` = answered attempts (`TRIM(COALESCE(answer,'')) <> ''`) — a weak tiebreak only; Phase 3 owns scoring. Same-concept tier-0 ALWAYS beats related tiers even when unmarked vs marked-related: analogy-family relevance dominates, preventing cross-concept analogy pollution (a marked "RAG retrieval" lesson must not steer a "RAG" lesson as "this worked before"). Rejected: global marks-first (risks wrong-family injection; harder to reason about). Winner = first candidate; `None` when zero candidates (teaching never blocked). `created_at DESC` via negated epoch (`datetime.fromisoformat`, unparseable → `0.0` fallback); `id ASC` final tiebreak.

**D4 — Reuse = injection + disclosure (no choice flow).** PRD F-4 allows "offered first … OR injected as context" — injection through the existing `memory_block` (all 3 stages, zero `explainer.py` changes) is the mechanism; `prior_steps` = the winner's FULL steps dict (bounded ~KBs; stage budgets absorb it per assumption 5). Disclosure = the LearnView reuse notice + history strip (provenance visibility, F-11). Rejected: interactive offer/pick flow (new contracts, modal UI, scope creep for an "or" clause).

**D5 — Framing templates (free text; `grounding.py` untouched).** `build_framing_note(*, same_concept, marked, winner_id, winner_version, winner_concept, marker_note) -> str` (pure, unit-tested):
- marked + same: `"This concept clicked for you before (marked explanation {short} v{n}). Reuse its analogy family — this worked for you before."`
- unmarked + same: `"You studied this concept before (explanation {short} v{n}, not marked as clicked). Build on its analogy family only where it fits."`
- marked + related: `"A related concept ({concept!r}) clicked for you before (marked explanation {short} v{n}). Its analogy family may help here — adapt it, do not force it."`
- unmarked + related: `"You studied a related concept ({concept!r}) before (explanation {short} v{n}). Its analogy family may help — adapt it, do not force it."`
- When a non-empty latest explanation-scope marker note exists, append `" Your note on what clicked: {note}"`. `{short}` = first 8 chars of the id. Tests assert: "worked for you before" present ONLY in marked-same; "related concept" present ONLY in related; note text appended verbatim when present.

**D6 — Marker write semantics: events, not state.** Every POST inserts one row (duplicates allowed; "marked" = `EXISTS`). Rationale: notes + timestamps make each mark an event; dedup constraints would complicate re-marking with a new note, and `EXISTS` ranking is duplicate-insensitive. Validation (router, 404/422): unknown explanation → 404 (check `get_explanation` first); `scope` is `Literal["explanation","step"]` (bad value → automatic 422); step-scope requires `step ∈ STEP_KEYS` else 422 listing valid keys (mirror `learn.py:150-155`); explanation-scope with non-null `step` → 422 (`"step must be null when scope is 'explanation'"`); `note` defaults `""`. Response 201: `{marker_id, explanation_id, scope, step}` (PRD's `{marker_id, scope}` plus convenience fields — safe on a new endpoint). "Connections" (PRD wording) are covered by `step="mapping"` — no sub-step granularity, no schema change. No unmark endpoint (not in PRD); markers cascade-delete with their explanation (schema already `ON DELETE CASCADE`; Phase 3 owns deletion behavior).

**D7 — Additive markers read endpoint; `ExplanationOut` frozen.** New `GET /learn/explanations/{id}/markers` → `[{id, scope, step, note, created_at}]` chronological ASC (marker history). Rationale: the existing detail endpoint has an exact-keys contract test (`test_learn_api.py:134-152`) — additive fields would break it; a sibling endpoint mirrors the owner-approved additive `…/regenerate` precedent and keeps every existing test green. Unknown id → 404 (consistent with detail). The frontend needs this for marked-state display and banner wording.

**D8 — List endpoint with summary signals.** `GET /learn/explanations[?concept=]`: missing param → all, newest first; present-but-blank → 422 (mirror `ingest.py:87-89`); otherwise normalized same-concept filter (tier-0 only — the history strip wants versions of THIS concept, not related ones). Item: `{id, concept, version, created_at, reused_from, reuse_count, marked, marker_count, attempt_count}` ordered `created_at DESC, id ASC`. `marked` = any-marker EXISTS. No pagination (single-user scale; same documented cliff as D2). Aggregates computed with `GROUP BY` queries in ONE connection (mirror `chunks.py:21-44`).

**D9 — Router wiring is a one-line seam swap.** `post_explain`: `memory_fn=no_memory` → `memory_fn=functools.partial(build_memory_context, db_path)` with `build_memory_context` imported BY NAME (seam convention); drop the `no_memory` import (`no_memory` stays in `explainer.py` for its tests). `build_memory_context(db_path, concept)` matches `MemoryFn = Callable[[str], MemoryContext | None]` after partial application. Existing router tests stub `generate_explanation` wholesale → unaffected. `MemoryContext(reused_from=winner.id, prior_steps=dict(winner.steps), framing_note=…)`; blank concept → `None` (defense-in-depth; router already 422s blanks).

**D10 — Frontend: lazy fetching, zero new requests on existing flows.** Marker/history/banner-detail fetches happen ONLY on (a) marker-button click (POST then local state), (b) history-toggle click (list fetch), (c) `reused_from != null` banner detail (source detail + markers fetch). The teach/regenerate POST-then-GET flows keep their exact fetch counts, so all 8 existing view tests pass unmodified. Rationale: no regression risk to the tested flows, fewer requests, simpler loading states.

**D11 — Preservation ≠ classification (F-4/F-12 boundary, load-bearing).** NOTHING auto-marks: teach, ask, regenerate, reuse, and reload never create marker rows; only explicit POSTs do. Regen rows write `reused_from = NULL` (D1 D8 — add a regression test here); reused_from lineage never implies success. New versions (fresh or regen) start unmarked — markers stay on the row the user marked. Tested explicitly (see Testing Strategy).

**D12 — Accepted MVP edge: reload-then-remark duplicates.** Since marked state loads lazily (D10), reloading a marked lesson shows enabled buttons until the user opens history (which shows ✓ badges) — a re-click inserts a duplicate row, harmless by D6 `EXISTS` semantics. Documented, tested (duplicate POST → 201 + `marked` stays true), not fixed — fixing it (eager marker fetch) would perturb the tested teach flow for cosmetic gain.

## IMPLEMENTATION PLAN

### Phase 1: Foundation

Repository + selection core. No router or UI changes yet — pure deterministic logic over the existing schema, fully unit-testable on tmp DBs.

**Tasks:**

- Extend `app/db/explanations.py` with `normalize_concept` (single owner), `Marker`/`ExplanationSummary` dataclasses, `create_marker`, `list_markers`, `list_explanations` (with aggregate signals + optional normalized concept filter), and aggregate helpers — one connection per function, existing functions byte-untouched.
- Create `app/llm/memory.py` with `concept_tier`, `marked_rank_of`, `build_framing_note`, `build_memory_context` per D1–D5/D9 (takes `normalize_concept` + repo reads via one function-local import — cycle-free by construction).

### Phase 2: Core Implementation

Router endpoints + wiring. Thin router over Phase 1; exception shapes mirror `learn.py`/`ingest.py`.

**Tasks:**

- UPDATE `app/api/learn.py`: import swap (`functools.partial(build_memory_context, db_path)`), `GET /learn/explanations`, `POST …/markers` (201), `GET …/markers`; Pydantic models `MarkerCreate`/`MarkerCreated`/`MarkerOut`/`ExplanationSummaryOut`; docstring seam-note update. No other endpoint touched.

### Phase 3: Integration

Frontend client + LearnView marker/reuse UI over the Phase 2 contracts; lazy fetching per D10.

**Tasks:**

- UPDATE `frontend/src/api/types.ts` (`MarkerScope`, `MarkerCreate`, `MarkerOut`, `ExplanationSummary`) + `frontend/src/api/learn.ts` (`listExplanations`, `createMarker`, `listMarkers`).
- UPDATE `frontend/src/views/LearnView.tsx`: whole + per-step clicked buttons with shared optional note input, reuse notice banner with view-prior, lazy earlier-versions strip — exact aria-labels specified in the task.

### Phase 4: Testing & Validation

- CREATE `backend/tests/test_memory.py` (15 tests); UPDATE `backend/tests/test_learn_api.py` (11 new tests, append-only — existing 11 untouched); UPDATE `frontend/src/api/learn.test.ts` (+4) and `frontend/src/views/LearnView.test.tsx` (+6).
- Run Levels 1–4 validation; L4 live TestClient proof with the real key; browser E2E recorded `NOT_PERFORMED` (deployment out of scope).

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable. Task 0 records the pre-change baseline every later `Expected:` line compares against.

### Task 0 — BASELINE gates on the clean tree

- **IMPLEMENT**: Run the full gate suite BEFORE any edit and record exact outputs (pass counts, file counts) for regression comparison.
- **VALIDATE**: `cd backend && uv run pytest -q 2>&1 | tail -n 3`
- **VALIDATE**: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app 2>&1 | tail -n 3`
- **VALIDATE**: `cd frontend && npm test -- --run 2>&1 | tail -n 5 && npm run build 2>&1 | tail -n 3`

### UPDATE backend/app/db/explanations.py

- **IMPLEMENT**: ADD (existing `ExplanationDetail`/`create_explanation`/`get_explanation`/`max_version_for_concept` byte-untouched): `normalize_concept(s: str) -> str` = `re.sub(r"\s+", " ", s.strip()).casefold()` — the SINGLE owner of concept normalization (pure, stdlib-only; lives here beside `max_version_for_concept` because the repo owns concept-matching semantics); `Marker` dataclass (`id, explanation_id, scope, step: str | None, note, created_at`); `ExplanationSummary` dataclass (`id, concept, version, created_at, reused_from: str | None, reuse_count, marked: bool, has_explanation_marker: bool, marker_count, attempt_count`); `create_marker(db_path, explanation_id, scope, step, note) -> Marker` (uuid4hex + UTC isoformat idiom, single-transaction insert, `logger.info` mirroring `create_explanation`); `list_markers(db_path, explanation_id) -> list[Marker]` (`ORDER BY created_at ASC, id ASC`); `list_explanations(db_path, concept_filter: str | None = None) -> list[ExplanationSummary]` — one connection, four queries: base rows (`SELECT id, concept, version, created_at, reused_from FROM explanations ORDER BY created_at DESC, id ASC`), reuse counts (`SELECT reused_from, COUNT(*) … WHERE reused_from IS NOT NULL GROUP BY reused_from`), marker aggregates (`SELECT explanation_id, scope, COUNT(*) … GROUP BY explanation_id, scope`), answered-attempt counts (`SELECT explanation_id, COUNT(*) FROM attempts WHERE explanation_id IS NOT NULL AND TRIM(COALESCE(answer,'')) <> '' GROUP BY explanation_id`); apply `concept_filter` in Python via the local `normalize_concept`; derive `marked` = explanation has any marker row, `has_explanation_marker` = any explanation-scope row (needed for D3 marked-rank without N+1 marker reads), `marker_count` = total rows.
- **PATTERN**: `backend/app/db/explanations.py:28-74` (insert idiom + logging); `backend/app/db/chunks.py:21-44` (one-connection batch reads).
- **IMPORTS**: reuse `json, logging, uuid, dataclass, datetime/UTC, connect`; ADD `re` (for `normalize_concept`). No new module imports — this file gains ZERO cross-module edges.
- **GOTCHA**: (1) Do NOT touch existing functions — `test_explainer.py`/`test_learn_api.py` pin their behavior. (2) `create_marker` assumes validated input (router validates; mirror `ingest_source` layering). (3) `explanation_markers.explanation_id` FK raises `sqlite3.IntegrityError` for unknown ids — router pre-checks via `get_explanation`, so let it propagate (never swallowed). (4) Import direction is DEFINITIVE and cycle-free: `app/llm/explainer.py` already imports this module at module level (`explainer.py:25-29`), so this module must NEVER import `app.llm.*` at any level — `normalize_concept` is defined HERE, and `app/llm/memory.py` takes it via its function-local repo import (see next task).
- **VALIDATE**: `cd backend && uv run ruff check app/db/explanations.py && uv run ruff format --check app/db/explanations.py && uv run mypy app/db/explanations.py`

### CREATE backend/app/llm/memory.py

- **IMPLEMENT**: Module docstring: "Explanation memory selection — pure deterministic cascade over repository reads (PRD F-4). No network, no model, no settings; the router partially applies `db_path`." Contents: `_TOKEN_RE = re.compile(r"\w+", re.UNICODE)` (mirror `search.py:31`); `concept_tier(query_norm, cand_norm) -> int | None` per D2 (equal→0; containment with `min(len) >= 3`→1; token overlap `|Q∩C|/|Q| >= 0.5` on len≥2 tokens→2; empty query tokens→None guard against div-zero; else None); `_epoch(s: str) -> float` (`datetime.fromisoformat`, `except ValueError → 0.0`); `marked_rank_of(has_explanation_marker: bool, has_step_marker: bool) -> int` (0/1/2); `build_framing_note(*, same_concept: bool, marked: bool, winner_id: str, winner_version: int, winner_concept: str, marker_note: str = "") -> str` with the EXACT D5 templates (`{short}` = `winner_id[:8]`; append `" Your note on what clicked: {marker_note}"` iff `marker_note.strip()`); `build_memory_context(db_path: str, concept: str) -> MemoryContext | None` — (1) `if not concept.strip(): return None`; (2) function-local `from app.db.explanations import get_explanation, list_explanations, list_markers, normalize_concept` (ALL repo access through this one local import — see GOTCHA); (3) `summaries = list_explanations(db_path)`; (4) tier each by `concept_tier(qn, normalize_concept(s.concept))`, drop `None`s; (5) winner = `min` by `(tier, marked_rank, -reuse_count, -attempt_count, -_epoch(created_at), id)` with `marked_rank = marked_rank_of(s.has_explanation_marker, s.marked and not s.has_explanation_marker)` per summary (the repo computes `has_explanation_marker` from the scope aggregate — no N+1 marker reads; the router maps summary→Pydantic explicitly so the extra dataclass field never leaks to the API); (6) `winner_detail = get_explanation(db_path, winner.id)` (None-defensive: return None); (7) latest non-empty explanation-scope marker note via `list_markers` filtered in Python; (8) return `MemoryContext(reused_from=winner.id, prior_steps=dict(winner_detail.steps), framing_note=build_framing_note(same_concept=(tier == 0), marked=(rank < 2), …))`. `normalize_concept` is NOT defined here — single owner is `app/db/explanations.py` (previous task).
- **PATTERN**: `backend/app/llm/explainer.py:50-54` (`MemoryContext` field order); `backend/app/retrieval/search.py:31` (token regex).
- **IMPORTS**: module level — `logging, re`, `datetime.datetime` (for `_epoch`), `from app.llm.explainer import MemoryContext` (type only); function-local inside `build_memory_context` — `from app.db.explanations import get_explanation, list_explanations, list_markers, normalize_concept`. `dataclasses` NOT needed.
- **GOTCHA**: (1) Import direction is DEFINITIVE and cycle-free: module level imports `app.llm.explainer` (types) only — legal because explainer never imports memory; `app.db.*` is imported ONLY inside `build_memory_context` (function-local), so the module-level chain `memory → explainer → db.explanations` is acyclic (`db.explanations` imports no `app.llm.*` per the previous task). `app/llm/explainer.py` must NEVER import this module. (2) `min()` with the key tuple implements D3 exactly — do NOT hand-roll comparisons. (3) `prior_steps=dict(…)` defensive copy (never alias the repo dict into the prompt renderer). (4) Empty-DB → `[]` → return None (teaching never blocked). (5) `concept_tier` and `build_framing_note` MUST be pure (no DB) for direct unit tests.
- **VALIDATE**: `cd backend && uv run ruff check app/llm/memory.py && uv run ruff format --check app/llm/memory.py && uv run mypy app/llm/memory.py`

### UPDATE backend/app/api/learn.py

- **IMPLEMENT**: (1) Imports: ADD `functools`, ADD `Query` from fastapi (for `?concept`), ADD `Literal` from typing, ADD `list_explanations, create_marker, list_markers` to the by-name db imports, REMOVE `no_memory` from the explainer import (keep `default_learner_context, generate_explanation, regenerate_step, ExplainerValidationError`); extend the module docstring seam list with `build_memory_context`, `list_explanations`, `create_marker`, `list_markers`. (2) `post_explain`: change ONLY `memory_fn=no_memory` → `memory_fn=functools.partial(build_memory_context, db_path)` (line 99); nothing else in the function. (3) ADD models: `MarkerCreate(scope: Literal["explanation","step"], step: str | None = None, note: str = "")`, `MarkerCreated(marker_id, explanation_id, scope, step: str | None)`, `MarkerOut(id, explanation_id, scope, step: str | None, note, created_at)`, `ExplanationSummaryOut(id, concept, version, created_at, reused_from: str | None, reuse_count: int, marked: bool, marker_count: int, attempt_count: int)`. (4) ADD `GET /learn/explanations` BEFORE the detail route: `def list_explanations_endpoint(concept: str | None = Query(default=None))` — `concept is not None and not concept.strip()` → 422 `"concept filter must not be blank"`; pass through to repo (`concept_filter=concept`); map to `ExplanationSummaryOut`. (5) ADD `POST /learn/explanations/{explanation_id}/markers` (`status_code=201`): `source = get_explanation(…)` None → 404 `"explanation not found"`; `body.scope == "step"` and `(body.step is None or body.step not in STEP_KEYS)` → 422 with the `learn.py:150-155` message shape; `body.scope == "explanation"` and `body.step is not None` → 422 `"step must be null when scope is 'explanation'"`; `marker = create_marker(db_path, explanation_id, body.scope, body.step, body.note)`; `logger.info("marker created: …")`; return `MarkerCreated`. (6) ADD `GET /learn/explanations/{explanation_id}/markers`: 404-check then `[MarkerOut(…) for … in list_markers(…)]`.
- **PATTERN**: `backend/app/api/learn.py:83-117` (wiring + exception order — new endpoints need no LLM exception handling: pure DB reads/writes); `backend/app/api/ingest.py:84` (201), `:158-171` (list mapping + registration order).
- **IMPORTS**: `functools`, `fastapi.{APIRouter, HTTPException, Query, status}`, `typing.Literal`, `app.llm.memory.build_memory_context` (BY NAME), `app.db.explanations.{get_explanation, list_explanations, create_marker, list_markers}` (BY NAME).
- **GOTCHA**: (1) Route order: list (`/learn/explanations`) BEFORE detail (`/learn/explanations/{explanation_id}`); FastAPI distinguishes them anyway, but mirror `ingest.py`. (2) `Literal` bad-scope → FastAPI auto-422 (no manual check; TEST it). (3) Do NOT add keys to `ExplanationOut`/`ExplainResponse` (frozen contracts). (4) Keep the `ExplainerValidationError`-before-`ValueError` order in `post_explain` (untouched, but do not disturb).
- **VALIDATE**: `cd backend && uv run ruff check app/api/learn.py && uv run ruff format --check app/api/learn.py && uv run mypy app/api/learn.py`

### UPDATE frontend/src/api/types.ts + frontend/src/api/learn.ts

- **IMPLEMENT**: types.ts APPEND (after `RegenerateResponse`): `MarkerScope = 'explanation' | 'step'`; `MarkerCreate { scope: MarkerScope; step?: string | null; note?: string }`; `MarkerOut { id: string; explanation_id: string; scope: MarkerScope; step: string | null; note: string; created_at: string }`; `ExplanationSummary { id: string; concept: string; version: number; created_at: string; reused_from: string | null; reuse_count: number; marked: boolean; marker_count: number; attempt_count: number }` (field names mirror Pydantic JSON exactly). learn.ts APPEND: `listExplanations(concept?: string)` → `apiGet<ExplanationSummary[]>(concept === undefined ? '/api/v1/learn/explanations' : \`/api/v1/learn/explanations?concept=${encodeURIComponent(concept)}\`)`; `createMarker(id, body)` → `apiPost<MarkerOut>(\`/api/v1/learn/explanations/${id}/markers\`, body)`; `listMarkers(id)` → `apiGet<MarkerOut[]>(\`…/markers\`)`; one-line docstrings mirroring existing style.
- **PATTERN**: `frontend/src/api/types.ts:100-104` (request/response style); `frontend/src/api/learn.ts:11-26` (wrappers); `frontend/src/api/client.ts:16-30` (helpers).
- **GOTCHA**: (1) `step?: string | null` optional-vs-null: whole-explanation POSTs send `{scope: 'explanation', note?}` with NO step key… Pydantic default None handles absence — but TEST the actual serialized body (`JSON.parse(init.body)`). Decide: always serialize `step: null` explicitly for explanation scope (explicit > absent; matches PRD's `"step": "mapping|null"`). (2) No `undefined` leaking into query strings — branch on `=== undefined`, never interpolate possibly-undefined.
- **VALIDATE**: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`

### UPDATE frontend/src/views/LearnView.tsx

- **IMPLEMENT**: ADD imports (`createMarker`, `listExplanations`, `listMarkers`, types `ExplanationSummary`, `MarkerOut`). ADD state: `noteInput: string`, `wholeMarked: boolean`, `stepMarked: Record<string, boolean>`, `notice: { text: string; priorId: string } | null`, `history: ExplanationSummary[] | null` (null = never fetched / hidden), `historyOpen: boolean`. Behavior: (1) In `teach()` success path after `setExplanation(detail)`: reset `noteInput/wholeMarked/stepMarked/notice/history/historyOpen`; if `response.reused_from` non-null → `Promise.all([getExplanation(response.reused_from), listMarkers(response.reused_from)])` then `setNotice({text: markers.some(m => m.scope === 'explanation') ? 'This builds on an explanation that clicked for you before.' : 'This builds on your earlier explanation.', priorId: response.reused_from})` (failures → existing `setError` path; reused_from-null → NO fetches, D10). (2) `regenerate()` success: clear `notice` (regen returns null reused_from) and reset marker states for the new id (new versions start unmarked, D11). (3) `markWhole()`: guard `loading/explanation/null`; POST `createMarker(explanation.id, {scope: 'explanation', step: null, ...(noteInput.trim() ? {note: noteInput.trim()} : {})})` → on 201 `setWholeMarked(true)`; errors → `setError` alert. (4) `markStep()`: same with `{scope: 'step', step: STEP_KEYS[stepIndex], …}` → `setStepMarked(prev => ({…prev, [step]: true}))`. (5) `toggleHistory()`: if open → close (set null/false, no fetch); else fetch `listExplanations(explanation.concept)` → `setHistory`; errors → alert. (6) `loadVersion(id)`: `getExplanation(id)` → `setExplanation`, reset stepIndex 0, clear notice + marker states + threads/conversation (mirror `teach` resets minus concept inputs). (7) `viewPrior()`: `loadVersion(notice.priorId)`. Render (in lesson view, exact labels): note input `aria-label="What clicked (optional note)"`; buttons `aria-label="Mark whole explanation as clicked"` (text `wholeMarked ? 'Clicked ✓' : 'This clicked'`, `disabled={loading || wholeMarked}`) and `aria-label="Mark this step as clicked"` (text per `stepMarked[step]`, disabled likewise); banner `{notice && <div role="status" aria-label="Reuse notice">…<button aria-label="View prior explanation">…}`; history toggle button `aria-label={historyOpen ? 'Hide earlier versions' : 'Show earlier versions'}` + `{historyOpen && history && <div aria-label="Earlier versions">chips <button aria-label={\`Load version ${v}\`}>v{n}{marked ? ' ✓' : ''}…}` with `aria-current={id === explanation.id ? 'true' : undefined}` on the current chip.
- **PATTERN**: `frontend/src/views/LearnView.tsx:57-120` (async handler shape: trim-guard, loading/error, try/catch/finally); `:137-144` (alert block); existing `aria-label` conventions (`Step: …`, `Ask`, …).
- **GOTCHA**: (1) D10 is load-bearing for existing tests: teach-with-null-reused MUST issue exactly the 2 existing fetches — put the notice fetch strictly inside `if (response.reused_from)`. (2) Regenerate MUST NOT refetch markers/notice (response.reused_from is null; just clear). (3) `mappingText` for chips not needed (chips show version + ✓ only). (4) Keep `loading` gating on every new button (mirror Ask/Regenerate disabled logic).
- **VALIDATE**: `cd frontend && npx tsc --noEmit -p tsconfig.app.json && npm run lint`

### CREATE backend/tests/test_memory.py

- **IMPLEMENT**: 15 tests (mirror `test_explainer.py:240-243` tmp-DB pattern + `asyncio.run` where needed — memory fns are sync, so plain tests except none; no async needed): (1) `normalize_concept` collapses case/whitespace/tabs; (2) `concept_tier`: equal→0, containment→1, `"AI"`/`"air"`→None (min-len guard), token-overlap `"RAG retrieval"`/`"RAG"`→2, disjoint→None, empty-query-tokens→None; (3) `build_memory_context` on empty DB → None; blank concept → None; (4) tier-first: unmarked same-concept beats marked related; (5) marked beats unmarked same-concept (mark the OLDER; assert `reused_from` == older id — the Phase-gate proof at unit level); (6) explanation-marker beats step-marker; (7) reuse-count breaks marked ties (seed `reused_from` rows directly via `create_explanation`); (8) answered-attempt count breaks reuse ties (seed `attempts` via raw SQL `INSERT`); unanswered (`answer NULL`) rows do NOT count; (9) recency + id tiebreak deterministic (two identical unmarked → later `created_at` wins; assert repeated calls agree); (10) framing: marked-same contains "worked for you before"; unmarked-same does NOT contain it; related contains "related concept"; marker note appended verbatim when present, absent when blank; (11) `prior_steps` equals winner steps dict (and is a copy: mutating result does not affect a second call); (12) D8 regression: regen-style row (`reused_from=None`) never inflates any candidate's `reuse_count`; (13) repo: `create_marker`/`list_markers` round-trip (fields + ASC order); (14) repo: `list_explanations` summaries (counts incl. `has_explanation_marker`, DESC order, `concept_filter` normalized match + non-match exclusion); (15) `build_memory_context` returns None when only unrelated concepts exist. Seed helper `_seed(db, concept, version=1) -> ExplanationDetail` via `create_explanation` with minimal 8-key steps; `_mark(db, id, scope='explanation', step=None, note='')` via `create_marker`.
- **PATTERN**: `backend/tests/test_explainer.py:26-39` (STEPS constants), `:240-269` (tmp-DB repo tests, `connect` row-count assertions).
- **IMPORTS**: `json?` (no), `pathlib.Path`, `pytest` (fixture not needed — plain tmp_path args), `app.db.connection.{connect, init_db}`, `app.db.explanations.{create_explanation, create_marker, get_explanation, list_explanations, list_markers, normalize_concept}`, `app.llm.memory.{build_framing_note, build_memory_context, concept_tier, marked_rank_of}`.
- **GOTCHA**: (1) No network/model/key anywhere. (2) `create_explanation` requires 8-key steps dict + mapping list + limitations str — reuse a module-level `STEPS` constant (copy from `test_learn_api.py:23-32`). (3) Attempt seeding via raw `INSERT INTO attempts (id, mode, explanation_id, question, answer, …)` — columns per `schema.sql:120-130` (id/mode/question required NOT NULL; explanation_id/answer nullable).
- **VALIDATE**: `cd backend && uv run pytest tests/test_memory.py -q`

### UPDATE backend/tests/test_learn_api.py (append-only)

- **IMPLEMENT**: APPEND 11 tests reusing `_client`/`_detail`/`STEPS`/isolation fixture (DO NOT modify existing tests): (1) list shape+order (seed 2 explanations via real repo through `init_db` tmp DB… note `_client` creates its own tmp DB per test via `init_db` — seed by importing repo fns and writing to the SAME db path: refactor-free approach — replicate `_client`'s db path? `_client` hides the path. PATTERN FIX: write a local `_seeded_client(monkeypatch, tmp_path, seed_fn)` helper in the NEW tests that mirrors `_client` (init_db → seed via `create_explanation`/`create_marker` with the known path → setenv → TestClient). Assert keys == `{id, concept, version, created_at, reused_from, reuse_count, marked, marker_count, attempt_count}`, DESC order, counts correct incl. a `reused_from` child row); (2) `?concept` filter normalized (`?concept=++rag++` matches `RAG`; non-match → `[]`; blank `?concept=%20%20` → 422); (3) markers POST happy 201 (keys `{marker_id, scope, explanation_id, step}`; row exists via repo read on the seeded path); step-scope POST with `step=mapping` 201; (4) markers POST unknown id → 404 `"explanation not found"`; (5) step-scope with missing step → 422; bogus step → 422 with all STEP_KEYS in detail; (6) explanation-scope with `step=mapping` → 422 mentioning null; bad `scope` value → 422 (Pydantic Literal); (7) duplicate POSTs → both 201, `marked` true in list; (8) GET markers shape (keys `{id, scope, step, note, created_at}`… plus `explanation_id` — assert exact set incl. it) + ASC order + unknown id 404; (9) EXPLAIN-WIRES-MEMORY (the gate proof at router level): seed older + newer same-concept, mark OLDER, stub ONLY `app.api.learn.chat_completion` (canned Stage A/B/C JSON) so the REAL `generate_explanation` + REAL `build_memory_context` run; POST `/learn/explain {"concept": "rag"}` (lowercase — proves normalization end-to-end) → 200, `reused_from == older_id`, steps have 8 keys; assert new version row `v3` with `reused_from=older_id` via repo; (10) explain on empty DB with stubbed chat → 200 `reused_from is None` (teaching never blocked); (11) preservation≠classification: stubbed-chat explain + stubbed-chat regenerate (mirror tests 162-176 but with REAL repo: seed via `_seeded_client`, stub `chat_completion` for both calls) → `list_markers(new_id) == []` and `reused_from is None` on the regen row (D8/D11 joint proof).
- **PATTERN**: `backend/tests/test_learn_api.py:87-137` (stub + status + shape assertions); `test_explainer.py:240-269` (real-repo version assertions).
- **GOTCHA**: (1) Test 9/10/11 stub `chat_completion`, NOT `generate_explanation` — the ONLY tests that let the real orchestrator run; canned payloads must be valid Stage A/B/C JSON (copy shapes from `test_explainer.py:26-39`). (2) `DATABASE_PATH`/`MODEL_API_KEY` env dance must mirror `_client` (fixture clears env; set both). (3) `POST /learn/explain` needs non-blank concept; app lifespan `init_db` runs anyway — seeding order: init → seed → TestClient (TestClient without context-manager does NOT run lifespan — mirror existing tests which init explicitly).
- **VALIDATE**: `cd backend && uv run pytest tests/test_learn_api.py -q`

### UPDATE frontend/src/api/learn.test.ts + frontend/src/views/LearnView.test.tsx (append-only)

- **IMPLEMENT**: learn.test.ts APPEND 4 tests (mirror existing `mockFetch` style): (1) `listExplanations()` GETs `/api/v1/learn/explanations` bare; (2) `listExplanations('RAG retrieval')` encodes the query (`concept=RAG%20retrieval`); (3) `createMarker` POSTs `{scope:'step', step:'mapping'}` to `…/exp-1/markers`; (4) `listMarkers` GETs `…/exp-1/markers`. LearnView.test.tsx APPEND 6 tests (reuse `mockFetchSequence`/`teach`/`explanationDetail`): (1) whole-mark: teach → set note input → click `Mark whole explanation as clicked` → assert POST URL/body `{scope:'explanation', step:null, note:…}`, button text `Clicked ✓` + disabled; (2) step-mark: teach → goto `Step: mapping` → click `Mark this step as clicked` (empty note → body has NO `note` key) → disabled; other-step button still enabled; (3) reuse notice, marked source: `explainResponse({reused_from:'exp-0'})` + detail + `explanationDetail({id:'exp-0'})` + `[{scope:'explanation',…}]` queue → banner `Reuse notice` contains "clicked for you before"; click `View prior explanation` → GET `…/exp-0` asserted + header shows prior; (4) reuse notice, unmarked source: same queue with `[]` markers → banner contains "builds on your earlier explanation" (and NOT "clicked for you before"); (5) history: teach → click `Show earlier versions` → GET `…/explanations?concept=RAG` asserted → chips `Load version 1` with `✓` for marked; click chip → GET detail asserted; toggle hides; (6) marker POST failure (Error payload) → dismissible alert (mirror `:175-184`). Totals: learn.test.ts 4 existing + 4 new = 8; LearnView.test.tsx 8 existing + 6 new = 14.
- **PATTERN**: `frontend/src/api/learn.test.ts:20-45` (URL/body assertions); `frontend/src/views/LearnView.test.tsx:93-106` (POST-then-GET sequencing — new fetches slot AFTER the base queue in exact order; plan each queue explicitly).
- **GOTCHA**: (1) Existing-test queues are EXACT — new tests must enqueue every fetch the new code paths issue (banner = 2 fetches after the base 2; history = 1; mark POST = 1; load-version = 1). (2) `mockFetchSequence` returns `{ok:true…}` unless `__notOk` — for failure tests use `new Error(…)` entries (mirror `:176`). (3) `fireEvent` + `findBy` async patterns — mirror `:68-74` (await the text that proves the fetch landed before asserting calls).
- **VALIDATE**: `cd frontend && npm test -- --run 2>&1 | tail -n 5`

---

## TESTING STRATEGY

Deterministic behavior (tiers, cascade, validation matrices) gets unit tests on tmp DBs; LLM-touching paths get contract tests with stubbed `chat_completion` (real orchestrator + real memory underneath for the reuse proofs). No test touches the network, the fastembed model, or the real Meta key. Deletion-cascade tests are Phase 3 (no deletion endpoint exists yet); the no-auto-marking boundary IS this deliverable (D11) and is tested here.

### Unit Tests

`backend/tests/test_memory.py` (15 tests, all stub-free except tmp-DB repo): normalization; tier table incl. guards; cascade ordering (tier-first, marked > unmarked, explanation > step, reuse, attempts, recency, id-determinism); framing templates (4 wordings + note append); `prior_steps` copy semantics; empty-DB/blank/only-unrelated → None; D8 reuse-purity regression; repo round-trips (markers ASC, summaries + DESC + filter). Fixtures: module-level 8-key `STEPS`, `_seed(db, concept)` + `_mark(db, id, …)` helpers, raw-SQL attempt seeding.

### Integration Tests

`backend/tests/test_learn_api.py` +11 (append-only): list shape/order/filter-422; markers 201/404/422-matrix/duplicates; markers-list shape/404; router-level gate proof — seeded older-marked + newer-unmarked, stubbed `chat_completion` only, lowercase repeat concept → `reused_from == older_id` + v3 row; empty-DB explain → `reused_from None`; explain+regen create zero markers + regen `reused_from None`. Frontend: `learn.test.ts` +4 (paths, query encoding, bodies); `LearnView.test.tsx` +6 (whole-mark, step-mark, marked/unmarked banner variants + view-prior, history toggle/load, marker-failure alert).

### Edge Cases

- Repeat concept with different case/whitespace reuses (normalization); exact-versioning untouched (`max_version_for_concept` still exact — D1 tests prove it).
- Related-concept fallback only when NO same-concept candidate exists (tier-first), with "related concept" framing.
- Only-unrelated history → `reused_from None`, lesson still generates (teaching never blocked).
- `?concept=` blank → 422; non-match → `[]`; omitted → all newest-first.
- Markers on unknown explanation → 404; step-scope missing/bogus step → 422 (+ keys listed); explanation-scope with step → 422; bad scope → 422; duplicates → 201 + `marked` true.
- Fenced-quotes/unicode concepts normalize safely (`casefold`, no crash on empty-after-strip — router 422s first).
- Frontend: banner fetches fire ONLY when `reused_from` non-null; history toggle fetches once per open; mark buttons disabled while `loading` and after 201; regen clears notice/marker state.
- D11/D8: explain/ask/regenerate/reuse/reload create zero marker rows; regen rows carry `reused_from NULL` and inflate no counts.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness. Baselines from Task 0 are the comparison point: any previously-passing test failing now is a regression, not a stale test. All commands run from the repo root with `cd` prefixes (backend commands need `backend/`, frontend need `frontend/`).

### Level 1: Syntax & Style

- `cd backend && uv run ruff check .`
  - Expected: exit 0, "All checks passed".
- `cd backend && uv run ruff format --check .`
  - Expected: exit 0, all files already formatted, no diffs.
- `cd backend && uv run mypy app`
  - Expected: exit 0, no issues found.
- `cd frontend && npm run lint`
  - Expected: exit 0, no warnings/errors.
- `cd frontend && npx tsc --noEmit -p tsconfig.app.json`
  - Expected: exit 0, no output.

### Level 2: Unit Tests

- `cd backend && uv run pytest tests/test_memory.py -q`
  - Expected: exit 0, "15 passed".
- `cd backend && uv run pytest tests/test_learn_api.py -q`
  - Expected: exit 0, "22 passed" (11 pre-existing untouched + 11 new).
- `cd backend && uv run pytest -q`
  - Expected: exit 0, zero failed/error; pass count = Task-0 baseline + 26.
- `cd frontend && npm test -- --run`
  - Expected: exit 0, all suites pass; `learn.test.ts` 8 passed (4 + 4 new), `LearnView.test.tsx` 14 passed (8 + 6 new), zero failures elsewhere.

### Level 3: Integration Tests

Covered by the stubbed TestClient router tests above (no localhost servers in sandbox) plus the production build:

- `cd frontend && npm run build`
  - Expected: exit 0, `tsc -b` clean + Vite build emits `dist/` (confirms no frontend type breakage from the LearnView changes).
- `git status --porcelain -- backend/app/llm/explainer.py backend/app/core/grounding.py backend/app/db/schema.sql` (from repo root)
  - Expected: exit 0, empty output (no-diff proof: explainer, grounding, and schema byte-untouched).

### Level 4: Manual Validation

Performer `agent` = executable in this environment (MUST be run by the executor). Performer `human` = requires the deployed app (deployment out of scope → pending; steps recorded for post-deploy verification).

**A1. [agent] Live marked-preferred reuse via in-process TestClient (real key, scratch DB).** No localhost server (sandbox denies bind) — same routers, model calls, and persistence as production per AGENTS.md equivalent procedure. Write `/tmp/mem_live_check.py` exactly:

```python
"""Live L4: marked explanation reused on normalized repeat concept (deliverable 2)."""
# Run with cwd=backend so `app` imports; DATABASE_PATH + MODEL_API_KEY from env.
from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())
r1 = client.post("/api/v1/learn/explain", json={"concept": "Photosynthesis"})
assert r1.status_code == 200, r1.text
id1 = r1.json()["explanation_id"]
assert r1.json()["reused_from"] is None
m = client.post(f"/api/v1/learn/explanations/{id1}/markers",
                json={"scope": "explanation", "step": None, "note": "chloroplast factory clicked"})
assert m.status_code == 201, m.text
r2 = client.post("/api/v1/learn/explain", json={"concept": "  PHOTOSYNTHESIS "})
assert r2.status_code == 200, r2.text
body = r2.json()
assert body["reused_from"] == id1, f"expected reuse of {id1}, got {body['reused_from']}"
assert sorted(body["steps"].keys()) == ["analogy", "definition", "familiar_system",
    "interview_ready", "limitations", "mapping", "placement", "walkthrough"]
lst = client.get("/api/v1/learn/explanations", params={"concept": "photosynthesis"}).json()
assert len(lst) == 2, lst
first = next(x for x in lst if x["id"] == id1)
assert (first["marked"], first["reuse_count"], first["version"]) == (True, 1, 1), first
print(f"LIVE-MEMORY-OK reused_from={body['reused_from']}")
```

1. `cd backend && rm -f /tmp/mem_live.db* && set -a && . ../.env && set +a && DATABASE_PATH=/tmp/mem_live.db uv run python /tmp/mem_live_check.py` (allow ~120s: two real multi-stage generations).
   - Expected: exit 0, stdout ends with `LIVE-MEMORY-OK reused_from=<id1>`; proves normalization + marked reuse + list signals end-to-end with the real model.
2. `rm -f /tmp/mem_live.db* /tmp/mem_live_check.py` after recording output (scratch cleanup; never commit).

**H1. [human] Marker + reuse UI on the deployed app (pending deployment — NOT_PERFORMED until deploy).** Prerequisite: a deployment serving the Phase 2 frontend+backend at a known URL (out of this deliverable's scope).
1. Open the deployed app Learn view; teach concept "RAG".
   - Expected: 8-step lesson renders; no reuse notice (first explanation).
2. Type "librarian analogy finally made retrieval click" in "What clicked (optional note)"; click "This clicked".
   - Expected: button becomes "Clicked ✓" disabled; no error.
3. Click "Step: mapping", then "Mark this step as clicked".
   - Expected: step button becomes "Clicked ✓" disabled; Definition step's button still enabled.
4. Click "Show earlier versions".
   - Expected: strip lists "v1 ✓"; clicking "Load version 1" reloads the lesson.
5. Click "Start over"; teach "rag" (lowercase).
   - Expected: banner "This builds on an explanation that clicked for you before." + "View prior explanation" button; clicking it loads the v1 lesson.

### Level 5: Additional Validation

NOT_PERFORMED — automated browser E2E requires the Playwright MCP browser against a deployed URL (never localhost) with verified deployment freshness per AGENTS.md; deployment is out of this deliverable's scope. Revisit in Phase 4 (live deployment verified end-to-end) using manual steps H1 as the script.

---

## MANUAL VERIFICATION CHECKLIST

- [ ] [agent] Live reuse proof: run L4-A1 steps 1–2; expected: exit 0, `LIVE-MEMORY-OK`, scratch files removed afterwards.
- [ ] [agent] No-touch proof: run the L3 `git status --porcelain` check; expected: `explainer.py`, `grounding.py`, `schema.sql` show zero modifications.
- [ ] [agent] Edge/validation matrix: run L2 suites; expected: 404/422 marker cases + blank-filter 422 + duplicate-201 + D8/D11 proofs all pass (named tests in `test_learn_api.py`/`test_memory.py`).
- [ ] [agent] Frontend lazy-fetch proof: run L2 frontend suite; expected: all 8 pre-existing `LearnView` tests pass with unchanged fetch-count assertions (D10 holds).
- [ ] [human] Marker + reuse UI (H1 steps 1–5 on deployed URL); expected: clicked states, ✓ badges, reuse banner, view-prior round-trip — PENDING deployment.
- [ ] [agent] Docs reflection: `git status --porcelain` shows only intended files (`app/db/explanations.py`, `app/llm/memory.py`, `app/api/learn.py`, `frontend/src/api/{types,learn}.ts`, `LearnView.tsx`, `tests/test_memory.py`, `tests/test_learn_api.py`, `learn.test.ts`, `LearnView.test.tsx`, this plan); expected: no `.env`, `conversation-log/`, or scratch DB committed.

## ROLLBACK CONSIDERATIONS

- Revert is a plain code revert (`git revert` / drop the working tree): NO schema migration exists in this deliverable (`explanations`, `explanation_markers`, `attempts` are schema-v1 tables from Phase 1 scaffolding), so there is nothing to unwind.
- Data written by this deliverable is inert under old code: pre-change code never reads `explanation_markers` (table stays, ignored) and passes `reused_from` through `GET` unchanged; `list_explanations`/`build_memory_context` vanish with the revert.
- Rollback verification: re-run the Task-0 baseline commands; expected: baseline counts restored exactly.
- Special handling: none — no config keys, no env vars, no dependencies added.

## ACCEPTANCE CRITERIA

- [ ] Marked explanation reused on normalized repeat concept request, marked preferred over unmarked (L2 `test_learn_api.py` explain-wires-memory test: `reused_from == older_marked_id`; L4-A1 live: `LIVE-MEMORY-OK`).
- [ ] "Clicked" markers persist at explanation + step level with notes; invalid writes rejected with 404/422 (L2 markers tests: 201 happy paths, unknown-id 404, step-validation 422s, bad-scope 422, duplicate-201).
- [ ] `GET /learn/explanations` lists summaries with signals + normalized `?concept` filter (L2 list tests: exact key set, DESC order, counts, filter match/non-match/blank-422).
- [ ] Success cascade deterministic per D1–D3 (L2 `test_memory.py`: 15 passed — tier table, cascade ties, framing wordings, None cases).
- [ ] Nothing auto-marks; regen never pollutes reuse (L2 D11/D8 tests: explain+regen → zero marker rows, regen `reused_from None`, `reuse_count` excludes NULL rows).
- [ ] Zero regressions: all pre-existing backend + frontend tests pass UNMODIFIED (L2 full suites: backend = baseline + 26, frontend suites green with unchanged fetch-count assertions; L3 no-touch proof for `explainer.py`/`grounding.py`/`schema.sql`).
- [ ] Marker UI complete: whole + per-step buttons with note, reuse notice with view-prior, lazy history strip with ✓ badges (L2 frontend: +4 client / +6 view tests pass; L1 `tsc` + `lint` + `build` green).
- [ ] Human UI verification on deployed app (H1 steps 1–5) — `UNVERIFIED` pending deployment (deployment out of scope; browser E2E `NOT_PERFORMED` per AGENTS.md).
- [ ] Lint + typecheck + build green (L1 all five commands exit 0).
- [ ] No new dependencies, no DDL, no `ExplanationOut` shape change (manual checklist docs-reflection + no-touch proof; `git status` shows only intended files).

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

- **Why tier-first over marks-first (D3):** the deliverable title orders "same-concept retrieval" before "clicked markers", and PRD F-4 scopes retrieval to "past Explanations for the same concept (and related ones by similarity)" — relevance first, signals within relevance. A global marks-first rule would let a marked lesson for a different concept steer a new concept's analogy family with a "this worked before" claim that is false for THIS concept. Revisit only with evidence that related-marked lessons outperform same-unmarked ones (no such signal exists pre-Phase-3 scoring).
- **Why token-overlap over embeddings (D2):** "simplest rung that holds" (PRD principle 4). Concept strings are short; exact+substring+overlap covers realistic repeats ("RAG" → "rag", "RAG retrieval"); embeddings would add model latency to every explain plus threshold tuning, for recall gains that are speculative at single-user scale.
- **Why duplicates allowed (D6):** markers are timestamped events with optional notes ("what clicked TODAY"); a uniqueness constraint would need conflict semantics (ignore? overwrite? 409?) that no PRD behavior requires. `EXISTS` ranking + ASC history reads make duplicates harmless and auditable.
- **Why the weak attempt signal:** `attempts` has no score column until Phase 3 builds evaluation; answered-count is the only honest signal available, so it sits last among the success signals (PRD lists it secondary; within secondary, reuse-count — a direct reuse vote — outranks it). Phase 3 may re-weight without changing this module's interface (counts in, ordering out).
- **Scaling cliffs (documented, not engineered):** full-table candidate scan (D2) and unpaginated list (D8) assume ≤ thousands of explanations. Past that: normalized-concept column + index, `LIMIT` + cursor pagination. Single-user hackathon scale never approaches this.
- **Framing voice:** templates use plain second-person ("you studied…", "this worked for you before") matching the explainer's "smart friend" voice; the em-dash + "adapt it, do not force it" close on related tiers deliberately hedges cross-concept transfer.
- **Reviewer attention:** (1) RESOLVED in Cycle 1 — `normalize_concept` is owned by `app/db/explanations.py` (pure, beside `max_version_for_concept`); `app/llm/memory.py` takes it via its function-local repo import. No new module-level edges anywhere, so the chain `memory → explainer → db.explanations` is acyclic by construction (verified: `explainer.py:25-29` already imports the repo at module level, which is exactly why the repo must never import `app.llm.*`). (2) D12's reload-then-remark duplicate is the visible wart — accepted by design, tested, one eager fetch away if the owner disagrees.

---

## Revision History

### Cycle 1

Review: `NEEDS_REVISION` (3 failed checks, 4 findings, zero escalations). All four findings addressed; nothing escalated; nothing left undone.

1. "Resolve the likely circular import … pick one fixed approach instead of 'if a circular import surfaces'." — ADDRESSED. Verified the cycle was real (`app/llm/explainer.py:25-29` already imports `app.db.explanations` at module level). Definitive design: `normalize_concept` is defined in `app/db/explanations.py` (pure, stdlib-only, beside `max_version_for_concept`); `app/llm/memory.py` takes it plus all repo reads through ONE function-local import inside `build_memory_context`. Zero new module-level edges, so `memory → explainer → db.explanations` is acyclic by construction. Updated: db task (IMPLEMENT/IMPORTS/GOTCHA), memory task (IMPLEMENT/IMPORTS/GOTCHA), Phase 1 bullets, `test_memory.py` IMPORTS line, NOTES reviewer-attention item (1).
2. "Remove `normalize_concept` from the `app/api/learn.py` import additions" (ruff F401). — ADDRESSED. Router passes `concept_filter` to the repo and never calls it; removed from the learn.py task IMPORTS line.
3. "Add `list_markers` to the function-local repo import in `build_memory_context`" (step 7 uses it, step 2 did not import it). — ADDRESSED. Step (2) now reads `from app.db.explanations import get_explanation, list_explanations, list_markers, normalize_concept`; IMPORTS line mirrors it.
4. "Make the frontend test task consistent: `learn.test.ts` appends 4 tests and `LearnView.test.tsx` appends 6." — ADDRESSED. Task now states "APPEND 4 tests" / "APPEND 6 tests" with individually numbered enumerations (banner split into marked-source (3) and unmarked-source (4) tests); totals (8/14) agree with Testing Strategy, Level 2 expectations, and acceptance criteria, which needed no changes.

Limitation: none — all corrections were routine and technical, resolved within the plan.


