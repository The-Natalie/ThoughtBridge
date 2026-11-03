# Execution Report: explanation-memory-retrieval-markers

Plan: `.agents/plans/explanation-memory-retrieval-markers.md` (approved; review `.agents/plans/reviews/explanation-memory-retrieval-markers-plan-review.md`, Overall: APPROVED after Cycle 1)
Started: 2026-11-03 (UTC)
Branch: main @ 95667d2 (Interactive eight-step explainer endpoint + Learn view)
Tree at start: clean except untracked plan + review files (verified via `git status --porcelain`).

This report records every command, output, validation result, and deviation verbatim as execution proceeds.

## Environment note (applies to all backend commands)

The sandbox denies writes to the default uv cache (`/Users/natalie/.cache/uv` → `Operation not permitted`). Every backend `uv run` command in this report was executed with `UV_CACHE_DIR=/tmp/uv-cache` exported first. This changes only the cache location, not the environment or assertions.

Verbatim first failure:

```
error: Failed to initialize cache at `/Users/natalie/.cache/uv`
  Caused by: failed to open file `/Users/natalie/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)
```

## Task 0 — BASELINE gates on the clean tree

Command: `cd backend && export UV_CACHE_DIR=/tmp/uv-cache && uv run pytest -q 2>&1 | tail -n 3`

```
....................................................s................... [ 86%]
.................................                                        [100%]
247 passed, 2 skipped in 4.75s
```

Command: `cd backend && export UV_CACHE_DIR=/tmp/uv-cache && uv run ruff check . && uv run ruff format --check . && uv run mypy app 2>&1 | tail -n 3`

```
All checks passed!
49 files already formatted
Success: no issues found in 28 source files
```

Command: `cd frontend && npm test -- --run 2>&1 | tail -n 5 && npm run build 2>&1 | tail -n 3`

```
npm notice
npm notice New major version of npm available! 11.20.0 -> 12.2.1
npm notice Changelog: https://github.com/npm/cli/releases/tag/v12.2.1
npm notice To update run: npm install -g npm@12.2.1
npm notice
dist/assets/index-BSp2Znem.js   229.64 kB │ gzip: 71.19 kB

✓ built in 111ms
```

(The tail cut the vitest summary, so it was captured precisely with a follow-up grep.)

Command: `cd frontend && npm test -- --run 2>&1 | grep -E "Test Files|Tests |✓|❯|passed|failed" | tail -n 15`

```
 ✓ src/api/client.test.ts (3 tests) 2ms
 ✓ src/api/learn.test.ts (4 tests) 5ms
 ✓ src/api/query.test.ts (5 tests) 5ms
 ✓ src/views/ChatView.test.tsx (8 tests) 115ms
 ✓ src/views/LearnView.test.tsx (8 tests) 127ms
 Test Files  5 passed (5)
      Tests  28 passed (28)
```

(ANSI color codes stripped in transcription; counts verbatim.)

Command: `cd frontend && npm run lint 2>&1 | tail -n 5 && npx tsc --noEmit -p tsconfig.app.json && echo TSC_OK`

```
> frontend@0.0.0 lint
> oxlint

Found 0 warnings and 0 errors.
Finished in 24ms on 14 files with 116 rules using 8 threads.
TSC_OK
```

Baseline summary: backend 247 passed + 2 skipped; ruff clean (49 files); mypy clean (28 files); frontend 28 passed across 5 files; build, lint, tsc clean.

## UPDATE backend/app/db/explanations.py

Added `normalize_concept`, `Marker`/`ExplanationSummary` dataclasses, `create_marker`, `list_markers`, `list_explanations` after `max_version_for_concept`; added `import re`. Existing functions untouched.

Command: `cd backend && uv run ruff check app/db/explanations.py && uv run ruff format --check app/db/explanations.py && uv run mypy app/db/explanations.py`

First run output (exit 1 — formatting only):

```
All checks passed!
unformatted: File would be reformatted
   --> app/db/explanations.py:217:23
    |
216 |
    - def list_explanations(
    -     db_path: str, concept_filter: str | None = None
    - ) -> list[ExplanationSummary]:
