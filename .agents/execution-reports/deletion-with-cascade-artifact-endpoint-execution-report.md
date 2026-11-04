# Execution Report: deletion-with-cascade-artifact-endpoint

Plan: `.agents/plans/deletion-with-cascade-artifact-endpoint.md`
Review: `.agents/plans/reviews/deletion-with-cascade-artifact-endpoint-plan-review.md` (Overall: ✅ APPROVED)
Started: 2026-11-04

This report records every command run, every line of output, every validation result, and every deviation verbatim.

---

## Standing environment note

All `uv run` commands in this sandbox required `UV_CACHE_DIR=/tmp/uv-cache` (the default `~/.cache/uv` is outside the writable roots) plus `--no-sync` (deps already installed in `backend/.venv`; no dependency changes in this deliverable). This prefix is an environment equivalent, not a plan deviation in what was tested.

## Task 1: UPDATE backend/app/api/ingest.py

Edits: extended the `app.db.artifacts` import with `delete_artifacts_cascade` (BY NAME); added `ArtifactDeleteOut` (`deleted`/`unlinked` dicts); added `@router.delete("/artifacts/{artifact_id}")` after `get_artifact_endpoint` returning 404 when `counts["artifacts"] == 0`. Module docstring does not enumerate routes — untouched, per plan. `main.py` untouched (ingest router already registered).

Validation (plan one-liner, adapted — see Deviation 1):

```
$ cd backend && uv run python -c "from app.main import create_app; ..."
error: Failed to initialize cache at `/Users/natalie/.cache/uv`
  Caused by: failed to open file `/Users/natalie/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)
```

→ retried with `UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync` (see standing note). That run printed `0` instead of `1`. Investigation:

```
$ ... python -c "print(type(app), len(app.routes)); ..."
<class 'fastapi.applications.FastAPI'> 12
Route /openapi.json ['GET', 'HEAD']
...
_IncludedRouter None []
_IncludedRouter None []
```

The app flattens routers lazily (`_IncludedRouter`), so `app.routes` introspection sees no `APIRoute`s — including the pre-existing `DELETE /conversations/{id}`. Equivalent procedure via the OpenAPI table (same assertion: the DELETE operation is live on the real app object):

```
$ ... python -c "paths = create_app().openapi()['paths']; ..."
['delete', 'get']
conversations: ['delete', 'get']
```

Result: PASS via equivalent procedure (Deviation 1). `/api/v1/artifacts/{artifact_id}` serves `delete` + `get`.

## Task 2: UPDATE backend/tests/test_ingest_api.py

Added 4 tests reusing the file's `_client` fixture: `test_delete_artifact_happy_path_shape` (exact-dict lock), `test_delete_unknown_artifact_is_404` (DB untouched), `test_delete_artifact_twice_second_is_404`, `test_get_artifact_after_delete_is_404`.

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync pytest tests/test_ingest_api.py -q -k "delete"
....                                                                     [100%]
4 passed, 26 deselected in 0.76s
```

Result: PASS — `Expected: exit 0, "4 passed"`.

## Task 3: CREATE backend/tests/test_deletion.py

Created with `db` fixture, `_one_hot` / `_query_vec` / `_seed_note` / `_vec_rowids` helpers (mirrored from `test_conversation_memory.py`, local copies) and 5 tests: unlink multi-source fact (fact3 + bidirectional `fact_links` row assertions), vec/FTS row removal, artifact delete-then-query residue, conversation delete-then-query residue, direct-artifact-delete conversation asymmetry.

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync pytest tests/test_deletion.py -q -k "not no_evidence_mining"
.....                                                                    [100%]
5 passed in 0.76s
```

Result: PASS — `Expected: exit 0, "5 passed"`.

## Task 4: UPDATE backend/tests/test_deletion.py

Added `test_no_evidence_mining_rule_reaches_extraction_model` (`asyncio.run` runner mirrored from `test_extraction.py`; assertion (c) on `extract-v2` dropped per plan because `tests/test_extraction.py:191` already asserts it — verified by grep during execution). Docstring states PROVES/LIMITATIONS verbatim per plan.

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync pytest tests/test_deletion.py -q
......                                                                   [100%]
6 passed in 0.71s
```

Result: PASS — `Expected: exit 0, "6 passed"`.

