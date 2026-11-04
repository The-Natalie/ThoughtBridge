# Feature: deletion-with-cascade-artifact-endpoint

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Wire `DELETE /artifacts/{id}` (PRD F-10, Phase 3 build-list deliverable 4) to the existing shared cascade core, and add the two mandatory trust tests: delete-then-query residue proof and no-evidence-mining validation. Deliverable 3 already built the reusable core (`delete_artifacts_cascade`), the conversation-side cascade (`delete_conversation_cascade` + `DELETE /conversations/{id}`), and the role-asymmetry prompt rule — this deliverable wires the artifact endpoint, proves retrieval residue is zero, and validates no-evidence-mining via a committed wiring test (rule + tags reach the model) plus a live-model behavioral spot-check (L4, observed not gated). It decides no new cascade semantics and claims no deterministic behavioral enforcement.

## User Story

As a ThoughtBridge user
I want to delete a note or conversation and know everything derived only from it is gone while independently supported information stays
So that my memory store stays truthful and I can remove content with confidence.

## Problem Statement

`DELETE /artifacts/{id}` does not exist yet: artifacts are append-only via `POST /artifacts` with no removal path. The cascade core exists and is proven for conversations, but there is no artifact endpoint, no retrieval-level proof that deleted content never resurfaces, and no committed test proving the role-asymmetry prompt rule actually reaches the extraction model on the conversation-artifact path. Phase 3's validation gate requires both tests to pass.

## Scope

- In scope: `DELETE /artifacts/{id}` endpoint returning the F-10 shape; retrieval-level delete-then-query residue tests (artifact + conversation variants); no-evidence-mining wiring test over a conversation artifact; typed frontend `deleteArtifact` client mirror + unit test; full validation.
- Out of scope: any change to cascade semantics (frozen by the deliverable-3 handoff); deduplication/merging of equivalent facts (documented MVP limitation, PRD F-10); topic-wide deletion, automatic forgetting, editing, redaction; `explanations`/`attempts` deletion (no artifact linkage — owner-confirmed keep); user-facing Delete controls (owner decision 2026-11-04, plan review: assigned to deliverable 5, which owns the PRD §11 "delete content with visible cascade" demo requirement — this deliverable ships the endpoint + typed client the buttons will call; any deliverable-5 build-list scope amendment happens at deliverable-5 plan time, not here); rerank/HyDE (deliverable 6, default skip); backfill indexing of pre-existing conversations.

## Solution Statement

Add a thin `DELETE /artifacts/{id}` route on the existing ingest router that calls `delete_artifacts_cascade` verbatim and maps `artifacts == 0` to 404, returning `{"deleted": {"artifacts": 1, "chunks": N, "facts": M}, "unlinked": {"facts": K}}`. Prove the trust guarantees with two committed test groups in a new `backend/tests/test_deletion.py`: (1) delete-then-query residue tests seeding via the real pipeline with fake one-hot embeddings, asserting zero retrieval residue on both legs (BM25 + vector) plus 404s on artifact/chunk reads, with a conversation-delete variant proving identical guarantees; (2) a no-evidence-mining wiring test capturing the messages `run_extraction` hands its `chat_fn` over a role-tagged conversation artifact, asserting the shared `CONVERSATION_ROLE_RULE` and verbatim role tags reach the model. The wiring test proves mechanism delivery only — it does NOT prove the model obeys the rule; live-model obedience is observed (not gated) in the L4 spot-check. No committed test claims deterministic behavioral enforcement. Endpoint shape/404 tests extend `test_ingest_api.py` per the mirror convention; a live-model behavioral spot-check runs as an L4 agent step (not committed — model output is non-deterministic).

## Feature Metadata

