# Execution Report: checkpoint-prompt-provenance-visibility

Plan: `.agents/plans/checkpoint-prompt-provenance-visibility.md`
Review: `.agents/plans/reviews/checkpoint-prompt-provenance-visibility-plan-review.md` (Overall: ✅ APPROVED)
Started: 2026-11-04

This report records every command run, every line of output, every validation result, and every deviation verbatim.

---

## Standing environment note

All `uv run` commands in this sandbox use `UV_CACHE_DIR=/tmp/uv-cache` (the default `~/.cache/uv` is outside the writable roots) plus `--no-sync` (deps already installed in `backend/.venv`; no dependency changes in this deliverable). Same standing equivalent as prior deliverables, not a plan deviation in what was tested.

## Task 1: CREATE backend/app/api/prompts.py

Created the static endpoint: `CHECKPOINT_PROMPT` const (verbatim §NOTES text, em dashes U+2014), `APIRouter(tags=["prompts"])`, `CheckpointPromptResponse {prompt: str}`, sync `GET /prompts/checkpoint`. Imports only `APIRouter`, `BaseModel`.

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync ruff check app/api/prompts.py && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync ruff format --check app/api/prompts.py
All checks passed!
1 file already formatted
```

Result: PASS.

## Task 2: UPDATE backend/app/main.py

Added the import (alpha position after practice) + `app.include_router(prompts_router, prefix="/api/v1")` after the practice line. Health routers untouched.

Plan VALIDATE as written:

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync python -c "from app.main import create_app; paths=[r.path for r in create_app().routes]; assert '/api/v1/prompts/checkpoint' in paths, paths; print('route ok')"
2026-11-04 12:31:44.957 Python[65710:15443077] 2026-11-04 12:31:44.957247 [W:onnxruntime:Default, telemetry_1ds.cc:600 operator()] Failed to persist telemetry device ID; using an in-memory identifier
Traceback (most recent call last):
  File "<string>", line 1, in <module>
AttributeError: '_IncludedRouter' object has no attribute 'path'
```

Same lazy-flattening behavior as the deletion deliverable (Deviation 1 there): `app.routes` holds `_IncludedRouter` objects. Equivalent procedure via the OpenAPI table (same assertion — the GET operation is live on the real app object):

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync python -c "... openapi()['paths'] ..." (asserts '/api/v1/prompts/checkpoint' present with exactly ['get'])
route ok: ['get']
```

Result: PASS via equivalent procedure (Deviation 1).

## Task 3: CREATE backend/tests/test_prompts_api.py

Created 4 tests over `TestClient(create_app())` with `_isolated_settings` (env cleared, `DATABASE_PATH`→tmp, `app.main.get_settings`→`Settings(_env_file=None)`): shape (`{"prompt": CHECKPOINT_PROMPT}`), static+keyless (two GETs byte-identical, key unset), OpenAPI registration, 4 F-9 content markers. Imports `CHECKPOINT_PROMPT` from the router (single source).

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync pytest tests/test_prompts_api.py -q
....                                                                     [100%]
4 passed in 0.81s
```

Result: PASS — `Expected: exit 0, "4 passed"`.

## Task 4: UPDATE frontend/src/api/types.ts

Added `export interface CheckpointPromptResponse { prompt: string }` after `PracticeAttempt`. No other type changes.

```
$ cd frontend && npx tsc --noEmit -p tsconfig.app.json && echo TSC_OK
TSC_OK
```

Result: PASS.

## Task 5: CREATE frontend/src/api/prompts.ts

Created `FALLBACK_CHECKPOINT_PROMPT` (template literal, byte-identical text, starts/ends immediately at the backticks, no `${`/escapes) + `getCheckpointPrompt()` via `apiGet('/api/v1/prompts/checkpoint')`.

```
$ cd frontend && npx tsc --noEmit -p tsconfig.app.json && echo TSC_OK
TSC_OK
```

Result: PASS.

## Task 6: CREATE frontend/src/api/prompts.test.ts

Created 2 tests (endpoint URL + verbatim return; fallback 4 markers) with inline queue-mock + `vi.unstubAllGlobals()` in `afterEach`.

```
$ cd frontend && npm test -- --run src/api/prompts.test.ts
✓ src/api/prompts.test.ts (2 tests) 2ms
 Test Files  1 passed (1)
      Tests  2 passed (2)
```