## Task 5: UPDATE frontend/src/api/artifacts.ts (+ types.ts, artifacts.test.ts, client.ts docstring)

Added `deleteArtifact` (via verified `apiDelete` export), `ArtifactDeleteResponse` next to `ConversationDeleteResponse`, 2 unit tests mirroring `query.test.ts`; updated the `client.ts:43` docstring ("Conversation and artifact deletes go through here"). Grep confirmed no view/component imports `deleteConversation` or `deleteArtifact` — no view changes made, per plan.

```
$ cd frontend && npm test -- --run src/api/artifacts.test.ts
 ✓ src/api/artifacts.test.ts (4 tests) 3ms
 Test Files  1 passed (1)
      Tests  4 passed (4)
NO_VIEW_USAGE
```

Result: PASS — 4 passed (2 existing + 2 new delete tests).

## Validation L1: Syntax & Style

```
$ cd backend && ... ruff check .
All checks passed!
$ ... ruff format --check .
2 files would be reformatted, 69 files already formatted
```

Two files needed formatting (my new/edited test files); ran `ruff format` on the three touched files (`2 files reformatted, 1 file left unchanged`), then re-verified:

```
$ ... ruff check . && ... ruff format --check . && ... mypy app
All checks passed!
71 files already formatted
Success: no issues found in 38 source files
$ cd frontend && npm run lint
Found 0 warnings and 0 errors.
Finished in 30ms on 36 files with 116 rules using 8 threads.
```

Result: PASS — ruff check + format clean, mypy clean (38 files), oxlint 0/0.

## Validation L2: Unit Tests

```
$ cd backend && ... pytest tests/test_ingest_api.py tests/test_deletion.py -q
36 passed in 1.88s
$ cd backend && ... pytest -q
525 passed, 2 skipped in 11.95s
$ cd frontend && npm test -- --run
 Test Files  16 passed (16)
      Tests  130 passed (130)
```

Skip check (`pytest -q -rs`):

```
SKIPPED [1] tests/test_ingest_pipeline.py:300: needs network + ~90MB model
SKIPPED [1] tests/test_retrieval.py:358: needs network + ~90MB model
525 passed, 2 skipped in 12.18s
```

Result: PASS — targeted 36 passed (30 ingest incl. 4 new + 6 deletion); full backend 525 passed with only the 2 pre-existing network-gated skips (untouched files, unrelated to this deliverable); frontend 16 files / 130 tests all pass.

## Validation L3: Integration Tests + Build

Residue tests are inside L2 (`test_deletion.py` = the L3 gate, per plan). Build:

```
$ cd frontend && npm run build
✓ built in 199ms
$ ls frontend/dist/index.html
frontend/dist/index.html
```

Result: PASS — `tsc -b` clean + `vite build` emits `dist/`.

## Manual verification checklist (agent items)

```
$ cd backend && ... pytest tests/test_ingest_api.py -q -k delete -v     → 4 passed (Task 2 output above)
$ cd backend && ... pytest tests/test_deletion.py -q -v                 → 6 passed (Task 4 output above)
$ git diff --stat -- backend/app/db/                                     → (empty output)
$ git diff --stat -- frontend/src/views/ frontend/src/components/       → (empty output)
```

Result: PASS — endpoint live (L4-2 also proves it over HTTP below); F-10 shape locked; residue + retention proven; wiring test committed; zero `app/db/` drift; zero view/component change.

## Validation L4: Manual Validation (agent)

No local-server or browser steps: no browser-visible surface changed (plan records browser E2E as N/A, no redeploy). L4-1 and L4-2 ran as specified (uncommitted scripts under `/tmp`, scratch `/tmp` DBs — never the deployed volume DB; key loaded from `.env` inside the child process, never printed).

L4-2 delete smoke (`/tmp/tb_del4_delete_smoke.py`, real pipeline):

```
$ cd backend && TB_BACKEND=... uv run --no-sync python /tmp/tb_del4_delete_smoke.py
POST 201 {"artifact_id": "d06506561f4f4d2e870a33926ef61e20", "chunks": 1}
DELETE 200 {"deleted": {"artifacts": 1, "chunks": 1, "facts": 0}, "unlinked": {"facts": 0}}
GET 404
```

Result: PASS — `201` → `200` → `404` exactly as specified.

