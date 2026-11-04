# Execution Report: tb-conversation-memory-adapter

Plan: `.agents/plans/tb-conversation-memory-adapter.md` (review APPROVED after Cycle 1; Cycle 1 applied both owner decisions + SearchHitOut test task).
Started: 2026-11-04. Full verbatim log below — every command, output, validation result, deviation.

---

## Deviation 1: `uv run` unusable in sandbox (equivalent procedure)

Command: `cd backend && uv run pytest --version`
Output (verbatim):
```
error: Failed to initialize cache at `/Users/natalie/.cache/uv`
  Caused by: failed to open file `/Users/natalie/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)
```
Resolution: all backend validation runs via the existing `backend/.venv/bin/python -m ...` directly (same interpreter/environment; no sync needed — this deliverable adds zero dependencies). Every plan command spelled `uv run X` below was executed as `.venv/bin/python -m X`. Attempted once per this deliverable to confirm the block; not retried.

## Task 1: ADD backend/app/ingest/adapters.py::adapt_conversation — DONE

Edits: `TB_CONVERSATION_SOURCE_TYPE`, `ROLE_TAGS`, `CONVERSATION_TITLE_CHARS` constants + `adapt_conversation(conversation_id, kind, turns, turn_start)` (verbatim content, first-user-title slice, exact origin keys).

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_adapters.py -q` (equivalent procedure per Deviation 1)
Output:
```
................                                                         [100%]
16 passed in 0.17s
```
(exit 0)

## Task 2: CREATE backend/app/ingest/conversation_memory.py — DONE

Created module with `index_conversation_turns(...)` delegating to `adapt_conversation` + `ingest_source`. (Test file lands in a later task; validation deferred there per plan.)

Sanity check:
Command: `cd backend && .venv/bin/python -c "from app.ingest.conversation_memory import index_conversation_turns; print('import ok')"`
Output (verbatim):
```
2026-11-04 05:02:02.539 Python[56569:15316475] 2026-11-04 05:02:02.539920 [W:onnxruntime:Default, telemetry_1ds.cc:600 operator()] Failed to persist telemetry device ID; using an in-memory identifier
import ok
```
(exit 0; onnxruntime telemetry line is environment noise, unrelated.)

## Task 3: ADD backend/app/db/chunks.py::get_chunk_source_types — DONE

Added `get_chunk_source_types` (batched JOIN reader; `ChunkDetail` untouched).

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_retrieval.py -q` (`tests/test_conversation_memory.py` does not exist yet — runs when that task lands)
Output:
```
......................s                                                  [100%]
22 passed, 1 skipped in 1.23s
```
(exit 0; the 1 skip is the pre-existing `TB_REAL_EMBEDDINGS` conditional skip at `tests/test_retrieval.py:358`, unrelated to this change.)

## Task 4: ADD backend/app/db/artifacts.py cascade helpers — DONE

Added `find_conversation_artifacts` (json_extract lookup), `_delete_artifacts_cascade_conn` (caller-owned-transaction shared core), and `delete_artifacts_cascade` wrapper. Minor judgment: added stdlib `import sqlite3` for the conn annotation (plan said no new imports; stdlib-only, no dependency impact). Chunks count uses collected-id length (FK cascade enforced by `connect()` guarantees deletion).

Validation (plan's `tests/test_conversation_memory.py` lands later; regression check now):
Command: `cd backend && .venv/bin/python -m pytest tests/test_ingest_api.py tests/test_accomplishments.py -q`
Output:
```
........................................                                 [100%]
40 passed in 1.82s
```
(exit 0)

## Task 5: ADD backend/app/db/conversations.py::delete_conversation_cascade — DONE

Added `ConversationDeleteCounts` + `delete_conversation_cascade` (single-transaction; same-connection artifact lookup + shared cascade core; None on unknown id). No circular import (`artifacts` never imports `conversations`).

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_conversations.py -q` (`tests/test_conversation_memory.py` lands later)
Output:
```
.......                                                                  [100%]
7 passed in 0.35s
```
(exit 0)

## Task 6: UPDATE backend/app/core/grounding.py role-rule contracts — DONE

