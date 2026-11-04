# Execution Report: shared-practice-loop-endpoints-practice-interview-views

Plan: `.agents/plans/shared-practice-loop-endpoints-practice-interview-views.md` (review APPROVED after Cycle 1).
Started: 2026-11-04. Full verbatim log below — every command, output, validation result, deviation.

---

## Deviation 1: `uv run` unusable in sandbox (equivalent procedure)

Command: `cd backend && uv run pytest tests/test_db_init.py -q`
Output (verbatim):
```
error: Failed to initialize cache at `/Users/natalie/.cache/uv`
  Caused by: failed to open file `/Users/natalie/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)
```
Resolution: all backend validation runs via the existing `backend/.venv/bin/python -m ...` directly (same interpreter/environment; no sync needed — this deliverable adds zero dependencies). Every plan command spelled `uv run X` below was executed as `.venv/bin/python -m X`.

## Task 1: UPDATE backend/app/db/schema.sql — DONE

Edits: header comment → schema v2 + migration note; meta default `schema_version` 1→2; attempts DDL gains `conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL` and `reference_json TEXT` (both nullable).

## Task 2: UPDATE backend/app/db/connection.py — DONE

Added `_migrate(conn)` (PRAGMA table_info guard per column, single-transaction ALTERs + version bump, info log per added column), called from `init_db` after `executescript`.

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_db_init.py -q`
Output: `7 passed in 0.19s` (exit 0)

## Task 3: CREATE backend/app/db/attempts.py — DONE

`AttemptDetail` (incl. `reference: dict` NULL→{} + `conversation_id`), `create_attempt`, `record_answer` (overwrite), `get_attempt` (LEFT JOIN concept), `list_attempts` (mode/explanation_id SQL filters, retry_only in Python), defensive `_parse_json_dict`, `_needs_retry` rule. (Test file lands in Task 11; validation deferred there per plan.)

## Task 4: ADD backend/app/db/facts.py::get_facts_by_ids — DONE

Dict-keyed reader mirroring `list_accomplishments` hydration; `{}` on empty input.

## Task 5: ADD backend/app/core/grounding.py practice block — DONE

Tuples + Literals, focus/answer framing, QUESTION/EVALUATION system prompts per (mode,kind), JSON instructions, `resolve_grounding`, `build_question_messages`, `build_evaluation_messages`, `build_practice_request_turn`, `render_feedback_text`. Module stays pure (no new imports needed).

## Task 6: CREATE backend/app/llm/practice.py — DONE

Seams, budgets, caps, 5 error types, `QuestionModelOut`/`FeedbackModelOut`/`EvaluationModelOut`, `QuestionResult`/`EvaluationResult`, `build_career_block` (Phase-3 recipe), `render_fact_block`, `generate_question` (3 branches), `_experience_reference` (facts + excerpts, fact-by-fact cap), `_technical_reference` (possibly empty), `evaluate_answer` (stored-reference rehydration only — no search_fn param; learning self-exclusion on memory).

## Task 7: CREATE backend/app/api/practice.py — DONE

PRD-§10 models, 3 endpoints, `_make_chat_fn`, `_turn_mode_label`, defensive `_attempt_to_out`, full error map incl. 409, NULL-conversation recovery.

## Deviation 2: persist order turns-before-attempt (plan order impossible under FK)

The plan's Task 7 text says "on success `create_attempt(...)` then `create_conversation_with_turns(...)`". On the new-conversation path the conversation does not exist yet, so creating the attempt first violates the `attempts.conversation_id` FK. Implemented: generate → persist turns (create-or-append) → `create_attempt` with the resolved id. Success-path behavior is identical (attempt + 2 turns); the "no empty conversation rows" invariant from `conversations.py` is preserved. No plan re-review needed: routine technical necessity, same observable contract.

## Task 8: UPDATE backend/app/main.py — DONE

Import + `include_router(practice_router, prefix="/api/v1")` after work line.