Result: PASS.

## Task 7: CREATE frontend/src/components/GroundingBadge.tsx

Created the shared badge (moved `GROUNDING_STYLES` here as single owner; byte-identical classes + `aria-label="Grounding"`).

```
$ cd frontend && npx tsc --noEmit -p tsconfig.app.json && echo TSC_OK
TSC_OK
```

Result: PASS.

## Task 8: CREATE frontend/src/components/GroundingBadge.test.tsx

Created 4 tests (`it.each` verbatim labels + distinct border classes).

```
$ cd frontend && npm test -- --run src/components/GroundingBadge.test.tsx
✓ src/components/GroundingBadge.test.tsx (4 tests) 16ms
 Test Files  1 passed (1)
      Tests  4 passed (4)
```

Result: PASS.

## Task 9: REFACTOR frontend/src/components/FeedbackCard.tsx

Removed local `GROUNDING_STYLES`, render `<GroundingBadge grounding={grounding} />` at the same position. Nothing else changed.

```
$ cd frontend && npm test -- --run src/components/FeedbackCard.test.tsx src/components/GroundingBadge.test.tsx
✓ src/components/GroundingBadge.test.tsx (4 tests) 16ms
✓ src/components/FeedbackCard.test.tsx (4 tests) 27ms
 Test Files  2 passed (2)
      Tests  8 passed (8)
```

Result: PASS — existing `FeedbackCard.test.tsx` green unchanged (zero-visual-change refactor confirmed).

## Task 10: CREATE frontend/src/components/CitationPanel.tsx

Created the shared panel (header meta + `Close citation` + `Conversation source` badge iff `tb_conversation` + full text). Self-correction during the task: first draft split the span line across two JSX lines, which would render a space after the en dash — fixed to a single line before validating.

```
$ cd frontend && npx tsc --noEmit -p tsconfig.app.json && echo TSC_OK
TSC_OK
```

Result: PASS.

## Task 11: CREATE frontend/src/components/CitationPanel.test.tsx

Created 3 tests (meta+text render; badge iff `tb_conversation` with `queryByLabelText` negative leg; Close callback).

```
$ cd frontend && npm test -- --run src/components/CitationPanel.test.tsx
✓ src/components/CitationPanel.test.tsx (3 tests) 21ms
 Test Files  1 passed (1)
      Tests  3 passed (3)
```

Result: PASS.

## Task 12: REFACTOR frontend/src/views/ChatView.tsx

Replaced `groundingLabel()` with `toGroundingLabel(): GroundingLabel` (evidence→`from your notes`, teaching+0→`general explanation`, teaching+N→`both`); italic `<p>` → `<GroundingBadge>`; inline panel → `<CitationPanel>`. Chips + `openCitation` + disclosure untouched.

```
$ cd frontend && npm test -- --run src/views/ChatView.test.tsx
❯ src/views/ChatView.test.tsx (11 tests | 1 failed) 1137ms
     ✓ renders input and disclosure text with no mode select 17ms
     ✓ sends on submit and renders answer with citation chips 11ms
     ✓ passes the stored conversation_id on the second send 9ms
     ✓ opens the citation panel with full chunk text on chip click 9ms
     ✓ shows the error banner and keeps input content on 502 44ms
     ✓ badges evidence answers as from your notes 4ms
     ✓ badges uncited teaching answers as general explanation 3ms
     × badges cited teaching answers as blended 1011ms
     ✓ shows no conversation badge for note citations 10ms
     ✓ badges conversation citations on the chip 7ms
     ✓ badges the citation panel for conversation chunks 10ms
 Test Files  1 failed (1)
      Tests  1 failed | 10 passed (11)
```

Result: EXPECTED single failure — `badges cited teaching answers as blended` (line 131) asserts the old string; the plan's deliberate contract change fixes it in the ChatView.test task. All other 10 pass, proving the shared-component refactor is behavior-preserving.

## Task 13: REFACTOR frontend/src/views/WorkView.tsx

Replaced the inline panel with `<CitationPanel>` (adds the conversation badge). Nothing else changed.

```
$ cd frontend && npm test -- --run src/views/WorkView.test.tsx
 Test Files  1 passed (1)
      Tests  19 passed (19)
```

