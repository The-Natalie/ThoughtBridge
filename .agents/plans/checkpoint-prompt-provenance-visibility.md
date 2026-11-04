# Feature: checkpoint-prompt button + provenance/grounding visibility pass

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Phase 3 deliverable 5 (build list lines 33-37): (a) a static, copyable coding-assistant checkpoint prompt behind a one-click UI button/modal plus its `GET /prompts/checkpoint` backend endpoint; (b) a provenance/grounding visibility pass across all frontend views so "from your notes" vs. "general explanation" is visually distinct everywhere, every derived item links back to its sources with the original one click away, role labels are visible on conversation-derived content, and status/confidence stay visible on extracted facts. Per PRD F-11 this is a product requirement, not polish.

## User Story

As a ThoughtBridge user
I want a one-click checkpoint prompt for my coding assistant plus consistent "from your notes" vs. "general explanation" labeling and one-click access to original sources in every view
So that I can capture work journals frictionlessly and always tell what the app knows from my notes versus what it generated.

## Problem Statement

F-9 has no implementation: there is no `/prompts/checkpoint` endpoint, no checkpoint button, and no fallback text anywhere in the codebase (grep for `checkpoint` in `backend/` + `frontend/src` returns zero hits). F-11 is partially implemented but inconsistent: ChatView renders grounding as ad-hoc italic text with a blended label (`general explanation + your notes`) that matches neither the PRD F-7 vocabulary (`from your notes` / `general explanation` / `both`) nor FeedbackCard's badge; ChatView and WorkView each hand-roll a different chunk-detail panel (WorkView's lacks the `tb_conversation` role badge ChatView has); LearnView's interrupt Q&A threads show bare answers with no grounding label, no citations, and no path to the source chunk.

## Scope

- In scope: `GET /api/v1/prompts/checkpoint` static endpoint + router registration; typed frontend client + hardcoded fallback text (PRD §10); header button + modal UI with clipboard copy + fallback; shared `GroundingBadge` + `CitationPanel` components; ChatView/LearnView/WorkView/PracticeView/InterviewView visibility refactors listed in the tasks; unit + contract tests for all new behavior.
- Out of scope: any AI generation in the checkpoint prompt (static text only, no integration); new endpoints beyond `GET /prompts/checkpoint`; a conversations-browser view; LearnView step-structure or limitations-display changes; Capture view; deliverable 6 (rerank/HyDE — only on measured failure); all Phase 4 work (seeded demo, README, video, submission).

## Solution Statement