Validation:
Command: `cd backend && .venv/bin/python -c "import app.main; import app.api.practice; import app.llm.practice; import app.db.attempts; print('imports ok')" && .venv/bin/python -m pytest tests/test_app_boot.py -q`
Output (verbatim):
```
2026-11-04 03:55:35.319 Python[49831:15241776] 2026-11-04 03:55:35.319570 [W:onnxruntime:Default, telemetry_1ds.cc:600 operator()] Failed to persist telemetry device ID; using an in-memory identifier
imports ok
.                                                                        [100%]
1 passed in 0.54s
```
(exit 0; onnxruntime telemetry line is environment noise, unrelated.)

## Task 9: ADD migration test to test_db_init.py — DONE

`test_attempts_v1_to_v2_migration`: synthetic v1 DB (meta + v1 attempts only) → `init_db` → asserts new columns, version '2', row intact with NULLs, full schema created, second `init_db` no-op.

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_db_init.py -q`
Output: `8 passed in 0.22s` (exit 0)

## Task 10: ADD practice cases to test_grounding.py — DONE

Builder branch tests, rubric markers, JSON-instruction keys, `resolve_grounding` truth table, request-turn format, `render_feedback_text` full + odd-shapes.

Issue encountered: first run `1 failed, 35 passed` — test marker `"unsupported"` did not match the rubric's actual wording `"supported by neither"`. Fixed the TEST marker (plan rule: assert on builder output; prose is the implementation's). Re-run green.

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_grounding.py -q`
Output: `36 passed in 0.03s` (exit 0)

## Task 11: CREATE backend/tests/test_attempts.py — DONE

13 tests: round-trip, missing→None, concept join/null, record+overwrite, record-missing→False, needs_retry 7-row truth table, malformed→None, NULL-ref→{}, newest-first + filters, retry_only, FK IntegrityError.

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_attempts.py tests/test_accomplishments.py -q`
Output: `31 passed in 1.18s` (exit 0)

## Task 12: CREATE backend/tests/test_practice.py — DONE

32 tests per plan incl. no-search-fn structural lock, excerpt-verbatim assertion, self-match guard, stale/missing handling, career injection.

Issues encountered (both test-side typos, implementation untouched):
1. Collection `SyntaxError` — extra `]` in `test_malformed_question_json_502` payload list. Removed.
2. `test_experience_fact_cap_newest_first` UNIQUE failure — helper id scheme collided on same-prefix summaries. Switched to `uuid4().hex`.
3. `test_evaluate_technical_deleted_chunks_degrade` IndexError — stub wired to `[]` instead of `record`. Fixed arg.

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_practice.py -q`
Output: `32 passed in 0.98s` (exit 0)

## Task 13: CREATE backend/tests/test_practice_api.py — DONE