Result: PASS.

## Task 14: UPDATE frontend/src/views/LearnView.tsx

Extended `ThreadEntry` with `citations` + `modeUsed` (stored in `ask()`); added identical `toGroundingLabel`; per-thread badge + ChatView-mirrored chips (incl. conversation-source span) + shared `CitationPanel` via new `activeCitation` state + `openCitation`. Panel renders inside the lesson branch so it unmounts on Start over with the rest of the lesson UI.

```
$ cd frontend && npm test -- --run src/views/LearnView.test.tsx
 Test Files  1 passed (1)
      Tests  18 passed (18)
```

Result: PASS — all 18 pre-existing tests unaffected.

## Task 15: CREATE frontend/src/components/CheckpointPromptModal.tsx

Created the modal: fetch-on-mount → readonly textarea; fetch error → fallback + `Showing built-in copy (couldn't reach the server).`; Copy via feature-detected `navigator.clipboard.writeText` with hidden-textarea + `execCommand('copy')` fallback; `Copied ✓` / `Copy failed — select and copy manually.`; Close → `onClose`; root `role="dialog" aria-label="Checkpoint prompt"`. Clipboard attempted only in the click handler.

```
$ cd frontend && npx tsc --noEmit -p tsconfig.app.json && echo TSC_OK
TSC_OK
```

Result: PASS (full test validation in the modal test task).

## Task 16: UPDATE frontend/src/App.tsx

Added `checkpointOpen` state, header `Checkpoint prompt` button (outside `<nav>`, same button classes), and `{checkpointOpen && <CheckpointPromptModal .../>}` between header and main. No `VIEWS` entry added.

(Validation ran with the App.test task below.)

## Task 17: CREATE frontend/src/App.test.tsx

Created 3 tests (button outside primary nav via `within(nav)` absence leg; click opens dialog with fetched text; Close dismisses).

```
$ cd frontend && npm test -- --run src/App.test.tsx && npx tsc --noEmit -p tsconfig.app.json && echo TSC_OK
✓ src/App.test.tsx (3 tests) 81ms
 Test Files  1 passed (1)
      Tests  3 passed (3)
TSC_OK
```

Result: PASS — validates Tasks 15–17 together.

## Task 18: UPDATE frontend/src/views/ChatView.test.tsx (1 deliberate change)

Renamed `badges cited teaching answers as blended` → `as both`, expectation → `both`, with a plan-citing comment. No other line in the file touched.

```
$ cd frontend && npm test -- --run src/views/ChatView.test.tsx
 Test Files  1 passed (1)
      Tests  11 passed (11)
```

Result: PASS.

## Task 19: CREATE frontend/src/components/CheckpointPromptModal.test.tsx

Created 5 tests. Two self-corrections during the task, both test-only: (1) `getByLabelText('Checkpoint prompt')` matches both the dialog and the textarea (shared accessible name per plan spec) — first switched to `getByDisplayValue`, which then failed on the multi-line fallback literal (Testing Library whitespace normalization); (2) final form asserts exact equality via `(screen.getByRole('textbox') as HTMLTextAreaElement).value`, which is unambiguous and stronger. Clipboard/execCommand stubbed via `Object.defineProperty` with descriptor restore in `afterEach`.

```
$ cd frontend && npm test -- --run src/components/CheckpointPromptModal.test.tsx
✓ src/components/CheckpointPromptModal.test.tsx (5 tests) 88ms
 Test Files  1 passed (1)
      Tests  5 passed (5)
```

Result: PASS.

## Task 20: UPDATE LearnView.test.tsx + WorkView.test.tsx (additive only)

LearnView +2 (uncited badge `general explanation` + no chips; cited chip opens panel with full text + chunks URL assertion). WorkView +1 (conversation badge in panel). No existing test modified.

```
$ cd frontend && npm test -- --run src/views/LearnView.test.tsx src/views/WorkView.test.tsx
✓ src/views/WorkView.test.tsx (20 tests) 233ms
✓ src/views/LearnView.test.tsx (20 tests) 247ms
 Test Files  2 passed (2)
      Tests  40 passed (40)
```

Result: PASS.

