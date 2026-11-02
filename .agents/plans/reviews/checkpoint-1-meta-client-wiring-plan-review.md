Overall: 🔁 NEEDS_REVISION

## Stage Summary

**Status:** Correction Limit Reached
**Corrections:** Cycle 4 truncation bound applied and verified fixed; this review raised 3 new findings instead
**Remaining issues:** Directory-DB edge case untested; garbage-DB step not executable for both endpoints; L4 steps 2-4 missing `cd backend`
**My next action:** Authorize a Cycle 5 correction run and I'll apply the 3 queued fixes plus re-verify, or accept as-is
Files: .agents/plans/checkpoint-1-meta-client-wiring.md | .agents/plans/reviews/checkpoint-1-meta-client-wiring-plan-review.md

### Structure

- ✅ **PASS** | Required sections: all 16 present
- ✅ **PASS** | Tasks have validation: all 10 tasks name validation
- ✅ **PASS** | Validation pass signals: 6 pass signals stated
- ✅ **PASS** | Acceptance criteria verifiable: 10/11 criteria name a verifying check
- ✅ **PASS** | Manual checks labeled: all 7 items labeled

### Checks

- ✅ **PASS** | Goal alignment: The plan wires one Meta client in core/, records muse-spark-1.3 in code and README, and gives honest health reporting, matching build-list deliverable 2 and the owner decisions recorded in Cycle 3.
- ✅ **PASS** | Problem definition: It states clearly that access was verified only outside the app and that there is no client module, no recorded model ID and no health endpoint.
- ✅ **PASS** | Implementation completeness: Every in-scope item has an atomic task with its own VALIDATE command: client, config default, read-only DB helper, two routers, factory wiring, both READMEs and the dependency promotion.
- ✅ **PASS** | Scope discipline: There are no LLM features, grounding contracts, frontend changes, deploy work or new env vars, and the liveness router is an owner-decided addition.
- ❌ **FAIL** | Acceptance criteria: The DB criterion claims 'garbage DB → db:false at 503 on both endpoints', but the garbage-DB step only curls /api/v1/health, so that claim is unverified for bare /health.
- ❌ **FAIL** | Validation coverage: The edge-case list claims a DATABASE_PATH pointing at a directory yields db:false, but no committed test or manual step exercises that case.
- ❌ **FAIL** | Validation quality: Two steps are not reproducible: L4 steps 2–4 omit `cd backend`, and the garbage-DB checklist step has no server start command, port, status-code capture or stop.
- ✅ **PASS** | Prerequisites: The scaffold (deliverable 1), httpx already in the lockfile, and the live key in .env are identified as existing, and no separate deliverable is absorbed.
- ✅ **PASS** | Design effectiveness: The design meets its stated purposes: a read-only mode=ro DB probe, a key-free liveness probe that never calls Meta, and a 503 with full JSON body when degraded.
- ✅ **PASS** | Performer labels: All manual steps are labeled agent and can be run by the agent with the live key present.

### Needs Attention

- Add a verification for the claimed 'DATABASE_PATH pointing at a directory → db:false' edge case, either a committed test using a tmp_path directory or an explicit removal of the claim.
- Make the garbage-DB manual step fully executable and also curl bare /health, so the 'garbage DB → 503 on both endpoints' acceptance claim is verified.
- Prefix L4 steps 2–4 with `cd backend` (or state the working directory), since `uv run uvicorn app.main:create_app` only resolves from backend/.

### Give to Builder

Copy the prompt below into the builder session as-is:

````
You are revising the feature plan for CHECKPOINT 1 — Meta Model API client wiring.

Plan file: `.agents/plans/checkpoint-1-meta-client-wiring.md`
Review file: `.agents/plans/reviews/checkpoint-1-meta-client-wiring-plan-review.md`

Standing rules:
- You may edit ONLY the plan file. No code changes, no other files, no commits.
- Do not proceed to implementation.
- Do not silently redefine requirements. If a correction would conflict with PRD.md or with an owner decision, escalate it instead of resolving it yourself.
- Report limitations honestly instead of inventing coverage.

Corrections:

1. Directory-path DB edge case.
   - Procedure: the Edge Cases section claims that a `DATABASE_PATH` pointing at a directory yields `db:false`. Either add a committed test to the `CREATE backend/tests/test_health.py` IMPLEMENT list (for example `test_directory_db_reported`: `DATABASE_PATH=str(tmp_path)` → 503, `db False`, `db_error` non-empty), or remove the directory claim from Edge Cases.
   - Success: every edge case listed in the plan is tied to a named committed test or to a manual step.

2. Garbage-DB step.
   - Procedure: rewrite the garbage-DB manual checklist item and its VALIDATION OUTPUT REFERENCE entry as a fully executable procedure. It must include:
     - `cd backend`;
     - creating the file with `head -c 64 /dev/urandom > /tmp/tb_cp1_garbage.db`;
     - an exact server start, e.g. `DATABASE_PATH=/tmp/tb_cp1_garbage.db uv run uvicorn app.main:create_app --factory --port 8127` plus `sleep 4`;
     - `curl -s -w '\nHTTP:%{http_code}\n'` against BOTH `/api/v1/health` and bare `/health`;
     - expected `HTTP:503`, `db false` and a non-empty `db_error` on both endpoints;
     - stopping the server and removing the file.
   - Success: the 'garbage DB → 503 on both endpoints' acceptance claim is verified for both endpoints.

3. Working directory for L4 steps 2–4.
   - Procedure: prefix each server start command in L4 steps 2, 3 and 4 with `cd backend &&`, or state that they run from `backend/`.
   - Success: every L4 command runs as written from the repo root.

Closing:
- Append a `### Cycle 5` entry under the existing `## Revision History` section at the end of the plan, and keep all prior cycle entries unchanged.
- In that entry, quote each finding addressed, describe what changed, and list anything not done with its reason.
- Report any limitations encountered.
````

---
*Reviewer: `claude-opus-5-5` via `https://api.anthropic.com/v1/messages` (one fresh-context call, model-managed sampling); plan `.agents/plans/checkpoint-1-meta-client-wiring.md` (59813 chars); context `PRD.md` (55098 chars), `.agents/plans/phase-1-build-list.md` (4026 chars), `.agents/plans/prime-summary.md` (4616 chars); generated 2026-11-01 23:50 UTC.*