L4-1 live-model no-mining spot-check (`/tmp/tb_del4_mining_check.py`, real embedder + real Meta API over scratch DB; conversation: user "we talked through OAuth2 options for auth", assistant "I recommend migrating the auth service to OAuth2 with PKCE — I can draft the migration plan"):

```
$ cd backend && TB_BACKEND=... TB_ENV=... uv run --no-sync python /tmp/tb_del4_mining_check.py
indexed b86cfaeb9813433f9e6752aa23f6e7c6 chunks= 1
EXTRACT 200
{
  "facts": []
}
```

Result: PASS — `EXTRACT 200` with zero facts: no `kind=accomplishment` / `status=completed` claiming the assistant-suggested OAuth2 migration as done (absent = pass per plan). The live model declined to mine the assistant turn into any fact, consistent with the role rule. Non-gating observation recorded.

## Validation L5

None per plan (no UI change, no new dependencies). Dependency audits run once at submission, not per deliverable.

## Deviations

- **Deviation 1 (equivalent procedure, Task 1 validation):** the plan's `app.routes` introspection one-liner printed `0` because this app registers lazy `_IncludedRouter`s (pre-existing `DELETE /conversations/{id}` was equally invisible to it). Verified the same assertion — DELETE live on the real app object — via `create_app().openapi()['paths']` (`['delete', 'get']`), additionally proven over HTTP by L4-2. Same assertion, equivalent evidence.
- **Deviation 2 (environment, all `uv run` calls):** sandbox denies `~/.cache/uv` writes; all commands ran with `UV_CACHE_DIR=/tmp/uv-cache --no-sync` (deps pre-installed; no dependency changes). What was tested is unchanged.
- **No other deviations.** No scope widened; `ruff format` applied to the two new/edited test files only (formatting, no behavior change — suites re-run green after).

## Files created

- `backend/tests/test_deletion.py` (new; 6 tests)
- `/tmp/tb_del4_delete_smoke.py` (uncommitted L4-2 script; left in place for re-runs)
- `/tmp/tb_del4_mining_check.py` (uncommitted L4-1 script; left in place for re-runs)

## Files modified

- `backend/app/api/ingest.py` (import + `ArtifactDeleteOut` + `DELETE /artifacts/{artifact_id}`)
- `backend/tests/test_ingest_api.py` (4 endpoint tests)
- `frontend/src/api/artifacts.ts` (`deleteArtifact`)
- `frontend/src/api/types.ts` (`ArtifactDeleteResponse`)
- `frontend/src/api/artifacts.test.ts` (2 client tests)
- `frontend/src/api/client.ts` (docstring only)

## Evidence Map

Status each acceptance criterion from the plan. Implementation alone is never evidence — a criterion is VERIFIED only by recorded passing checks that establish the full criterion:

- VERIFIED: sufficient recorded evidence establishes that the criterion passed
- PARTIALLY VERIFIED: some relevant checks passed, but the full criterion was not established — state what passed and what remains
- UNVERIFIED: the criterion lacks adequate verification evidence — state what remains and give manual verification steps where appropriate
- FAILED: recorded validation demonstrates that the criterion was not met — state the failing evidence