## Validation L1: Syntax & Style

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync ruff check . && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync ruff format --check . && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync mypy app
All checks passed!
73 files already formatted
Success: no issues found in 39 source files
```

Expected: exit 0, `All checks passed!` + `73 files already formatted` + `Success: no issues found` — PASS.

```
$ cd frontend && npm run lint
> frontend@0.0.0 lint
> oxlint
Found 0 warnings and 0 errors.
Finished in 30ms on 45 files with 116 rules using 8 threads.
```

Expected: exit 0, no errors or warnings — PASS.

## Validation L2: Unit Tests

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync pytest tests/test_prompts_api.py -q
....
4 passed in 0.91s
```

Expected: exit 0, `4 passed` — PASS.

```
$ cd frontend && npm test -- --run src/App.test.tsx src/api/prompts.test.ts src/components/GroundingBadge.test.tsx src/components/CitationPanel.test.tsx src/components/CheckpointPromptModal.test.tsx
✓ src/api/prompts.test.ts (2 tests) 5ms
✓ src/components/GroundingBadge.test.tsx (4 tests) 18ms
✓ src/components/CitationPanel.test.tsx (3 tests) 27ms
✓ src/components/CheckpointPromptModal.test.tsx (5 tests) 95ms
✓ src/App.test.tsx (3 tests) 76ms
 Test Files  5 passed (5)
      Tests  17 passed (17)
```

Expected: exit 0, `17 passed` (3 + 2 + 4 + 3 + 5) — PASS.

## Validation L3: Integration Tests

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync pytest -q
........................................................................ [ 81%]
.................s...................................................... [ 94%]
...........................                                              [100%]
529 passed, 2 skipped in 12.48s
```

The 2 skips are pre-existing and unrelated (named via `-rs`):

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync pytest -q -rs
SKIPPED [1] tests/test_ingest_pipeline.py:300: needs network + ~90MB model
SKIPPED [1] tests/test_retrieval.py:358: needs network + ~90MB model
529 passed, 2 skipped in 12.36s
```

Expected: exit 0, full suite green, zero regressions — PASS.

```
$ cd frontend && npm test -- --run && npm run build
 Test Files  21 passed (21)
      Tests  150 passed (150)
dist/assets/index-CzWN9tDg.js   262.73 kB │ gzip: 77.80 kB
✓ built in 112ms
```

Expected: exit 0, full suite green + build — PASS (bundle hash `index-CzWN9tDg.js` noted for the L5 freshness comparison).

## Validation L4-0: Prompt byte-identity [agent]