22 tests: real orchestration + repos, stubbed chat/search/career only. Shapes, full status matrix (422×5 paths/404×3/409/502×2), inheritance, re-answer, NULL-conversation recovery, filters, malformed-feedback resilience.

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_practice_api.py -q`
Output: `22 passed in 1.44s` (exit 0)

## Backend regression + lint gate (early, before frontend)

Command: `cd backend && .venv/bin/python -m pytest -q`
Output: `482 passed, 2 skipped in 9.96s` (exit 0; skips pre-existing)

Command: `cd backend && .venv/bin/python -m ruff check .` → `Found 1 error` (import sort in test_grounding.py)
Command: `cd backend && .venv/bin/python -m ruff format --check .` → `8 files would be reformatted` (all 8 mine, verified via git)
Fix: `ruff check --fix .` (`1 fixed, 0 remaining`) + `ruff format` on those 8 files (`8 files reformatted`).
Re-verify: `ruff check .` → `All checks passed!`; `ruff format --check .` → `68 files already formatted`.
Re-run: `pytest -q` → `482 passed, 2 skipped in 10.04s`; `mypy app` → `Success: no issues found in 37 source files`.

## Task 14: ADD practice types to frontend/src/api/types.ts — DONE

PracticeMode/QuestionKind/ReferenceKind/GroundingLabel + all request/response/attempt interfaces mirroring backend JSON exactly.

## Task 15: CREATE frontend/src/api/practice.ts + practice.test.ts — DONE

postPracticeQuestion/postPracticeAnswer/listAttempts (+AttemptFilters; retry_only=false omits the param). 6 contract tests.

Validation:
Command: `cd frontend && npm test -- --run src/api/practice.test.ts`
Output: `Test Files 1 passed (1)` / `Tests 6 passed (6)` (exit 0)

## Task 16: CREATE FeedbackCard + test — DONE

Pure presentational: 5 fixed-order sections, `(none)` for empty lists, emphasized next_step, verbatim grounding badge with per-value border style.

Validation:
Command: `cd frontend && npm test -- --run src/components/FeedbackCard.test.tsx`
Output: `Test Files 1 passed (1)` / `Tests 4 passed (4)` (exit 0)

## Task 17: CREATE AttemptHistory + test — DONE

Counts header, retry queue oldest-first with `Retry {id}` buttons + onRetry(attempt), full list newest-first with Retry/grounding labels, empty state.

Validation:
Command: `cd frontend && npm test -- --run src/components/AttemptHistory.test.tsx`
Output: `Test Files 1 passed (1)` / `Tests 3 passed (3)` (exit 0)

## Task 18: CREATE PracticeView + test — DONE

Learning loop per plan (lesson select, question/answer/feedback, next-question, retry, new-session, history, error/dismiss/disclosure).

Issue encountered: `shows and dismisses errors` failed — synchronous `within().getByText` raced the mount fetch. Fixed test to `await screen.findByText` (other tests already used it); removed the unused `within` import.

Validation:
Command: `cd frontend && npm test -- --run src/views/PracticeView.test.tsx`
Output: `Test Files 1 passed (1)` / `Tests 8 passed (8)` (exit 0)

## Task 19: CREATE InterviewView + test — DONE

Interview loop per plan (kind radio default experience, focus input, kind chip, kind-switch clears stale question, retry syncs radio).

Validation:
Command: `cd frontend && npm test -- --run src/views/InterviewView.test.tsx`
Output: `Test Files 1 passed (1)` / `Tests 6 passed (6)` (exit 0)

## Task 20: UPDATE frontend/src/App.tsx — DONE

PracticeView/InterviewView imports, stub blurbs emptied, render chain extended. Capture stub untouched.

Validation:
Command: `cd frontend && npm test -- --run`
Output: `Test Files 16 passed (16)` / `Tests 121 passed (121)` (exit 0)
Command: `cd frontend && npx oxlint`
Output: `Found 0 warnings and 0 errors.` (exit 0)
Command: `cd frontend && npm run build`
First output: `src/api/practice.test.ts(24,32): error TS2345: ... Type 'string' is not assignable to type 'PracticeMode'.`
Fix: typed the test `body` const as `PracticeQuestionRequest` (test-only change).
Re-run output: `✓ built in 106ms` (exit 0; bundle `dist/assets/index-DpdxnZNE.js`)
Re-verify: practice.test.ts `6 passed (6)`.

## Validation ladder — final runs

### Level 1: Syntax & Style

Command: `cd backend && .venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .` (+ `mypy app`)
Output: `All checks passed!` / `68 files already formatted` / `Success: no issues found in 37 source files` (exit 0)

Command: `cd frontend && npx oxlint`
Output: `Found 0 warnings and 0 errors.` (exit 0)

### Level 2: Unit Tests

Command: `cd backend && .venv/bin/python -m pytest tests/test_attempts.py tests/test_practice.py tests/test_grounding.py tests/test_db_init.py -q`
Output: `93 passed in 1.60s` (exit 0)

Command: `cd frontend && npm test -- --run src/api/practice.test.ts src/components/FeedbackCard.test.tsx src/components/AttemptHistory.test.tsx`
Output: `Test Files 3 passed (3)` / `Tests 13 passed (13)` (exit 0)

### Level 3: Integration Tests

Command: `cd backend && .venv/bin/python -m pytest -q`
Output: `482 passed, 2 skipped in 10.26s` (exit 0; skips pre-existing)

Command: `cd frontend && npm test -- --run && npm run build`
Output: `Test Files 16 passed (16)` / `Tests 121 passed (121)` + `✓ built in 92ms` (exit 0)

### Level 4: Manual Validation (agent steps)

Pre-check: `.env` contains `MODEL_API_KEY` (presence confirmed via grep count, value never printed); `/tmp` scratch clean.

**L4-1** — first attempt failed with `ModuleNotFoundError: No module named 'app'` (pytest sets `pythonpath`, plain python does not). Re-ran with `PYTHONPATH=.`:
Command: `cd backend && DATABASE_PATH=/tmp/practice_smoke.db PYTHONPATH=. .venv/bin/python /tmp/practice_live_smoke.py`
Output (verbatim, minus onnxruntime telemetry noise):
```
Q: How would you explain to an interviewer how RAG grounds an LLM's answer in retrieved documents?
grounding: general explanation
next_step: Recite the full walkthrough in order: query, retrieve top-k, stuff into prompt, generate.
L4-1 OK
```
(exit 0; all assertions passed: non-blank question, reference_kind `explanation`, 5-key feedback, teaching grounding)

**L4-2**:
Command: `cd backend && DATABASE_PATH=/tmp/practice_smoke2.db PYTHONPATH=. .venv/bin/python /tmp/practice_live_smoke2.py`
Output (verbatim, minus telemetry noise):
```
EXP Q: When you investigated the slow checkout endpoint and found the N+1 query in the order loader, why did you reject adding
EXP grounding: from your notes
TECH Q: You noted you fixed a slow checkout endpoint caused by an N+1 query in the order loader with a batched loader instead of
TECH grounding: both
L4-2 OK
```
(exit 0; all five asserted values observed: experience reference+feedback+`from your notes`, technical reference+feedback+`both`. Note the technical question wove personal context unprompted — the designed behavior.)
Cleanup: `rm -f /tmp/practice_smoke.db* /tmp/practice_smoke2.db*` → `SCRATCH_CLEAN`. Probe scripts `/tmp/practice_live_smoke.py` + `/tmp/practice_live_smoke2.py` retained in /tmp for review/re-run (not committed).

**L4-3 (human walkthrough)** — performed by agent via Playwright MCP against the fresh deployment (real browser; see L5 log below): Practice tab renders real view with empty-lessons state (0 lessons in deployed DB); Interview experience flow end-to-end with `from your notes` feedback; kind-switch clears stale state; retry queue + badge observed. The Practice-with-lesson browser path was instead proven by L4-1 (same endpoints, real LLM) + `PracticeView.test.tsx` (8 tests). Owner may still click through post-seeding (Phase 4).

### Level 5: Redeploy + Playwright E2E (performed, not skipped)

Rebuild: `cd frontend && VITE_API_URL= npm run build` → `✓ built in 99ms`, bundle `dist/assets/index-Bnzp0ZBr.js`.
Deploy: `cd backend && .venv/bin/modal deploy modal_app.py` → `✓ App deployed in 35.742s!` at `https://the-natalie--thoughtbridge-serve.us-east.modal.run`.
Freshness: deployed `/` references `index-Bnzp0ZBr.js` (matches just-built bundle); `/api/v1/practice/attempts` → `[]` (new route live; the SELECT includes the new columns, proving the volume DB migrated at boot); `/api/v1/health` → `{"status":"ok","db":true,"meta_api":true,"model":"muse-spark-1.3",...}`.
Deployed data: `explanations: 0`, `accomplishments: 1`.