- `DELETE /artifacts/{id}` returns the F-10 shape with exact keys → VERIFIED: `pytest tests/test_ingest_api.py -k delete` → 4 passed, incl. exact-dict `{"deleted": {"artifacts": 1, "chunks": N, "facts": 0}, "unlinked": {"facts": 0}}` lock; L4-2 over HTTP returned the same shape
- Unknown id → 404 with DB untouched; double delete → 404 → VERIFIED: same L2 run, both 404 tests passed (survivor list-count assertion proves untouched)
- Multi-source facts unlink while zero-support facts delete, links proven → VERIFIED: `test_deletion.py` unlink test passed with exact counts `{"artifacts": 1, "chunks": N, "facts": 1, "unlinked_facts": 1}`, zero `fact_links` rows touching fact1, surviving fact2→fact3 row
- Vec rows, FTS rows, and chunk rows for deleted artifacts are gone → VERIFIED: row-removal test passed (zero vec rowids, `[]` BM25 ids, `{}` from `get_chunks`)
- Post-delete queries never surface deleted content while retained content still retrieves → VERIFIED: artifact residue test passed (zero hits for deleted id on `hybrid_search`, ≥1 hit for retained id)
- Conversation deletion carries the same retrieval-level guarantees → VERIFIED: conversation residue test passed (`get_conversation` None, zero artifacts, zero `hybrid_search` hits)
- No-evidence-mining wiring committed (mechanism delivery only) → VERIFIED: `pytest tests/test_deletion.py -k no_evidence_mining` → 1 passed, asserting `CONVERSATION_ROLE_RULE` in system text + verbatim `User:`/`Assistant:` passages in the captured model-bound messages; PROVES/LIMITATIONS docstring in the test
- Live-model mining behavior observed and recorded (non-gating) → VERIFIED: L4-1 `EXTRACT 200` with `"facts": []` — no accomplishment/completed claim on the assistant-suggested migration (absent = pass); full JSON quoted above
- Frontend `deleteArtifact` mirrors `deleteConversation` with unit tests → VERIFIED: `npm test -- --run` → 16 files / 130 tests all pass incl. the 2 new artifacts tests; `npm run build` exit 0 with `dist/index.html` emitted
- Zero cascade-semantics drift and zero UI-surface change → VERIFIED: `git diff --stat -- backend/app/db/` empty; `git diff --stat -- frontend/src/views/ frontend/src/components/` empty
- Full suite + lint + format + typecheck green → VERIFIED: backend `525 passed, 2 skipped` (skips pre-existing network-gated, unrelated files); `ruff check` + `ruff format --check` clean; `mypy app` clean (38 files); `oxlint` 0 warnings 0 errors; frontend 130 passed
- Code follows project conventions → VERIFIED: thin router delegating to the untouched wrapper, BY-NAME import, no `chunks_fts` touch, mirrored fixtures/seams — all visible in the recorded diffs and green suites above

## Ready for Commit

- [x] All tasks completed
- [x] All validation commands passed
- [x] All tests passing
- [x] Evidence Map complete: every acceptance criterion has a status; PARTIALLY VERIFIED, UNVERIFIED, and FAILED items (if any) are named in the one-line status and detailed under Follow-up Items

## Follow-up Items

- None. No deviations outstanding (Deviation 1 + 2 documented above with equivalent evidence), no deferred items, no leftover edge cases. Uncommitted L4 scripts (`/tmp/tb_del4_delete_smoke.py`, `/tmp/tb_del4_mining_check.py`) and scratch DBs (`/tmp/tb_del4_*.db*`) retained for re-runs; scratch DBs hold only synthetic quokka/harbor/zephyrfield/OAuth2-fixture content.

## Follow-up Validation (cycle 1)

Delegated by the independent execution review (code-conventions criterion + `types.ts` file status were NOT_VERIFIED for lack of recorded diffs). Inspection only — no code changed, no PASS validations rerun.

### Task 1: backend conventions check — PASS

```
$ git diff -- backend/app/api/ingest.py
diff --git a/backend/app/api/ingest.py b/backend/app/api/ingest.py
index 8277713..ff4f093 100644
--- a/backend/app/api/ingest.py
+++ b/backend/app/api/ingest.py
@@ -20,7 +20,7 @@ from fastapi import APIRouter, File, HTTPException, UploadFile, status
 from pydantic import BaseModel, Field

 from app.core.config import get_settings
-from app.db.artifacts import get_artifact_detail, list_artifacts
+from app.db.artifacts import delete_artifacts_cascade, get_artifact_detail, list_artifacts
 from app.db.connection import EmbeddingDimMismatchError
 from app.ingest.adapters import (
     UndecodableUploadError,
@@ -83,6 +83,11 @@ class ArtifactDetailOut(BaseModel):
     interpretation_ids: list[str]


+class ArtifactDeleteOut(BaseModel):
+    deleted: dict[str, int]
+    unlinked: dict[str, int]
+
+
 @router.post("/artifacts", response_model=ArtifactCreated, status_code=status.HTTP_201_CREATED)
 def create_artifact(body: ArtifactCreate) -> ArtifactCreated:
     """Ingest typed/pasted text as a new artifact."""
@@ -197,3 +202,19 @@ def get_artifact_endpoint(artifact_id: str) -> ArtifactDetailOut:
         fact_ids=detail.fact_ids,
         interpretation_ids=detail.interpretation_ids,
     )
+
+
+@router.delete("/artifacts/{artifact_id}", response_model=ArtifactDeleteOut)
+def delete_artifact_endpoint(artifact_id: str) -> ArtifactDeleteOut:
+    """Delete an artifact with full derived cascade (chunks, orphaned facts)."""
+    counts = delete_artifacts_cascade(get_settings().database_path, [artifact_id])
+    if counts["artifacts"] == 0:
+        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found")
+    return ArtifactDeleteOut(
+        deleted={
+            "artifacts": 1,
+            "chunks": counts["chunks"],
+            "facts": counts["facts"],
+        },
+        unlinked={"facts": counts["unlinked_facts"]},
+    )

$ git diff --stat -- backend/app/main.py
(empty output)
```