Added shared `CONVERSATION_ROLE_RULE`, appended to `EVIDENCE_SYSTEM_PROMPT`, `EXTRACTION_SYSTEM_PROMPT`, and the experience-evaluation branch; bumped `EXTRACTION_PROMPT_VERSION` to `extract-v2`. Placement deviation (necessity): the plan said "directly above the extraction contract block", but `EVIDENCE_SYSTEM_PROMPT` (module top) must reference the constant, so it sits with the other shared framing constants after `UNTRUSTED_PASSAGE_FRAMING` — same semantics, valid evaluation order.

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_grounding.py -q`
Output:
```
....................................                                     [100%]
36 passed in 0.02s
```
(exit 0)
Command: `cd backend && .venv/bin/python -m pytest tests/test_extraction.py -q`
Output (tail):
```
tests/test_extraction.py:191: AssertionError
=========================== short test summary info ============================
FAILED tests/test_extraction.py::test_persist_receives_model_and_prompt_version
1 failed, 19 passed in 0.96s
```
(exit 0 overall for the chained call; the single failure is the `extract-v1` version assert fixed in the later version-bump task — expected at this stage.)

## Task 7: UPDATE backend/app/api/query.py (index hook + DELETE + source_type) — DONE

Edits: by-name `index_conversation_turns`/`get_chunk_source_types`/`delete_conversation_cascade` imports + docstring seams; `CitationOut.source_type` with batched hydration (direct index); index hook after turn persist (`turn_start` 0/continue); `DELETE /conversations/{id}` + `ConversationDeleteOut` F-10-mirror shape.

Required test fallout fixed in this task (additive-field + new-seam contract, same category as the plan's anticipated frontend fixture fallout): added autouse `_no_conversation_index` no-op stub to `tests/test_query_api.py` (hook tests re-stub with recorders later), and extended the exact-keys citation assert with `source_type`. Without the stub the suite would download the fastembed model (no cache at `~/.cache/fastembed`); the file header contract says the default suite never downloads it.

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_query_api.py -q`
Output:
```
...........................                                              [100%]
27 passed in 1.73s
```
(exit 0)

## Task 8: UPDATE backend/app/api/practice.py (index hooks + fresh-id capture) — DONE

Edits: by-name `index_conversation_turns` import + docstring seam; question hook after `create_attempt` (mode-derived kind, 0/continue `turn_start`); answer path now pre-fetches the conversation (`get_conversation` first; missing/None → fresh conversation with captured id, `turn_start=0`), then indexes. The pre-fetch also fixes the latent FK-crash on answering into a deleted conversation (now takes the fresh path).

Required test fallout fixed in this task: autouse `_no_conversation_index` no-op stub in `tests/test_practice_api.py` (same rationale as Task 7 — no fastembed download in the default suite).

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_practice_api.py -q`
Output:
```
......................                                                   [100%]
22 passed in 1.70s
```
(exit 0)

## Task 9: UPDATE backend/app/api/retrieval.py (source_type hydration) — DONE

Edits: `SearchHitOut`/`ChunkOut` gain `source_type`; batched hydration on search, single-id on chunk read; by-name seam + docstring line.

Required test fallout fixed in this task: two exact-keys asserts in `tests/test_retrieval_api.py` extended with `source_type` (additive-field contract).

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_retrieval_api.py tests/test_search.py -q`
Output:
```
...............................................                          [100%]
47 passed in 1.25s
```
(exit 0)

## Task 10: UPDATE backend/tests/test_extraction.py version assert — DONE

Bumped the one assert to `extract-v2`; grepped tests for prompt-text snapshots first (only keyword asserts exist — no other changes). Historical `extract-v1` fixture strings untouched.

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_extraction.py tests/test_work_api.py tests/test_accomplishments.py -q`
Output:
```
..............................................................           [100%]
62 passed in 2.41s
```
(exit 0)

## Task 11: ADD backend/tests/test_adapters.py conversation cases — DONE

Added 5 tests: exact two-turn transcript + origin, title slice (`text[:60]`-built expected), title fallback, verbatim tag/content preservation, both ValueErrors.

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_adapters.py -q`
Output:
```
.....................                                                    [100%]
21 passed in 0.13s
```
(exit 0)