**Feature Type**: Enhancement
**Estimated Complexity**: Low
**Primary Systems Affected**: `backend/app/api/ingest.py`, `backend/tests/` (new `test_deletion.py` + `test_ingest_api.py` additions), `frontend/src/api/` client mirror
**Dependencies**: none (cascade core, conversation cascade, role rule, and retrieval labeling all landed in deliverable 3)
**Assumptions**: cascade semantics frozen per the deliverable-3 handoff (verify by reading, do not redesign); `interpretations` table still never written (verify with grep — if it is now written, its FK cascade already covers it and no task changes); committed tests stay deterministic (live-model behavior stays in L4).

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `backend/app/db/artifacts.py` (lines 168-247) - Why: THE cascade core (`_delete_artifacts_cascade_conn`) + wrapper (`delete_artifacts_cascade`) the new endpoint calls verbatim; counts-dict shape defined here
- `backend/app/api/ingest.py` (lines 161-199) - Why: router the new route joins; GET 404 pattern (lines 181-182) and response-model style (lines 57-83) to mirror
- `backend/app/api/query.py` (lines 272-287) - Why: `DELETE /conversations/{id}` endpoint — exact response-assembly pattern (`deleted`/`unlinked` dicts) and 404 branch to mirror
- `backend/app/db/conversations.py` (lines 184-249) - Why: conversation cascade + counts dataclass; proves the "same guarantees" claim and the attempts-NULLed (not deleted) decision
- `backend/app/db/schema.sql` (lines 27-54, 62-97, 122-152) - Why: FK cascades, FTS5 sync triggers (never touch `chunks_fts` directly), fact_chunks join semantics, attempts/conversations SET NULL vs CASCADE split
- `backend/app/db/connection.py` (lines 21-30, 59-77) - Why: `connect` enforces FKs on every connection (cascade depends on this); `init_db` for test fixtures
- `backend/app/llm/extraction.py` (lines 178-211) - Why: `run_extraction` `chat_fn` seam — the capture point for the no-evidence-mining wiring test
- `backend/app/core/grounding.py` (lines 26-51, 404-438) - Why: shared `CONVERSATION_ROLE_RULE`, its inclusion in evidence/extraction prompts, `build_extraction_messages` passage rendering
- `backend/app/ingest/adapters.py` (lines 21, 67-99) - Why: `ROLE_TAGS` literals and `adapt_conversation` role-tagged content the rule keys on
- `backend/app/ingest/conversation_memory.py` (lines 19-38) - Why: `index_conversation_turns` — how the conversation-variant residue test seeds
- `backend/app/db/facts.py` (lines 32-97, 142-193) - Why: `create_facts` (multi-artifact support edges for the unlink test) and `get_facts_by_ids` (survivor assertion reads)
- `backend/app/retrieval/search.py` (lines 43-52, 105-125) - Why: `SearchHit` shape and `hybrid_search` signature (`embed_fn` stub) for the residue test
- `backend/app/db/chunks.py` (lines 21-47) - Why: chunk read helpers for survivor/residue assertions
- `backend/app/api/retrieval.py` (lines 98-102) - Why: chunk 404 branch the residue test asserts post-delete
- `backend/tests/test_conversation_memory.py` (whole file, esp. fixtures ~lines 37-60 and delete tests ~lines 197-390) - Why: fixture + fake-embedding + cascade-assertion patterns to mirror exactly
- `backend/tests/test_ingest_api.py` (lines 1-55) - Why: TestClient + stubbed-`ingest_source` fixture pattern the new endpoint tests extend
- `backend/tests/test_query_api.py` (lines 466-502) - Why: delete-endpoint API test pattern (happy path + 404) to mirror
- `backend/tests/test_grounding.py` (lines 250-270) - Why: existing role-rule branch lock (do not duplicate; the new test proves *wiring*, this one proves *content*)
- `backend/app/main.py` (lines 56-63) - Why: router registration — NO change needed (route joins the existing ingest router); read to confirm
- `frontend/src/api/client.ts` (lines 43-47) - Why: typed DELETE helper both delete clients use
- `frontend/src/api/query.ts` (line 32) + `frontend/src/api/query.test.ts` (lines 47-65) - Why: `deleteConversation` client + unit-test pattern to mirror for artifacts
- `frontend/src/api/artifacts.ts` + `frontend/src/api/artifacts.test.ts` + `frontend/src/api/types.ts` (~line 63) - Why: files the `deleteArtifact` mirror touches; read `types.ts` for the response-type convention
- `.agents/plans/phase-3-build-list.md` (deliverable 4, lines 27-31) - Why: authoritative scope boundaries for this deliverable
- `PRD.md` (F-10 §7 line 248; API §10 line 326; Phase 3 gate §12 lines 436-445) - Why: response shape, independent-support semantics, MVP limitation, gate criteria

### New Files to Create

- `backend/tests/test_deletion.py` - Independent-support + delete-then-query residue + no-evidence-mining wiring tests (cross-cutting by nature, hence one file)

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

Phase 3 research conclusion: this deliverable adds no dependencies and no new SQL techniques — the cascade core, FK enforcement, and FTS5 triggers already exist and are test-covered (`test_db_init.py`). No external research beyond these already-applied references:

- [SQLite Foreign Key Support](https://www.sqlite.org/foreignkeys.html)
  - Specific section: 4.3 ON DELETE actions (CASCADE / SET NULL)
  - Why: confirms the schema's cascade/SET-NULL split behaves as the plan assumes; executor confirmation only
- [SQLite FTS5 External Content Tables](https://www.sqlite.org/fts5.html#external_content_fts5_tables)
  - Specific section: delete trigger pattern for external-content tables
  - Why: confirms `chunks_fts_delete` trigger keeps the keyword leg residue-free with zero endpoint code; executor confirmation only

### Patterns to Follow

**Router pattern (thin, mirror `delete_conversation_endpoint` at `query.py:272-287`):**

```python
@router.delete("/conversations/{conversation_id}", response_model=ConversationDeleteOut)
def delete_conversation_endpoint(conversation_id: str) -> ConversationDeleteOut:
    counts = delete_conversation_cascade(get_settings().database_path, conversation_id)
    if counts is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    return ConversationDeleteOut(
        deleted={...},
        unlinked={"facts": counts.unlinked_facts},
    )
```

**Repository pattern (single transaction, caller-owned connection for shared core):** the wrapper `delete_artifacts_cascade(db_path, ids)` opens one connection and runs the conn-level core inside `with conn:` — the endpoint calls the wrapper and adds no transaction logic of its own.

**Naming Conventions:** `snake_case` backend modules/functions; `PascalCase` Pydantic models (`ArtifactDeleteOut`); `delete_*` repo functions returning counts; test names `test_delete_<what>_<expectation>`.

**Error Handling:** unknown id → 404 with `detail` (FastAPI default shape); never 200-with-zeros for a single-id delete. Upstream failures N/A (no model calls on this path).

**Logging Pattern:** repo-level `logger.info` with `key=%s` counts already exists in the wrapper — the endpoint adds no logging.

**Test seam pattern:** router symbols imported BY NAME (`from app.db.artifacts import delete_artifacts_cascade`) so tests *could* stub; but like the conversation-delete tests, these tests run the REAL cascade against a tmp DB (the cascade is what's under test — stubbing it would prove nothing).

**Other Relevant Patterns:** FTS rows follow via schema triggers — code never touches `chunks_fts` directly (stated in both `store_artifact` and the cascade core docstrings); vec rows deleted explicitly (vec0 has no FK); `unlinked_facts = affected - deleted`.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

No foundation work: schema, cascade core, conversation cascade, role rule, retrieval, and fixtures all exist. The executor's first act is reading the CONTEXT REFERENCES files above (especially `artifacts.py:168-247`) and confirming the two Assumptions (grep `INSERT INTO interpretations` expecting zero hits; confirm no `DELETE /artifacts` route exists yet).

**Tasks:**

- Confirm Assumptions and read context files (no code changes)

### Phase 2: Core Implementation

**Tasks:**

- Add `DELETE /artifacts/{id}` to the ingest router calling the wrapper verbatim
- Add endpoint contract tests (200 shape, 404 unknown, double-delete 404, GET-after-delete 404)
- Add independent-support + delete-then-query residue tests incl. conversation variant
- Add no-evidence-mining wiring test over a conversation artifact
- Add frontend `deleteArtifact` client mirror + type + unit test

### Phase 3: Integration

No integration work: the route joins the already-registered ingest router (`main.py` unchanged — verify, do not edit); no config, middleware, or migration. Frontend client is additive with no callers yet (same precedent as `deleteConversation`, which no view calls — delete buttons belong to deliverable 5's visibility pass, explicitly out of scope here).

**Tasks:**

- Verify `main.py` needs no change (read-only check inside Task 1 validation)

### Phase 4: Testing & Validation

**Tasks:**

- Run backend suite + lint + format + typecheck
- Run frontend tests + build
- Run L4 agent live-model mining spot-check (TestClient + real key + scratch DB, uncommitted script under `/tmp`)

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

### UPDATE backend/app/api/ingest.py

- **IMPLEMENT**: ADD `ArtifactDeleteOut` Pydantic model (`deleted: dict[str, int]`, `unlinked: dict[str, int]` — MIRROR `ConversationDeleteOut` in `query.py`) and ADD `@router.delete("/artifacts/{artifact_id}", response_model=ArtifactDeleteOut)` endpoint AFTER `get_artifact_endpoint`: call `delete_artifacts_cascade(get_settings().database_path, [artifact_id])` (import BY NAME from `app.db.artifacts`, extending the existing `from app.db.artifacts import get_artifact_detail, list_artifacts` line); if `counts["artifacts"] == 0` raise 404 `detail="artifact not found"`; else return `deleted={"artifacts": 1, "chunks": counts["chunks"], "facts": counts["facts"]}, unlinked={"facts": counts["unlinked_facts"]}`. Also update the module docstring's route list IF it enumerates routes (check first — only touch if it does).
- **PATTERN**: `backend/app/api/query.py:272-287` (endpoint shape + 404 branch); `backend/app/api/ingest.py:177-199` (sibling route placement + 404 detail style)
- **IMPORTS**: extend existing `from app.db.artifacts import ...` with `delete_artifacts_cascade` (BY NAME — seam convention, even though tests run the real function)
- **GOTCHA**: the 404 signal is `counts["artifacts"] == 0` (wrapper returns all-zero dict for unknown ids) — do NOT pre-check existence with a separate query (extra round-trip + TOCTOU smell; single-writer MVP still prefers the single call). An artifact with zero chunks still returns `artifacts: 1` → 200, correctly. Response keys are the F-10-exact subset: `artifacts/chunks/facts` + `unlinked.facts` — do NOT add `conversations`/`turns` keys (conversation endpoint's additive extras, not this endpoint's). Do NOT touch `main.py` (ingest router already registered). Do NOT touch `chunks_fts` / `chunks_vec` (core handles both).
- **VALIDATE**: `cd backend && uv run python -c "from app.main import create_app; r=[x for x in create_app().routes if getattr(x,'path',None)=='/api/v1/artifacts/{artifact_id}' and 'DELETE' in getattr(x,'methods',[])]; print(len(r))"` — `Expected: exit 0, "1"`

### UPDATE backend/tests/test_ingest_api.py

- **IMPLEMENT**: ADD four endpoint tests reusing the file's existing `_client` fixture (stubbed `ingest_source` runs the REAL pipeline with fake vectors; deletion path needs no stub — real cascade on tmp DB): (1) `test_delete_artifact_happy_path_shape`: POST a note, DELETE it → 200 + `deleted == {"artifacts": 1, "chunks": >=1, "facts": 0}` + `unlinked == {"facts": 0}` (exact-equality on the full `deleted` dict — locks the F-10-exact key set); (2) `test_delete_unknown_artifact_is_404`: DELETE `"0"*32` → 404 + DB untouched (POST-then-list count unchanged, or `GET /artifacts` still lists the surviving seed); (3) `test_delete_artifact_twice_second_is_404`: DELETE → 200, DELETE again → 404; (4) `test_get_artifact_after_delete_is_404`: POST, DELETE, GET same id → 404. All asserts on `response.status_code` + `response.json()` only.
- **PATTERN**: `backend/tests/test_query_api.py:466-502` (delete-endpoint test shape incl. exact-dict assertion); `backend/tests/test_ingest_api.py:22-55` (fixture reuse — do NOT create a second fixture)
- **IMPORTS**: none new (file already imports `pytest`, `TestClient` machinery, `_client`)
- **GOTCHA**: tests must create artifacts through `POST /api/v1/artifacts` (exercises the real pipeline incl. vec rows), NOT by direct repo calls — the residue tests in `test_deletion.py` cover repo-level seeding. 32-hex-char fake id for the 404 case (matches uuid4hex shape; no format validation exists so any string 404s, but keep it realistic).
- **VALIDATE**: `cd backend && uv run pytest tests/test_ingest_api.py -q -k "delete"` — `Expected: exit 0, "4 passed"`

### CREATE backend/tests/test_deletion.py

- **IMPLEMENT**: CREATE the file with: module docstring (`Independent-support cascade + delete-then-query residue + no-evidence-mining wiring. Tmp DBs with fake one-hot passage embeddings (mirrors test_conversation_memory.py); no network, no fastembed model.`); `DIM`/`MODEL`/`MAXC` constants; `db` fixture (`tmp_path / "deletion.db"`, `init_db`); `_one_hot()` embed factory + `_query_vec()` fixed query vector + `_seed_note(db, content, embed)` helper (MIRROR `test_conversation_memory.py` fixtures — same semantics, local copies, no cross-test imports). Then the tests: (1) `test_delete_artifact_unlinks_multi_source_fact`: seed notes A (distinctive term e.g. `quokka`) + B; `create_facts` with fact1 chunk_ids=[A-chunk], fact2 chunk_ids=[A-chunk, B-chunk], fact3 chunk_ids=[B-chunk], plus `fact_links` fact1→fact2 (outgoing from the doomed fact) and fact2→fact3 (survivor→survivor); call `delete_artifacts_cascade(db, [A])`; assert counts `{"artifacts": 1, "chunks": len(A-chunks), "facts": 1, "unlinked_facts": 1}` exactly; assert `get_facts_by_ids` shows fact1 gone, fact2 alive with chunk_ids == [B-chunk] only, fact3 alive; assert via `connect()` that `SELECT COUNT(*) FROM fact_links WHERE from_fact_id = fact1 OR to_fact_id = fact1` == 0 (links touching the deleted fact cascade in BOTH directions) and that the fact2→fact3 row still exists (exactly one row, same relation — survivor→survivor links intact); (2) `test_delete_artifact_removes_vec_and_fts_rows`: seed A; collect chunk ids; delete; assert `SELECT COUNT(*) FROM chunks_vec WHERE rowid IN (...)` == 0, `search_bm25_ids(db, build_fts_match("quokka"), 10)` contains no A-chunk ids, `get_chunks(db, A-chunks)` == {}; (3) `test_delete_then_query_never_surfaces_deleted_content`: seed A (distinctive `quokka deployment ledger`) + B (`harbor tide schedule`); DELETE A via `delete_artifacts_cascade`; `hybrid_search(db_path=db, query="quokka deployment ledger", top_k=8, embedding_model=MODEL, embed_fn=_query_vec)` returns zero hits with `artifact_id == A`; same query for B's terms still returns B's chunks (independently supported information REMAINS — assert ≥1 hit with `artifact_id == B`); (4) `test_delete_conversation_then_query_never_surfaces_turns`: `create_conversation_with_turns` (user turn with distinctive term e.g. `zephyrfield decision`, assistant turn) + `index_conversation_turns` (fake embed, `turn_start=0`); `delete_conversation_cascade`; assert `get_conversation` is None AND `hybrid_search(... "zephyrfield decision" ...)` returns zero hits AND `find_conversation_artifacts(db, cid)` == []; (5) `test_delete_conversation_artifact_directly_keeps_conversation_row`: index a conversation, then `delete_artifacts_cascade` on its artifact id directly; assert artifact/chunks gone but `get_conversation(db, cid)` still returns turns (documents the intentional asymmetry: conversation-delete cascades to artifacts, artifact-delete does not cascade upward to the conversation).
- **PATTERN**: `backend/tests/test_conversation_memory.py:37-60` (fixtures), `:209-390` (cascade assertion style incl. `connect()` row-count checks); `backend/app/retrieval/search.py:105-125` (`hybrid_search` kwargs); `backend/app/db/facts.py:32-97` (`create_facts` items shape `(fact_id, FactCreate, links)` with caller-generated `uuid.uuid4().hex` ids)
- **IMPORTS**: `uuid`, `pytest`, `pathlib.Path`, `init_db`/`connect` (connection), `delete_artifacts_cascade`/`find_conversation_artifacts` (artifacts), `delete_conversation_cascade`/`create_conversation_with_turns`/`get_conversation` (conversations), `FactCreate`/`FactLinkCreate`/`create_facts`/`get_facts_by_ids` (facts), `get_chunks` (chunks), `search_bm25_ids` (chunks), `ingest_source` (pipeline), `index_conversation_turns` (conversation_memory), `hybrid_search`/`build_fts_match` (search)
- **GOTCHA**: one-hot embed factory MUST be per-test fresh state (closure counter) so passage vectors are distinct; the query stub returns a FIXED vector (e.g. all-ones normalized or the same one-hot slot) — what matters is deleted rowids can never score, not that the vector is meaningful. `create_facts` needs `model="test"` + `prompt_version="extract-v2"` args (any strings; use realistic ones). `hybrid_search` requires non-blank query + `1 <= top_k <= TOP_K_MAX` (router-enforced in prod; test passes valid values). Do NOT re-test attempts-NULLing or multi-append conversation deletion (covered in `test_conversation_memory.py:290-360` — verify-only, no duplicates). Do NOT assert anything about `explanations`/`attempts` deletion (owner-confirmed keep). Future-proofing note for span-level editing: this task changes no chunk-span storage — nothing to do, do not add span machinery.
- **VALIDATE**: `cd backend && uv run pytest tests/test_deletion.py -q -k "not no_evidence_mining"` — `Expected: exit 0, "5 passed"` (Task 4 adds the 6th test; rerun unfiltered after Task 4)

### UPDATE backend/tests/test_deletion.py

- **IMPLEMENT**: ADD `test_no_evidence_mining_rule_reaches_extraction_model` (async — check how `test_extraction.py` runs `run_extraction`: if it uses `asyncio.run` or `anyio`/`pytest.mark.asyncio`, MIRROR that file's runner exactly): seed a conversation via `create_conversation_with_turns` + `index_conversation_turns` where the ASSISTANT turn proposes something the user never confirms (e.g. assistant: `I suggest migrating the auth service to OAuth2` / user: `we discussed auth options`); resolve the artifact id via `find_conversation_artifacts`; define capturing `async def fake_chat(messages, max_tokens)` recording `messages` and returning `'{"facts": []}'`; call `run_extraction(artifact_ids=[...], db_path=db, chat_fn=fake_chat, career_fn=no_career, model="test-model")`; assert (a) the system message contains the full `CONVERSATION_ROLE_RULE` constant (import from `app.core.grounding` — membership, not retyped text), (b) the user message contains `ROLE_TAGS["assistant"]` + the assistant's suggestion text verbatim AND `ROLE_TAGS["user"]` (import `ROLE_TAGS` from `app.ingest.adapters` — proves the tags the rule keys on are present in what the model sees), (c) `EXTRACTION_PROMPT_VERSION == "extract-v2"` (import from `app.core.grounding` — first verify no existing test already asserts this; if one does, drop assertion (c) instead of duplicating). Docstring on the test MUST state PROVES and LIMITATIONS explicitly: PROVES — the shared rule paragraph and the literal role tags it keys on are handed to the model on the extraction-over-conversation path (mechanism delivery). LIMITATIONS — does not prove the model obeys the rule; behavioral obedience is observed in the L4 live-model spot-check only, which is non-deterministic and non-gating by design; no deterministic behavioral enforcement exists or is claimed (owner decision 2026-11-04: prompt-based enforcement from deliverable 3 stands for the MVP).
- **PATTERN**: `backend/tests/test_grounding.py:250-263` (constant-membership assertion style — MIRROR, do not duplicate its branch coverage); `backend/app/llm/extraction.py:178-211` (`run_extraction` signature: `chat_fn(messages, max_tokens)` positional, `career_fn=no_career` importable from `app.llm.extraction`)
- **IMPORTS** (add to the Task 3 file): `CONVERSATION_ROLE_RULE`, `EXTRACTION_PROMPT_VERSION` (core.grounding), `ROLE_TAGS` (ingest.adapters), `no_career`, `run_extraction` (llm.extraction)
- **GOTCHA**: the stub returns ZERO facts — this test asserts on what the model was GIVEN (captured messages), never on mined output (asserting on stub output would prove nothing — the stub is ours). Do NOT add code-side citation filtering (e.g. rejecting facts that cite assistant-tagged chunks) — deliverable 3 explicitly decided prompt-only enforcement ("excluding assistant chunks would break 'what did you suggest' recall"); a structural change here would contradict a frozen decision and break recall. If the async runner needs a plugin (e.g. `anyio`), confirm it is already a dev dependency — never add a dependency for one test; fall back to `asyncio.run(...)` inside a sync test.
- **VALIDATE**: `cd backend && uv run pytest tests/test_deletion.py -q` — `Expected: exit 0, "6 passed"`

### UPDATE frontend/src/api/artifacts.ts

- **IMPLEMENT**: ADD `deleteArtifact(id: string): Promise<ArtifactDeleteResponse>` calling the typed DELETE helper with `/api/v1/artifacts/${id}` (MIRROR `deleteConversation` in `query.ts:32` exactly, including JSDoc style); ADD `ArtifactDeleteResponse` type to `frontend/src/api/types.ts` next to `ConversationDeleteResponse` (`{ deleted: Record<string, number>; unlinked: Record<string, number> }` — read `types.ts` first and match its exact conventions); ADD two unit tests to `frontend/src/api/artifacts.test.ts` MIRRORING `query.test.ts:47-65` (resolves payload + asserts `init.method === 'DELETE'` and URL path; rejects on non-OK). Update the `client.ts:43` docstring ONLY if it names specific callers (read first — if it says "future artifact deletes", update it to name both).
- **PATTERN**: `frontend/src/api/query.ts:32`, `frontend/src/api/query.test.ts:47-65`, `frontend/src/api/client.ts:43-47`
- **IMPORTS**: `apiDelete` (verify exact export name in `client.ts` before writing), `ArtifactDeleteResponse` type
- **GOTCHA**: NO view changes — no delete buttons anywhere (no artifact-list surface exists; delete UI belongs to deliverable 5's visibility pass). The new client function has no callers yet — same precedent as `deleteConversation` (verify with grep that no view imports it; if a view DOES import deleteConversation by now, do NOT add an artifact button anyway — out of scope, note it in the report).
- **VALIDATE**: `cd frontend && npm test -- --run src/api/artifacts.test.ts` — `Expected: exit 0, all tests passed (2 new delete tests among them)`

---

## TESTING STRATEGY

Deterministic behavior gets unit/integration tests with fake embeddings and stubbed model boundaries; the live model is exercised only in L4 (agent, uncommitted). No new test infrastructure — all fixtures mirror `test_conversation_memory.py` / `test_ingest_api.py`.

### Unit Tests

- Endpoint contract (`test_ingest_api.py` additions): 200 shape with exact-dict key lock, 404 unknown, double-delete 404, GET-after-delete 404.
- Cascade semantics (`test_deletion.py`): independent-support unlink-vs-delete with link cleanup; vec + FTS row removal; direct-artifact-delete conversation asymmetry.

### Integration Tests

- Delete-then-query residue (`test_deletion.py`, real pipeline + real `hybrid_search` with one-hot fakes): artifact variant proves both retrieval legs are residue-free while retained content still retrieves; conversation variant proves identical guarantees through `DELETE /conversations/{id}`.
- No-evidence-mining wiring (`test_deletion.py`): proves the enforcement mechanism (shared rule + verbatim role tags) is actually handed to the model on the extraction-over-conversation path.

### Edge Cases

- Unknown id → 404 with DB untouched (must hold: zeros must never masquerade as success).
- Double delete → second is 404 (idempotency is explicit non-goal; 404 is the contract).
- Artifact with zero facts → `facts: 0, unlinked.facts: 0` (no crash on empty affected set).
- Multi-source fact → survives with only retained chunk_ids; `unlinked.facts` counts it.
- Fact links touching a deleted fact cascade in both directions; links between survivors intact (covered via direct `fact_links` row-count assertions: zero rows touching fact1, surviving fact2→fact3 row).
- `tb_conversation` artifact deleted directly → conversation row + turns survive (intentional upward asymmetry, locked by test).
- Conversation delete keeps attempt rows with NULLed `conversation_id` (already covered in `test_conversation_memory.py` — verify-only, no new test).
- `interpretations` rows linked to a deleted artifact cascade via FK (vacuous while the table is never written — verified by grep, no test).
- `explanations`/`attempts`/`reference_json` untouched by artifact deletion (frozen decision — no test asserts deletion; the residue tests assert retained-content retrieval still works).

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

Every command or block MUST state its exact pass signal on an `Expected:` line (exit code plus the key output, count, or observation that proves success — e.g. `Expected: exit 0, "11 passed"`, `Expected: exit 0, docs:200`). A check whose passing output is not specified cannot confirm anything; do not write checks you cannot describe passing.

### Level 1: Syntax & Style

- `cd backend && uv run ruff check . && uv run ruff format --check .`
  - `Expected: exit 0, "All checks passed!" + "N files already formatted" (ruff's exact success lines)`
- `cd backend && uv run mypy app`
  - `Expected: exit 0, "Success: no issues found in N source files"`
- `cd frontend && npx oxlint 2>&1 | tail -3` (only if `package.json` shows an oxlint script/executor-confirmed equivalent; otherwise skip with reason recorded)
  - `Expected: exit 0, no errors`

### Level 2: Unit Tests

- `cd backend && uv run pytest tests/test_ingest_api.py tests/test_deletion.py -q`
  - `Expected: exit 0, "4 passed" (ingest delete subset) + "6 passed" (deletion file) within the total — record the exact total in the report`
- `cd backend && uv run pytest -q`
  - `Expected: exit 0, full suite passes (record exact count, e.g. "NNN passed"); zero failures, zero regressions in conversation/practice/work suites`
- `cd frontend && npm test -- --run`
  - `Expected: exit 0, all test files pass (record exact count); the 2 new artifacts delete tests among them`

### Level 3: Integration Tests

- Covered inside L2: `test_deletion.py` residue tests ARE the integration tests (real pipeline → real cascade → real `hybrid_search`). No separate L3 command.
  - `Expected: (same L2 pass signal — the 6-test file passing IS the L3 gate)`
- `cd frontend && npm run build`
  - `Expected: exit 0, `tsc -b` clean + `vite build` emits `dist/` (proves the new client/type code typechecks)`

### Level 4: Manual Validation

No local-server steps: sandboxed sessions deny TCP bind, so Uvicorn/Vite cannot run here (per AGENTS.md — do NOT attempt them; the one-attempt block confirmation was already recorded by earlier deliverables, never re-probe). No redeploy: this deliverable changes no browser-visible surface (no view edits), so there is nothing Playwright could verify that committed tests don't — record "browser E2E N/A (no UI change)" rather than redeploying.

- Performer: `agent` — L4-1 live-model no-mining spot-check (TestClient + real key + scratch DB, uncommitted script under `/tmp`):
  1. `export $(grep -v '^#' .env | xargs)` from the repo root ONLY to obtain `MODEL_API_KEY` for the child process env (never print it, never commit anything containing it);
  2. write `/tmp/tb_del4_mining_check.py`: builds a TestClient over a scratch `/tmp` DB (mirroring `test_work_api.py` settings isolation but WITHOUT stubbing `chat_completion`), seeds one conversation via `create_conversation_with_turns` (user: `we talked through OAuth2 options for auth`, assistant: `I recommend migrating the auth service to OAuth2 with PKCE — I can draft the migration plan`) + `index_conversation_turns` with the REAL embedder, then `POST /work/extract` with the conversation's artifact id;
  3. run `cd backend && uv run python /tmp/tb_del4_mining_check.py`;
  - expected: exit 0; printed facts contain NO `kind=accomplishment` with `status=completed` claiming the OAuth2 migration as done (proposed-only or absent is a pass); the script prints the full facts JSON for the execution report. If the model DOES mine the assistant turn into a completed accomplishment, that is a finding (prompt-rule failure on the live model), not a code bug — record the output verbatim in the report and escalate to the owner; do NOT add code-side filtering to make the spot-check pass.
- Performer: `agent` — L4-2 live cascade smoke on scratch DB (same constraints as L4-1):
  1. write `/tmp/tb_del4_delete_smoke.py`: TestClient over scratch `/tmp` DB, `POST /api/v1/artifacts` a note, `DELETE` it, `GET` it;
  - expected: `201` then `200 {"deleted": {"artifacts": 1, ...}}` then `404`; print all three status codes + the DELETE body for the report.

### Level 5: Additional Validation (Optional)

None. No MCP browser flows (no UI change), no new dependencies to audit (`pip audit`/`npm audit` run once at submission per AGENTS.md, not per deliverable).

---

## MANUAL VERIFICATION CHECKLIST

Label each item `agent` or `human` (same performer rule as Level 4). Each item MUST give numbered steps and the exact expected observable result — never a bare "verify X works."

- [ ] [agent] Endpoint live on the real app object: 1. run the Task 1 python one-liner; expected: prints `1` (exactly one DELETE route at `/api/v1/artifacts/{artifact_id}`).
- [ ] [agent] F-10 response shape exact: 1. run `cd backend && uv run pytest tests/test_ingest_api.py -q -k delete -v`; expected: exit 0, 4 passed, including the exact-dict key-lock assertion.
- [ ] [agent] Residue zero + retention intact: 1. run `cd backend && uv run pytest tests/test_deletion.py -q -v`; expected: exit 0, 6 passed — residue tests assert zero deleted-artifact hits AND ≥1 retained-artifact hit.
- [ ] [agent] Wiring proof committed: 1. run `cd backend && uv run pytest tests/test_deletion.py -q -k no_evidence_mining -v`; expected: exit 0, 1 passed; the test asserts on captured model-bound messages, not stub output.
- [ ] [agent] No cascade-semantics drift: 1. `cd backend && git diff --stat -- app/db/`; expected: empty output (zero lines changed under `app/db/` — the core is reused, not modified).
- [ ] [agent] No UI surface changed: 1. `git diff --stat -- frontend/src/views/ frontend/src/components/`; expected: empty output.
- [ ] [agent] Live-model spot-check recorded: 1. perform L4-1 steps; expected: per-step observations above, full facts JSON pasted into the execution report (pass or finding, never silently dropped).
- [ ] [agent] Live delete smoke recorded: 1. perform L4-2 steps; expected: `201` → `200` → `404` with bodies pasted into the report.

No `human` items: nothing in this deliverable is browser-visible or judgment-gated (the L4-1 judgment call — "does this fact claim the migration as done" — is executable by the agent reading the printed JSON).

## ROLLBACK CONSIDERATIONS

- Revert is a clean `git revert`: one router hunk, one new test file, test additions, three frontend hunks. No migration (schema untouched), no data backfill, no config.
- Deployed-DB safety: the endpoint only deletes what the caller names; no background jobs or async indexers interact with it. The pre-existing deployed volume is unaffected by merging this code (deletion requires an explicit per-id call).
- If L4-1 shows live-model mining: no rollback needed (nothing committed depends on model behavior) — escalate the transcript to the owner as a prompt-rule finding.

## ACCEPTANCE CRITERIA

Each criterion MUST name the check that proves it: the validation level/command, the test file, or the manual-checklist item — plus the exact expected result. A criterion with no verification named is an incomplete plan.

- [ ] `DELETE /artifacts/{id}` returns the F-10 shape with exact keys (L2 `test_ingest_api.py -k delete`: 4 passed, incl. exact-dict `{"artifacts": 1, "chunks": N, "facts": M}` + `unlinked.facts` lock)
- [ ] Unknown id → 404 with DB untouched; double delete → 404 (same L2 run: the two 404 tests pass)
- [ ] Multi-source facts unlink (survive with retained chunk_ids) while zero-support facts delete (L2/L3 `test_deletion.py`: unlink test passes with exact counts dict; link cascade proven by zero `fact_links` rows touching the deleted fact plus the surviving fact2→fact3 row)
- [ ] Vec rows, FTS rows, and chunk rows for deleted artifacts are gone (L2/L3 `test_deletion.py`: row-removal test passes — zero vec rows, zero BM25 ids, empty `get_chunks`)
- [ ] Post-delete queries never surface deleted content on either retrieval leg while retained content still retrieves (L2/L3 `test_deletion.py`: artifact residue test passes — zero hits for deleted id, ≥1 hit for retained id)
- [ ] Conversation deletion carries the same retrieval-level guarantees (L2/L3 `test_deletion.py`: conversation residue test passes — turns gone, zero hits, zero artifacts)
- [ ] No-evidence-mining wiring committed: extraction over a conversation artifact hands the model the shared rule + verbatim role tags (L2 `test_deletion.py -k no_evidence_mining`: 1 passed, asserting on captured messages; proves mechanism delivery only — the test docstring states PROVES/LIMITATIONS explicitly and claims no behavioral enforcement)
- [ ] Live-model mining behavior observed and recorded (manual checklist L4-1 item: facts JSON in report; pass or escalated finding; non-gating by design — a mining observation is owner-escalated data, never a suite failure)
- [ ] Frontend `deleteArtifact` mirrors `deleteConversation` with unit tests (L2 `npm test -- --run`: all pass incl. 2 new; L3 `npm run build`: exit 0)
- [ ] Zero cascade-semantics drift and zero UI-surface change (manual checklist git-diff items: both diffs empty)
- [ ] Full suite + lint + format + typecheck green (L1 commands + L2 full `pytest -q`: exit 0 throughout, exact counts recorded)
- [ ] Code follows project conventions (thin router, BY-NAME import, no `chunks_fts` touch, mirror fixtures — reviewer confirms against the Patterns section)

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

- **Why this plan is small on purpose:** deliverable 3's handoff froze the semantics and built the core; the highest-risk failure mode for THIS deliverable would be re-deciding or "improving" the cascade. The `git diff --stat -- app/db/` empty-check exists to catch that drift mechanically.
- **Why the no-mining test asserts on inputs, not outputs:** with a stubbed model, output assertions prove only our stub. The committed test locks that the enforcement mechanism (one shared rule paragraph + literal role tags in the evidence) actually reaches the model on the extraction path; the existing `test_grounding.py` branch lock proves the rule's content and placement. Live-model obedience is inherently non-deterministic and belongs in L4, where a failure is data (escalate transcript), not a red suite.
- **Why no code-side mining filter:** deliverable 3 decided prompt-only enforcement because excluding assistant-tagged chunks from retrieval would break "what did you suggest" recall, which must stay answerable. A validator rejecting assistant-citing facts would reintroduce the same break through the back door (extraction over pure-recall conversations would fail validation). Do not add one.
- **Why `artifacts: 1` is in the `deleted` dict:** PRD's `{"chunks": N, "facts": M, ...}` explicitly leaves room (`...`), and the conversation endpoint's additive `conversations: 1` key sets the precedent that each endpoint names its primary row. It also gives the 404 branch its signal without a second query.
- **Intentional asymmetry to preserve:** conversation-delete cascades DOWN to artifacts; artifact-delete does not cascade UP to conversations (a directly deleted conversation artifact leaves its turns readable). The Task 3 test locks this; "fixing" it would destroy turn history through the artifact path.
- **Owner decisions 2026-11-04 (plan review, both escalations resolved):** (1) prompt-based role-asymmetry enforcement from deliverable 3 stands — the committed wiring test plus the L4 live-model spot-check are accepted as the MVP no-evidence-mining validation approach; the plan is explicit everywhere that the wiring test proves mechanism delivery only and the spot-check observes (never gates) behavior; deterministic behavioral enforcement is neither implemented nor claimed. (2) User-facing Delete controls are assigned to deliverable 5 (which owns the PRD §11 visible-cascade demo requirement); deliverable 4 stays endpoint + tests + typed client.
- **Deadline-day note (Nov 4):** this plan is executable in one pass with no research spikes, no migrations, and no UI work. If time forces a cut, cut Task 5's frontend mirror (backend + tests are the gate; the mirror is convention-completeness) — never cut the residue or wiring tests, which ARE the Phase 3 gate items.
- **Review-loop provenance:** this plan consumed the deliverable-3 handoff note ("decides nothing new about cascade semantics"), the owner-confirmed attempts-NULL decision, and the owner-confirmed recall-stays-answerable interpretation — all restated above as frozen constraints, not open questions.

---

## Revision History

### Cycle 1

- **Finding addressed (reviewer, routine):** "The `fact2.links == []` assertion on a fact1→fact2 link proves neither cascade of the deleted fact's links nor intact survivor links, yet the edge-case list claims both are covered." Changed Task 3 test (1) to seed a third fact (fact3, B-supported) with links fact1→fact2 + fact2→fact3, and to assert via `connect()` that zero `fact_links` rows touch fact1 in either direction and that the fact2→fact3 row survives with its relation; updated the matching Edge Cases bullet and acceptance criterion to reference these assertions. No text now claims link coverage the test does not provide.
- **Owner decisions applied (both review escalations resolved by the owner 2026-11-04, not by fiat):** (1) prompt-based role-asymmetry stands; wiring test + L4 spot-check accepted as MVP validation — Feature Description, Solution Statement, Task 4 docstring requirement, both acceptance criteria, and NOTES now state PROVES (mechanism delivery) vs LIMITATIONS (no behavioral proof; L4 observes, never gates) explicitly; all "proves assistant turns never become evidence" phrasing removed. (2) User-facing Delete controls assigned to deliverable 5 — Scope out-of-scope bullet and NOTES record the assignment and the PRD §11 demo-requirement ownership; deliverable-4 scope unchanged.
- **Not done:** nothing outstanding from this review cycle; the deliverable-5 build-list scope amendment (if needed) is explicitly deferred to deliverable-5 plan time and is not this plan's to make.