Verdict: PASS. Justification per criterion: BY-NAME import on the `+from app.db.artifacts import delete_artifacts_cascade, ...` line; `ArtifactDeleteOut` carries both `dict[str, int]` fields; the `@router.delete(...)` route follows `get_artifact_endpoint`'s closing `)` (third hunk context); exactly one `delete_artifacts_cascade(get_settings().database_path, [artifact_id])` call with no pre-check; 404 with `detail="artifact not found"` on `counts["artifacts"] == 0`; `deleted` has exactly `artifacts/chunks/facts` and `unlinked` exactly `facts` (no `conversations`/`turns`); no transaction/logging lines; no `chunks_fts`/`chunks_vec` references; `main.py` diff empty.

### Task 2: frontend conventions check — PASS

```
$ git diff -- frontend/src/api/artifacts.ts frontend/src/api/types.ts frontend/src/api/client.ts
diff --git a/frontend/src/api/artifacts.ts b/frontend/src/api/artifacts.ts
index 610efe5..1891bfd 100644
--- a/frontend/src/api/artifacts.ts
+++ b/frontend/src/api/artifacts.ts
@@ -1,7 +1,12 @@
-import { apiGet } from './client'
-import type { ArtifactSummary } from './types'
+import { apiDelete, apiGet } from './client'
+import type { ArtifactDeleteResponse, ArtifactSummary } from './types'

 /** List artifacts with provenance metadata and derived counts. */
 export function listArtifacts(): Promise<ArtifactSummary[]> {
   return apiGet<ArtifactSummary[]>('/api/v1/artifacts')
 }
+
+/** Delete one artifact with full derived cascade. */
+export function deleteArtifact(id: string): Promise<ArtifactDeleteResponse> {
+  return apiDelete<ArtifactDeleteResponse>(`/api/v1/artifacts/${id}`)
+}
diff --git a/frontend/src/api/client.ts b/frontend/src/api/client.ts
index 3b597a5..3a0e211 100644
--- a/frontend/src/api/client.ts
+++ b/frontend/src/api/client.ts
@@ -40,7 +40,7 @@ export async function apiPut<T>(path: string, body: unknown): Promise<T> {
   )
 }

-/** Typed DELETE helper. Conversation (and future artifact) deletes go through here. */
+/** Typed DELETE helper. Conversation and artifact deletes go through here. */
 export async function apiDelete<T>(path: string): Promise<T> {
   return parseJson<T>(
     await fetch(apiUrl(path), {
diff --git a/frontend/src/api/types.ts b/frontend/src/api/types.ts
index 200948b..ba228b6 100644
--- a/frontend/src/api/types.ts
+++ b/frontend/src/api/types.ts
@@ -64,6 +64,11 @@ export interface ConversationDeleteResponse {
   unlinked: Record<string, number>
 }

+export interface ArtifactDeleteResponse {
+  deleted: Record<string, number>
+  unlinked: Record<string, number>
+}
+
 export interface ExplainRequest {
   concept: string
   familiar_system_hint?: string | null
```

Verdict: PASS. Justification per criterion: `deleteArtifact(id: string): Promise<ArtifactDeleteResponse>` calls `apiDelete` with `` `/api/v1/artifacts/${id}` `` and its JSDoc ("Delete one artifact with full derived cascade.") mirrors `deleteConversation`'s ("Delete one conversation with full derived cascade."); `ArtifactDeleteResponse` sits immediately after `ConversationDeleteResponse` with the identical `{ deleted; unlinked }` Record shape; the `client.ts` hunk changes one comment line only.

No findings, no deviations. Nothing was modified; both NOT_VERIFIED items are now evidenced by the recorded diffs above.