## Task 12: ADD backend/tests/test_grounding.py role-rule cases — DONE

Added 6 tests: tag-constant equality, three-prompt governance + version, branch-exclusion lock, verbatim tag rendering, evidence-only builder rule, experience-eval builder rule.

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_grounding.py -q`
Output:
```
..........................................                               [100%]
42 passed in 0.10s
```
(exit 0)

## Task 13: CREATE backend/tests/test_conversation_memory.py — DONE

Created 9 tests: index shape/origin, hybrid_search round-trip with tags, source-type mapping, artifact filtering, unknown-delete None, full cascade (vec/FTS/facts/unlinked/attempt-NULL), multi-append delete, zero-artifact delete, wrapper smoke.

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_conversation_memory.py -q`
Output:
```
.........                                                                [100%]
9 passed in 0.67s
```
(exit 0)

## Task 14: ADD backend/tests/test_query_api.py hook + DELETE + source_type cases — DONE

Added 6 tests: index-call recording (contents/kind/turn_start 0), continue-path turn_start sequence, citation source_type value, DELETE happy path (exact F-10-mirror shape + 404 + artifact gone), DELETE unknown 404, index-failure 500 with turns persisted. Test-only fix: `_client` gained a `raise_server_exceptions` flag (default True) so the 500-propagation test observes the real 500 response instead of TestClient re-raising.

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_query_api.py -q`
Output:
```
.................................                                        [100%]
33 passed in 2.17s
```
(exit 0)

## Task 15: ADD backend/tests/test_practice_api.py hook cases — DONE

Added 6 tests: question hook (learning kind + turn_start sequence 0/2 + turn roles/question echo), interview-kind hook, answer hook (same conversation + pre-answer turn count), NULL-conversation fresh-at-0, deleted-conversation recovery (covers the FK-crash fix), answer 500-propagation with attempt recorded. Test-only: `_client` gained the same `raise_server_exceptions` flag as the query file.

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_practice_api.py -q`
Output:
```
............................                                             [100%]
28 passed in 1.71s
```
(exit 0)

## Task 16: ADD backend/tests/test_retrieval_api.py source_type cases — DONE

Added `test_search_hits_carry_exact_source_types`: note + conversation seeds, one term matching both, every hit asserts exact `source_type` (note vs `tb_conversation` distinguished by the `User:` tag in the excerpt), plus `GET /chunks` lock per hit.

Validation:
Command: `cd backend && .venv/bin/python -m pytest tests/test_retrieval_api.py -q`
Output:
```
...................                                                      [100%]
19 passed in 1.32s
```
(exit 0)

## Task 17: UPDATE frontend/src/api/types.ts + query.ts + query.test.ts — DONE

Edits: `apiDelete` helper in `client.ts` (no delete helper existed); `source_type` on `Citation`/`ChunkDetail` + `ConversationDeleteResponse` in types; `deleteConversation` in `query.ts`; 2 new client tests (URL+method+payload, non-OK rejection). Fixture fallout fixed in this task: `source_type: 'note'` added to all `Citation`/`ChunkDetail` literals in `ChatView.test.tsx` (3) and `WorkView.test.tsx` (1) — verified via grep that no other literals exist.

Validation:
Command: `cd frontend && npm test -- --run src/api/query.test.ts`
Output: `✓ src/api/query.test.ts (7 tests)`, `Test Files 1 passed (1)`, `Tests 7 passed (7)` (exit 0)
Command: `cd frontend && npm run build`
Output (tail): `✓ built in 102ms` (exit 0; `tsc -b` + vite green)

## Task 18: UPDATE frontend/src/views/ChatView.tsx + test (conversation badge) — DONE

Edits: citation chips render `<span aria-label="Conversation source"> (from a ThoughtBridge conversation)</span>` when `source_type === 'tb_conversation'`; citation panel renders the verbatim badge line under the same condition. Styling reuses existing neutral Tailwind classes only (no new visual identity).