Add a dependency-free static endpoint (`backend/app/api/prompts.py`, module-constant prompt text, registered in `main.py`) and mirror it in a tiny typed client (`frontend/src/api/prompts.ts`) carrying the identical fallback string. Add a global "Checkpoint prompt" header button in `App.tsx` opening a new `CheckpointPromptModal` (fetches, falls back on error, copies via Clipboard API with textarea fallback). Extract the two duplicated provenance renderings into shared components — `GroundingBadge` (canonical 3-label vocabulary + FeedbackCard's border-color system) and `CitationPanel` (chunk meta + text + conversation badge + Close) — and refactor ChatView, WorkView, LearnView (threads gain citations + badge + panel), and FeedbackCard onto them. Unify ChatView's blended teaching label to `both` (one deliberate test-expectation update, flagged below).

## Feature Metadata

**Feature Type**: New Capability (checkpoint button) + Enhancement (visibility pass)
**Estimated Complexity**: Medium
**Primary Systems Affected**: `backend/app/api` (new router), `frontend/src/api` (new client), `frontend/src/components` (3 new/shared), `frontend/src/views` (Chat/Learn/Work refactors), `frontend/src/App.tsx` (header button)
**Dependencies**: none (no new packages; no DB migration; no LLM calls; deliverables 1–4 already committed: `ca41a02`, `13f59ae`, `40f941c`)
**Assumptions**: PRD §10 `GET /prompts/checkpoint` response shape is unspecified beyond "returns the static copyable prompt text" — this plan fixes `{"prompt": "<text>"}` (JSON-everywhere rule, §10); verify at review that no hidden contract expects a different key.

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `backend/app/main.py` (lines 14-21 imports, 56-62 router registration) - Why: exact `include_router(..., prefix="/api/v1")` pattern the new prompts router must follow.
- `backend/app/api/health.py` (lines 15-16 router decl, 34-35 GET route) - Why: thinnest GET-endpoint pattern to mirror (router + response_model).
- `backend/app/api/retrieval.py` (line 97 `GET /chunks/{chunk_id}`) - Why: citation-target endpoint the shared panel links to; do not change it.
- `backend/app/api/query.py` (lines 236-243 conversations list) - Why: shows conversations endpoints live in the query router (no separate conversations router exists); context for provenance sources.
- `backend/app/core/grounding.py` (lines 486-491 `GROUNDING_LABELS`, `GroundingLabel`) - Why: canonical grounding vocabulary (`from your notes` / `general explanation` / `both`) the badge must use.
- `frontend/src/App.tsx` (lines 28-42 nav, 44-58 main) - Why: header button + modal mount point; nav button styling to mirror.
- `frontend/src/api/client.ts` (lines 17-19 `apiGet`) - Why: all backend reads go through here; prompts client must use it.
- `frontend/src/api/query.ts` (lines 12-19 `postQuery`/`getChunk`) - Why: client-function shape + citation-fetch pattern LearnView must adopt.
- `frontend/src/api/types.ts` (lines 6-12 `Citation`, 29-36 `ChunkDetail`, 224 `GroundingLabel`) - Why: exact JSON field names; add `CheckpointPromptResponse` here.
- `frontend/src/views/ChatView.tsx` (lines 13-16 `groundingLabel`, 82-84 grounding render, 90-107 chips, 113-136 panel) - Why: current grounding/citation rendering to refactor onto shared components.
- `frontend/src/views/WorkView.tsx` (lines 107-114 `openCitation`, 285-303 panel) - Why: panel to replace with `CitationPanel` (gains the missing conversation badge).
- `frontend/src/views/LearnView.tsx` (lines 42-45 `ThreadEntry`, 150-174 `ask()`, 476-485 thread render) - Why: threads to extend with citations + badge + panel.
- `frontend/src/components/FeedbackCard.tsx` (lines 8-12 `GROUNDING_STYLES`, 35-37 badge) - Why: border-color badge system `GroundingBadge` extracts; refactor to use it.
- `frontend/src/components/FactCard.tsx` (lines 25-27 kind/status/confidence, 38-52 chunk chips) - Why: already satisfies "status + confidence visible" — verify, do not change.
- `frontend/src/components/AttemptHistory.tsx` (line 49 grounding text) - Why: leave as text (list density); out of the badge refactor.
- `backend/tests/test_query_api.py` (lines 43-72 settings fixtures, 74+ `_client` helper) - Why: TestClient + isolated-settings pattern for the prompts contract test.
- `frontend/src/views/ChatView.test.tsx` (lines 20-32 `mockFetchSequence`, 126-132 blended-label test) - Why: fetch-mock pattern to reuse; line 131 expectation changes to `both` (deliberate, see the ChatView.test update task).
- `frontend/src/components/FeedbackCard.test.tsx` (lines 34-40 badge test) - Why: verbatim-badge assertion pattern for `GroundingBadge` tests.
- `backend/modal_app.py` (line 14 deploy docstring) - Why: deploy command for L4/L5 (`cd backend && uv run modal deploy modal_app.py`).
- `backend/pyproject.toml` + `frontend/package.json` (scripts) - Why: exact validation commands (L1-L3).
- `.agents/plans/phase-3-build-list.md` (lines 33-37) - Why: deliverable scope boundaries (static prompt + visibility only).
- `PRD.md` (§7 F-9 line 246, F-11 line 250; §10 lines 353-355; §6 dir sketch lines 210-224 naming the checkpoint-prompt modal) - Why: authoritative requirements + component placement.

### New Files to Create

- `backend/app/api/prompts.py` - Static checkpoint-prompt endpoint (`CHECKPOINT_PROMPT` const + `GET /prompts/checkpoint`).
- `backend/tests/test_prompts_api.py` - 4 contract tests (shape, static, registration, content markers).
- `frontend/src/api/prompts.ts` - `getCheckpointPrompt()` + identical `FALLBACK_CHECKPOINT_PROMPT`.
- `frontend/src/api/prompts.test.ts` - 2 tests (URL/shape passthrough, fallback markers).
- `frontend/src/App.test.tsx` - 3 tests (header button outside primary nav, opens dialog, Close dismisses).
- `frontend/src/components/GroundingBadge.tsx` - Shared grounding badge (3 canonical labels + border colors).
- `frontend/src/components/GroundingBadge.test.tsx` - 4 tests (3 verbatim labels + distinct styles).
- `frontend/src/components/CitationPanel.tsx` - Shared chunk-detail panel (meta + text + conversation badge + Close).
- `frontend/src/components/CitationPanel.test.tsx` - 3 tests (render, conversation badge iff `tb_conversation`, Close).
- `frontend/src/components/CheckpointPromptModal.tsx` - Modal (prompt text, Copy with fallback, Close, error→fallback note).
- `frontend/src/components/CheckpointPromptModal.test.tsx` - 5 tests (fetch render, clipboard copy, fetch-failure fallback, close, execCommand fallback).

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [MDN Clipboard API — writeText](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard/writeText)
  - Specific section: secure-context requirement + user-gesture requirement.
  - Why: `navigator.clipboard` is `undefined` on non-secure origins and rejects without a click gesture — the modal MUST feature-detect and fall back.
- [MDN `document.execCommand('copy')`](https://developer.mozilla.org/en-US/docs/Web/API/Document/execCommand) (deprecated but functional)
  - Specific section: `copy` command with a selected textarea.
  - Why: the sanctioned fallback path (temporary off-screen textarea, select, execCommand, cleanup) when the async API is unavailable.
- No library/framework docs needed: zero new dependencies, plain React + fetch, established repo patterns only.

### Patterns to Follow

**Thin GET router (mirror `backend/app/api/health.py:15,34-35`):**

```python
router = APIRouter(tags=["prompts"])

class CheckpointPromptResponse(BaseModel):
    prompt: str

@router.get("/prompts/checkpoint", response_model=CheckpointPromptResponse)
def get_checkpoint_prompt() -> CheckpointPromptResponse:
    """Return the static copyable checkpoint prompt (PRD F-9)."""
    return CheckpointPromptResponse(prompt=CHECKPOINT_PROMPT)
```

**Router registration (mirror `backend/app/main.py:56-62`):**

```python
from app.api.prompts import router as prompts_router
# ...
app.include_router(prompts_router, prefix="/api/v1")
```

**Typed GET client (mirror `frontend/src/api/query.ts:12-19` + `client.ts:17-19`):**

```ts
import { apiGet } from './client'
import type { CheckpointPromptResponse } from './types'

/** Fetch the static checkpoint prompt text. Errors propagate as thrown Errors. */
export function getCheckpointPrompt(): Promise<CheckpointPromptResponse> {
  return apiGet<CheckpointPromptResponse>('/api/v1/prompts/checkpoint')
}
```

**Grounding badge styles (extract from `frontend/src/components/FeedbackCard.tsx:8-12` — move, don't copy):**

```tsx
const GROUNDING_STYLES: Record<GroundingLabel, string> = {
  'from your notes': 'border-green-600',
  'general explanation': 'border-neutral-400',
  both: 'border-blue-600',
}
```

**Naming Conventions:** `snake_case` backend modules/functions, `PascalCase` Pydantic models + React components (`PascalCase.tsx`), `camelCase` frontend utils; `aria-label`s are the test contract (`Grounding`, `Citation ${id}`, `Close citation`, `Conversation source`).

**Error Handling:** endpoint is infallible by construction (no DB, no settings, no network) — no 502 path possible; frontend fetch failure shows the hardcoded fallback text with a one-line server-unreachable note (never a blank modal, never a throw).

**Logging Pattern:** none needed (static endpoint, no logging in health GET either).

**Other Relevant Patterns:** `mockFetchSequence` queue-mock from `ChatView.test.tsx:20-32` for all new frontend tests; TestClient-over-`create_app()` with `_isolated_settings`-style fixture from `test_query_api.py:43-58` for the backend contract test; `it.each<GroundingLabel>([...])` verbatim-label assertions from `FeedbackCard.test.tsx:34-40`.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

Static backend endpoint + typed client + shared badge/panel components. No view changes yet; new units land with their tests first so the refactors in Phase 2 compose tested parts.

**Tasks:**

- Create `backend/app/api/prompts.py` with the verbatim `CHECKPOINT_PROMPT` (§NOTES) + response model + GET route; register in `main.py`.
- Add `CheckpointPromptResponse` to `frontend/src/api/types.ts`; create `frontend/src/api/prompts.ts` with `FALLBACK_CHECKPOINT_PROMPT` (byte-identical text).
- Create `GroundingBadge` (extracts `GROUNDING_STYLES` from FeedbackCard) and `CitationPanel` (ChatView panel shape + conversation badge + Close) with their test files.

### Phase 2: Core Implementation

Checkpoint modal + global button; refactor existing renderings onto the shared components; extend LearnView threads with provenance.

**Tasks:**

- Create `CheckpointPromptModal` (fetch → fallback on error, Clipboard API + textarea fallback, Copied confirmation, Close); wire the header button + modal state in `App.tsx`.
- Refactor `FeedbackCard` to render `GroundingBadge` (zero visual change — same label, same classes).
- Refactor `ChatView`: grounding `<p>` → `GroundingBadge` with unified mapping (evidence→`from your notes`, teaching+0 cites→`general explanation`, teaching+N cites→`both`); chunk panel → `CitationPanel`.
- Refactor `WorkView`: chunk panel → `CitationPanel` (gains the conversation badge); keep `openCitation` flow unchanged.
- Extend LearnView `ThreadEntry` with `citations` + `modeUsed` from `postQuery`; render badge + chips + panel per thread.

### Phase 3: Integration

Wire the feature into the application's entry points (router registry, nav header) and update the test suite to the unified contract.

**Tasks:**

- Confirm prompts router mounted under `/api/v1` (OpenAPI lists `/api/v1/prompts/checkpoint`); header button visible on every view (lives in `App.tsx`, not one view).
- Update the one ChatView blended-label test to `both`; add LearnView (badge+chip+panel) and WorkView (conversation badge) tests; add modal/client/component tests.
- No config, middleware, or DB changes — nothing else to register.

### Phase 4: Testing & Validation

**Tasks:**

- New backend contract file (4 tests) + new frontend files (17 tests) + 4 added/updated view tests, all green.
- Full ladders: backend `pytest -q` + ruff + mypy; frontend `npm test -- --run` + `npm run build` (tsc) + oxlint.
- Agent live check: TestClient GET with `MODEL_API_KEY` unset proves no-key static serving; scratch DB deleted after.
- Human + Playwright E2E against a fresh redeploy (button/modal/copy, badges in Chat/Learn/Work/Practice); `NOT_PERFORMED`/`UNVERIFIED` with reason if deploy is impossible — never a failure, never a pass.

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

### CREATE backend/app/api/prompts.py

- **IMPLEMENT**: module docstring (static F-9 prompt, no DB/settings/network); `CHECKPOINT_PROMPT: str` const copied VERBATIM from §NOTES; `router = APIRouter(tags=["prompts"])`; `CheckpointPromptResponse(BaseModel)` with `prompt: str`; sync `GET /prompts/checkpoint` returning the model. No imports beyond `APIRouter`, `BaseModel`.
- **PATTERN**: `backend/app/api/health.py:15,34-35` (router + GET + response_model).
- **IMPORTS**: `from fastapi import APIRouter`, `from pydantic import BaseModel`.
- **GOTCHA**: route path is `/prompts/checkpoint` WITHOUT the `/api/v1` prefix (prefix comes from `main.py`); keep the handler sync (no I/O — matches `list_attempts_endpoint` style, avoids needless async).
- **VALIDATE**: `cd backend && uv run ruff check app/api/prompts.py && uv run ruff format --check app/api/prompts.py`

### UPDATE backend/app/main.py

- **IMPLEMENT**: ADD `from app.api.prompts import router as prompts_router` (alpha position after practice import) + `app.include_router(prompts_router, prefix="/api/v1")` after the practice line.
- **PATTERN**: `backend/app/main.py:18,62` (practice router lines).
- **IMPORTS**: `from app.api.prompts import router as prompts_router`.
- **GOTCHA**: two health routers exist (`health_router` + `health_liveness_router`) — do not touch either; bare `/health` liveness must keep its distinct body.
- **VALIDATE**: `cd backend && uv run python -c "from app.main import create_app; paths=[r.path for r in create_app().routes]; assert '/api/v1/prompts/checkpoint' in paths, paths; print('route ok')"`

### CREATE backend/tests/test_prompts_api.py

- **IMPLEMENT**: 4 tests over `TestClient(create_app())`: (1) `GET /api/v1/prompts/checkpoint` → 200 + body `{"prompt": CHECKPOINT_PROMPT}` non-empty; (2) static: two GETs byte-identical AND passes with `MODEL_API_KEY` unset (proves no-key serving); (3) OpenAPI contains the path with GET; (4) prompt contains all 4 content markers (`Work performed`, `Problems encountered`, `Decisions and reasoning`, `Accomplishments and skills demonstrated`). Import `CHECKPOINT_PROMPT` from the router module (single source — never retype the text).
- **PATTERN**: `backend/tests/test_query_api.py:43-58` (settings isolation fixture); `test_health.py` for plain TestClient GET shape.
- **IMPORTS**: `fastapi.testclient.TestClient`, `app.main.create_app`, `app.api.prompts.CHECKPOINT_PROMPT`.
- **GOTCHA**: `create_app()` lifespan runs `init_db` — point `DATABASE_PATH` at `tmp_path` via monkeypatched settings (MIRROR `test_query_api.py` `_isolated_settings`); never touch the real `./data/` DB.
- **VALIDATE**: `cd backend && uv run pytest tests/test_prompts_api.py -q`

### UPDATE frontend/src/api/types.ts

- **IMPLEMENT**: ADD `export interface CheckpointPromptResponse { prompt: string }` after the `PracticeAttempt` block (end of file). Field name mirrors backend Pydantic JSON exactly.
- **PATTERN**: `frontend/src/api/types.ts:259-262` (`PracticeAnswerResponse` interface shape).
- **IMPORTS**: none.
- **GOTCHA**: no other type changes — `Citation`, `ChunkDetail`, `GroundingLabel` already carry everything the shared components need.
- **VALIDATE**: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`

### CREATE frontend/src/api/prompts.ts

- **IMPLEMENT**: `FALLBACK_CHECKPOINT_PROMPT: string` const with text BYTE-IDENTICAL to backend `CHECKPOINT_PROMPT` (copy from §NOTES, not from memory); `getCheckpointPrompt(): Promise<CheckpointPromptResponse>` via `apiGet('/api/v1/prompts/checkpoint')`. Docstring notes the fallback contract (PRD §10: frontend hardcodes as fallback).
- **PATTERN**: `frontend/src/api/query.ts:12-19`.
- **IMPORTS**: `import { apiGet } from './client'`, `import type { CheckpointPromptResponse } from './types'`.
- **GOTCHA**: keep the fallback string formatting identical (same `\n` positions) — the modal test asserts marker substrings, and reviewers diff the two files. The template literal MUST start immediately after the opening backtick with `Summarize...` and end with `...raw note.` immediately before the closing backtick (no leading/trailing newline inside the literal), and MUST contain no `${` or backslash escapes — L4-0 extracts the literal verbatim and byte-compares it against the backend const.
- **VALIDATE**: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`

### CREATE frontend/src/api/prompts.test.ts

- **IMPLEMENT**: 2 tests with stubbed fetch: (1) `getCheckpointPrompt()` calls `http://localhost:8000/api/v1/prompts/checkpoint` and returns `{prompt}` verbatim; (2) `FALLBACK_CHECKPOINT_PROMPT` contains all 4 content markers. MIRROR the `mockFetchSequence` shape from `ChatView.test.tsx:20-32` (minimal inline version; `apiGet` path only).
- **PATTERN**: `frontend/src/api/query.test.ts` (client-function URL/shape test); `ChatView.test.tsx:20-32` (fetch stub).
- **IMPORTS**: `vitest`, `../api/prompts` funcs.
- **GOTCHA**: `vi.unstubAllGlobals()` in `afterEach` (MIRROR `ChatView.test.tsx:34-39`) so stubs never leak across files.
- **VALIDATE**: `cd frontend && npm test -- --run src/api/prompts.test.ts`

### CREATE frontend/src/components/GroundingBadge.tsx

- **IMPLEMENT**: `function GroundingBadge({ grounding }: { grounding: GroundingLabel })` rendering `<p aria-label="Grounding" className={inline-block rounded border px-2 py-0.5 text-xs + GROUNDING_STYLES[grounding]}>{grounding}</p>`; MOVE `GROUNDING_STYLES` here from FeedbackCard (this file becomes the single owner). No other props, no logic.
- **PATTERN**: `frontend/src/components/FeedbackCard.tsx:8-12,35-37` (exact classes + aria-label — copy verbatim).
- **IMPORTS**: `import type { GroundingLabel } from '../api/types'`.
- **GOTCHA**: class string must stay byte-identical to FeedbackCard's current badge so the later FeedbackCard refactor is zero-visual-change (snapshot-free codebase, but the human L4-3 walkthrough compares by eye).
- **VALIDATE**: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`

### CREATE frontend/src/components/GroundingBadge.test.tsx

- **IMPLEMENT**: 4 tests: `it.each<GroundingLabel>(['from your notes', 'general explanation', 'both'])` renders label verbatim under `getByLabelText('Grounding')` (3) + 1 test asserting the three render with pairwise-distinct border classes (visibility requirement, not just text).
- **PATTERN**: `frontend/src/components/FeedbackCard.test.tsx:34-40`.
- **IMPORTS**: `vitest`, `@testing-library/react`, `../api/types`, `./GroundingBadge`.
- **GOTCHA**: `cleanup()` in `afterEach` (MIRROR FeedbackCard.test).
- **VALIDATE**: `cd frontend && npm test -- --run src/components/GroundingBadge.test.tsx`

### REFACTOR frontend/src/components/FeedbackCard.tsx

- **IMPLEMENT**: REMOVE local `GROUNDING_STYLES`; import `GroundingBadge`; replace the badge `<p>` with `<GroundingBadge grounding={grounding} />`. Nothing else changes.
- **PATTERN**: `frontend/src/components/FeedbackCard.tsx:8-12,35-37` (delete the const, keep the call site position).
- **IMPORTS**: ADD `import GroundingBadge from './GroundingBadge'`; `GroundingLabel` type import stays.
- **GOTCHA**: existing `FeedbackCard.test.tsx` must pass UNCHANGED (same aria-label, same text, same classes) — if it fails, the refactor drifted.
- **VALIDATE**: `cd frontend && npm test -- --run src/components/FeedbackCard.test.tsx src/components/GroundingBadge.test.tsx`

### CREATE frontend/src/components/CitationPanel.tsx

- **IMPLEMENT**: `function CitationPanel({ chunk, onClose }: { chunk: ChunkDetail; onClose: () => void })` rendering: header line `Chunk {id} · artifact {artifact_id} · span {s}–{e}` + `Close citation` button; `Conversation source` badge line (`from a ThoughtBridge conversation`) IFF `chunk.source_type === 'tb_conversation'`; body `<p>{chunk.text}</p>`. Verbatim classes/aria-labels from ChatView's panel.
- **PATTERN**: `frontend/src/views/ChatView.tsx:113-136` (exact markup source); `WorkView.tsx:285-303` (second consumer — same props cover it).
- **IMPORTS**: `import type { ChunkDetail } from '../api/types'`.
- **GOTCHA**: the `–` in the span line is an EN DASH (U+2013) in both views — preserve it exactly or the human eye-test sees a diff; keep the outer `rounded border px-3 py-2` div so both call sites keep their layout.
- **VALIDATE**: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`

### CREATE frontend/src/components/CitationPanel.test.tsx

- **IMPLEMENT**: 3 tests: (1) renders header meta + full text + Close button; (2) `tb_conversation` chunk shows `Conversation source` badge, `note` chunk does not; (3) Close button calls `onClose`. Minimal `ChunkDetail` factory inline.
- **PATTERN**: `frontend/src/components/FeedbackCard.test.tsx` (render + query structure).
- **IMPORTS**: `vitest`, `@testing-library/react` (`render`, `screen`, `fireEvent`, `cleanup`), `../api/types`, `./CitationPanel`.
- **GOTCHA**: assert badge ABSENCE with `queryByLabelText` (MIRROR `ChatView.test.tsx:140`), never `getBy*` in a try/catch.
- **VALIDATE**: `cd frontend && npm test -- --run src/components/CitationPanel.test.tsx`

### REFACTOR frontend/src/views/ChatView.tsx

- **IMPLEMENT**: (a) REPLACE `groundingLabel()` free function with a `toGroundingLabel(modeUsed, citations): GroundingLabel` mapping evidence→`from your notes`, teaching+0 cites→`general explanation`, teaching+N cites→`both`, and render `<GroundingBadge grounding={...}/>` where the italic `<p>` was; (b) REPLACE the inline citation panel (lines 113-136) with `<CitationPanel chunk={activeCitation} onClose={() => setActiveCitation(null)} />`. Chips + `openCitation` + disclosure line untouched.
- **PATTERN**: `GroundingBadge` / `CitationPanel` (new shared); mapping table from `backend/app/core/grounding.py:486` vocabulary.
- **IMPORTS**: ADD `import GroundingBadge from '../components/GroundingBadge'`, `import CitationPanel from '../components/CitationPanel'`; `ModeUsed` type import stays.
- **GOTCHA**: DELIBERATE contract change — blended teaching label becomes `both` (was `general explanation + your notes`); the ChatView.test update task below updates that ONE test expectation with this rationale. No other ChatView behavior changes.
- **VALIDATE**: `cd frontend && npm test -- --run src/views/ChatView.test.tsx`

### REFACTOR frontend/src/views/WorkView.tsx

- **IMPLEMENT**: REPLACE the inline citation panel (lines 285-303) with `<CitationPanel chunk={activeCitation} onClose={() => setActiveCitation(null)} />`. This ADDS the conversation badge WorkView lacked. Nothing else changes.
- **PATTERN**: `frontend/src/components/CitationPanel.tsx` (new shared).
- **IMPORTS**: ADD `import CitationPanel from '../components/CitationPanel'`; `ChunkDetail` type import stays (state type).
- **GOTCHA**: WorkView's panel previously had NO conversation badge — after this task `WorkView.test.tsx` gains a badge test (see the additive view-test task below); do not "preserve" the old badge-less output.
- **VALIDATE**: `cd frontend && npm test -- --run src/views/WorkView.test.tsx`

### UPDATE frontend/src/views/LearnView.tsx

- **IMPLEMENT**: (a) EXTEND `ThreadEntry` to `{question, answer, citations: Citation[], modeUsed: ModeUsed}`; (b) in `ask()`, store `response.citations` + `response.mode_used` on the pushed entry; (c) per-thread render: `<GroundingBadge grounding={toGroundingLabel(t.modeUsed, t.citations)}/>` + citation chips (MIRROR ChatView chips: `Citation ${chunk_id}` aria-labels) + shared `<CitationPanel>` via new `activeCitation` state + `openCitation` (MIRROR `WorkView.tsx:107-114` using `getChunk`); (d) ADD the same `toGroundingLabel` mapping as ChatView (small local copy — 3 lines; a shared util is overkill for two call sites, but keep the bodies identical).
- **PATTERN**: chips from `ChatView.tsx:90-107`; panel from `CitationPanel`; fetch from `WorkView.tsx:107-114`.
- **IMPORTS**: ADD `getChunk` to the `../api/query` import, `GroundingBadge`, `CitationPanel`, types `Citation`, `ChunkDetail`, `ModeUsed`.
- **GOTCHA**: `postQuery` in teaching mode may return zero citations — badge then reads `general explanation` and no chips render (valid state, covered by a test); thread entries created before this change don't exist (threads are in-memory state, no migration).
- **VALIDATE**: `cd frontend && npm test -- --run src/views/LearnView.test.tsx`

### CREATE frontend/src/components/CheckpointPromptModal.tsx

- **IMPLEMENT**: `function CheckpointPromptModal({ onClose }: { onClose: () => void })`: on mount, `getCheckpointPrompt()` → show `prompt` in a readonly `<textarea aria-label="Checkpoint prompt">`; on fetch error show `FALLBACK_CHECKPOINT_PROMPT` + note `Showing built-in copy (couldn't reach the server).`; `Copy prompt` button: try `navigator.clipboard.writeText(text)` (feature-detect `navigator.clipboard`), catch/absence → hidden-textarea + `document.execCommand('copy')` fallback; success shows `Copied ✓` (revert on next open), failure shows `Copy failed — select and copy manually.`; `Close` button calls `onClose`. Root `role="dialog" aria-label="Checkpoint prompt"`.
- **PATTERN**: error/dismiss/disclosure microcopy style from `ChatView.tsx:63-70`; api import from `../api/prompts`.
- **IMPORTS**: `useEffect`, `useState` from react; `getCheckpointPrompt`, `FALLBACK_CHECKPOINT_PROMPT` from `../api/prompts`.
- **GOTCHA**: clipboard MUST be attempted only inside the click handler (user-gesture requirement) — never on mount; jsdom has no `navigator.clipboard` — tests stub it explicitly (see the modal test task below) and must also cover the execCommand path via a textarea-select spy.
- **VALIDATE**: `cd frontend && npm test -- --run src/components/CheckpointPromptModal.test.tsx`

### UPDATE frontend/src/App.tsx

- **IMPLEMENT**: ADD `checkpointOpen` state; header gets `<button type="button" aria-label="Checkpoint prompt">Checkpoint prompt</button>` next to the nav (same `rounded border px-3 py-1 text-sm` classes); `{checkpointOpen && <CheckpointPromptModal onClose={() => setCheckpointOpen(false)} />}` under `<main>`. Button lives OUTSIDE the view switch so it is one click away on every view.
- **PATTERN**: `frontend/src/App.tsx:28-42` (nav button classes); modal-conditional pattern `{x && <Y/>}` used across views.
- **IMPORTS**: ADD `import CheckpointPromptModal from './components/CheckpointPromptModal'`.
- **GOTCHA**: do NOT add a nav `VIEWS` entry (the modal is an overlay, not a view — adding a view id breaks the `ViewId` union + `active.blurb` logic); keep the button out of `<nav aria-label="Primary">` (screen-reader nav stays the 6 views).
- **VALIDATE**: `cd frontend && npm test -- --run src/App.test.tsx && npx tsc --noEmit -p tsconfig.app.json`

### CREATE frontend/src/App.test.tsx

- **IMPLEMENT**: 3 tests rendering `<App />` with queue-mocked fetch (default view is Chat, which fetches nothing on mount, so the queue needs only the modal's call): (1) `getByLabelText('Checkpoint prompt')` renders AND `within(getByRole('navigation', { name: 'Primary' })).queryByLabelText('Checkpoint prompt')` is null (button outside the view nav); (2) clicking the button (fetch stub `{prompt: 'PROMPT-TEXT'}`) shows `findByRole('dialog')` containing `PROMPT-TEXT`; (3) clicking `Close` dismisses the dialog (`queryByRole('dialog')` null). Cleanup + `vi.unstubAllGlobals()` in `afterEach`.
- **PATTERN**: `frontend/src/views/ChatView.test.tsx:20-39` (queue mock + afterEach hygiene); `within` from `@testing-library/react` for the nav-scoped absence assertion.
- **IMPORTS**: `vitest`, `@testing-library/react` (`render`, `screen`, `fireEvent`, `cleanup`, `within`), `./App`.
- **GOTCHA**: test 1's absence leg MUST use `queryByLabelText` inside `within(nav)` (MIRROR `ChatView.test.tsx:140`); modal copy is not exercised here (no clipboard stub needed) — copy paths belong to the modal test file.
- **VALIDATE**: `cd frontend && npm test -- --run src/App.test.tsx`

### UPDATE frontend/src/views/ChatView.test.tsx (1 deliberate expectation change)

- **IMPLEMENT**: in test `badges cited teaching answers as blended` (line 126-132), change expected text `general explanation + your notes` → `both` and rename the test to `badges cited teaching answers as both`. ADD a comment citing this plan (F-11 unification onto the PRD F-7 vocabulary). No other test in the file changes.
- **PATTERN**: existing test body stays identical except the string + title.
- **IMPORTS**: none.
- **GOTCHA**: this is the ONLY existing test modified in the whole deliverable — if any other existing test needs editing to pass, the implementation drifted; stop and re-examine instead of "fixing" more tests.
- **VALIDATE**: `cd frontend && npm test -- --run src/views/ChatView.test.tsx`

### CREATE frontend/src/components/CheckpointPromptModal.test.tsx

- **IMPLEMENT**: 5 tests with queue-mocked fetch: (1) renders fetched prompt text in the readonly textarea; (2) Copy with stubbed `navigator.clipboard.writeText` (define via `Object.defineProperty(navigator, 'clipboard', ...)`) → asserts called with prompt text + `Copied ✓` appears; (3) fetch rejects → fallback text + server-unreachable note shown, Copy still works (clipboard stubbed as in test 2); (4) Close button calls `onClose`; (5) execCommand fallback: `navigator.clipboard` removed (defineProperty to `undefined`) + `document.execCommand` mocked to return true → Copy succeeds + `Copied ✓` appears. Cleanup + unstub globals + restore clipboard/execCommand in `afterEach`.
- **PATTERN**: `ChatView.test.tsx:20-39` (queue mock + afterEach hygiene).
- **IMPORTS**: `vitest`, `@testing-library/react`, `../api/prompts` fallback const (`FALLBACK_CHECKPOINT_PROMPT`), `./CheckpointPromptModal`.
- **GOTCHA**: `navigator.clipboard` is read-only in jsdom — MUST use `Object.defineProperty` to stub/remove and MUST restore the original descriptor in `afterEach`; never assign directly. Test 5 pins success (execCommand → true); the `Copy failed` branch is unreachable in jsdom without deeper DOM-selection mocking and is covered only by the human L4-2 walkthrough — do not invent a fake for it.
- **VALIDATE**: `cd frontend && npm test -- --run src/components/CheckpointPromptModal.test.tsx`

### UPDATE frontend/src/views/LearnView.test.tsx + WorkView.test.tsx (additive only)

- **IMPLEMENT**: LearnView +2 tests: (a) interrupt answer renders a `Grounding` badge with `general explanation` for the uncited teaching stub; (b) cited interrupt answer renders `Citation ${id}` chip and clicking it opens the panel with full chunk text (extend the fetch queue with a chunk payload; MIRROR `ChatView.test.tsx:78-93`). WorkView +1 test: citation panel for a `tb_conversation` chunk shows the `Conversation source` badge (MIRROR `ChatView.test.tsx:160-182`, adapted to WorkView's extract→cite flow or a direct `FactCard` evidence click — whichever the existing WorkView tests already drive; read the file first).
- **PATTERN**: `ChatView.test.tsx` chip/panel/badge tests (verbatim structure, new view wiring).
- **IMPORTS**: none new (existing test imports cover render/fireEvent/screen; reuse local factories).
- **GOTCHA**: ADDITIVE ONLY — no existing LearnView/WorkView test may be modified; LearnView's `__stream` mock helper stays untouched (ask-path tests bypass streaming).
- **VALIDATE**: `cd frontend && npm test -- --run src/views/LearnView.test.tsx src/views/WorkView.test.tsx`

---

## TESTING STRATEGY

Deterministic behavior gets unit tests; no LLM paths exist in this deliverable, so no contract/stubbed-model tests are needed. Backend: one contract file proving the static endpoint's shape, stability, registration, and content markers (real TestClient, no network, no model). Frontend: component tests pin the shared badge/panel/modal rendering and copy behavior with stubbed fetch/clipboard; view tests prove each surface composes the shared pieces (badge present, chips open the panel, conversation badge appears).

### Unit Tests

- Backend `tests/test_prompts_api.py` (4 tests): shape, static/no-key, OpenAPI registration, 4 content markers.
- Frontend `api/prompts.test.ts` (2): URL/shape passthrough, fallback markers.
- Frontend `GroundingBadge.test.tsx` (4): 3 verbatim labels + distinct border classes.
- Frontend `CitationPanel.test.tsx` (3): meta+text render, conversation badge iff `tb_conversation`, Close callback.
- Frontend `CheckpointPromptModal.test.tsx` (5): fetch render, clipboard copy + `Copied ✓`, fetch-failure fallback, Close callback, execCommand fallback success.
- Frontend `App.test.tsx` (3): header button renders outside the primary nav, opens the dialog, Close dismisses.
- Fixtures: minimal inline factories (`ChunkDetail`, `QueryResponse`); MIRROR `ChatView.test.tsx:20-32` queue-mock and `FeedbackCard.test.tsx` render/assert structure. Never touch the real DB or network.

### Integration Tests

- Full backend suite (`pytest -q`) proves zero regressions in existing routers (main.py edit is the only shared-file backend touch).
- Full frontend suite (`npm test -- --run`) + `npm run build` (tsc -b + vite) proves the refactors compose and the production bundle builds.
- `tsc --noEmit` after each frontend task gives per-task type safety (vitest does not typecheck).

### Edge Cases

- Fetch failure on the modal (server down): fallback text + unreachable note, copy still works (modal test 3).
- `navigator.clipboard` undefined (non-secure context / jsdom): execCommand fallback path, never a throw (modal test 5 pins success; the `Copy failed` branch is human-walkthrough-only per the modal test task).
- Uncited teaching answer (LearnView thread, ChatView): badge reads `general explanation`, zero chips, no panel trigger (LearnView test a).
- `note` chunk in panel: NO conversation badge (CitationPanel test 2 negative leg).
- Double-GET stability + unset `MODEL_API_KEY`: identical bodies (backend test 2).
- FactCard status/confidence rendering: already covered by existing `FactCard.test.tsx` — no new tests, verify green.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

Every command or block MUST state its exact pass signal on an `Expected:` line (exit code plus the key output, count, or observation that proves success — e.g. `Expected: exit 0, "11 passed"`, `Expected: exit 0, docs:200`). A check whose passing output is not specified cannot confirm anything; do not write checks you cannot describe passing.

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
cd frontend && npm run lint
```
Expected: exit 0, no errors or warnings.

### Level 2: Unit Tests

```bash
cd backend && uv run pytest tests/test_prompts_api.py -q
```
Expected: exit 0, `4 passed`.

```bash
cd frontend && npm test -- --run src/App.test.tsx src/api/prompts.test.ts src/components/GroundingBadge.test.tsx src/components/CitationPanel.test.tsx src/components/CheckpointPromptModal.test.tsx
```
Expected: exit 0, `17 passed` (3 + 2 + 4 + 3 + 5), 0 failed.

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

**L4-0 [agent] Prompt-text byte-identity check (backend const vs. frontend fallback):**

1. Write `/tmp/prompts_diff.py` (NOT committed): imports `CHECKPOINT_PROMPT` from `app.api.prompts`; extracts `FALLBACK_CHECKPOINT_PROMPT` from `../frontend/src/api/prompts.ts` with `re.search` + `re.S` for the template literal (const name, up to the first `=`, optional whitespace, opening backtick, lazy capture, closing backtick + `;`); asserts the literal contains no `${` or backslash escapes; byte-compares the two strings and prints a unified diff + exits nonzero on mismatch.
2. `cd backend && uv run python /tmp/prompts_diff.py`; then delete `/tmp/prompts_diff.py`.
3. Expected: exit 0, prints `identical: N chars` (N = the exact prompt length), no diff output — proves the fallback is byte-identical, not just marker-equal.

**L4-1 [agent] Static endpoint live check (no key, scratch DB):**

1. Write `/tmp/prompts_live_smoke.py` (NOT committed): TestClients `create_app()` as context manager with `DATABASE_PATH=/tmp/prompts_smoke.db` and `MODEL_API_KEY` unset; `GET /api/v1/prompts/checkpoint` twice; assert 200, identical bodies, body has exactly key `prompt`, prompt contains all 4 markers.
2. `cd backend && DATABASE_PATH=/tmp/prompts_smoke.db uv run python /tmp/prompts_live_smoke.py`; then delete `/tmp/prompts_live_smoke.py` + `/tmp/prompts_smoke.db*`.
3. Expected: exit 0, all asserts pass (proves keyless static serving through the real app factory), scratch files deleted after.

**L4-2 [human] Deployed UI walkthrough (after redeploy per AGENTS.md):**

1. Open the deployed app URL (from `backend/README.md` Live URL line); hard-refresh; confirm the bundle is fresh (header shows a `Checkpoint prompt` button on every tab).
2. Click `Checkpoint prompt` — expected: modal with the 4-section prompt text; click Copy — expected: `Copied ✓` (or manual-copy hint on failure); Close dismisses.
3. Chat tab: ask a personal question (`what did I work on?`) — expected: `from your notes` badge; ask a conceptual question — expected: `general explanation` or `both` badge; citation chip opens the chunk panel; conversation-sourced chunks show the conversation badge.
4. Learn tab: teach a concept, ask about the current step — expected: thread shows a grounding badge; cited threads show chips opening the chunk panel.
5. Work tab: run Extract, open an evidence chunk — expected: shared panel with header meta; conversation-sourced chunks show the conversation badge; facts still show kind · status · confidence.
6. Practice/Interview tabs: submit one answer — expected: FeedbackCard badge unchanged (`from your notes` / `general explanation` / `both` with green/neutral/blue borders).

### Level 5: Additional Validation (Optional)

Playwright MCP browser E2E against the DEPLOYED URL (never localhost — sandboxed sessions deny local sockets):

1. Redeploy first (per AGENTS.md this deliverable has browser-verifiable changes): rebuild frontend same-origin (`VITE_API_URL=`), `cd backend && uv run modal deploy modal_app.py`; verify freshness FIRST (new bundle hash + `GET /api/v1/prompts/checkpoint` returns the 4-section text) — an outdated deployment never validates new code.
2. Script: assert header `Checkpoint prompt` button visible → click → assert dialog with prompt text → click Copy → assert `Copied ✓` → Close → Chat tab: send `what did I work on?` → assert `Grounding` badge reads `from your notes` → click a citation chip → assert panel + Close; Work tab: assert evidence flow still renders.
3. Expected: all assertions pass; console shows no errors (`browser_console_messages` level error empty).
4. If deployment is impossible (missing credentials/blocked deploy), mark browser E2E `NOT_PERFORMED` with reason and L4-2 `UNVERIFIED` pending deployment with the manual steps above — never a failure, never a pass.

---

## MANUAL VERIFICATION CHECKLIST

- [ ] [agent] Backend ladder green: run Level 1–3 backend commands in order; expected: exact Expected outputs above, zero failures.
- [ ] [agent] Frontend ladder green: run Level 1 (oxlint) + Level 2–3 frontend commands; expected: exact Expected outputs above (`17 passed`, full suite green, build succeeds), zero failures.
- [ ] [agent] Prompt byte-identity: run L4-0; expected: exit 0, prints `identical: N chars`, no diff output, script deleted after.
- [ ] [agent] Static live check: run L4-1; expected: exit 0, identical bodies, exactly key `prompt`, 4 markers present, scratch files deleted after.
- [ ] [human] Deployed UI walkthrough: perform L4-2 steps 1–6 on the fresh deployment; expected: per-step observations above (modal + copy, badges in Chat/Learn/Work/Practice, conversation badges, FactCard status lines).
- [ ] [agent] Single-test-change proof: run `cd frontend && git diff --stat -- '*.test.*'` (or `git status` if uncommitted); expected: exactly one MODIFIED existing test file (`ChatView.test.tsx`, one string + title) and all other test files NEW — plus `cd backend && git status --short` shows no `tests/` modifications, only the new `test_prompts_api.py`.
- [ ] [agent] No leftover scratch: `ls /tmp/prompts_smoke* /tmp/prompts_live_smoke.py /tmp/prompts_diff.py` shows no files; `git status --short` shows only intended new/modified files (no `.env`, no `conversation-log/`, no scratch scripts in repo, no lockfile churn).

## ROLLBACK CONSIDERATIONS

- Code rollback: `git revert` the single deliverable commit — all changes are additive (one router, one client, three components, additive view JSX) except the ChatView grounding-label mapping + its one test expectation, which revert atomically with the commit.
- Data rollback: none needed — no schema, migration, or stored-data changes; the endpoint reads no state.
- Deployed volume DB: untouched (no boot path changes beyond router registration); redeploying the prior bundle restores the old UI with zero data consequences.

## ACCEPTANCE CRITERIA

- [ ] `GET /api/v1/prompts/checkpoint` returns 200 `{"prompt": "<4-section text>"}` with no key/DB/LLM involvement (L2 `test_prompts_api.py` 4 tests + L4-1 agent check; expected: `4 passed` + exit 0)
- [ ] Frontend client fetches the endpoint and carries a byte-identical fallback (L2 `prompts.test.ts` markers; expected: `2 passed`; byte-identity proven by L4-0 agent diff; expected: exit 0, `identical: N chars`)
- [ ] Header button renders outside the primary nav and opens/closes the dialog on every view (L2 `App.test.tsx`; expected: `3 passed`); modal covers fetch render, copy confirmation, fetch-failure fallback, execCommand fallback, close (L2 `CheckpointPromptModal.test.tsx`; expected: `5 passed`; plus L4-2 human steps 1–2 observed)
- [ ] One shared `GroundingBadge` renders the 3 canonical labels with distinct styles; FeedbackCard uses it with zero visual change (L2 `GroundingBadge.test.tsx` `4 passed` + unchanged `FeedbackCard.test.tsx` green)
- [ ] One shared `CitationPanel` renders chunk meta + text + conversation badge + close (L2 `CitationPanel.test.tsx`; expected: `3 passed`)
- [ ] ChatView uses both shared components with the unified `both` blended label (L3 `ChatView.test.tsx` green incl. the single updated expectation; expected: pass)
- [ ] WorkView panel is the shared panel incl. the conversation badge (L3 `WorkView.test.tsx` green incl. the new badge test; expected: pass)
- [ ] LearnView interrupt threads show grounding badge + citation chips opening the shared panel (L3 `LearnView.test.tsx` green incl. 2 new tests; expected: pass)
- [ ] FactCard kind · status · confidence still visible (L3 existing `FactCard.test.tsx` green unchanged; expected: pass)
- [ ] Full backend + frontend suites green with zero regressions (L3 `pytest -q`, `npm test`, `npm run build`; expected: exit 0 throughout)
- [ ] Lint/type gates pass (L1 ruff + mypy + oxlint; expected: exit 0 throughout)
- [ ] No new dependencies added (`git diff backend/pyproject.toml frontend/package.json` empty of new deps; `uv.lock`/`package-lock.json` unchanged — checklist item, verified by `git status`)
- [ ] Code follows project conventions (thin router, shared rendering, by-name test seams where applicable, exact-JSON types — reviewer judgment at `/review-plan` + execution review)

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

### Verbatim prompt text (single source — copy, never retype)

Backend `CHECKPOINT_PROMPT` and frontend `FALLBACK_CHECKPOINT_PROMPT` must be byte-identical to this text (same `\n` positions). Python form uses implicit concat; TypeScript form uses a template literal — both must render exactly these lines:

```
Summarize this coding session for my work journal. Be specific and concrete.

1. Work performed — what was built, changed, or fixed.
2. Problems encountered — each problem, how it was resolved, or what is still open.
3. Decisions and reasoning — choices made and why, including approaches considered and rejected and the reason each was rejected.
4. Accomplishments and skills demonstrated — what got done and what it shows (for example debugging, design judgment, or failure-mode analysis).

I will paste your response into ThoughtBridge as a raw note.
```

Note: the `—` separators are EM DASHES (U+2014). The 4 content markers asserted in tests are the bolded labels without numbers: `Work performed`, `Problems encountered`, `Decisions and reasoning`, `Accomplishments and skills demonstrated`.

### Design decisions (with rationale)

1. **Prompt constant lives in `api/prompts.py`, not `core/`**: grounding contracts in `core/grounding.py` are LLM system prompts; the checkpoint text is static user-facing copy with no prompt-engineering role. A module constant next to its only consumer is the simplest rung that holds; tests import it as the single source.
2. **Response shape `{"prompt": str}`**: PRD §10 fixes JSON-everywhere but no key name; `prompt` mirrors the endpoint noun and the frontend type name. Flagged as an assumption for review.
3. **Global header button, not a Work-view button**: F-9 says "behind a UI button" without placement; the checkpoint summarizes any session (learn/practice/qa alike), and `App.tsx` placement makes it one click away on every view. Modal (not inline page) matches the PRD §6 dir sketch (`checkpoint-prompt modal`).
4. **Blended chat label unified to `both`**: ChatView's `general explanation + your notes` matched neither the PRD F-7 vocabulary nor any backend value; unifying onto the canonical 3 labels is the point of the visibility pass. One test expectation changes, explicitly flagged — the only existing test touched.
5. **`toGroundingLabel` duplicated in ChatView + LearnView (3 lines)**: a third shared util for a pure 3-branch map is abstraction without payoff; the plan requires identical bodies instead. Revisit if a third call site appears.
6. **`AttemptHistory` grounding stays plain text**: list-density rows, not feedback display; badging every row would add noise without aiding the F-11 distinction. Unchanged by design.
7. **No conversation-browser view**: the build list asks for role labels on conversation-derived content, which the citation chips + panel badges deliver; a full `/conversations` UI is unrequested scope (the API client already exists for a future slice).
8. **FactCard untouched**: kind · status · confidence already render (lines 25-27) with chunk chips + reasoning links — the build-list requirement is satisfied; existing tests pin it.

### Trade-offs

- Dual-copy prompt text (backend + frontend fallback) can drift: guarded at two levels — identical marker assertions on both sides (backend test 4 + `prompts.test.ts` test 2) for unit speed, plus the L4-0 agent byte-diff as the authoritative identity proof at validation time.
- `document.execCommand('copy')` is deprecated but remains the only non-Clipboard-API fallback that works without permissions prompts; used strictly as a fallback, never primary.

### Confidence

8.5/10 for one-pass execution success: no DB, no LLM, no async, no new deps; the only judgment calls (prompt wording, badge mapping, modal placement) are fixed above with verbatim content. Main residual risks: (1) the `{"prompt"}` shape assumption if a hidden consumer expects another key (low — no consumer exists yet); (2) LearnView's large component file makes the thread-render edit fiddly (mitigated by exact line anchors + additive tests).

---

## Revision History

### Cycle 1

Findings addressed (all 3 from the first independent review, `.agents/plans/reviews/checkpoint-prompt-provenance-visibility-plan-review.md`):

1. "The byte-identical fallback criterion is checked only by marker substrings; add an agent check comparing the full backend and frontend prompt texts, or reword the criterion" — addressed via the agent-check option.
2. "The App.tsx header button has no automated test; add an App-level test ... and update test counts accordingly" — addressed.
3. "The modal test task describes an execCommand-fallback assertion without assigning it to one of the 4 listed tests" — addressed via the 5th-test option.

What changed:

- Added L4-0 agent byte-identity step (scratch `/tmp/prompts_diff.py` extracting the TS template literal and byte-comparing against the backend const, deleted afterward) with an exact `Expected:` line; added a matching manual-checklist item; extended the `prompts.ts` GOTCHA with template-literal exactness rules (no leading/trailing newline, no `${`/escapes) so the extraction is deterministic; acceptance criterion 2 now cites L4-0 as the identity proof; scratch-cleanup item covers the new script; trade-offs note updated to the two-level guard.
- Added a `CREATE frontend/src/App.test.tsx` task (3 tests: button outside primary nav, opens dialog, Close dismisses) wired into the App.tsx task VALIDATE line; added the file to New Files, Unit Tests, and the L2 command; frontend new-test count updated 13 → 17 everywhere (Phase 4 paragraph, L2 `Expected:`, manual checklist, criteria).
- Rewrote the modal test task to 5 numbered tests with test 5 pinning the execCommand fallback (clipboard removed + execCommand mocked true → success); fixed the test file's import path to `../api/prompts`; recorded that the `Copy failed` branch is human-walkthrough-only in jsdom; updated New Files, Unit Tests, Edge Cases, L2 count, and acceptance criterion 3 to the 5-test shape.

Not done: nothing — all three corrections applied in full. No requirement was redefined; no item needs human judgment.