Note on tooling: the `agent-browser` skill was loaded per reminder, but AGENTS.md Environment Constraints + the approved plan require the Playwright MCP browser against the deployed URL (agent-browser's daemon cannot run sandboxed). Used Playwright MCP throughout; no agent-browser/localhost probe needed.

Playwright E2E (verbatim observations):
1. Navigate deployed URL → Chat view default, tabs Chat/Capture/Learn/Work/Practice/Interview present.
2. Click Practice → real view: `combobox "Lesson"` (only "Choose a lesson…"), `Get question [disabled]`, hint `No lessons yet — teach a concept in the Learn tab first.`, `Practice history (0) · Retry queue (0)`, `No attempts yet.`, disclosure line. Correct for 0 deployed lessons.
3. Click Interview → `radio Experience [checked]` + `radio Technical`, `Focus (optional)` input, Get question, history (0), disclosure.
4. Click Get question (experience, empty focus) → after ~30s LLM call, Question card: kind chip `experience`, question `Why did you decide to add a retry with backoff instead of doubling the timeout to fix the checkout timeout?` (grounded in the stored accomplishment) + `Your answer` textarea + Submit.
5. Type answer + Submit → after ~30s, Feedback card: badge `from your notes`, sections Correct/Missing/Inaccurate/Terminology help (`Say 'checkout timeout' instead of generic 'timeouts'`…), `Next step: Add metrics for retry counts…`, `Next question` button; history refreshed to `Practice history (1) · Retry queue (1)` with retry-queue entry + `Retry {id}` button and row `interview/experience · Retry · from your notes`.
6. Click Technical radio → question + feedback + answer cleared (only `Question kind` group remains). Correct.
7. `browser_console_messages` level error → `Total messages: 0 (Errors: 0, Warnings: 0)`.
8. Server-side proof: `GET /api/v1/practice/attempts` → 1 attempt, `interview experience | retry: True | grounding: from your notes`.
9. Browser closed.

Deployed-DB writes from E2E: 1 attempt + 1 conversation + 4 turns (one live loop). Deliberate and minimal; Phase 4 re-seeds the demo DB.

## Manual verification checklist results

- [agent] Backend ladder green: L1–L3 commands above; exact Expected outputs observed, zero failures. DONE.
- [agent] Frontend ladder green: oxlint + L2–L3 commands above; exact Expected outputs observed, zero failures. DONE.
- [agent] Live learning + interview exchanges: L4-1/L4-2 exit 0 with asserted values; scratch DBs deleted. DONE.
- [human→agent-equivalent] Deployed UI walkthrough: L4-3 steps performed via Playwright MCP (see L5 log); Practice-with-lesson path covered by L4-1 + unit tests pending Phase 4 seeding. DONE with noted qualification.
- [agent] Migration proof: `pytest tests/test_db_init.py::test_attempts_v1_to_v2_migration -q` → `1 passed`; deployed volume DB migrated at boot (proven by `/api/v1/practice/attempts` → `[]` selecting the new columns). DONE.
- [agent] No leftover scratch: `ls /tmp/practice_smoke*` → clean; `git status --short` shows only intended files (no `.env`, no `conversation-log/`, no scratch in repo; `frontend/dist/` untracked-but-ignored — absent from status). DONE.

## Evidence Map

- Question endpoint shapes per mode/kind with correct reference_kind → VERIFIED: `test_practice_api.py` (22 passed incl. 3 shape tests) + L4-1/L4-2 live values (`explanation`/`facts`/`general` all observed).
- Answer returns 5-key feedback + code-computed grounding → VERIFIED: `test_practice_api.py` answer-shape test + `test_practice.py` grounding cases + L4-1 (`general explanation`) / L4-2 (`from your notes`, `both`) + browser (`from your notes` badge).
- Evaluator constrained to stored references (zero retrieval) → VERIFIED: `test_practice.py::test_evaluate_takes_no_search_fn_by_design` (structural: no `search_fn` parameter) + experience evaluation tests passing with only stored refs.
- Conversation inheritance in order with roles → VERIFIED: `test_practice_api.py::test_answer_happy_path_inherits_conversation` (4-turn role/mode/content assertions via `get_conversation`).
- Status matrix 422/404/409/502 → VERIFIED: `test_practice_api.py` matrix (overlong-focus/blank-answer/mode-kind/no-evidence 422s; unknown conversation/explanation/attempt 404s; stale 409; Meta/junk 502s) — all passing.
- v1→v2 migration idempotent/data-preserving/version-bumping → VERIFIED: `test_db_init.py::test_attempts_v1_to_v2_migration` (`1 passed`) + deployed boot migration proven by live `/api/v1/practice/attempts`.
- Practice + Interview views run the full loop (shared cards, history, retry queue, error/dismiss/disclosure) → VERIFIED: frontend suite 121 passed (incl. 8 PracticeView + 6 InterviewView flow tests) + live browser interview loop + Practice empty-state render. Qualification: the Practice-with-stored-lesson browser path ran against 0 deployed lessons; its full loop is proven by L4-1 (same endpoints, real LLM) + `PracticeView.test.tsx` flows. No separate criterion status needed — the loop is verified; the deployed lesson data arrives with Phase 4 seeding.
- Kind-switch clears stale question; empty-explanations disables Get-question → VERIFIED: `InterviewView.test.tsx` kind-switch test + `PracticeView.test.tsx` empty-lessons test + both behaviors re-observed in the live browser.
- Full suites green, zero regressions → VERIFIED: backend `482 passed, 2 skipped` (skips pre-existing); frontend `16 files / 121 tests` + build OK.
- Lint/type gates → VERIFIED: ruff check `All checks passed!`, ruff format `68 files already formatted`, mypy `Success: no issues found in 37 source files`, oxlint `0 warnings and 0 errors`.
- Live Meta exchanges on scratch DBs → VERIFIED: L4-1 + L4-2 exit 0 with all asserted values (quoted above).
- No new dependencies → VERIFIED: `git diff --stat backend/pyproject.toml backend/uv.lock frontend/package.json frontend/package-lock.json` → empty (DEPS_UNCHANGED).
- Project conventions → VERIFIED: thin router, shared grounding contracts, by-name seams, exact-JSON types — all mirror cited precedents (reviewer judgment at `/review-execution` still to come per workflow).

## Ready for Commit

- [x] All tasks completed
- [x] All validation commands passed
- [x] All tests passing
- [x] Evidence Map complete: every acceptance criterion has a status; PARTIALLY VERIFIED, UNVERIFIED, and FAILED items (if any) are named in the one-line status and detailed under Follow-up Items

## Follow-up Items

- Deviation 1 (equivalent procedure): `uv run` blocked in sandbox (uv cache `Operation not permitted`); all backend commands ran via `backend/.venv/bin/python -m ...` (same env, no sync; zero new deps). No action needed.
- Deviation 2 (plan order corrected): Task 7's "create_attempt then turns" order is impossible under the `conversation_id` FK on the new-conversation path; implemented turns-then-attempt (identical success-path behavior, preserves the no-empty-conversations invariant). No action needed.
- L4-1 first attempt needed `PYTHONPATH=.` (plain python lacks pytest's `pythonpath` config). Reflected in the recorded command. No action needed.
- Deployed volume DB now holds 1 practice attempt + 1 conversation + 4 turns from the browser E2E (deliberate minimal live-loop proof). Phase 4 demo seeding should account for (keep or wipe) these rows.
- Phase 4 seeding will add deployed lessons; owner may then click through the Practice-with-lesson browser path (fully covered here by L4-1 + `PracticeView.test.tsx`, so this is optional, not a gap).
- Next workflow step: `/review-execution` on this report (human manual verification + `/commit` after).

---

## Follow-up Validation (cycle 1)

Review: `.agents/execution-reports/reviews/shared-practice-loop-endpoints-practice-interview-views-execution-report-review.md` (Overall: NOT_VERIFIED — L4-3 browser gaps + schema.sql fresh-DDL evidence). No code changes; validations only. All findings addressed below.

### F1. schema.sql fresh-DB columns (direct evidence)

Concern: `_migrate` would mask a missing DDL, so boot-migration success only indirectly evidences `schema.sql`.
Check 1 (file content): `grep -n "conversation_id\|reference_json" backend/app/db/schema.sql` → lines 131-132 define both columns inside `CREATE TABLE attempts` (lines 144/152 are the pre-existing `turns` table, unrelated).
Check 2 (DDL-only init, NO `_migrate`): fresh `/tmp/fresh_ddl_probe.db` via `C.connect()` + `executescript(SCHEMA_PATH.read_text())` only, then `PRAGMA table_info(attempts)`.
Output (verbatim): `conversation_id in fresh DDL: True` / `reference_json in fresh DDL: True` / `schema_version: 2` (exit 0; probe DB deleted after).
Result: PASS — `schema.sql` alone creates both columns and version 2 on fresh DBs.

### F2. Practice-tab full loop in browser (L4-3 step 2)

Setup: deployed DB had 0 lessons, so per the delegated prompt I taught one via the Learn tab: concept `RAG` → ~3 min streamed generation → heading `RAG v1 explanation 4593544c…` with all 7 step buttons + marker/ask/regenerate controls. API confirms `explanations: [('RAG', 'v1')]`.
Practice tab: Lesson select listed `RAG (v1)`; selected it (Get question enabled); clicked Get question → Question card `Explain back: Pretend you're in an interview — in your own words, how would you explain how RAG produces an answer from external documents?` + Your-answer box.
Typed `RAG retrieves relevant passages and stuffs them into the prompt before generating.` → Submit → FeedbackCard: badge `general explanation`, all five sections (Correct/Missing/Inaccurate/Terminology help with e.g. `replace 'stuffs them into the prompt' with 'insert that retrieved text directly into the prompt as context'` / Next step with a concrete retry instruction), `Next question` button; history refreshed to `Practice history (1) · Retry queue (1)` with retry-queue entry + `Retry {id}` button and row `learning · RAG · Retry · general explanation`.
Result: PASS — full Practice loop observed in a real browser against the deployed app.

### F3. Technical question after kind switch (L4-3 step 4)

Interview tab → Technical radio → focus `APIs` → Get question → Question card: kind chip `technical`, question `Given your experience fixing a checkout timeout with retry and backoff instead of doubling the timeout, how would you design a resilient checkout API client that handles transient faults, ensures idempotency across retries, and exposes retry-count metrics?` (conceptual + personalized).
Answered `I would use retries with backoff and idempotency keys.` → FeedbackCard badge `both` (Terminology: `Specify 'exponential backoff with jitter'…`; Next step: `Add metrics for retry counts…`); history `Practice history (2) · Retry queue (2)` with row `interview/technical · Retry · both`.
Result: PASS — technical kind chip, conceptual question, teaching grounding badge, all observed.

### F4. Retry reload (L4-3 step 5)

In Practice, clicked `Retry 53572d84…` (the learning attempt, `needs_retry: true`) → question card reloaded with the attempt's exact question text, `Your answer` box present with Submit enabled.
Honest note on the delegated success line ("empty Your answer box"): the box was PREFILLED with the prior answer (`RAG retrieves relevant passages…`), not empty. That is the specified behavior — plan Task 18 / `PracticeView.tsx retryAttempt` sets `answerInput(attempt.answer ?? '')`, locked by `PracticeView.test.tsx` (`toBe('old answer')`). The substance (question reloads, ready to resubmit) holds; only the reviewer's "empty" wording differs from the approved spec. No code change made (spec-compliant behavior).
Result: PASS on substance, with the wording difference recorded here.

### Console + persistence

`browser_console_messages` level error after the full session: `Total messages: 0 (Errors: 0, Warnings: 0)`.
Deployed rows written THIS cycle: 1 explanation (RAG v1) + 2 attempts (learning, technical) + 2 conversations × 4 turns. Cumulative deployed practice data: 3 attempts, 3 conversations, 1 explanation (verified via `/api/v1/practice/attempts`, `/api/v1/conversations`, `/api/v1/learn/explanations`). Phase 4 seeding should account for these rows (supersedes the Follow-up Items note that cited 1 attempt).
Browser closed. No application-code changes, no commits, no PASS-validation reruns (no contradictions found).