Tests added (3): no badge for note citations, chip badge with verbatim text, panel badge (chip + panel = 2 badges, panel text exact).

Validation:
Command: `cd frontend && npm test -- --run src/views/ChatView.test.tsx`
Output: `Test Files 1 passed (1)`, `Tests 11 passed (11)` (exit 0)

## Task 19: UPDATE frontend/src/views/LearnView.tsx + WorkView.tsx (disclosure line) — DONE

Edits: verbatim `<p className="text-xs">Conversations are saved and retrievable.</p>` at the bottom of both view roots + one render assertion per view test.

Validation:
Command: `cd frontend && npm test -- --run src/views/LearnView.test.tsx src/views/WorkView.test.tsx`
Output: `Test Files 2 passed (2)`, `Tests 37 passed (37)` (exit 0)

## Validation ladder

### L1: Syntax & Style

Command: `cd backend && .venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .` (equivalent procedure)
Initial output: `Found 1 error.` (I001 unsorted import in new practice test) + `6 files would be reformatted, 64 files already formatted` (all 6 mine).
Fix: `.venv/bin/python -m ruff check --fix .` → `Found 1 error (1 fixed, 0 remaining).`; `.venv/bin/python -m ruff format <6 files>` → `6 files reformatted`.
Re-run output:
```
All checks passed!
70 files already formatted
```
(exit 0)

Command: `cd backend && .venv/bin/python -m mypy app`
Output: `Success: no issues found in 38 source files` (exit 0)

Command: `cd frontend && npx oxlint`
Output:
```
Found 0 warnings and 0 errors.
Finished in 30ms on 36 files with 116 rules using 8 threads.
```
(exit 0)

### L2: Unit Tests

Command: `cd backend && .venv/bin/python -m pytest tests/test_conversation_memory.py tests/test_adapters.py tests/test_grounding.py tests/test_conversations.py -q`
Output:
```
.......                                                                  [100%]
79 passed in 1.08s
```
(exit 0)

Command: `cd frontend && npm test -- --run src/api/query.test.ts src/views/ChatView.test.tsx`
Output: `Test Files 2 passed (2)`, `Tests 18 passed (18)` (exit 0)

### L3: Integration Tests

Command: `cd backend && .venv/bin/python -m pytest -q`
Output:
```
...s.................................................................... [ 97%]
.............                                                            [100%]
515 passed, 2 skipped in 11.85s
```
(exit 0; the 2 skips are the pre-existing `TB_REAL_EMBEDDINGS` conditional skips at `tests/test_ingest_pipeline.py:300` and `tests/test_retrieval.py:358` — verified via `-rs`)

Command: `cd frontend && npm test -- --run && npm run build`
Output: `Test Files 16 passed (16)`, `Tests 128 passed (128)` (exit 0); `✓ built in 73ms` (exit 0; `tsc -b` + vite green)

### L4-1: Live index → follow-up retrieval round-trip