First run failed on the extraction regex (missing `;` after the TS template literal's closing backtick — see below), then passed after the one-character fix:

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync python /tmp/prompts_diff.py
Traceback (most recent call last):
  File "/tmp/prompts_diff.py", line 13, in <module>
    assert m, "fallback template literal not found"
AssertionError: fallback template literal not found
```

Investigation (`od -c` on the `raw note.` line) showed the literal ended `` ` `` + `\n` with no `;`. Fix: added the missing `;` to `frontend/src/api/prompts.ts` line 16 (matches codebase statement style; the plan's L4-0 regex prescribes `` `; ``). Re-ran:

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync python /tmp/prompts_diff.py
identical: 553 chars
```

Script deleted after. Expected: exit 0, `identical: N chars`, no diff — PASS.

## Validation L4-1: Static live check [agent]

First run failed on a script bug (`ModuleNotFoundError: No module named 'app'` — `uv run python /tmp/...` puts `/tmp` first on `sys.path`; the L4-0 script had the `sys.path.insert(0, ".")` fixup and L4-1 did not). Rewrote the script with the fixup and re-ran (effective key asserted empty to prove keyless serving with the repo `.env` blocked):

```
$ cd backend && DATABASE_PATH=/tmp/prompts_smoke.db UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync python /tmp/prompts_live_smoke.py
live static check ok: 553 chars
```

Scratch deleted after (`/tmp/prompts_live_smoke.py`, `/tmp/prompts_smoke.db*`; verified absent along with `/tmp/prompts_diff.py`). Expected: exit 0, asserted values — PASS.

## Validation L5: Redeploy + browser E2E [agent]

Baseline (pre-redeploy): `GET /api/v1/prompts/checkpoint` on the live URL → `HTTP 404 Not Found` (deployment predates this deliverable — redeploy required, not optional).

Same-origin rebuild + deploy:

```
$ cd frontend && VITE_API_URL= npm run build
✓ built in 87ms
index-B9VeRXFq.js
index-BHdYJWT9.css
```

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync modal deploy modal_app.py
✓ Created objects.
├── ✓ Uploaded .../backend/modal_app.py
├── ✓ Uploaded .../frontend/dist
├── ✓ Uploaded .../backend/app
└── ✓ Created Function serve
    └── https://the-natalie--thoughtbridge-serve.us-east.modal.run
        (unauthenticated)
✓ App deployed in 2.771s! 🎉
View Deployment: https://modal.com/apps/the-natalie/main/deployed/thoughtbridge
```

Freshness verification (immediate post-deploy fetch still 404 — propagation lag; rechecked after 20s):

```
$ sleep 20 && curl -s https://the-natalie--thoughtbridge-serve.us-east.modal.run/api/v1/prompts/checkpoint | head -c 300
{"prompt":"Summarize this coding session for my work journal. Be specific and concrete.\n\n1. Work performed — what was built, changed, or fixed.\n2. Problems encountered — each problem, how it was resolved, or what is still open.\n3. Decisions and reasoning — choices made and why, including a
$ curl -s https://the-natalie--thoughtbridge-serve.us-east.modal.run/ | grep -o 'assets/index-[A-Za-z0-9_.-]*\.js'
assets/index-B9VeRXFq.js
```

Freshness PROVEN: new endpoint live with the 4-section text + served bundle `index-B9VeRXFq.js` matches the just-built same-origin bundle (differs from the L3 local build hash, as expected under a different `VITE_API_URL`).

Playwright MCP browser E2E against the deployed URL (the `agent-browser` skill CLI was loaded per reminder but cannot run in this sandbox — its daemon needs local sockets — so the Playwright MCP browser was used per AGENTS.md, exactly as the plan's L5 prescribes):

1. Navigate `/` → snapshot shows header `button "Checkpoint prompt"` OUTSIDE `navigation "Primary"` (6 view buttons intact). OBSERVED.
2. Click `Checkpoint prompt` → `dialog "Checkpoint prompt"` opens with the full 4-section prompt text in the readonly textarea and NO fallback note (live fetch succeeded). OBSERVED.
3. Click `Copy prompt` → paragraph `Copied ✓` appears (real clipboard write succeeded). OBSERVED.
4. Click `Close` → dialog dismissed. OBSERVED.
5. Chat: type `what did I work on?` + Enter → `wait_for "from your notes"` satisfied; snapshot shows `paragraph: from your notes`, a cited answer, and `button "Citation 1"`. OBSERVED.
6. Click `Citation 1` → shared panel: `Chunk 1 · artifact 3e60d3dda71d4e99811c7e55447dd9a2 · span 0–222` + full chunk text + `Close citation`; no conversation badge (correct — note source). OBSERVED.
7. Work tab → artifact list (incl. the auto-saved `tb_conversation` artifact from step 5's question — conversation memory working) + Saved accomplishments `Fact 02039e10`: `accomplishment · completed · 95%` + skill chips + `Evidence chunk 1` + reasoning link. Click evidence → shared panel with identical header meta + full text + Close. OBSERVED.
8. `browser_console_messages` level error → `Total messages: 0 (Errors: 0, Warnings: 0)`. OBSERVED.
9. Browser closed.

Expected: all assertions pass; console error-free — PASS. E2E side effect (precedent-consistent): step 5's question persisted one 2-turn conversation + artifact on the deployed volume DB; no Learn generations were run (reuse cascade untouched per project memory).

Single-test-change proof:

```
$ git diff --stat -- '*.test.*'
 frontend/src/views/ChatView.test.tsx  |  6 ++++--
 frontend/src/views/LearnView.test.tsx | 33 +++++++++++++++++++++++++++++++++
 frontend/src/views/WorkView.test.tsx  | 14 ++++++++++++++
 3 files changed, 51 insertions(+), 2 deletions(-)
$ git status --short | grep '??' | grep test
?? backend/tests/test_prompts_api.py
?? frontend/src/App.test.tsx
?? frontend/src/api/prompts.test.ts
?? frontend/src/components/CheckpointPromptModal.test.tsx
?? frontend/src/components/CitationPanel.test.tsx
?? frontend/src/components/GroundingBadge.test.tsx
```

Exactly one modified expectation (ChatView blended label + title + comment = the 2 changed lines); LearnView/WorkView purely additive (+33/+14, 0 deletions); all other test files new. Backend `tests/` has no modifications, only the new file. No lockfile/`pyproject`/`package.json` changes (see Final tree state below).

Final tree state (product files only; `.agents/` workflow artifacts omitted):

```
M backend/app/main.py
M frontend/src/App.tsx
M frontend/src/api/types.ts
M frontend/src/components/FeedbackCard.tsx
M frontend/src/views/ChatView.test.tsx
M frontend/src/views/ChatView.tsx
M frontend/src/views/LearnView.test.tsx
M frontend/src/views/LearnView.tsx
M frontend/src/views/WorkView.test.tsx
M frontend/src/views/WorkView.tsx
?? backend/app/api/prompts.py
?? backend/tests/test_prompts_api.py
?? frontend/src/App.test.tsx
?? frontend/src/api/prompts.test.ts
?? frontend/src/api/prompts.ts
?? frontend/src/components/CheckpointPromptModal.test.tsx
?? frontend/src/components/CheckpointPromptModal.tsx
?? frontend/src/components/CitationPanel.test.tsx
?? frontend/src/components/CitationPanel.tsx
?? frontend/src/components/GroundingBadge.test.tsx
?? frontend/src/components/GroundingBadge.tsx
```

`frontend/dist/` is git-ignored (verified via `git check-ignore`); no `.env`, `conversation-log/`, or scratch in the repo.

## Evidence Map

- `GET /api/v1/prompts/checkpoint` returns 200 `{"prompt": "<4-section text>"}` with no key/DB/LLM involvement → VERIFIED: L2 `test_prompts_api.py` `4 passed` + L4-1 live check `live static check ok: 553 chars` (key asserted empty) + deployed curl returning the prompt text.
- Frontend client fetches the endpoint and carries a byte-identical fallback → VERIFIED: L2 `prompts.test.ts` `2 passed` + L4-0 agent diff `identical: 553 chars`.
- Header button renders outside the primary nav and opens/closes the dialog on every view; modal covers fetch render, copy confirmation, fetch-failure fallback, execCommand fallback, close → VERIFIED: L2 `App.test.tsx` `3 passed` + L2 `CheckpointPromptModal.test.tsx` `5 passed` + L5 E2E steps 1–4 observed on the fresh deployment (dialog text, `Copied ✓`, dismiss) + console error-free.
- One shared `GroundingBadge` renders the 3 canonical labels with distinct styles; FeedbackCard uses it with zero visual change → VERIFIED: L2 `GroundingBadge.test.tsx` `4 passed` + `FeedbackCard.test.tsx` green unchanged (4 passed) + L5 E2E `from your notes` badge observed in Chat.
- One shared `CitationPanel` renders chunk meta + text + conversation badge + close → VERIFIED: L2 `CitationPanel.test.tsx` `3 passed` (incl. badge iff `tb_conversation`) + L5 E2E panels observed in Chat and Work with header meta + full text + Close.
- ChatView uses both shared components with the unified `both` blended label → VERIFIED: L3 `ChatView.test.tsx` `11 passed` incl. the single updated expectation + L5 E2E badge/chip/panel observed.
- WorkView panel is the shared panel incl. the conversation badge → VERIFIED: L3 `WorkView.test.tsx` `20 passed` incl. the new conversation-badge test + L5 E2E shared panel observed in WorkView.
- LearnView interrupt threads show grounding badge + citation chips opening the shared panel → VERIFIED: L3 `LearnView.test.tsx` `20 passed` incl. the 2 new tests (uncited badge + chip→panel with chunks URL assertion).
- FactCard kind · status · confidence still visible → VERIFIED: existing `FactCard.test.tsx` green unchanged (inside the L3 150 passed) + L5 E2E `accomplishment · completed · 95%` observed.
- Full backend + frontend suites green with zero regressions → VERIFIED: L3 `529 passed, 2 skipped` (skips pre-existing network/model) + frontend `150 passed` + `npm run build` succeeding; frontend suite re-run green on the final code after the `;` fix.
- Lint/type gates pass → VERIFIED: L1 ruff `All checks passed!` + `73 files already formatted` + mypy `Success: no issues found in 39 source files` + oxlint `0 warnings and 0 errors`.
- No new dependencies added → VERIFIED: `git status` shows no `pyproject.toml`/`package.json`/`uv.lock`/`package-lock.json` changes.
- Code follows project conventions → PARTIALLY VERIFIED: implementation mirrors the plan's pinned patterns (thin router, shared rendering, exact-JSON types, established test seams) and all L1–L3 gates pass; the independent-reviewer half of this criterion is pending at `/review-execution`. What remains: run `/review-execution` for this deliverable.

## Ready for Commit

- [x] All tasks completed
- [x] All validation commands passed
- [x] All tests passing
- [x] Evidence Map complete: every acceptance criterion has a status; the one PARTIALLY VERIFIED item is named in the one-line status and detailed under Follow-up Items

## Follow-up Items

- Deviation 1 (equivalent procedure, same assertion): Task 2's plan VALIDATE introspects `app.routes` for `.path`, but the app flattens routers lazily (`_IncludedRouter`, no `.path` attr — same as the deletion deliverable). Verified instead via the OpenAPI table on the real app object: `/api/v1/prompts/checkpoint` serves exactly `['get']`. No re-verification needed.
- Conventions criterion PARTIALLY VERIFIED: run `/review-execution` on this report for the independent-reviewer judgment (the only remaining check for that criterion).
- L4-2 human step 6 not performed live (Practice/Interview FeedbackCard badge in the deployed browser): the FeedbackCard refactor is proven zero-change by its unchanged unit tests, and the plan's L5 script does not require it. Human-optional residual — if the owner wants eyes on it: open the deployed URL → Practice tab → answer one question → confirm the grounding badge + five feedback sections render; no code risk either way.
- E2E left one 2-turn conversation (`what did I work on?` + answer) on the deployed volume DB — precedent-consistent with prior deliverables' browser E2E; delete via `DELETE /api/v1/conversations/{id}` if a pristine demo DB is wanted before seeding.

## Follow-up Validation (cycle 1)

Addresses the first independent execution review (`.agents/execution-reports/reviews/checkpoint-prompt-provenance-visibility-execution-report-review.md`, Overall: NOT_VERIFIED): the L4-2 walkthrough gap (steps 3-conceptual, 4-Learn, 6-Practice/Interview) and the `FeedbackCard.tsx` filesystem check. No application code was changed in this cycle (validation only).

Freshness re-confirmed before any browser step:

```
$ curl -s https://the-natalie--thoughtbridge-serve.us-east.modal.run/ | grep -o 'assets/index-[A-Za-z0-9_.-]*\.js'
assets/index-B9VeRXFq.js
```

Expected `assets/index-B9VeRXFq.js` — PASS (same deployment as the L5 E2E; no redeploy in between).

FeedbackCard GroundingBadge-use proof (direct file inspection):

```
$ muse.search regex 'GroundingBadge|GROUNDING_STYLES' in frontend/src/components/FeedbackCard.tsx
frontend/src/components/FeedbackCard.tsx:2:import GroundingBadge from './GroundingBadge'
frontend/src/components/FeedbackCard.tsx:30:      <GroundingBadge grounding={grounding} />
```

Import at line 2, render at line 30, zero `GROUNDING_STYLES` remnants — the refactor provably uses the shared component. PASS.

Check 1 — Chat conceptual-question badge (L4-2 step 3), Playwright MCP on the deployed URL:

- Typed `what is a hash map?` + Enter; `wait_for "general explanation"` satisfied.
- Snapshot excerpt: `paragraph: general explanation` + uncited conceptual answer, zero `Citation N` chips, and the old string `general explanation + your notes` nowhere present.
- `browser_console_messages` (level error): `Total messages: 0 (Errors: 0, Warnings: 0)`.
- Persisted: one 2-turn chat conversation + its `tb_conversation` artifact on the deployed volume DB.

Result: PASS.

Check 2 — Learn thread provenance (L4-2 step 4): NOT PERFORMED (prohibited). Project memory (`MEMORY.md`, personal_project scope) requires Learn prompt-generations to use isolated scratch DBs, never the deployed volume DB — test lessons accumulate versions and pollute the reuse cascade; the only exception (explicitly testing saved lessons/reuse) does not apply to this badge-observation check. Teaching a concept in the deployed browser would violate that standing agreement, and the Learn UI offers no way to open an existing explanation without generating. Learn thread provenance remains covered by L3 unit tests (`LearnView.test.tsx` 20 passed incl. the badge + chip→panel tests). Human fallback for the owner (runs one Learn generation — do this only if willing to add a lesson to the deployed DB): open the deployed URL, hard-refresh, Learn tab → teach any concept → ask about the current step → confirm the thread shows a `Grounding` badge, cited threads show `Citation N` chips opening the shared panel with `Chunk N · artifact … · span s–e` + full text + working `Close citation`.

Check 3 — Practice/Interview FeedbackCard badge (L4-2 step 6), Playwright MCP on the deployed URL:

- Practice: selected existing lesson `RAG (v1)` (id `4593544c…b322`, read from the dropdown options — no new lesson created), Get question → answered → Submit. FeedbackCard rendered with badge `general explanation` + all five sections (Correct/Missing/Inaccurate/Terminology help/Next step). Badge element: text `general explanation`, class `inline-block rounded border px-2 py-0.5 text-xs border-neutral-400` (exact shared-component mapping, via element evaluate). History grew to 2 entries; new attempt id `54ad43e62d5643f2bc82edbdecb5de7b`.
- Interview: kind → Technical, Get question (one 30s wait timed out on a slow LLM call; question card arrived on re-wait — no error), answered, Submit → FeedbackCard rendered with badge `both` + all five sections. Badge element: text `both`, class `inline-block rounded border px-2 py-0.5 text-xs border-blue-600` (exact shared mapping). History grew to 3 entries; new attempt id `749d196b75ce4c54bbc94e20acb8f739`.
- `browser_console_messages` (level error) after both loops: `Total messages: 0 (Errors: 0, Warnings: 0)`.
- Persisted: 2 practice attempts + their conversation turns on the deployed volume DB (attempts link to the pre-existing RAG lesson / general reference; no new lessons, no cascade pollution beyond one ordinary attempt row each — same footprint as prior deliverables' E2E).

Result: PASS.

Limitations: none beyond Check 2's principled skip. No code fixes were needed; no validations were re-run beyond the delegated browser checks (per the delegate prompt's standing rules).

## Follow-up Validation (cycle 2)

One-time owner exception for the L4-2 step 4 live browser check (Learn thread provenance on the deployed app). No application code was changed and no tests were rerun in this cycle — documentation only, per the owner's instruction.

Owner decision (2026-11-04): accept the existing LearnView unit-test coverage in place of generating another lesson on the deployed database. Rationale: a live check would require a Learn generation on the deployed volume DB, which standing project memory prohibits (test lessons accumulate versions and pollute the explanation reuse cascade).

Status of the check: the L4-2 step 4 **live browser check remains NOT_PERFORMED** — it is not upgraded, reworded, or silently approved. What follows distinguishes exactly what is and is not established:

- Established by unit-test coverage (LearnView.test.tsx, 20 passed, L3-verified): the LearnView thread entry renders a `Grounding` badge with the canonical mapping (uncited teaching → `general explanation`); cited threads render `Citation N` chips; clicking a chip fetches `/api/v1/chunks/{id}` and opens the shared panel with full chunk text; the panel dismisses via `Close citation`. These tests run against stubbed API responses.
- NOT established (would require live verification): end-to-end thread provenance against the real deployed backend — actual retrieval quality for interrupt questions, real teaching-mode generation with citations, and the badge/chip/panel wiring in a genuine lesson thread.

Effect on the Evidence Map: none — no criterion changes status. The LearnView acceptance criterion's verifying check is L3 (`LearnView.test.tsx` green incl. the 2 new tests), which passed; it was already VERIFIED and remains so. This exception concerns manual-validation completeness (L4-2), not criterion evidence.

Related residual now closed: the original Follow-up Items note about L4-2 step 6 (Practice/Interview browser badge) predates cycle 1 and is superseded — cycle 1 observed both badges live with exact shared-component classes and zero console errors. The original Follow-up Items text is preserved above per the append-only rule; this section records its resolution.