217 + def list_explanations(db_path: str, concept_filter: str | None = None) -> list[ExplanationSummary]:
218 |     """Summaries of stored explanations with aggregate success signals.
    |

1 file would be reformatted
```

Fix: collapsed the signature to one line as ruff suggested. Re-run output (exit 0):

```
All checks passed!
1 file already formatted
Success: no issues found in 1 source file
```

## CREATE backend/app/llm/memory.py

Created with `concept_tier`, `_epoch`, `marked_rank_of`, `build_framing_note` (exact D5 templates), `build_memory_context` (min-by-key cascade, winner tier stored, `TYPE_CHECKING`-only `ExplanationSummary` import, function-local repo import). Refinements during writing: typed rank tuples for mypy, no winner-tier recompute, framing rank expression aligned with step (5).

Command: `cd backend && uv run ruff check app/llm/memory.py && uv run ruff format --check app/llm/memory.py && uv run mypy app/llm/memory.py`

First run output (exit 1 — formatting only):

```
All checks passed!
unformatted: File would be reformatted
   --> app/llm/memory.py:158:17
    |
157 |     )
    -     logger.info(
    -         "memory selected: concept=%s winner=%s tier=%s", concept, winner.id, winner_tier
    -     )
158 +     logger.info("memory selected: concept=%s winner=%s tier=%s", concept, winner.id, winner_tier)
159 |     return MemoryContext(
    |

1 file would be reformatted
```

Fix: collapsed the `logger.info` call as ruff suggested. Re-run output (exit 0):

```
All checks passed!
1 file already formatted
Success: no issues found in 1 source file
```

Command: `cd backend && uv run python -c "import app.llm.memory, app.api.learn, app.main; print('IMPORTS_OK')"` (import-cycle sanity check for the reviewer's finding)

```
2026-11-03 17:22:13.776 Python[98715:14579664] 2026-11-03 17:22:13.776796 [W:onnxruntime:Default, telemetry_1ds.cc:600 operator()] Failed to persist telemetry device ID; using an in-memory identifier
IMPORTS_OK
```

(The onnxruntime telemetry line is pre-existing import noise from `app.main` → embedder; harmless.)

## UPDATE backend/app/api/learn.py

Changes: docstring seam-note extended; imports added `functools`, `Query`, `Literal`, by-name `create_marker`/`list_explanations`/`list_markers` + `build_memory_context`; removed `no_memory`; `memory_fn=no_memory` → `functools.partial(build_memory_context, db_path)`; added models `MarkerCreate`/`MarkerCreated`/`MarkerOut`/`ExplanationSummaryOut`; added `GET /learn/explanations` (before detail), `POST …/markers` (201), `GET …/markers`. `ExplanationOut`/`ExplainResponse`/existing endpoints untouched.

Command: `cd backend && uv run ruff check app/api/learn.py && uv run ruff format --check app/api/learn.py && uv run mypy app/api/learn.py`

First run output (exit 1 — formatting only):

```
All checks passed!
unformatted: File would be reformatted
   --> app/api/learn.py:240:13
    |
239 |
    - @router.get(
    -     "/learn/explanations/{explanation_id}/markers", response_model=list[MarkerOut]
    - )
240 + @router.get("/learn/explanations/{explanation_id}/markers", response_model=list[MarkerOut])
241 | def list_markers_endpoint(explanation_id: str) -> list[MarkerOut]:
    |

1 file would be reformatted
```

Fix: collapsed the decorator as ruff suggested. Re-run output (exit 0):

```
All checks passed!
1 file already formatted
Success: no issues found in 1 source file
```

## UPDATE frontend/src/api/types.ts + frontend/src/api/learn.ts

types.ts: appended `MarkerScope`, `MarkerCreate`, `MarkerOut`, `ExplanationSummary` (field names mirror Pydantic JSON). learn.ts: appended `listExplanations` (branches on `=== undefined`, encodes query), `createMarker`, `listMarkers`.

Command: `cd frontend && npx tsc --noEmit -p tsconfig.app.json && echo TSC_OK`

```
TSC_OK
```

## UPDATE frontend/src/views/LearnView.tsx

Added imports (`createMarker`, `listExplanations`, `listMarkers`, type `ExplanationSummary`); state (`noteInput`, `wholeMarked`, `stepMarked`, `notice`, `history`, `historyOpen`); `teach()` notice fetch strictly inside `if (response.reused_from)`; `regenerate()`/`startOver()` state resets; handlers `markWhole`/`markStep`/`toggleHistory`/`loadVersion`/`viewPrior`; render blocks (reuse notice banner, marker row with note input + two buttons, lazy earlier-versions strip) with the plan's exact aria-labels.

Minor deviation: the plan listed a `MarkerOut` type import, but no name in the component references `MarkerOut` (marker objects arrive via `listMarkers`' inferred return type), so importing it would trip `no-unused-vars` in lint. Omitted; `ExplanationSummary` (used in `useState` typing) imported as planned.

One edit retry: the marker-row anchor initially missed by one space of indentation; re-applied with exact text. No behavior impact.

Command: `cd frontend && npx tsc --noEmit -p tsconfig.app.json && npm run lint 2>&1 | tail -n 3`

```
Found 0 warnings and 0 errors.
Finished in 10ms on 14 files with 116 rules using 8 threads.
```

(tsc emitted no output = clean; lint tail shown.)

## CREATE backend/tests/test_memory.py

Wrote 15 tests per plan (normalization, tier table, cascade, framing, copy semantics, D8 regression, repo round-trips). One correction applied during writing: the plan's tier-2 example `concept_tier("rag retrieval", "rag")` actually yields tier 1 (substring containment takes precedence), so the test asserts 1 for that pair and uses `("vector retrieval", "vector indexes")` as the genuine tier-2 case. Recorded as Deviation 1 below.

Command: `cd backend && uv run pytest tests/test_memory.py -q 2>&1 | tail -n 5`

```
...............                                                          [100%]
15 passed in 0.86s
```

## UPDATE backend/tests/test_learn_api.py (append-only) + casing investigation

Appended `_seeded_client`/`_mkexplanation` helpers, `STAGE_A/B/C` payloads, and 11 tests. One correction during writing: the plan said the lowercase-repeat explain yields "v3" — wrong under exact-string versioning (`max_version_for_concept("rag")` is 0 when rows store `"RAG"`), so the test asserts the new row is `("rag", v1)` with `reused_from == older_id`, which additionally proves normalization end-to-end. Recorded as Deviation 2 below.

Initial run: `5 failed, 17 passed` — all 5 failures were `KeyError: 'Detail'` in new error-body assertions, while all pre-existing `["Detail"]` assertions passed. A long investigation followed (~40 probes). Verified findings, in order:

1. The app code was correct: endpoints ran (log lines), raised the right statuses/messages, and all success-path tests passed. Only the error-body *key casing* differed.
2. Every computed signal (response-body sha256 vs known literals, handler bytecode `co_consts`, full-file pass/fail splits) was self-consistent with lowercase `{"detail": ...}` everywhere.
3. Displayed text repeatedly showed capital `"Detail"` for old code (old test assertions, FastAPI's installed handler source) — including self-contradictory outputs (capital text alongside `KeyError: 'Detail'`).
4. Decisive check via Python (`python3 -c`, exact bytes): on-disk old assertions (lines 165, 192, 201, 214) are lowercase `["detail"]`; my 6 new assertion lines were the only capital `["Detail"]` occurrences; FastAPI/starlette/app sources contain no capital producer. My file views had shown capital where disk holds lowercase, and I had written the new assertions as capital mirroring that flipped view.

Root cause: wrong key casing in my 6 new assertions. FastAPI's real default error body is lowercase `{"detail": ...}` (standard behavior); the repo's existing tests assert lowercase; only my new lines said capital.

Fix (byte-exact, via Python): replaced the 6 `["Detail"]` with `["detail"]`; removed all debug scaffolding (105 print/trace lines + the 30-line temporary `test_zz_cells_in_module`). Verification afterward (via Python): `CAPITAL= 0 lowercase= 10`.

Self-inflicted incident during cleanup: the debug-test deletion used `rfind("\n\ndef ", 0, fn_start)` whose window excluded the sought boundary, so the span swallowed the preceding `test_explain_no_memory_returns_null_reused` too (21 collected instead of 22). Detected immediately via def count; restored the test byte-identical (verified by re-reading the plan's specified body). Recorded as Deviation 3 below (no behavioral impact; final file contains all 11 new tests).

Command: `cd backend && uv run pytest tests/test_learn_api.py -q 2>&1 | tail -n 2` (after fix + restore)

```
......................                                                   [100%]
22 passed in 1.21s
```

Command: `cd backend && uv run pytest tests/test_memory.py -q 2>&1 | tail -n 2` (re-confirm)

```
...............                                                          [100%]
15 passed in 0.65s
```

Notes:
- The approved plan's test-task text shows `["Detail"]` assertions (same flipped view at plan time). Implementation uses the true lowercase convention. Recorded as Deviation 4 below (plan-text correction, no behavior change).
- PRD §10's `{"Detail": "..."}` "(FastAPI default)" claim is inaccurate about the key case; pre-existing doc issue, out of this deliverable's scope. Noted here only.
- Operational lesson applied for the rest of this execution: casing-sensitive content is verified via Python byte reads and test outcomes (structural signals), never via displayed file text alone.

## UPDATE frontend/src/api/learn.test.ts + frontend/src/views/LearnView.test.tsx (append-only)

learn.test.ts: extended the client import, appended 4 tests (bare list path, encoded `?concept`, marker POST body, markers list path). LearnView.test.tsx: appended 6 tests (whole-mark with note, step-mark without note key + per-step state, marked-source banner + view-prior, unmarked-source banner wording, history toggle/badges/load, marker-failure alert).

First run: `2 failed, 36 passed` — both failures were my invented header text `'Lesson: RAG (v1)'` in `findByText` after version loads; the real header renders multi-node (`RAG v1 explanation exp-1…`, confirmed via the Testing Library DOM dump), so exact-string matching failed. The loads themselves worked. Fixed both tests to seed distinct step content (`PRIOR-DEF`/`V1-DEF`) in the loaded version and assert on that instead — more semantic (proves the prior content displays) and decoupled from header format.

Command: `cd frontend && npm test -- --run 2>&1 | grep -E "Test Files|Tests |learn.test|LearnView.test|failed|FAIL" | tail -n 8` (after fix)

```
 ✓ src/api/learn.test.ts (8 tests) 5ms
 ✓ src/views/LearnView.test.tsx (14 tests) 182ms
 Test Files  5 passed (5)
      Tests  38 passed (38)
```

(ANSI codes stripped; file counts verbatim; total reads 38 passed.)

## Validation

### Level 1: Syntax & Style

Command: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app`

First run output (exit 1 — isort rule on the new test import block):

```
I001 [*] Import block is un-sorted or un-formatted
  --> tests/test_learn_api.py:9:1
...
Found 1 error.
[*] 1 fixable with `--fix`.
```

Fix: split the aliased import per ruff's suggestion (`from app.db.explanations import get_explanation as repo_get_explanation` on its own line; isort `combine-as-imports = false`). Second run output (exit 1 — formatting in the two new/edited test files only):

```
All checks passed!
unformatted: File would be reformatted
   --> tests/test_learn_api.py:309:43
...
2 files would be reformatted, 49 files already formatted
```

Fix: `uv run ruff format tests/test_learn_api.py tests/test_memory.py` (sanctioned formatter, deterministic). Final run output (exit 0):

```
2 files reformatted
All checks passed!
51 files already formatted
Success: no issues found in 29 source files
```

Command: `cd frontend && npm run lint 2>&1 | tail -n 3 && npx tsc --noEmit -p tsconfig.app.json && echo TSC_OK`

```
Found 0 warnings and 0 errors.
Finished in 25ms on 14 files with 116 rules using 8 threads.
TSC_OK
```

### Level 2: Unit Tests

- `cd backend && uv run pytest tests/test_memory.py -q` → `15 passed in 0.65s` (exit 0).
- `cd backend && uv run pytest tests/test_learn_api.py -q` → `22 passed in 1.21s` (exit 0; 11 pre-existing untouched + 11 new).
- `cd backend && uv run pytest -q` → `273 passed, 2 skipped in 5.46s` (exit 0; exactly baseline 247 + 26 new, same 2 skipped).
- `cd frontend && npm test -- --run` → `Test Files 5 passed (5)`, `Tests 38 passed (38)` (exit 0; exactly baseline 28 + 10 new; `learn.test.ts` 8, `LearnView.test.tsx` 14).

### Level 3: Integration Tests

- `cd frontend && npm run build` → `✓ built in 74ms`, `build_exit=0`.
- `git status --porcelain -- backend/app/llm/explainer.py backend/app/core/grounding.py backend/app/db/schema.sql` → empty output, `no-touch-exit=0` (no-diff proof).
- `git status --porcelain` shows only intended files: 8 modified (`app/api/learn.py`, `app/db/explanations.py`, `tests/test_learn_api.py`, `src/api/learn.test.ts`, `src/api/learn.ts`, `src/api/types.ts`, `src/views/LearnView.test.tsx`, `src/views/LearnView.tsx`) + 5 untracked (this report, the plan, the plan review, `app/llm/memory.py`, `tests/test_memory.py`). No `.env`, scratch DBs, or `conversation-log/` entries.

### Level 4: Manual Validation

**A1. [agent] Live marked-preferred reuse via in-process TestClient (real key, scratch DB) — PERFORMED.** Two corrections to the plan script were required (Deviation 5): explicit `init_db` (bare `TestClient` skips lifespan, so tables would not exist) and `PYTHONPATH=.` (`uv run python /tmp/script.py` puts the script dir, not cwd, on `sys.path`). First attempt failed with `ModuleNotFoundError: No module named 'app'`; after the `PYTHONPATH` fix:

Command: `cd backend && rm -f /tmp/mem_live.db* && set -a && . ../.env && set +a && export UV_CACHE_DIR=/tmp/uv-cache && DATABASE_PATH=/tmp/mem_live.db PYTHONPATH=. uv run python /tmp/mem_live_check.py`

```
2026-11-03 17:59:34.146 Python[3965:14617231] 2026-11-03 17:59:34.146698 [W:onnxruntime:Default, telemetry_1ds.cc:600 operator()] Failed to persist telemetry device ID; using an in-memory identifier
LIVE-MEMORY-OK reused_from=259a2609918945e589722e6ad1928a47
```

(exit 0; the onnxruntime line is pre-existing import noise.) Scratch cleaned afterward (`rm -f /tmp/mem_live.db* /tmp/mem_live_check.py`, verified absent).

**H1. [human] Marker + reuse UI on the deployed app — NOT_PERFORMED** (pending deployment; deployment is out of this deliverable's scope; steps H1.1–H1.5 in the plan remain the post-deploy script).

### Level 5: Additional Validation

NOT_PERFORMED — automated browser E2E requires the Playwright MCP browser against a deployed URL with verified deployment freshness per AGENTS.md; deployment is out of scope. Revisit in Phase 4 using plan steps H1 as the script.

## Manual verification checklist

- [x] [agent] Live reuse proof: L4-A1 exit 0, `LIVE-MEMORY-OK`, scratch removed.
- [x] [agent] No-touch proof: L3 `git status --porcelain` empty for `explainer.py`, `grounding.py`, `schema.sql`.
- [x] [agent] Edge/validation matrix: L2 suites green (404/422 marker cases, blank-filter 422, duplicate-201, D8/D11 proofs all in the passing suites).
- [x] [agent] Frontend lazy-fetch proof: all 8 pre-existing `LearnView` tests pass with unchanged fetch-count assertions (D10 holds; full frontend suite green).
- [ ] [human] Marker + reuse UI (H1 steps 1–5 on deployed URL) — PENDING deployment.
- [x] [agent] Docs reflection: `git status` shows only intended files (listed in L3).

## Deviations

1. **Tier-2 example corrected** (plan test-task text): `concept_tier("rag retrieval", "rag")` is tier 1 (containment precedence), not 2 as the plan text said. Test asserts 1 for that pair and uses `("vector retrieval", "vector indexes")` as the genuine tier-2 case. More coverage than planned, same intent.
2. **Version assertion corrected** (`test_explain_wires_real_memory_marked_preferred`): plan said the lowercase repeat yields "v3"; exact-string versioning yields `("rag", v1)`. Asserted v1 + `reused_from == older_id` — proves normalization end-to-end (stronger than planned).
3. **Surgery swallowed a test; restored**: debug cleanup deleted `test_explain_no_memory_returns_null_reused` (span bug); detected via def count; restored byte-identical. Final file has all 11 new tests; no behavioral impact.
4. **Error-body key casing** (plan test-task text + my initial tests): plan shows `["Detail"]`; true FastAPI default and repo convention is lowercase `["detail"]` (verified byte-exact). Implemented lowercase. See the casing-investigation section above.
5. **L4 script corrections**: added explicit `init_db` (bare TestClient skips lifespan) and `PYTHONPATH=.` invocation fix. Same assertions as planned.
6. **`MarkerOut` import omitted** in `LearnView.tsx` (plan listed it; the name is never referenced — markers arrive via inferred return type — and importing it trips `no-unused-vars`).
7. **Environment**: `UV_CACHE_DIR=/tmp/uv-cache` exported for all backend `uv run` commands (sandbox denies the default `~/.cache/uv`). Cache location only; no behavioral effect.
8. **Mechanical**: `ruff format` applied to the two test files; isort split of the aliased test import. No logic changes.

## Evidence Map

Each plan Acceptance Criterion with its verdict and the exact observed result:

1. Marked explanation reused on normalized repeat concept request, marked preferred over unmarked — **PROVEN**.
   - L2: `tests/test_learn_api.py::test_explain_wires_real_memory_marked_preferred` passed (in the `22 passed` run); asserts `body["reused_from"] == box["older"]` for lowercase repeat with real orchestrator + real memory.
   - L4-A1 live: `LIVE-MEMORY-OK reused_from=259a2609918945e589722e6ad1928a47` (exit 0).
2. "Clicked" markers persist at explanation + step level with notes; invalid writes rejected — **PROVEN**. L2 (in the `22 passed` run): `test_create_marker_happy_paths` (201s + repo rows), `test_create_marker_unknown_explanation_404`, `test_create_marker_step_scope_validation_422`, `test_create_marker_scope_step_mismatch_422`, `test_create_marker_duplicates_allowed`, `test_list_markers_shape_order_and_404`.
3. `GET /learn/explanations` lists summaries with signals + normalized `?concept` filter — **PROVEN**. L2: `test_list_explanations_shape_order_and_counts` (exact 9-key set, DESC order, counts) and `test_list_explanations_concept_filter` (match/non-match/blank-422); also asserted live in L4-A1 (`len(lst) == 2`, marked/reuse/version tuple).
4. Success cascade deterministic per D1–D3 — **PROVEN**. L2: `tests/test_memory.py`, `15 passed`.
5. Nothing auto-marks; regen never pollutes reuse — **PROVEN**. L2: `test_explain_and_regen_create_no_markers` (zero marker rows, regen `reused_from None`) and `test_regen_rows_do_not_pollute_reuse_counts`.
6. Zero regressions; pre-existing tests pass unmodified — **PROVEN**. Backend `273 passed, 2 skipped` = baseline `247 passed, 2 skipped` + 26 new; frontend `38 passed` = baseline 28 + 10 new with unchanged fetch-count assertions; L3 no-touch proof empty for `explainer.py`/`grounding.py`/`schema.sql`.
7. Marker UI complete (buttons + note, notice + view-prior, history + badges) — **PROVEN** (automated). L2 frontend: `learn.test.ts` 8 passed (4+4), `LearnView.test.tsx` 14 passed (8+6); L1 `tsc` clean, `lint` 0/0, L3 `npm run build` exit 0.
8. Human UI verification on deployed app (H1 steps 1–5) — **NOT PROVEN (UNVERIFIED, pending deployment)**. Deployment is out of scope; browser E2E NOT_PERFORMED per AGENTS.md. Manual steps recorded in the plan.
9. Lint + typecheck + build green — **PROVEN**. `ruff check`: `All checks passed!`; `ruff format --check`: `51 files already formatted`; `mypy app`: `Success: no issues found in 29 source files`; `oxlint`: `0 warnings and 0 errors`; `tsc --noEmit`: clean; `vite build`: `✓ built in 74ms`.
10. No new dependencies, no DDL, no `ExplanationOut` shape change — **PROVEN**. `git status` shows only the 8 modified + 5 untracked intended files; no `pyproject`/`package.json`/schema changes; existing exact-keys tests pass unmodified.

## Outcome

Done. All implementation tasks complete; validation Levels 1–4 (agent portions) green with exact expected counts; H1/L5 recorded NOT_PERFORMED pending deployment as the plan and AGENTS.md prescribe. No commit made (per skill: never auto-invoke `/commit`).

---

## Follow-up Validation (cycle 1): post-deploy H1/L5 browser verification

Owner-directed (2026-11-03 UTC): fresh deploy of the working tree + H1/L5 via Playwright MCP against the deployed Modal app, following the D1-established process. No commit made (owner instruction). This section appends new evidence; original sections above are unedited. Where this section and the original Outcome disagree (criterion 8), this section supersedes with observed evidence.

### agent-browser probe (one attempt, per AGENTS.md)

The project agent-browser skill was loaded; its CLI needs a local daemon socket, which the sandbox denies:

```
$ which agent-browser && agent-browser open about:blank 2>&1 | head -n 5
/opt/homebrew/bin/agent-browser
✗ Socket directory '/Users/natalie/.agent-browser' is not writable: Operation not permitted (os error 1)
```

Recorded once; browser work used the Playwright MCP browser instead (D1 process, AGENTS.md-compliant).

### Deployment

Volume `thoughtbridge-data` and secret `thoughtbridge-env` already existed (verified via `modal volume list` / `modal secret list`); no secret values were handled.

```
$ cd frontend && VITE_API_URL= npm run build 2>&1 | grep -E "built in|error|dist/assets"
dist/assets/index-CGcCP9ga.css    8.21 kB │ gzip:  2.40 kB
dist/assets/index-KSpSWihU.js   232.94 kB │ gzip: 71.83 kB
✓ built in 75ms
```

```
$ cd backend && export UV_CACHE_DIR=/tmp/uv-cache && uv run modal deploy modal_app.py 2>&1 | tail -n 15
✓ Created objects.
├── ✓ Uploaded .../backend/modal_app.py
├── ✓ Uploaded .../frontend/dist
├── ✓ Uploaded .../backend/app
└── ✓ Created Function serve
    └── https://the-natalie--thoughtbridge-serve.us-east.modal.run
        (unauthenticated)
✓ App deployed in 2.525s! 🎉
```

### Freshness verification (before any browser testing)

```
$ curl -s -o /tmp/fresh_list.json -w "HTTP %{http_code}\n" $BASE/api/v1/learn/explanations
HTTP 200
explanation count: 4
  CSS media queries for responsive web layouts v1 marked=False reuse=0 188db1ba
  rag v1 marked=False reuse=0 be4fc136
  Vector indexes v2 marked=False reuse=0 91248e53
  Vector indexes v1 marked=False reuse=0 17a798ad
$ curl -s -X POST $BASE/api/v1/learn/explanations/00000000000000000000000000000000/markers ... {"scope":"explanation"}
{"detail":"explanation not found"}
HTTP 404
$ curl -s $BASE/ | grep -o 'index-[A-Za-z0-9]*\.js'
index-KSpSWihU.js
```

New backend live (`GET /learn/explanations` → 200; D1 code 404s that path) with D2 validation messages; served bundle hash matches the just-built `dist/`. (`/tmp/fresh_list.json` removed afterward.)

Observation: the deployed DB already held an unmarked `rag v1` row (not from this deliverable's scratch-DB checks). H1's scripted concept `RAG` therefore could not satisfy step 1's "no reuse notice on first explanation" — memory would correctly reuse it. Concept substituted with `Photosynthesis` (fresh on the deployed DB); all H1 steps otherwise verbatim, plus a case/whitespace variant (`"  photosynthesis "`) at step 5 to exercise normalization live.

### H1 browser run via Playwright MCP (also serves as L5)

Method: Playwright MCP browser tools against `https://the-natalie--thoughtbridge-serve.us-east.modal.run/?fresh=d2` (cache-busting param, D1 practice). All observations below are quoted accessibility-snapshot text.

1. Learn view concept form visible (`textbox "Concept"`, `textbox "Familiar system hint (optional)"`, `button "Teach me"`). Taught `Photosynthesis` (~3.5 min incl. cold start; container verified warm/responsive mid-wait via a 0.3 s list call, and the row persisted server-side before the UI returned). Lesson rendered: heading `Photosynthesis v1 explanation 47af89f6…`, all 8 `Step: <key>` buttons, Definition content, marker row (`What clicked (optional note)` + `This clicked` + `This step clicked`), Ask/Regenerate, Back/Next, `Show earlier versions`. No reuse notice (correct: unrelated `rag`/`Vector indexes` rows ignored). PASS.
2. Typed note `oak tree food factory clicked`, clicked `Mark whole explanation as clicked`: button became `Clicked ✓` + disabled; step button still enabled; no error. PASS.
3. Clicked `Step: mapping` (7 prose passages rendered), clicked `Mark this step as clicked`: step button became `Clicked ✓` + disabled. Returned to `Step: definition`: step button shows `This step clicked` enabled (per-step state), whole stays `Clicked ✓` disabled. PASS.
4. Clicked `Show earlier versions`: strip `Earlier versions` with `Load version 1` (`v1 ✓` — marked badge). Clicked it: lesson reloaded (`Photosynthesis v1 explanation 47af89f6…`), note cleared, buttons reset to enabled (lazy D10/D12 behavior as designed; ✓ badge retains marked visibility). PASS.
5. `Start over`, taught `"  photosynthesis "`: new lesson `photosynthesis v1 explanation b8f9797b…` with reuse notice `This builds on an explanation that clicked for you before.` + `View prior explanation` button (normalization + marked-source detection end to end). New version starts unmarked (both buttons enabled — D11). New definition reuses the v1 oak-tree analogy family verbatim in places (reuse injection visible in output). Clicked `View prior explanation`: loaded `Photosynthesis v1 explanation 47af89f6…` (original id), notice cleared. PASS.

Result: H1 steps 1–5 PASS (5/5) on the freshly deployed app. Browser closed after the run; no local servers started.

Server-side cross-check after the run (`GET /learn/explanations?concept=photosynthesis` + markers reads):

```
photosynthesis rows: 2
  Photosynthesis v1 47af89f6 reused_from=None marked=True markers=2 reuse=1
    marker: explanation None 'oak tree food factory clicked'
    marker: step mapping 'oak tree food factory clicked'
  photosynthesis v1 b8f9797b reused_from=47af89f6 marked=False markers=0 reuse=0
```

Exactly the designed end state: v1 marked (explanation + step markers sharing the note input), v2-lineage row pointing `reused_from` at v1 and starting unmarked.

### Verdict updates from this cycle

- H1 (plan manual checklist + acceptance criterion 8): now **PERFORMED / PROVEN** — 5/5 steps pass on the freshly deployed app with quoted snapshot evidence above. This supersedes the original `NOT_PERFORMED`/`UNVERIFIED` entries, which were accurate at the time (pre-deploy).
- L5 (automated browser E2E): now **PERFORMED** — the Playwright MCP run above is the automated browser E2E against the deployed URL (same combined H1/L5 treatment as D1's "H1-equivalent" run).
- Remaining caveat: the deployment serves the uncommitted working tree (owner declined commit); a post-commit redeploy would be needed for a SHA-pinned freshness claim. Recorded, not blocking: freshness was verified by behavior (new routes + bundle hash), not by SHA.

---