Command: `DATABASE_PATH=/tmp/conv_memory_smoke.db PYTHONPATH=backend backend/.venv/bin/python /tmp/conv_memory_smoke.py` (with `MODEL_API_KEY` from `.env`; `PYTHONPATH=backend` replaces the plan's `cd backend` since the script lives in `/tmp` — same code under test)
First attempt without `PYTHONPATH` failed with `ModuleNotFoundError: No module named 'app'` (script-path issue, not product); reran with `PYTHONPATH=backend`.
Output (verbatim, minus onnxruntime telemetry noise):
```
Q1 mode: teaching citations: 0
Q2 mode: teaching
Q2 answer: We decided the session cache lives in Redis with a 5-minute TTL because Memcached lacked the eviction policy we need [1].
Q2 citations: [{"chunk_id": 1, "artifact_id": "45898b93579f45bb8e9938071c91ce4d", "span": [0, 299], "excerpt": "User: We decided the session cache lives in Redis with a 5-minute TTL because Memcached lacked the eviction policy we need. Remember this decision.\n\nAssistant: Understood — I'll remember that the session cache lives in Redis with a 5-minute TTL because Memcached lacked the eviction policy you need.", "source_type": "tb_conversation"}]
L4-1 retrieval asserts passed
Q3 answer (judge framing): I didn't make any suggestions about the session cache. You stated your decision that it lives in Redis with a 5-minute TTL because Memcached lacked the eviction policy you need and asked me to remember it [2].
L4-1 DONE
```
(exit 0. Q2 ran in a FRESH conversation — proves pipeline retrieval, not in-prompt history. Executor judgment on Q3: PASS — correctly attributes the decision to the user and denies making suggestions, exactly the recall-vs-evidence boundary.)

### L4-2: Live extraction role-asymmetry spot-check

Command: `DATABASE_PATH=/tmp/conv_extract_smoke.db PYTHONPATH=backend backend/.venv/bin/python /tmp/conv_extract_smoke.py` (with `MODEL_API_KEY` from `.env`)
Output (verbatim, minus onnxruntime telemetry noise):
```
conversation artifacts: 2
facts: [
 {
  "fact_id": "3071cde923be4e47897744f48b1f585e",
  "kind": "accomplishment",
  "status": "completed",
  "summary": "Shipped the Redis session-cache fix and merged PR 42",
  "skills": [
   "Redis session-cache fixing"
  ],
  "confidence": 1.0,
  "chunk_ids": [
   1
  ],
  "links": []
 },
 {
  "fact_id": "2ed9ca0ad6854b969760a88191db73d0",
  "kind": "problem",
  "status": "proposed",
  "summary": "Root cause was a missing cache invalidation on logout",
  "skills": [
   "root cause analysis"
  ],
  "confidence": 0.95,
  "chunk_ids": [
   2
  ],
  "links": []
 }
]
L4-2 DONE
```
(exit 0. Executor judgment: PASS — the completed accomplishment traces to the explicit user statement "I shipped ... merged PR 42"; no assistant suggestion became a fact; chunk-tag asserts passed.)

### Deploy + freshness

Command: `cd frontend && VITE_API_URL= npm run build`
Output: `✓ built in 71ms`; bundle `dist/assets/index-APJm85PM.js`

Command: `cd backend && .venv/bin/modal deploy modal_app.py`
Output (tail):
```
✓ Created objects.
├── ✓ Uploaded /Users/natalie/Documents/Agentic
│   AI/Projects/ThoughtBridge/backend/modal_app.py
├── ✓ Uploaded /Users/natalie/Documents/Agentic
│   AI/Projects/ThoughtBridge/frontend/dist
├── ✓ Uploaded /Users/natalie/Documents/Agentic
│   AI/Projects/ThoughtBridge/backend/app
└── ✓ Created Function serve
    └── https://the-natalie--thoughtbridge-serve.us-east.modal.run
        (unauthenticated)
✓ App deployed in 2.976s! 🎉

View Deployment: https://modal.com/apps/the-natalie/main/deployed/thoughtbridge
```
(exit 0)

Freshness verification:
```
DELETE-404:404
{"status":"ok","db":true,"meta_api":true,"model":"muse-spark-1.3","db_error":null,"meta_error":null}
assets/index-APJm85PM.js
```
New DELETE route live (404 JSON on nonexistent id), health ok with Meta reachable, served bundle hash matches the just-built `dist/` — deployment is fresh.

### L5: Playwright MCP browser E2E (fresh deployment)

Tool note: used the Playwright MCP browser per AGENTS.md (the agent-browser CLI daemon cannot run in the sandbox; project skill `agent-browser` loaded and its ref-based workflow mirrored via MCP).

Script (all against `https://the-natalie--thoughtbridge-serve.us-east.modal.run`):
1. Navigated; Chat view rendered with input, Send, and the disclosure line.
2. Asked "Our deploy checklist has seven items and lives in Notion. Remember this decision." → answered in 14s with one note citation chip `[1] Work log. I fixed the checkout timeout b` and NO conversation badge (correct — seeded note).
3. Asked follow-up "What did we decide about the deploy checklist?" → answered in 12s: "You decided the deploy checklist has seven items and lives in Notion [1]." with chip `[2] User: Our deploy checklist has seven ite (from a ThoughtBridge conversation)` — badge asserted present.
4. Clicked `Citation 2` → panel showed `Chunk 2 · artifact b685a4a5760b457b9f44d148e83dbb34 · span 0–369`, badge line `from a ThoughtBridge conversation`, and chunk text starting `User: Our deploy checklist has seven items and lives in Notion. Remember this decision. Assistant: Noted. ...` — role tags asserted present; 2 `Conversation source` badges on screen (chip + panel).
5. `browser_console_messages` level error → `Total messages: 0 (Errors: 0, Warnings: 0)`.

Cleanup (keeps the deployed volume as found): deleted the E2E conversation via the new live endpoint —
```
latest conversation: 6e9e9df66d784b33b2d1da2f14dd7277
{"deleted":{"conversations":1,"turns":4,"artifacts":2,"chunks":2,"facts":0},"unlinked":{"facts":0}}
re-get:404
```
(4 turns / 2 artifacts match this E2E session exactly; single-user demo volume; re-GET 404 confirms removal. This also exercises L4-3 step 4 live.)

### Manual checklist

- Backend ladder green: L1–L3 backend outputs above, zero failures. DONE.
- Frontend ladder green: oxlint + L2–L3 frontend outputs above, zero failures. DONE.
- Live round-trip + extraction spot-check: L4-1/L4-2 exit 0 with asserted values; scratch DBs deleted. DONE.
- Deployed UI walkthrough (L4-3 human): steps 1–4 performed as the L5 agent E2E above on the fresh deployment (badge, role tags, disclosure line rendered in Chat; delete-then-requery via live API) — owner may optionally repeat by hand; Learn/Work disclosure lines verified by unit tests + same-bundle deploy.
- Cascade proof:
```
.....                                                                    [100%]
5 passed, 4 deselected in 0.75s
229:def delete_artifacts_cascade(db_path: str, artifact_ids: list[str]) -> dict[str, int]:
```
DONE.
- No leftover scratch: `/tmp/conv_memory_smoke.db*` and `/tmp/conv_extract_smoke.db*` deleted (`ls /tmp/conv_*smoke.db*` → `No such file or directory`); `/tmp/conv_memory_smoke.py` + `/tmp/conv_extract_smoke.py` retained for re-runs per workspace policy (scratch scripts stay in /tmp, never in the repo). `git status --short` shows only intended files: 24 modified (8 backend app, 6 backend tests, 10 frontend) + 5 untracked (report, plan, plan review, `conversation_memory.py`, `test_conversation_memory.py`) — no `.env`, no `conversation-log/`, no lockfile/dependency changes. DONE.
- Zero-diff confirmations: `git diff --stat backend/pyproject.toml backend/uv.lock frontend/package.json frontend/package-lock.json` → empty; `git diff --stat backend/app/db/schema.sql backend/app/db/connection.py` → empty.

## Evidence Map

Status each acceptance criterion from the plan. Implementation alone is never evidence — a criterion is VERIFIED only by recorded passing checks that establish the full criterion:

- `adapt_conversation` produces exact role-tagged transcripts with correct origin/title → VERIFIED: `tests/test_adapters.py` 21 passed (5 new conversation cases: exact transcript, origin keys, title slice/fallback, ValueErrors).
- Index → hybrid_search round-trip retrieves the conversation chunk with tags in the excerpt → VERIFIED: `tests/test_conversation_memory.py::test_index_then_hybrid_search_finds_user_turn` passed (part of 9 passed); plus L4-1 live exit 0 with `tb_conversation` citation containing `User:` + `Redis` in a fresh conversation.
- All three write paths index exactly their new turns with correct kind + turn_start → VERIFIED: `tests/test_query_api.py` 33 passed (incl. turn_start 0/[0,2] recording tests); `tests/test_practice_api.py` 28 passed (incl. question/answer hooks, NULL + deleted-conversation fresh-at-0).
- Extraction, evidence-Q&A, and experience-evaluation prompts carry the shared role-asymmetry rule keyed on the exact `ROLE_TAGS` literals, with teaching/learning/technical branches excluded; version `extract-v2` → VERIFIED: `tests/test_grounding.py` 42 passed (6 new: tag equality, three-prompt governance, branch-exclusion lock, verbatim rendering, evidence-only + experience builder rules); `tests/test_extraction.py` version assert `extract-v2` passed (62 passed across extraction/work/accomplishments).
- `source_type` present on all citation/hit/chunk shapes → VERIFIED: `test_query_api.py` citation cases + `test_retrieval_api.py::test_search_hits_carry_exact_source_types` (note vs `tb_conversation` on hits + `GET /chunks` lock) passed; 19 passed in file.
- `DELETE /conversations/{id}` removes conversation + turns + all its artifacts + chunks/vec/FTS rows, deletes only zero-support facts, unlinks shared facts, NULLs attempt links, 404s unknown ids → VERIFIED: `test_conversation_memory.py` cascade tests (vec rowids gone, BM25 residue gone, shared-fact unlink counted, attempt NULLed) + `test_query_api.py` DELETE tests (exact F-10-mirror shape, 404) passed; live DELETE on deployed volume returned `{"deleted":{"conversations":1,"turns":4,"artifacts":2,"chunks":2,"facts":0},"unlinked":{"facts":0}}` + re-GET 404.
- `delete_artifacts_cascade` wrapper exists with the documented counts shape for deliverable 4 → VERIFIED: `grep -n "def delete_artifacts_cascade" backend/app/db/artifacts.py` → line 229 + wrapper smoke test passed (incl. empty-input zeros + dedupe).
- ChatView badges conversation citations + panel; Learn/Work show the disclosure line → VERIFIED: `ChatView.test.tsx` 11 passed (3 new badge cases), Learn/Work suites 37 passed (2 new disclosure cases); live Playwright E2E observed both badges + role tags on the fresh deployment with 0 console errors.
- Full backend + frontend suites green with zero regressions → VERIFIED: backend `515 passed, 2 skipped` (skips pre-existing `TB_REAL_EMBEDDINGS` gates); frontend `16 files / 128 tests passed` + `✓ built in 73ms`.
- Lint/type gates pass → VERIFIED: ruff `All checks passed!` + `70 files already formatted`, mypy `Success: no issues found in 38 source files`, oxlint `0 warnings and 0 errors`.
- Live index→retrieve→extract exchanges against the Meta API succeed on scratch DBs → VERIFIED: L4-1 exit 0 (fresh-conversation citation + judged Q3 framing PASS) and L4-2 exit 0 (2 artifacts, user-statement-only facts, judged PASS), both on isolated `/tmp` DBs, DBs deleted after.
- No new dependencies added → VERIFIED: `git diff --stat` over `pyproject.toml`/`uv.lock`/`package.json`/`package-lock.json` empty.
- No schema change → VERIFIED: `git diff --stat` over `schema.sql`/`connection.py` empty.
- Code follows project conventions → VERIFIED (executor judgment, pending independent review): thin routers, pure grounding additions, by-name seams + docstring lists, exact-JSON frontend types, single-transaction writes; independent confirmation at `/review-execution`.

## Ready for Commit

- [x] All tasks completed
- [x] All validation commands passed
- [x] All tests passing
- [x] Evidence Map complete: every acceptance criterion has a status; PARTIALLY VERIFIED, UNVERIFIED, and FAILED items (if any) are named in the one-line status and detailed under Follow-up Items

## Follow-up Items

- L4-3 human walkthrough was performed as the scripted L5 agent E2E on the fresh deployment (same steps + assertions, 0 console errors) plus a live API delete; the owner may optionally repeat it by hand after `/commit` — no blocking verification remains.
- Pre-existing conversations on the deployed volume were never indexed (planned no-backfill limitation); they stay unretrievable until re-discussed and are deletable with zero-count cascades (covered by `test_delete_conversation_without_artifacts_keeps_zeros`).
- Deliverable 4 handoff: call `delete_artifacts_cascade(db_path, ids)` (`backend/app/db/artifacts.py:229`) verbatim for `DELETE /artifacts/{id}`; mandatory delete-then-query residue + no-evidence-mining tests are deliverable 4's scope.
- `/tmp/conv_memory_smoke.py` and `/tmp/conv_extract_smoke.py` retained for re-runs (workspace policy); scratch DBs deleted.

## Follow-up Validation (cycle 1)

Delegated by the execution review (`NOT_VERIFIED` on L4-3 steps 3–4 as observed on the deployment). No code changes; no redeploy (same `index-APJm85PM.js` bundle throughout).

### Check 1: Deployed Learn/Work disclosure lines — PASS

Playwright MCP browser against `https://the-natalie--thoughtbridge-serve.us-east.modal.run`:
- Navigated (fresh load = hard refresh semantics for a new context); served script confirmed via DOM: `["/assets/index-APJm85PM.js"]` — same fresh bundle.
- Learn tab snapshot tail:
```
- paragraph [ref=f1e27]: Lessons are saved and reusable.
- paragraph [ref=f1e28]: Conversations are saved and retrievable.
```
- Work tab snapshot tail (after the accomplishments region):
```
- paragraph [ref=f1e58]: Conversations are saved and retrievable.
```
Exact text visible in both views. PASS.

### Check 2: Delete-then-requery on the deployment — PASS (one honest adaptation, see note)

All curl against `https://the-natalie--thoughtbridge-serve.us-east.modal.run/api/v1`:

1. Statement POST:
```
{"answer":"Noted: your staging database is named heron-staging-7.","citations":[],"mode_used":"teaching","conversation_id":"219f96783e874c739ed86de3e081750a"}
```
2. Follow-up POST (fresh conversation):
```
{"answer":"Our staging database is named heron-staging-7 [1].","citations":[{"chunk_id":2,"artifact_id":"1b570b97e0d641079a90b82b55e1d73c","span":[0,143],"excerpt":"User: Our staging database is named heron-staging-7. Remember this decision.\n\nAssistant: Noted: your staging database is named heron-staging-7.","source_type":"tb_conversation"}],"mode_used":"teaching","conversation_id":"f91c20d5c3d647e98bd23fa3076142e8"}
```
First follow-up cites the `tb_conversation` chunk (id 2, excerpt contains `heron-staging-7`). PASS.
3. DELETEs:
```
{"deleted":{"conversations":1,"turns":2,"artifacts":1,"chunks":1,"facts":0},"unlinked":{"facts":0}}
{"deleted":{"conversations":1,"turns":2,"artifacts":1,"chunks":1,"facts":0},"unlinked":{"facts":0}}
```
Both return the `{"deleted":{...},"unlinked":{...}}` shape. PASS.
4. Re-ask POST (fresh conversation):
```
{"answer":"The provided notes do not specify the staging database name.","citations":[],"mode_used":"teaching","conversation_id":"476536b350d64928800d5371a5ae5417"}
```
Zero citations + explicit refusal — no `heron-staging-7` citation from the deleted exchange. PASS.
5. Chunk-404 note (adaptation): `GET /chunks/2` returned 200, NOT 404 — because the re-ask's own turn-append was indexed and SQLite reused integer id 2 (max+1). The current row 2 is provably a different row:
```
{"id":2,"artifact_id":"21c5900a75d645598a92e905937d732e","chunk_idx":0,"span":[0,114],"text":"User: What is our staging database named?\n\nAssistant: The provided notes do not specify the staging database name.","source_type":"tb_conversation"}
```
(different `artifact_id` = the re-ask conversation's artifact; text is the re-ask transcript). The original row was deleted — ids are reused, rows are not resurrected. Additionally `GET /artifacts` shows 2 artifacts with zero `heron` title references. Equivalent evidence for "deleted content never surfaces": uncited re-ask + refusal + replaced row. PASS (adapted criterion, evidence quoted).
6. Cleanup DELETE + conversation census:
```
{"deleted":{"conversations":1,"turns":2,"artifacts":1,"chunks":1,"facts":0},"unlinked":{"facts":0}}
total: 3
mine remaining: []
```
All three created conversations removed; the 3 remaining are pre-existing volume conversations, untouched. Volume left as found. PASS.

No limitations; no human fallback needed. Both L4-3 steps now observed on the deployment.
