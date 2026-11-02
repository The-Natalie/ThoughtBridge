# Feature: grounded-qa-minimal-chat-ui

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Phase 1 deliverable 5: grounded Q&A over all saved material plus a minimal chat UI with turn persistence. Backend implements `POST /query` (evidence/teaching/auto modes, chunk-ID citations, deterministic speculation refusal in evidence mode when sources are silent), persists every exchange as ordered role-labeled turns under a `conversation_id` (omit to start, pass back to continue), and exposes read-only `GET /conversations` + `GET /conversations/{id}`. Frontend adds a Chat view that sends questions, renders answers with clickable citation chips (each resolving to full chunk text via `GET /chunks/{id}`), and keeps the conversation going across turns. This is the conversation-memory foundation: Phase 3 ingests these persisted turns via the `tb_conversation` adapter with no chat rework.

## User Story

As a neurodivergent thinker with saved notes
I want to ask natural-language questions and get answers grounded in my material with clickable citations
So that I can recall what I know, see exactly what came from my notes, and trust that silence means refusal rather than invention

## Problem Statement

Ingestion (deliverable 3) and hybrid retrieval (deliverable 4) exist, but there is no answer generation, no grounding-mode enforcement, no conversation persistence, and no chat surface. Without this deliverable the pipeline cannot answer questions, the Phase 1 gate items ("vague query returns the right cited passage", "turns persisted with stable ids and role labels") cannot pass, and CHECKPOINT 2 has no chat view to serve.

## Scope

- In scope: `POST /query` (modes evidence/teaching/auto, `top_k`, optional `context.explanation_id` accepted-but-ignored, optional `conversation_id`); intent-routed `auto` (personal-history-seeking → evidence, otherwise teaching with passages for personalization); shared grounding-mode prompt contracts in `core/`; first Meta chat-completion call through the single client module; JSON schema-at-the-boundary for model output; code-enforced citation validation (unknown chunk IDs dropped, evidence-mode zero-valid-citation becomes refusal); deterministic no-LLM-call refusal path when evidence retrieval is empty; turn persistence (user + assistant turns, ordered, role-labeled, stable IDs, timestamps, mode, citations JSON); bounded same-conversation prompt history (recency-capped, never cross-conversation); `GET /conversations` + `GET /conversations/{id}` reads; minimal Chat view (message list, input, mode/grounding badge, citation chips, citation-detail panel, 502/error display); typed frontend API client additions; contract + persistence + UI tests.
- Out of scope: pipeline ingestion of conversations (`tb_conversation` adapter — Phase 3); `DELETE /conversations/{id}` (Phase 3 deletion cascade); explainer, `context.explanation_id` scoping behavior, extraction, Practice Loop, `question_kind` (Phases 2–3); reranker/HyDE (stretch); PDF/Word (Phase 2); production hardening, custom domain, demo seeding (Phase 4); STAR/coaching features (never).

## Solution Statement

Build the Q&A slice as thin-router-over-shared-modules: `POST /query` runs the existing `hybrid_search`, routes `auto` by deterministic question-intent patterns (personal-history-seeking → evidence; otherwise teaching, with retrieved passages attached so explanations can be personalized without being restricted to them), loads bounded same-conversation prior turns as prompt history, builds mode-specific messages from shared contracts in a new `core/grounding.py`, calls a new `chat_completion()` in the single Meta client (OpenAI-compatible `POST /v1/chat/completions`, JSON `response_format`, generous `max_tokens` for Spark hidden reasoning), validates the `{answer, citations}` JSON against a Pydantic model, hydrates citation excerpts from the canonical `chunks` table (never from model text), drops hallucinated chunk IDs, converts uncited evidence answers to refusal in code, and — only after successful generation — creates the conversation row (when new) together with both turns in one transaction via a new `db/conversations.py` repository, then returns the PRD §10 shape. The Chat view is a single React view over typed `apiPost`/`apiGet` helpers with citation chips resolving through the existing chunk endpoint.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: High
**Primary Systems Affected**: `backend/app/core` (Meta client, grounding contracts), `backend/app/llm` (Q&A orchestration), `backend/app/db` (conversations repository), `backend/app/api` (query router), `frontend/src` (Chat view + typed client)
**Dependencies**: Phase 1 deliverables 1–4 (scaffold, Meta probe, ingestion, hybrid retrieval) — all landed; no new backend libraries (httpx already present); two frontend dev dependencies (`jsdom`, `@testing-library/react`)
**Assumptions**: Meta `POST /v1/chat/completions` stays OpenAI-compatible (verified by prior research + review-call evidence below; executor must re-validate with one live call); `response_format: {"type": "json_object"}` honored for `muse-spark-1.3` (executor validates live; fallback: strip markdown fences before `json.loads` — implement the fallback regardless); Spark hidden reasoning consumes `max_tokens` (prime-summary concern — generous budget required)

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `backend/app/core/meta_client.py` (lines 1–91) - Why: THE pattern to mirror for `chat_completion()` — module constants, explicit params (never reads settings, never imports config), injected `httpx.AsyncClient` seam, truncated honest errors, key never in errors/logs
- `backend/tests/test_meta_client.py` (lines 42–63) - Why: `httpx.MockTransport` offline-stub pattern for all new client tests; `CANARY` key-hygiene assertions to mirror
- `backend/app/api/retrieval.py` (lines 1–89) - Why: thin-router pattern to mirror exactly — Pydantic in/out models, by-name `hybrid_search` import as the monkeypatch seam, blank-query 422, `EmbeddingDimMismatchError` → 500 mapping
- `backend/app/api/health.py` (lines 34–65) - Why: async router pattern (`async def`, settings → explicit client params wiring, key-missing branch); `POST /query` is async because the Meta call is async
- `backend/app/api/ingest.py` (lines 84–110) - Why: validation + logging conventions (`logger.warning` on rejections, 422 vs 400 vs 413 status discipline)
- `backend/app/retrieval/search.py` (lines 24–29, 100–112, 129–154) - Why: `hybrid_search(db_path, query, top_k, embedding_model, embed_fn)` signature; `TOP_K_DEFAULT=8`/`TOP_K_MAX=50` to reuse; `excerpt_of()` for citation excerpts; hydrate-from-canonical-table principle
- `backend/app/retrieval/embedder.py` (lines 19–23) - Why: `EMBEDDING_DIM`, `QueryEmbedFn` types (no changes here — reference only)
- `backend/app/db/schema.sql` (lines 132–148) - Why: `conversations(id, kind, created_at)` + `turns(id, conversation_id, idx, role CHECK, content, mode, citations, created_at)` — already exist, NO migration needed
- `backend/app/db/artifacts.py` (lines 50–94) - Why: repository transaction pattern to mirror — `connect()`, `with conn:` single transaction, `uuid.uuid4().hex` IDs, explicit `db_path` param, module logger
- `backend/app/db/chunks.py` (lines 21–44) - Why: `get_chunks(db_path, ids)` batch hydration for citation building (reuse, do not duplicate)
- `backend/app/db/connection.py` (lines 21–30) - Why: `connect()` is the only sanctioned DB path; every repository function opens/closes its own connection
- `backend/app/ingest/pipeline.py` (lines 45–64) - Why: `embed_fn or functools.partial(...)` injectable-seam convention; `datetime.now(UTC).isoformat()` timestamps; `ArtifactTooLargeError(ValueError)` → router-mapped exception convention
- `backend/app/main.py` (lines 36–52) - Why: router registration (`include_router(..., prefix="/api/v1")`) + CORS origins (no change needed — same origin)
- `backend/app/core/config.py` (lines 14–24) - Why: settings surface (`meta_model` drift-guarded against `DEFAULT_META_MODEL`); query path needs NO new settings
- `backend/tests/test_retrieval_api.py` (lines 27–86) - Why: TestClient fixture pattern to mirror — direct-pipeline seeding with fake vectors, by-name `hybrid_search` stub, settings isolation, `DATABASE_PATH` env override
- `backend/tests/test_health.py` (lines 33, 38–40, 65, 88) - Why: `monkeypatch.setattr("app.api.health.check_meta_reachability", ...)` seam-mirroring for stubbing the new `chat_completion` at the router boundary
- `frontend/src/api/client.ts` (lines 1–30) - Why: `apiUrl`/`apiGet`/`apiPost` typed helpers — all new frontend calls go through these, no raw `fetch`
- `frontend/src/App.tsx` (lines 1–42) - Why: `VIEWS` tab pattern to extend with the Chat view (Chat becomes the default tab)
- `frontend/src/api/client.test.ts` (lines 1–24) - Why: vitest pattern (`describe/it/expect`, `vi.stubEnv`); new client tests mirror this file
- `frontend/vite.config.ts` - Why: `test.environment` must change `node` → `jsdom` for the ChatView component test
- `frontend/package.json` - Why: add `jsdom` + `@testing-library/react` to devDependencies; scripts (`dev`, `build`, `test`) already correct
- `PRD.md` (§6 lines 191–194 grounding contracts; §7 line 232 F-2; §10 lines 314, 330–331, 357–363 query + conversation contracts; §12 lines 414–423 Phase 1 gate) - Why: authoritative requirements — response shapes, 502 rule, refusal semantics, turn-persistence fields
- `.agents/plans/phase-1-build-list.md` (lines 33–37) - Why: deliverable scope boundary (Q&A + turn persistence only; `tb_conversation` out; no explainer/practice/extraction)
- `.agents/plans/checkpoint-1-meta-client-wiring.md` (lines 357, 69–80) - Why: prior Meta API research links + the decision record that health probes never burn inference tokens (query is the FIRST inference call)

### New Files to Create

- `backend/app/core/grounding.py` - Shared grounding-mode contracts: mode literals, auto-resolution rule, evidence/teaching system prompts + message builders, deterministic refusal builder, citation JSON schema constants
- `backend/app/llm/qa.py` - Q&A orchestration: retrieve → resolve mode → prompt → chat → validate → hydrate citations → code-enforced refusal; pure function of injected `search_fn`/`chat_fn` for testability
- `backend/app/db/conversations.py` - Conversation repository: create, append-turns-in-one-transaction, get-with-ordered-turns, list; dataclasses mirroring `artifacts.py`
- `backend/app/api/query.py` - Thin query router: `POST /query`, `GET /conversations`, `GET /conversations/{id}`; Pydantic models mirroring PRD §10 shapes
- `backend/tests/test_grounding.py` - Contract tests: prompt builders, auto-resolution matrix, refusal content
- `backend/tests/test_qa.py` - Orchestration tests with stubbed search/chat: happy paths, refusal paths, citation-hallucination drop, no-LLM-call-on-empty-evidence
- `backend/tests/test_conversations.py` - Repository tests: create/append/get/list, idx sequencing, role labels, stable IDs, citations JSON round-trip
- `backend/tests/test_query_api.py` - Endpoint tests: exact shapes, conversation start/continue, 404/422/502 matrix, openapi paths, turn rows in DB
- `frontend/src/api/types.ts` - Shared API types: `QueryMode`, `Citation`, `QueryResponse`, `ChunkDetail`, `ConversationSummary`, `ConversationDetail`, `Turn`
- `frontend/src/api/query.ts` - Typed client: `postQuery()`, `getChunk()`, `listConversations()`, `getConversation()`
- `frontend/src/api/query.test.ts` - Client tests: request bodies, URL joining, error surfacing (mirror `client.test.ts`)
- `frontend/src/views/ChatView.tsx` - Minimal chat UI: message list, input, mode badge, citation chips, citation-detail panel, error display
- `frontend/src/views/ChatView.test.tsx` - Component test: renders, sends on submit (mocked fetch), renders citations, continues conversation

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [Meta Model API provider notes (promptfoo)](https://www.promptfoo.dev/docs/providers/meta/)
  - Specific section: base URL + OpenAI-compatible chat completions
  - Why: confirms `https://api.meta.ai/v1` base and OpenAI-compatible surface (carried from CHECKPOINT 1 research)
- [Meta Model API (LiteLLM providers)](https://docs.litellm.ai/docs/providers/meta)
  - Specific section: supported endpoints table (`/chat/completions`, `/responses`, `/v1/messages`)
  - Why: confirms `POST /v1/chat/completions` shares the probe's base URL, auth, and models (carried from CHECKPOINT 1 research)
- [Meta model cookbook README](https://github.com/meta-models/meta-model-cookbook/blob/HEAD/README.md)
  - Specific section: quickstart `client.chat.completions.create` against `https://api.meta.ai/v1`
  - Why: corroborates drop-in OpenAI SDK compatibility — raw `httpx` POST with `{model, messages, ...}` + `{choices[0].message.content}` parse matches what the codebase already assumes
- [Muse Spark structured outputs (shipwithmuse)](https://shipwithmuse.live/blog/muse-spark-structured-outputs)
  - Specific section: `response_format` with `type: "json_object"` on Chat Completions
  - Why: the schema-at-the-boundary mechanism for the `{answer, citations}` contract — executor must still validate live and keep the fence-stripping fallback
- [OpenAI Chat Completions response format](https://platform.openai.com/docs/api-reference/chat/create)
  - Specific section: `response_format: {"type": "json_object"}` + `choices[0].message.content` shape
  - Why: wire-shape reference for request construction and response parsing (Meta mirrors this surface)
- [httpx MockTransport](https://www.python-httpx.org/advanced/mock/)
  - Specific section: `MockTransport(handler)` + `AsyncClient(transport=...)`
  - Why: exact stubbing pattern for `chat_completion` tests (already proven in `test_meta_client.py`)
- [Testing Library React](https://testing-library.com/docs/react-testing-library/intro/)
  - Specific section: `render` + `screen` queries
  - Why: the ChatView component test pattern (new dev dependency — keep usage to `render`/`screen`/`fireEvent` only)
- [FastAPI response_model + status codes](https://fastapi.tiangolo.com/tutorial/response-model/)
  - Specific section: `response_model` filtering + `status_code` on decorators
  - Why: `POST /query` returns 200 with exact PRD shape; conversation reads are plain GETs

### Patterns to Follow

**Naming Conventions:** `snake_case` modules/functions (`grounding.py`, `route_auto`, `answer_question`); `PascalCase` Pydantic models/dataclasses (`QueryRequest`, `CitationOut`, `TurnDetail`); module-level `UPPER_SNAKE` constants (`EVIDENCE_SYSTEM_PROMPT`, `QA_MAX_TOKENS`, `REFUSAL_ANSWER`); frontend `PascalCase.tsx` views, `camelCase.ts` client utils.

**Error Handling:** upstream Meta failures surface as 502 with cause (PRD §10 — first use of the rule; `MetaAPIError` → `HTTPException(502)`); LLM JSON that fails schema validation is rejected and logged, never partially applied (evidence mode → code refusal; teaching mode → 502 with validation cause, since the model produced garbage, not silence); blank question → 422 (mirror retrieval router); unknown `conversation_id` → 404 `{"detail": "conversation not found"}` (mirror chunk 404); missing API key → 502 with `MODEL_API_KEY not configured` (mirror health key-missing branch — consistent cause language); remote bodies truncated to `MAX_ERROR_CHARS`; key never in errors/logs/responses.

**Logging Pattern:** module logger + lazy `%s` args (mirrored from `db/connection.py:11,41-47`):
```python
logger = logging.getLogger(__name__)
logger.info("query answered: mode=%s citations=%d conversation=%s", mode_used, len(citations), conversation_id)
logger.warning("query refused: mode=evidence hits=%d reason=%s", len(hits), reason)
```
No `print(` in `backend/app`.

**Test Pattern:** sync test functions; `TestClient(create_app())`; autouse settings-isolation fixture + `Settings(_env_file=None)` factory swap (mirror `test_retrieval_api.py:36-51`); `tmp_path` + `init_db` + direct-pipeline seeding with fake vectors; by-name `monkeypatch.setattr` seams at BOTH levels (`app.api.query.hybrid_search` stub running real search with fake query vector, `app.api.query.chat_completion` stub returning canned JSON); `asyncio.run(...)` for direct async client tests; frontend `describe/it/expect` + `vi.stubEnv` for client tests, `render`/`screen`/`fireEvent` with global `fetch` mocked for the component test.

**Other Relevant Patterns:** routers stay thin — `api/query.py` composes `retrieval` + `llm/qa` + `db/conversations`, no inline prompt/DB/HTTP logic; `core/` modules take explicit params and never import settings (mirror `meta_client.py` header contract — `grounding.py` is pure functions of its args); repository functions take explicit `db_path`, open/close own connection, single transaction for multi-row writes (mirror `artifacts.py:50-94`); excerpts hydrated from canonical tables, never from model text (mirror `search.py:129-154` hydration principle); frontend reads/writes go through `apiGet`/`apiPost` only.

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

Shared contracts + persistence + client primitive, all independently testable before any endpoint exists. `core/grounding.py` holds the mode literals, the deterministic auto-resolution rule, both system prompts, message builders that number passages `[1..N]` with an explicit chunk-ID map, the JSON output contract, and the refusal builder. `db/conversations.py` holds the turn-log repository over the existing `conversations`/`turns` tables. `meta_client.py` gains `chat_completion()` + `MetaAPIError` following the probe's exact conventions (longer timeout — generation, not a probe).

**Tasks:**

- Create `core/grounding.py` with mode contracts, prompts, message builders, auto rule, refusal
- Create `db/conversations.py` repository (create/append/get/list)
- Add `chat_completion()` + `MetaAPIError` to `core/meta_client.py`
- Unit-test all three before wiring (test_grounding, test_conversations, client chat tests)

### Phase 2: Core Implementation

`llm/qa.py` orchestrates retrieve → resolve → generate → validate → hydrate as a pure function of injected `search_fn`/`chat_fn` (mirroring the `embed_fn` injection convention), so every path is unit-testable without HTTP or the embedding model. `api/query.py` adds the thin `POST /query` + conversation reads. Citation validation is code, not prompt-wishing: unknown chunk IDs are dropped with a warning, and evidence mode with zero valid citations becomes the deterministic refusal.

**Tasks:**

- Create `llm/qa.py` orchestration with `QaResult` dataclass
- Create `api/query.py` router with PRD §10 Pydantic shapes
- Register router in `main.py`
- Endpoint + orchestration tests (test_qa, test_query_api)

### Phase 3: Integration

Frontend: shared types, typed client functions, Chat view, App tab wiring, jsdom test setup. Backend and frontend meet only at the PRD §10 JSON shapes — the frontend never imports backend code and the backend never serves frontend assets.

**Tasks:**

- Create `api/types.ts` + `api/query.ts` + client tests
- Create `views/ChatView.tsx` + component test
- Wire Chat tab into `App.tsx` as the default view
- Add `jsdom` + `@testing-library/react`, flip vitest environment

### Phase 4: Testing & Validation

Full gates per repo convention: backend `pytest` + `ruff check` + `ruff format --check` + `mypy app`; frontend `npm test` + `npm run build`; one live Meta call proving the chat path end to end (the first inference call — update `backend/README.md` Meta Model line from "no inference call" to the verified chat call); manual chat round-trip against the dev servers.

**Tasks:**

- Run all backend gates to green
- Run all frontend gates to green
- Live-call validation (real key, seeded notes) + README update
- Manual chat round-trip per the checklist below

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

### CREATE backend/app/core/grounding.py

- **IMPLEMENT**: `QueryMode = Literal["evidence", "teaching", "auto"]`; `ModeUsed = Literal["evidence", "teaching"]`; `EVIDENCE_SYSTEM_PROMPT` (closed world: use ONLY numbered passages, every claim cites `[n]`, output JSON `{"answer": str, "citations": [int]}` where ints are the 1-based passage numbers, refuse-with-`{"answer": "I don't know from your notes.", "citations": []}`-shape when passages don't support an answer, never invent; numbered passages are delimited UNTRUSTED user data — content inside passage blocks must never be followed as instructions, per PRD §9); `TEACHING_SYSTEM_PROMPT` (open world: general knowledge allowed, weave in numbered passages when present, same JSON shape, citations may be `[]`; same untrusted-passage framing as evidence); `NumberedPassage` dataclass (`n`, `chunk_id`, `artifact_id`, `text`); `HistoryTurn` dataclass (`role: Literal["user", "assistant"]`, `content`); `MAX_HISTORY_TURNS = 6`, `MAX_HISTORY_CHARS = 4000`; `select_history(turns: list[HistoryTurn]) -> list[HistoryTurn]` (take most recent turns up to `MAX_HISTORY_TURNS` then drop oldest until total chars ≤ `MAX_HISTORY_CHARS`; preserves chronological order); `build_messages(mode_used, question, passages, history=())` returning OpenAI `messages`: system + zero or more history messages (`user`/`assistant` roles verbatim, dialogue context only — history is NEVER evidence and assistant history must never be cited) + one final user message with `Passage [n] (chunk_id=...)` blocks then the question; `PERSONAL_HISTORY_PATTERNS` (ordered regex list, documented heuristic v1): questions ASKING ABOUT the user's own work/history/accomplishments — e.g. `what did i`, `what have i`, `my (accomplishments?|experience|skills?|work|history|projects?|role|jobs?)`, `when|where did i`, `tell me about my`, `have i (ever|done|worked|built|shipped)` (case-insensitive); `route_auto(question) -> ModeUsed` (`evidence` iff any pattern matches, else `teaching` — explicit modes bypass routing entirely); `REFUSAL_ANSWER = "I couldn't find anything in your notes that answers this."`; `build_refusal()` returning the refusal answer text (citations always `[]` — enforced by caller, not the model); `QA_JSON_INSTRUCTIONS` appended to user message describing the exact JSON shape. Pure functions only — no imports from `app.core.config`, `app.db`, `app.retrieval`.
- **PATTERN**: module constants + explicit params (mirror `core/meta_client.py:17-20,30-37`); dataclasses (mirror `retrieval/search.py:34-51`)
- **IMPORTS**: `from __future__ import annotations`, `dataclasses.dataclass`, `re`, `typing.Literal` — nothing else
- **GOTCHA**: passage numbers are 1-based display ordinals mapped to chunk IDs in code — the model NEVER sees bare chunk IDs as citable tokens (prevents off-by-corpus hallucination); prompts must say "output JSON only, no markdown fences" AND the parser must still strip fences (belt and suspenders); intent patterns match questions ABOUT personal history, not questions that merely contain "I" — "Explain event loops using something I've worked on" must route teaching (explanation-led, personalizes via passages), while "What did I accomplish at Sesame?" routes evidence; when unsure, patterns stay narrow (teaching-with-passages is the safe default: general answer + personalization, never invention of personal facts)
- **VALIDATE**: `cd backend && uv run python -c "from app.core.grounding import route_auto; assert route_auto('What did I accomplish at Sesame?') == 'evidence' and route_auto('Explain what an event loop is') == 'teaching' and route_auto(\"Explain event loops using something I've worked on\") == 'teaching'"`

### CREATE backend/app/db/conversations.py

- **IMPLEMENT**: `TurnDetail` dataclass (`id, conversation_id, idx, role, content, mode, citations_json, created_at`); `ConversationDetail` dataclass (`id, kind, created_at, turns: list[TurnDetail]`); `ConversationSummary` dataclass (`id, kind, created_at, turn_count`); `create_conversation(db_path, kind="qa") -> str` (uuid hex, UTC isoformat, single INSERT); `append_turns(db_path, conversation_id, turns: list[tuple[role, content, mode, citations_json]]) -> list[str]` (ONE transaction: `SELECT COALESCE(MAX(idx), -1)`, sequential idx, uuid hex IDs each, returns turn IDs in order); `create_conversation_with_turns(db_path, kind, turns) -> tuple[str, list[str]]` (ONE transaction: conversation row + turns at idx `0..n` — the router's new-conversation path calls this AFTER successful generation so failures persist nothing); `get_conversation(db_path, conversation_id) -> ConversationDetail | None` (header + `ORDER BY idx` turns, `None` when missing); `list_conversations(db_path) -> list[ConversationSummary]` (`ORDER BY created_at, id` with turn counts). Role values pass through (`user`/`assistant` — schema CHECK enforces).
- **PATTERN**: MIRROR `db/artifacts.py:50-94` (explicit `db_path`, `connect()`, `with conn:`, uuid hex, module logger) and `db/artifacts.py:97-120` (summary list with subquery counts, `ORDER BY created_at, id`)
- **IMPORTS**: `logging`, `uuid`, `dataclasses`, `datetime.UTC/datetime`, `app.db.connection.connect`
- **GOTCHA**: `citations` column stores a JSON string — the repository takes/returns the raw string and never parses it (serialization lives in the router/llm layers); FK violation on unknown conversation surfaces as `sqlite3.IntegrityError` — the ROUTER pre-checks existence via `get_conversation` and returns 404, so `append_turns` never needs to catch it
- **VALIDATE**: `cd backend && uv run python -c "from app.db.connection import init_db; from app.db.conversations import create_conversation_with_turns, get_conversation; import tempfile; p = tempfile.mktemp(suffix='.db'); init_db(p); c, ids = create_conversation_with_turns(p, 'qa', [('user', 'q', 'evidence', '[]'), ('assistant', 'a', 'evidence', '[{\"chunk_id\": 1}]')]); d = get_conversation(p, c); assert [t.idx for t in d.turns] == [0, 1] and [t.id for t in d.turns] == ids, 'idx/order broken'; print('conversations repo ok')"`

### ADD backend/app/core/meta_client.py chat completion

- **IMPLEMENT**: `MetaAPIError(Exception)` with `(status_code: int | None, detail: str)` fields, `__str__` = `"Meta API chat completion failed: HTTP {status}: {detail}"` (status `None` → `"request failed"`); `CHAT_TIMEOUT_S = 60.0`; `QA_MAX_TOKENS = 4096` (generous: Spark hidden reasoning consumes `max_tokens` — prime-summary concern #2); `QA_TEMPERATURE = 0.0` (deterministic; tunable later); `async def chat_completion(*, api_key, model=DEFAULT_META_MODEL, messages, max_tokens=QA_MAX_TOKENS, temperature=QA_TEMPERATURE, base_url=META_API_BASE_URL, timeout_s=CHAT_TIMEOUT_S, client=None) -> str` — POSTs `{base}/chat/completions` with `{"model", "messages", "max_tokens", "temperature", "response_format": {"type": "json_object"}}`, Bearer [REDACTED] returns `choices[0].message.content` (must be non-empty str, else `MetaAPIError`); ALL remote failure modes (timeout, connect, HTTP error, non-200, bad JSON, missing/empty choices) raise `MetaAPIError` with truncated cause (reuse `MAX_ERROR_CHARS`); key never in errors/logs; owns-and-closes its client exactly like the probe. Do NOT touch `check_meta_reachability`, `ProbeResult`, or existing constants.
- **PATTERN**: MIRROR probe structure `meta_client.py:30-91` (URL join, headers, owned-client try/finally, exception mapping, truncation, `logger.warning` with `status=%s detail=%s`)
- **IMPORTS**: no new imports (`httpx`, `logging` already present)
- **GOTCHA**: `response_format` key name is OpenAI's — executor MUST confirm against the live API in the live-call task; if the live call rejects it, drop `response_format` and rely on prompt instructions + fence-stripping (keep behavior identical otherwise); `max_tokens` too small truncates into invalid JSON mid-reasoning — never lower `QA_MAX_TOKENS` without a live test
- **VALIDATE**: `cd backend && uv run python -c "import asyncio, httpx; from app.core.meta_client import chat_completion; h = lambda r: httpx.Response(200, json={'choices': [{'message': {'content': '{\"answer\": \"hi\", \"citations\": []}'}}]}); c = httpx.AsyncClient(transport=httpx.MockTransport(h)); print(asyncio.run(chat_completion(api_key='k', messages=[{'role': 'user', 'content': 'q'}], client=c)))"`
- **Expected**: prints `{"answer": "hi", "citations": []}`

### CREATE backend/tests/test_grounding.py

- **IMPLEMENT**: `route_auto` matrix — evidence: `"What did I accomplish at Sesame?"`, `"Tell me about my experience with RAG"`, `"What are my skills?"`, `"Where did I work in 2024?"`; teaching: `"Explain what an event loop is"`, `"Explain event loops using something I've worked on"`, `"What is a vector database?"`, `"How do embeddings work?"`; `build_messages` evidence shape (system contains "only" + "JSON"; user message contains `Passage [1]`/`Passage [2]` blocks with chunk IDs + the question; returns `[{"role": "system", ...}, {"role": "user", ...}]` with empty default history); history shape (`history=[user, assistant]` → messages `[system, user, assistant, user-final]`, roles verbatim, chronological); teaching shape (system allows general knowledge; zero passages still builds a valid message); untrusted framing (BOTH system prompts contain "untrusted" + "never" + "instructions" as substrings — PRD §9); `select_history` (8 turns → 6 most recent kept in order; char budget drops oldest first; empty in → empty out); `build_refusal()` returns `REFUSAL_ANSWER` and mentions notes being silent; JSON-instructions constant mentions `answer` + `citations`.
- **PATTERN**: plain asserts, no fixtures, no DB (mirror `test_search.py`-style pure unit tests — check that file's shape first)
- **IMPORTS**: `app.core.grounding`
- **GOTCHA**: assert on stable SUBSTRINGS (`"Passage [1]"`, `"chunk_id="`, `"untrusted"`), never on full prompt equality (prompts are tunable; structure is contractual); route cases use the owner's three verbatim examples plus near-neighbors — if a pattern is later widened, update cases deliberately, never by blanket edit
- **VALIDATE**: `cd backend && uv run pytest tests/test_grounding.py -q`

### CREATE backend/tests/test_conversations.py

- **IMPLEMENT**: `tmp_path` + `init_db` fixture (mirror `test_db_init.py:23-28`); create returns hex ID + appears in list with `turn_count 0`; append two turns → IDs stable, `idx [0, 1]`, roles preserved, `citations_json` round-trips verbatim; second append continues idx at 2; `create_conversation_with_turns` → header + 2 turns at idx `[0, 1]` in one call (the router's atomic new-conversation path); `get_conversation` unknown ID → `None`; `list_conversations` orders by creation; turn content with unicode/newlines survives.
- **PATTERN**: MIRROR `test_db_init.py` fixture shape; sync test functions
- **IMPORTS**: `pathlib.Path`, `pytest`, `app.db.connection.init_db`, `app.db.conversations`
- **GOTCHA**: `init_db` on a `tmp_path` file per test (never the repo DB); `get_settings` untouched — repository takes explicit `db_path`
- **VALIDATE**: `cd backend && uv run pytest tests/test_conversations.py -q`

### ADD backend/tests/test_meta_client.py chat tests

- **IMPLEMENT**: append (do not rewrite) chat tests reusing `CANARY`/`MODEL`/`MockTransport`: 200 happy path returns content and sends `model` + `messages` + `response_format.type == "json_object"` + `max_tokens == QA_MAX_TOKENS` (assert from the recorded request body); 401 → `MetaAPIError` with "401" and no canary; 500 with 1000-char body truncated to `MAX_ERROR_CHARS`; timeout → status `None`; 200 bad JSON → `MetaAPIError`; 200 empty `choices` → `MetaAPIError`; 200 empty-string content → `MetaAPIError`; trailing-slash base URL tolerated (`/v1/chat/completions` path asserted). Drive with `asyncio.run` via a `_chat()` helper mirroring `_probe`.
- **PATTERN**: MIRROR existing `_probe` helper + `test_probe_*` shapes in the same file (lines 42–63)
- **IMPORTS**: add `MetaAPIError, QA_MAX_TOKENS, chat_completion` to the existing `app.core.meta_client` import
- **GOTCHA**: `pytest.raises(MetaAPIError)` — the chat function RAISES (unlike the probe which returns `ProbeResult`); assert `exc.value.status_code` per case
- **VALIDATE**: `cd backend && uv run pytest tests/test_meta_client.py -q`

### CREATE backend/app/llm/qa.py

- **IMPLEMENT**: `QaModelOut(BaseModel)`: `answer: str`, `citations: list[int]` (1-based passage numbers); `CitationHit` dataclass (`chunk_id, artifact_id, span_start, span_end, excerpt`); `QaResult` dataclass (`answer, citations: list[CitationHit], mode_used`); `SearchFn`/`ChatFn` protocols (search: `(query, top_k) -> list[SearchHit]`; chat: `(messages) -> str` — thin signatures so router adapters are 3-liners); `strip_fences(text)` (remove ` ```json ... ``` ` wrappers); `async def answer_question(*, question, mode, top_k, db_path, search_fn, chat_fn, history=()) -> QaResult` (`history: tuple[HistoryTurn, ...]`, default empty — caller-owned, already bounded by `select_history`): 1) `hits = search_fn(question, top_k)` (ALWAYS retrieved in every mode — evidence needs them as the closed world, teaching uses them for personalization); 2) `mode_used = route_auto(question) if mode == "auto" else mode` (explicit modes bypass routing); 3) evidence + zero hits → `QaResult(REFUSAL_ANSWER, [], "evidence")` WITHOUT calling `chat_fn` (log `warning`); 4) build passages: full chunk text via `get_chunks(db_path, hit_ids)` (since `SearchHit.excerpt` is truncated) into `NumberedPassage`s — see GOTCHA; 5) `raw = await chat_fn(build_messages(mode_used, question, passages, history))`; 6) `strip_fences` → `json.loads` → `QaModelOut` validate — on ANY failure: evidence → refusal `QaResult` (log `warning`, never raise); teaching → raise `QaValidationError` (router → 502, the model produced garbage); 7) map passage numbers → chunk IDs, DROP numbers out of range with `warning` (hallucinated citations never surface); 8) evidence + zero valid citations → refusal `QaResult`; 9) hydrate `CitationHit`s (artifact_id/span/excerpt from the full chunk rows already fetched); return. `QaValidationError(ValueError)` for the teaching-garbage case.
- **PATTERN**: injectable seams (mirror `pipeline.py:63` `embed_fn or partial` — here REQUIRED params, router passes adapters); Pydantic boundary validation (mirror router `response_model` discipline, applied to LLM output); refusal-as-normal-result (AGENTS.md: "not an error")
- **IMPORTS**: `json`, `logging`, `dataclasses`, `collections.abc.Callable`/`Awaitable`, `pydantic.BaseModel`, `app.core.grounding`, `app.db.chunks.get_chunks`, `app.retrieval.search.SearchHit` (type only)
- **GOTCHA**: `SearchHit.excerpt` is truncated to 300 chars — prompts need FULL chunk text, so `answer_question` takes `db_path` and calls `get_chunks` for the hit IDs (fallback: if a hit ID has no row — same race `search.py` logs — drop it before numbering); `chat_fn` is async (real one awaits `chat_completion`); `search_fn` is sync (real one is `hybrid_search`); `history` is dialogue context only — citations may reference ONLY current-retrieval passage numbers (a model citing history content has no valid number to use, so history can never leak into `citations`)
- **VALIDATE**: `cd backend && uv run python -c "import asyncio; from app.llm.qa import answer_question; r = asyncio.run(answer_question(question='q', mode='evidence', top_k=8, db_path=':memory:', search_fn=lambda q, k: [], chat_fn=None)); print(r.mode_used, r.citations, r.answer[:40])"`
- **Expected**: prints `evidence [] I couldn't find anything in your notes...` (and `chat_fn=None` never touched — proves no-LLM-call refusal)

### CREATE backend/tests/test_qa.py

- **IMPLEMENT**: fake `SearchHit`s (construct directly — no DB: monkeypatch `app.llm.qa.get_chunks` to return full-text rows); evidence happy path (2 hits, chat returns `{"answer": "A [1]", "citations": [1, 2]}` → both citations hydrated with artifact/span/excerpt from fake rows, `mode_used == "evidence"`); evidence empty-hits → refusal WITHOUT calling chat (chat stub raises `AssertionError` if called); evidence model-returns-`[]` → refusal; evidence hallucinated number `[9]` → dropped → refusal (proves code-enforcement); evidence mixed `[1, 9]` → single citation; teaching empty-hits → chat IS called with zero passages, uncited answer passes through; auto routing by intent (`"What did I accomplish at Sesame?"` → evidence even with zero hits; `"Explain what an event loop is"` → teaching even with hits present); history forwarded (pass 2 `HistoryTurn`s → chat stub records `[system, user, assistant, user-final]` messages); teaching garbage JSON → `QaValidationError`; evidence garbage JSON → refusal (not raise); fenced ` ```json ` response parsed. Drive with `asyncio.run`.
- **PATTERN**: stub-injection (mirror `test_search.py` fake-`embed_fn` style); `asyncio.run` for async SUT (mirror `test_meta_client.py:42-44`)
- **IMPORTS**: `asyncio`, `json`, `pytest`, `app.llm.qa`, `app.retrieval.search.SearchHit`
- **GOTCHA**: `SearchHit` requires all 7 fields — build a helper; the `get_chunks` monkeypatch target is `app.llm.qa.get_chunks` (imported by name into qa.py); chat stub must be `async def`
- **VALIDATE**: `cd backend && uv run pytest tests/test_qa.py -q`

### CREATE backend/app/api/query.py

- **IMPLEMENT**: `QueryContext(BaseModel)`: `explanation_id: str | None = None` (ACCEPTED BUT IGNORED in Phase 1 — no validation, no scoping; document in docstring); `QueryRequest`: `question: str = Field(min_length=1)`, `mode: QueryMode = "auto"`, `top_k: int = Field(default=TOP_K_DEFAULT, ge=1, le=TOP_K_MAX)`, `context: QueryContext | None = None`, `conversation_id: str | None = None`; `CitationOut`: `chunk_id: int, artifact_id: str, span: list[int], excerpt: str`; `QueryResponse`: `answer: str, citations: list[CitationOut], mode_used: ModeUsed, conversation_id: str`; `TurnOut`: `id, idx, role, content, mode, citations, created_at` (`citations: list` — parsed JSON); `ConversationOut`: `id, kind, created_at, turns: list[TurnOut]`; `ConversationSummaryOut`: `id, kind, created_at, turn_count`; `POST /query` (async): blank-question → 422 `detail="question must not be blank"`; `conversation_id` present → `get_conversation` pre-check → `None` → 404 `{"detail": "conversation not found"}` (reuse the fetched turns as prompt history — no second read); absent → history is empty and NO row is created yet; build history via `select_history([HistoryTurn(t.role, t.content) for t in existing.turns])` (same conversation ONLY — never any other conversation's turns); adapters: `search_fn = lambda q, k: hybrid_search(db_path, q, k, embedding_model, None)` (import `hybrid_search` BY NAME for the stub seam), `chat_fn = lambda messages: chat_completion(api_key=..., model=..., messages=messages)` (import `chat_completion` BY NAME; key from settings, missing key → 502 `MODEL_API_KEY not configured` — but ONLY on the chat path: evidence-empty refusal must NOT require a key, so check key lazily inside the adapter); `result = await answer_question(..., history=history)`; exception mapping IN THIS ORDER: `QaValidationError` → 502 with cause (BEFORE the generic `ValueError` branch — it subclasses `ValueError`), `MetaAPIError` → 502 with `str(exc)`, `EmbeddingDimMismatchError`/`ValueError` from search → 500 (mirror retrieval router); AFTER successful generation persist: new conversation → ONE `create_conversation_with_turns(db, "qa", turns)` call (row + both turns atomically); continued → ONE `append_turns` call; turns are `[("user", question, mode_used, "[]"), ("assistant", answer, mode_used, citations_json)]` (a 502/500 persists NOTHING — no orphan user turns, no empty conversation rows); return `QueryResponse` with `span=[start, end]`. `GET /conversations` → summaries; `GET /conversations/{id}` → `ConversationOut` (`citations` via `json.loads` per turn; unknown → 404). Module docstring documents both seams.
- **PATTERN**: MIRROR `api/retrieval.py` (by-name seam + docstring seam note, 422/500 mapping, `response_model`) + `api/health.py` (async def, settings→explicit-params, key-missing branch) + `api/ingest.py` (`logger.warning` on rejections)
- **IMPORTS**: `json`, `logging`, `fastapi.APIRouter/HTTPException/status`, `pydantic.BaseModel/Field`, `app.core.config.get_settings`, `app.core.grounding` (`HistoryTurn`, `ModeUsed`, `QueryMode`, `select_history`), `app.core.meta_client` (`DEFAULT_META_MODEL`, `MetaAPIError`, `chat_completion` BY NAME), `app.db.chunks` (unused — qa hydrates; do NOT import), `app.db.connection.EmbeddingDimMismatchError`, `app.db.conversations`, `app.llm.qa` (`QaValidationError`, `answer_question`), `app.retrieval.search` (`TOP_K_DEFAULT`, `TOP_K_MAX`, `hybrid_search` BY NAME)
- **GOTCHA**: key check MUST be lazy (inside `chat_fn` adapter) or keyless evidence-refusal breaks — add a regression test with no key + empty DB expecting 200 refusal; `turns.citations` for the assistant turn = the response `citations` list re-serialized (`json.dumps([c.model_dump() ...])`); persist (INCLUDING conversation creation) AFTER generation, never before — a failed new-conversation request leaves `GET /conversations` empty; `context` field must not 422 on `{"explanation_id": <uuid>}` (forward-compat — test it); history derives ONLY from the pre-checked same-`conversation_id` (never list/scan other conversations)
- **VALIDATE**: `cd backend && uv run python -c "from app.api.query import router; print(sorted({r.path for r in router.routes}))"`
- **Expected**: prints `['/conversations', '/conversations/{conversation_id}', '/query']`

### UPDATE backend/app/main.py

- **IMPLEMENT**: import `app.api.query.router as query_router`; `app.include_router(query_router, prefix="/api/v1")` after the retrieval line. No other changes (CORS already covers the Vite origin; lifespan untouched).
- **PATTERN**: MIRROR existing registration lines `main.py:48-50`
- **IMPORTS**: add one import line
- **GOTCHA**: none — two-line change; verify openapi lists the new paths in the API test, not here
- **VALIDATE**: `cd backend && DATABASE_PATH=/tmp/qq.db uv run python -c "from fastapi.testclient import TestClient; from app.main import create_app; c = TestClient(create_app()); print(sorted(p for p in c.get('/openapi.json').json()['paths'] if 'query' in p or 'conversations' in p))"`
- **Expected**: prints `['/api/v1/conversations', '/api/v1/conversations/{conversation_id}', '/api/v1/query']`

### CREATE backend/tests/test_query_api.py

- **IMPLEMENT**: fixture mirroring `test_retrieval_api.py:36-86` (settings isolation + `Settings(_env_file=None)` swaps for BOTH `app.api.query.get_settings` and `app.main.get_settings`; `tmp_path` init + direct-pipeline seeding with one-hot fake vectors; by-name `hybrid_search` stub with fake query vector) PLUS `chat_completion` stub (by-name `app.api.query.chat_completion`, async, returns canned `{"answer": ..., "citations": [...]}` JSON; record received `messages` for prompt assertions). Cases: evidence happy path → 200 exact keys `{answer, citations, mode_used, conversation_id}`, citation keys `{chunk_id, artifact_id, span, excerpt}`, `mode_used == "evidence"`, excerpt matches seeded text; conversation start (no `conversation_id` → new hex ID, `GET /conversations/{id}` shows 2 turns idx `[0,1]` roles `[user, assistant]`); conversation continue (pass back → 4 turns, idx `[0..3]`, same ID); unknown `conversation_id` → 404 `{"detail": "conversation not found"}`; blank question (`""`, `"   "`) → 422; `top_k` 0/51 → 422, 50 → 200; invalid `mode` → 422; `context: {"explanation_id": <uuid>}` accepted (200, ignored); auto personal (`"What did I accomplish at Sesame?"` over seeded DB) → `mode_used evidence`; auto conceptual (`"Explain what an event loop is"` over seeded DB) → `mode_used teaching` WITH passages in the recorded messages (personalization attached, answer uncited); evidence+empty DB → 200 refusal (answer == `REFUSAL_ANSWER`, citations `[]`, chat stub NOT called — assert via flag); Meta down (chat stub raises `MetaAPIError(503, "boom")`) → 502 with "boom"; teaching garbage (chat stub returns `"not json"` with mode teaching) → 502 with validation cause (proves `QaValidationError` ordering); no-key + empty DB + evidence → 200 refusal WITHOUT key (lazy-key regression test); no-key + teaching path → 502 `MODEL_API_KEY not configured`; 502/500 persist nothing on NEW conversations (`GET /conversations` empty after failed call) and append nothing on continue (turn count unchanged); continue passes history (second call's recorded messages contain the first question + first answer as `[system, user, assistant, user-final]`); isolation (seed conversation B with marker text, continue conversation A → A's recorded messages lack B's marker); `GET /conversations` shape `{id, kind: "qa", created_at, turn_count}`; `GET /conversations/{unknown}` → 404; key canary never in any body; openapi contains all three paths.
- **PATTERN**: MIRROR `test_retrieval_api.py` wholesale (module docstring seam note, `_client` builder, `db_of` helper, exact-keys assertions, status matrix)
- **IMPORTS**: `os`, `pathlib.Path`, `pytest`, `fastapi.testclient.TestClient`, `app.retrieval.search as search_mod`, `app.core.config Settings/get_settings`, `app.core.grounding.REFUSAL_ANSWER`, `app.core.meta_client.MetaAPIError`, `app.db.connection.init_db`, `app.ingest.pipeline.ingest_source`, `app.main.create_app`
- **GOTCHA**: the `chat_completion` stub signature must accept the router's keyword call — define `async def fake_chat(*, api_key, model, messages, **kw)` and mirror the REAL param names from the router task; TestClient + async endpoint works transparently (no `asyncio.run` needed at this level); seeding helper needs the one-hot closure from the retrieval test file — copy it, do not import across test modules
- **VALIDATE**: `cd backend && uv run pytest tests/test_query_api.py -q`

### CREATE frontend/src/api/types.ts

- **IMPLEMENT**: `export type QueryMode = "evidence" | "teaching" | "auto"`, `ModeUsed = "evidence" | "teaching"`; `Citation { chunk_id: number; artifact_id: string; span: [number, number]; excerpt: string }`; `QueryResponse { answer: string; citations: Citation[]; mode_used: ModeUsed; conversation_id: string }`; `QueryRequest { question: string; mode?: QueryMode; top_k?: number; context?: { explanation_id: string | null }; conversation_id?: string | null }`; `ChunkDetail { id: number; artifact_id: string; chunk_idx: number; span: [number, number]; text: string }`; `Turn { id: string; idx: number; role: "user" | "assistant"; content: string; mode: string | null; citations: Citation[]; created_at: string }`; `ConversationDetail { id: string; kind: string; created_at: string; turns: Turn[] }`; `ConversationSummary { id: string; kind: string; created_at: string; turn_count: number }`. Field names mirror backend JSON exactly (snake_case on the wire — no renaming).
- **PATTERN**: plain exported types, no runtime code (backend Pydantic shapes are the source of truth — re-check `api/query.py` before writing)
- **IMPORTS**: none
- **GOTCHA**: `span` is a 2-tuple, not `number[]` (enables `span[0]`/`span[1]` without length checks); keep `citations: Citation[]` on `Turn` even though user turns send `[]`
- **VALIDATE**: `cd frontend && npx tsc -b --dry 2>/dev/null; npx tsc --noEmit -p tsconfig.app.json`
- **Expected**: exit 0, no output

### CREATE frontend/src/api/query.ts

- **IMPLEMENT**: `postQuery(req: QueryRequest): Promise<QueryResponse>` → `apiPost("/api/v1/query", req)`; `getChunk(id: number): Promise<ChunkDetail>` → `apiGet("/api/v1/chunks/{id}")`; `listConversations(): Promise<ConversationSummary[]>` → `apiGet("/api/v1/conversations")`; `getConversation(id: string): Promise<ConversationDetail>` → `apiGet("/api/v1/conversations/{id}")`. No URL building, no fetch, no try/catch — errors propagate as thrown `Error` from `parseJson` (ChatView displays `err.message`).
- **PATTERN**: MIRROR `client.ts:16-30` (all calls through `apiGet`/`apiPost`)
- **IMPORTS**: `apiGet, apiPost` from `./client`; types from `./types`
- **GOTCHA**: none — 20-line file; keep it that way
- **VALIDATE**: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`
- **Expected**: exit 0, no output

### CREATE frontend/src/api/query.test.ts

- **IMPLEMENT**: mock global `fetch` (`vi.stubGlobal("fetch", vi.fn())`, restore in `afterEach`); `postQuery` sends POST to `http://localhost:8000/api/v1/query` with JSON body incl. `conversation_id` passthrough; `getChunk(7)` GETs `/api/v1/chunks/7`; non-OK response rejects with `API request failed: 502 ...`; `VITE_API_URL` honored (mirror `client.test.ts:13-17`); list/get conversation URLs. Mirror `client.test.ts` `describe/it/expect` + `vi.stubEnv` shape.
- **PATTERN**: MIRROR `api/client.test.ts` (lines 1–24)
- **IMPORTS**: `vitest`, `./query`
- **GOTCHA**: `fetch` mock must return `{ ok: true, json: async () => payload }` (match `parseJson`'s usage: `response.ok`, `response.status`, `response.statusText`, `response.json()`); `vi.unstubAllGlobals()` in `afterEach` alongside `vi.unstubAllEnvs()`
- **VALIDATE**: `cd frontend && npm test -- --run src/api/query.test.ts`

### CREATE frontend/src/views/ChatView.tsx

- **IMPLEMENT**: `useState` for `messages: {role, content, citations?, modeUsed?}[]`, `input`, `conversationId: string | null`, `mode: QueryMode` (default `"auto"`, `<select>` with evidence/teaching/auto), `loading`, `error: string | null`, `activeCitation: ChunkDetail | null`; `send()`: skip when blank/loading; optimistic user bubble; `postQuery({question, mode, conversation_id: conversationId})`; store returned `conversation_id`; append assistant bubble; `catch` → `error` banner (dismissible); render: message list (`role` → alignment/labels "You"/"ThoughtBridge"), assistant mode badge (`mode_used` + grounding label: evidence → "from your notes"; teaching without citations → "general explanation"; teaching WITH citations → "general explanation + your notes" — F-11 visibility for blended answers), citation chips (`[chunk_id]` buttons → `getChunk` → detail panel with full text + artifact link text + span, close button); input row (text input + Send button, Enter submits, disabled while loading); disclosure line "Conversations are saved and retrievable." (F-12 UI disclosure — static text, Phase 1 turns-only); Tailwind classes consistent with `App.tsx` (rounded border px-3 py-1 etc.); `aria-label`s on input/send/citation buttons (test + a11y hooks).
- **PATTERN**: function component + hooks (mirror `App.tsx`); errors displayed, never swallowed (mirror backend 502 honesty)
- **IMPORTS**: `react` (`useState`), `../api/query`, `../api/types` (type-only)
- **GOTCHA**: NO markdown rendering library (answer renders as plain paragraphs split on `\n\n` — minimal UI, no new runtime deps); NO auto-scroll or streaming (out of scope); `conversation_id` state is the ONLY conversation memory the view keeps (history reload via `getConversation` is NOT wired — minimal scope, note as future); chips show `chunk_id`, panel shows `text` (full) — never truncate client-side
- **VALIDATE**: `cd frontend && npx tsc --noEmit -p tsconfig.app.json && npm test -- --run src/api/query.test.ts`
- **Expected**: exit 0 both; ChatView covered by its own test next

### UPDATE frontend/vite.config.ts + package.json (jsdom test setup)

- **IMPLEMENT**: `npm install -D jsdom @testing-library/react` (exact versions resolved by npm at install; record them in the execution report); `vite.config.ts` `test.environment`: `"node"` → `"jsdom"`. Verify existing `client.test.ts` still passes under jsdom.
- **PATTERN**: additive dev-deps only — no runtime dependency changes, no config restructuring
- **IMPORTS**: n/a
- **GOTCHA**: `npm install` rewrites `package-lock.json` — expected, keep it; if `npm audit` flags the new deps, record exceptions per AGENTS.md validation rule (do not silently downgrade)
- **VALIDATE**: `cd frontend && npm test -- --run src/api/client.test.ts`
- **Expected**: exit 0, all existing tests pass under jsdom

### CREATE frontend/src/views/ChatView.test.tsx

- **IMPLEMENT**: `render`/`screen`/`fireEvent` from `@testing-library/react`; mock `fetch` per-test: first call returns canned `QueryResponse` (2 citations), `getChunk` call returns canned `ChunkDetail`; cases: renders input + mode select + disclosure text; typing + clicking Send calls `/api/v1/query` with `{question, mode: "auto", conversation_id: null}` and renders the answer + 2 chips; second send passes the stored `conversation_id`; clicking a chip fetches `/api/v1/chunks/{id}` and shows full text in the panel; 502 response shows the error banner and keeps the input content; evidence badge reads "from your notes"; teaching badge "general explanation" when uncited and "general explanation + your notes" when cited (three renders). `await screen.findByText(...)` for async renders (Testing Library async — no `act` warnings).
- **PATTERN**: Testing Library queries by role/label/text (see docs link); mocked global fetch (mirror `query.test.ts` mock shape)
- **IMPORTS**: `vitest`, `@testing-library/react`, `./ChatView`
- **GOTCHA**: component uses `import.meta.env` via `client.ts` — works under vitest; `fireEvent.change` on the input then `fireEvent.click` on Send; assert fetch CALL BODIES via `JSON.parse(vi.mocked(fetch).mock.calls[0][1].body)`; unmount between tests is automatic with Testing Library auto-cleanup
- **VALIDATE**: `cd frontend && npm test -- --run src/views/ChatView.test.tsx`

### UPDATE frontend/src/App.tsx (Chat tab)

- **IMPLEMENT**: import `ChatView`; prepend `{ id: "chat", label: "Chat" }` to `VIEWS` (no `blurb` — chat renders the component); default `useState<ViewId>("chat")`; `main` renders `<ChatView />` when `view === "chat"`, else the placeholder `<p>{active.blurb}</p>` (type: make `blurb` optional on the chat entry). Keep all five existing placeholders byte-identical.
- **PATTERN**: MIRROR existing `VIEWS` + `useState` + `aria-pressed` tab structure (lines 3–41)
- **IMPORTS**: add `import ChatView from "./views/ChatView"`
- **GOTCHA**: `as const` tuple + `.find` typing — the chat entry needs the same shape; simplest: give chat a `blurb: ""` and branch on `id` in the render (avoids union-type churn)
- **VALIDATE**: `cd frontend && npm run build`
- **Expected**: exit 0, `dist/` emitted (tsc -b + vite build)

### UPDATE backend/README.md (first inference call record)

- **IMPLEMENT**: after the live-call validation task below succeeds, edit the `## Meta Model` line: replace `verified listed via GET /models, no inference call` with `verified listed via GET /models (CHECKPOINT 1); first inference via POST /v1/chat/completions from POST /api/v1/query (grounded Q&A, Phase 1)`. One sentence, nothing else.
- **PATTERN**: MIRROR the existing single-paragraph `## Meta Model` style
- **IMPORTS**: n/a
- **GOTCHA**: do this task ONLY after a real 200 from Meta on the chat path (record date in the execution report, not the README)
- **VALIDATE**: `cd backend && grep -c "chat/completions" README.md`
- **Expected**: prints `1`

---

## TESTING STRATEGY

Backend: `pytest` (`testpaths = ["tests"]`, `pythonpath = ["."]` per `pyproject.toml`). Deterministic layers get true unit tests (grounding builders, auto rule, refusal, conversation repo, RRF-adjacent citation mapping); LLM-touching paths get contract tests with stubbed search + stubbed chat (JSON schema validation, citation presence/absence, hallucinated-ID dropping, refusal behavior, no-LLM-call proof via raising stubs); endpoint tests assert exact JSON keys, the full status matrix (200/404/422/502/500), turn rows in the DB, and openapi paths. The default suite NEVER touches the network (Meta stubbed, fastembed stubbed via fake vectors) — exactly one live Meta call happens in manual validation.

Frontend: `vitest run` under `jsdom`; client tests assert URLs/bodies/error propagation with mocked `fetch`; the component test asserts render → send → citations → continue → error flows with mocked `fetch`. Type safety via `tsc -b` inside `npm run build`.

### Unit Tests

`test_grounding.py` (mode resolution, message structure, refusal content), `test_conversations.py` (repo CRUD + ordering + idx sequencing), `test_meta_client.py` chat additions (wire shape, error mapping, truncation, key hygiene), `query.test.ts` (client URLs/bodies). No DB fixtures except `test_conversations.py` (`tmp_path` + `init_db`); no network anywhere.

### Integration Tests

`test_qa.py` (orchestration over stubbed search/chat + stubbed `get_chunks` — every refusal/validation branch), `test_query_api.py` (full TestClient stack: real router + real qa.py + real search legs + real DB, only the embedding model and Meta stubbed), `ChatView.test.tsx` (component over mocked fetch). These prove the seams compose: retrieval → prompt → validation → persistence → response.

### Edge Cases

- Evidence mode + empty retrieval → 200 refusal, zero Meta calls, turns STILL persisted (the refusal is the assistant turn — user asked, app answered; new conversation created atomically WITH the turns)
- Evidence mode + non-empty-but-unsupportive retrieval → model called, zero valid citations → code refusal (model-mediated refusal; the L4 seeded-corpus refusal step exercises this path)
- Evidence mode + model cites out-of-range passage → citation dropped; all-dropped → refusal (anti-invention is code-enforced)
- Evidence mode + model returns invalid JSON → refusal, logged (never 502 — silence/garbage in evidence mode is a refusal, not an upstream failure)
- Teaching mode + model returns invalid JSON → 502 with validation cause (the model genuinely failed; teaching has no silence fallback)
- Teaching mode + empty KB → answers from general knowledge (teaching never blocked by empty notes — PRD §6)
- `conversation_id` unknown → 404, nothing persisted; failed generation (502/500) → nothing persisted (no orphan user turns, no empty conversation rows), retry with same ID still works
- Continued conversation → prior same-conversation turns (bounded by `select_history`) are prompt history; other conversations' turns never included (isolation tested with marker text)
- History is dialogue context, never evidence: citations reference current-retrieval passages only; assistant history is never cited or mined
- Blank/whitespace question → 422 before any retrieval, chat, or persistence
- Missing API key + evidence-empty refusal → 200 (lazy key check); missing key + any chat path → 502 naming `MODEL_API_KEY`
- `context.explanation_id` present → accepted and ignored (forward-compat for Phase 2 interrupt/resume)
- `top_k` boundaries 1/50 pass, 0/51 fail (mirror retrieval contract)
- Citation excerpts come from DB rows, never model text (assert excerpt == seeded text in API test)
- Key canary absent from every response body and error string (mirror `test_config.py:40-44` + probe tests)

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

Every command or block MUST state its exact pass signal on an `Expected:` line (exit code plus the key output, count, or observation that proves success — e.g. `Expected: exit 0, "11 passed"`, `Expected: exit 0, docs:200`). A check whose passing output is not specified cannot confirm anything; do not write checks you cannot describe passing.

### Level 1: Syntax & Style

`cd backend && uv run ruff check . && uv run ruff format --check .`
Expected: exit 0, `All checks passed!` + `N files already formatted` (no `would reformat`)

`cd backend && uv run mypy app`
Expected: exit 0, `Success: no issues found` (non-strict per AGENTS.md; new modules must be annotation-clean — `chat_fn`/`search_fn` protocols typed)

`cd frontend && npm run lint`
Expected: exit 0 (oxlint per package.json; fix or justify every finding)

### Level 2: Unit Tests

`cd backend && uv run pytest tests/test_grounding.py tests/test_conversations.py tests/test_meta_client.py tests/test_qa.py -q`
Expected: exit 0, `N passed` with N ≥ 40 (count recorded in execution report; zero failures/skips)

`cd frontend && npm test -- --run src/api/query.test.ts`
Expected: exit 0, all client tests pass

### Level 3: Integration Tests

`cd backend && uv run pytest -q`
Expected: exit 0, full suite green (new + all pre-existing: scaffold/ingest/retrieval/health — no regressions)

`cd frontend && npm test -- --run`
Expected: exit 0, full vitest suite green (client + ChatView + pre-existing)

`cd frontend && npm run build`
Expected: exit 0, `tsc -b` clean + `dist/` emitted

### Level 4: Manual Validation

Performer: `agent` (executable in this environment — the executor MUST run it)

1. Seed + serve: `cd backend && uv run uvicorn app.main:create_app --factory --port 8000 &` then `curl -s -X POST localhost:8000/api/v1/artifacts -H 'Content-Type: application/json' -d '{"source_type":"note","title":"seed","content":"The deploy pipeline uses Modal with a persistent volume for the SQLite file."}'`; expected: `201 {"artifact_id": "<hex>", "chunks": 1}`
2. Live grounded answer: `curl -s -X POST localhost:8000/api/v1/query -H 'Content-Type: application/json' -d '{"question":"Where does the SQLite file live in the deploy pipeline?","mode":"evidence"}'`; expected: `200`, `mode_used == "evidence"`, answer names Modal/persistent volume, `citations[0].excerpt` contains "persistent volume", `conversation_id` is hex (THIS is the first inference call — record model ID + date in the execution report, then do the README task)
3. Refusal (model-mediated: seeded corpus returns neighbors, model finds no support, code refuses on zero valid citations): same endpoint with `{"question":"What is the CEO's favorite color?","mode":"evidence"}`; expected: `200`, answer == refusal text, `citations == []`
4. Continue: `curl` with `{"question":"And what serves the backend?","conversation_id":"<id from step 2>"}`; expected: same `conversation_id` echoed AND the answer resolves the follow-up in the context of step 2 (proves prior turns reached the prompt)
5. Turn log: `curl -s localhost:8000/api/v1/conversations/<id>`; expected: 4 turns, `idx [0,1,2,3]`, roles `[user, assistant, user, assistant]`, assistant turns carry `mode` + `citations`
6. Kill the backend (`jobs` → `kill %1` or `pkill -f "uvicorn app.main"`); expected: port 8000 free

Performer: `human` (requires a real browser + judgment the agent lacks)

1. Start both dev servers exactly as written: terminal A `cd backend && uv run uvicorn app.main:create_app --factory --port 8000`; terminal B `cd frontend && npm run dev`; open `http://localhost:5173`; expected: Chat tab active by default with input, mode select, and disclosure line
2. Type "Where does the SQLite file live?" (after seeding via step 1 above or any note) and press Enter; expected: user bubble + assistant bubble with "from your notes" badge and ≥1 citation chip within ~30s
3. Click a citation chip; expected: detail panel shows the full chunk text, chunk ID, and span — the original note content one click away
4. Select "teaching" mode, ask "What is a vector database?"; expected: answer with "general explanation" badge (citations optional)
5. Stop both servers (Ctrl-C in each terminal); expected: terminals idle, no stray processes

### Level 5: Additional Validation (Optional)

`cd backend && uv run pytest tests/test_query_api.py -q -k "refusal or 404 or 502 or persist"`
Expected: exit 0 — focused re-run of the load-bearing branches (refusal, unknown-conversation, upstream-failure, persistence-atomicity) as a final confidence pass

---

## MANUAL VERIFICATION CHECKLIST

Label each item `agent` or `human` (same performer rule as Level 4). Each item MUST give numbered steps and the exact expected observable result — never a bare "verify X works."

- [ ] [agent] live evidence answer: 1) seed one note via `POST /artifacts` (L4 step 1); 2) `POST /query` evidence asking about the seeded fact; expected: `200`, answer contains the seeded fact, `mode_used == "evidence"`, `citations[0].excerpt` contains seeded wording
- [ ] [agent] refusal + persistence: 1) `POST /query` evidence with an unanswerable question (seeded corpus → model-mediated zero-citation refusal); 2) `GET /conversations/{returned_id}`; expected: step 1 is `200` with refusal text + `citations == []`; step 2 shows 2 turns (user, assistant) with the refusal as the assistant turn
- [ ] [agent] conversation continuation: 1) `POST /query` without ID; 2) `POST /query` with the returned ID; 3) `GET /conversations/{id}`; expected: same ID echoed in step 2; step 3 has 4 turns idx `[0..3]` roles alternating from `user`
- [ ] [agent] failure atomicity: 1) stop Meta reachability (temporarily set `MODEL_API_KEY` to `invalid` and restart the dev server); 2) `POST /query` teaching; 3) `GET /conversations`; expected: step 2 is `502` naming the upstream cause; step 3 contains no conversation from step 2 (nothing persisted on failure); restore the key afterwards
- [ ] [human] chat view round-trip: 1) open `http://localhost:5173` with both dev servers running; 2) send a question about seeded notes; 3) click a citation chip; expected: answer bubble with "from your notes" badge appears; chip click opens a panel with the full original chunk text
- [ ] [human] mode badge distinction: 1) in Chat view select teaching mode; 2) ask a general concept question; expected: badge reads "general explanation", visually distinct from the evidence badge
- [ ] [human] docs/config reflection: 1) open `backend/README.md`; 2) confirm the `## Meta Model` line names the first chat-completion call; expected: line contains `POST /v1/chat/completions` and no longer claims "no inference call"

## ROLLBACK CONSIDERATIONS

- Revert safely: `git revert` the deliverable commit(s) — backend router removal restores prior API surface; frontend `App.tsx` revert restores placeholders. No schema migration exists (tables predate this deliverable), so no data migration to undo.
- Data handling: `conversations`/`turns` rows created by this deliverable are inert if the code is reverted (no other reader yet); a fresh `rm data/thoughtbridge.db` + restart re-inits. Never delete a shared/seeded DB without backup.
- Config: `package-lock.json` gains jsdom/testing-library (dev-only); reverting restores the old lockfile — run `npm ci` after revert.

## ACCEPTANCE CRITERIA

Each criterion MUST name the check that proves it: the validation level/command, the test file, or the manual-checklist item — plus the exact expected result. A criterion with no verification named is an incomplete plan.

- [ ] `POST /query` evidence over seeded notes returns the right cited passage (L4 agent steps 1–2: answer contains seeded fact, `citations[0].excerpt` contains seeded wording)
- [ ] Evidence mode with empty retrieval refuses without calling the model (L2 `test_qa.py` raising-stub case + L3 `test_query_api.py` evidence-over-empty-DB case: `200`, refusal text, `citations == []`, chat stub flag uncalled)
- [ ] Evidence mode over a seeded corpus with no supporting passage refuses via the model-mediated path (L4 agent refusal step: `200`, refusal text, `citations == []`)
- [ ] Hallucinated/uncited evidence output becomes refusal in code (L2 `test_qa.py` mixed `[1, 9]` → single citation and `[9]` → refusal cases)
- [ ] `auto` routes by question intent: personal-history-seeking → evidence, otherwise teaching with passages attached (L2 `test_grounding.py` `route_auto` matrix incl. the three owner examples + L3 `test_query_api.py` auto-personal/auto-conceptual cases over the same seeded DB)
- [ ] Every exchange persists as ordered role-labeled turns under a stable conversation ID (L4 agent continuation step: 4 turns, idx `[0..3]`, alternating roles)
- [ ] Unknown `conversation_id` → 404, failed generations persist nothing — including no empty conversation row (L3 `test_query_api.py` 404 + new-conversation atomicity cases; manual atomicity item)
- [ ] Upstream Meta failures surface as 502 with cause (L3 `test_query_api.py` Meta-down case: 502 containing stub cause; manual atomicity item)
- [ ] Malformed teaching-mode model output surfaces as 502 with validation cause (L3 `test_query_api.py` teaching-garbage case; router catches `QaValidationError` before generic `ValueError`)
- [ ] Follow-ups receive bounded same-conversation history and other conversations never leak in (L3 `test_query_api.py` history-forwarding + marker-isolation cases; L4 agent continuation step resolves the follow-up in context)
- [ ] `GET /conversations` + `GET /conversations/{id}` return PRD shapes (L3 `test_query_api.py` shape cases: `{id, kind, created_at, turn_count}` / ordered `turns`)
- [ ] Chat view sends, renders answers with mode badges + clickable citations resolving to full chunk text (L3 `ChatView.test.tsx` + human chat round-trip item)
- [ ] "From your notes" vs "general explanation" vs blended "general explanation + your notes" visibly distinct (L3 `ChatView.test.tsx` three-badge cases + human badge item)
- [ ] Full backend gates green: `pytest`, `ruff check`, `ruff format --check`, `mypy app` (L1–L3 commands, all exit 0)
- [ ] Full frontend gates green: `npm test -- --run`, `npm run build` (L3 commands, both exit 0)
- [ ] No regressions: pre-existing scaffold/ingest/retrieval/health suites pass unmodified (L3 full-suite `pytest`, exit 0)
- [ ] First inference call recorded: README no longer claims "no inference call" (human docs item: `grep -c chat/completions README.md` → `1`)
- [ ] Test coverage: no repo-wide threshold is stated (AGENTS.md/PRD set none) — this plan adds 4 backend test files + 2 frontend test files covering every new branch in the edge-case list

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

- **Design decision — deterministic no-LLM-call refusal:** when evidence mode has zero retrieval hits, `qa.py` returns the refusal without calling the model. Rationale: cheaper (zero hidden-reasoning tokens), faster, and provably tested via a raising stub; matches "code enforces cascades" (PRD §6) and "refusal is normal, not an error" (AGENTS.md). The evidence prompt ALSO instructs refusal for the non-empty-but-unsupportive case, and code validates citations regardless — three independent layers.
- **Design decision — `auto` = intent-routed by narrow personal-history patterns (owner decision, Cycle 1):** `route_auto` sends questions ABOUT the user's own work/history/accomplishments to evidence mode and everything else to teaching mode with passages attached for personalization — covering the owner's three cases (personal → evidence, conceptual → teaching, blended "explain X using something I've worked on" → teaching-with-passages, badged "general explanation + your notes"). Rationale: deterministic, zero extra LLM calls, unit-testable; patterns stay deliberately narrow so the safe default is teaching-with-passages (general answer + personalization, never invention of personal facts). An LLM classifier is deferred to Phase 3+ only if measured routing disappoints. Every mode ALWAYS retrieves; only evidence mode treats retrieval as the closed world.
- **Design decision — bounded same-conversation history in prompts (owner decision, Cycle 1):** continuations feed `select_history` output (last 6 turns, 4000 chars, oldest dropped first) as dialogue context; other conversations are never read. Rationale: recency-bounded history is the MVP-sufficient context window (no semantic selection, no summarization); history is labeled context, never evidence — citations reference current-retrieval passages only, so assistant history can never be cited or mined (consistent with F-12 role asymmetry).
- **Design decision — untrusted-passage framing in both system prompts (Cycle 1):** passages are delimited untrusted user data, never instructions (PRD §9 "imported text cannot override system behavior"). Substring-tested, not just wished.
- **Design decision — 1-based passage numbers as the citation contract:** the model cites display ordinals `[n]`, code maps them to chunk IDs. Rationale: raw chunk IDs are sparse integers the model would hallucinate variants of; ordinals bound the valid set to `[1..N]` so validation is a range check. Excerpts/artifact IDs/spans always come from DB rows.
- **Design decision — teaching garbage → 502, evidence garbage → refusal:** evidence mode treats unparseable/uncited output as silence (refuse); teaching mode has no silence fallback, so malformed model output is a genuine upstream failure (502 with validation cause). This asymmetry is deliberate and tested on both sides.
- **Design decision — persist AFTER generation, never before (atomicity fixed, Cycle 1):** a 502/500 leaves no orphan user turn AND no empty conversation row — new conversations are created together with their turns in one transaction via `create_conversation_with_turns`. Trade-off: a crash between generation and persistence loses the exchange — acceptable for single-user MVP (no background jobs to reconcile).
- **Design decision — `context.explanation_id` accepted-but-ignored:** preserves the PRD §10 wire shape so Phase 2 interrupt/resume needs no client change; ignoring (not 422ing) is the forward-compatible choice. Documented in the router docstring + this plan.
- **Design decision — lazy API-key check inside the chat adapter:** keyless deployments can still serve evidence refusals and health detail; the 502 names `MODEL_API_KEY` only when a model call is actually attempted. Regression-tested.
- **Design decision — chips-below-answer, no inline marker parsing:** the answer may contain `[n]` text but the UI renders citations as chips under the bubble (no markdown lib, no marker parser in Phase 1). Inline rendering is a Phase 4 polish candidate, not a correctness issue.
- **Design decision — jsdom + @testing-library/react as dev-only deps:** the scaffold's `node` vitest environment cannot render components; flipping to jsdom keeps the existing client tests passing (verified in-task) and enables one focused component test. No new runtime dependencies.
- **Trade-off — `get_chunks` call inside `qa.py`:** prompts need full chunk text but `SearchHit` carries truncated excerpts, so orchestration re-reads the hit rows. One extra indexed `IN` query per call — negligible at MVP scale, and it reuses the canonical hydration path rather than widening `SearchHit`.
- **Risk — `response_format: json_object` support on `muse-spark-1.3`:** corroborated by third-party docs, not yet proven against the live API. Mitigated three ways: prompt says "JSON only, no fences"; parser strips fences; executor validates live and drops `response_format` if rejected (documented fallback in the meta_client task).
- **Risk — Spark hidden reasoning eating `max_tokens`:** `QA_MAX_TOKENS = 4096` is deliberately generous; truncation would surface as invalid JSON → evidence-refusal / teaching-502 (loud, not silent). Never lower without a live test.
- **Out-of-phase guard:** `GET /conversations` list exists but the Chat view does NOT load history (single-session view); `DELETE /conversations/{id}` is Phase 3; `tb_conversation` ingestion is Phase 3 — the turn rows laid down here are its input, and no chat rework is expected.

---

## Revision History

### Cycle 1

Review: `.agents/plans/reviews/grounded-qa-minimal-chat-ui-plan-review.md` (Overall: NEEDS_DECISION; owner resolved both escalations 2026-11-02 — intent-based auto routing, same-conversation prompt history).

Findings addressed (quoted) and what changed:

1. "Owner must decide auto-mode semantics: the hit-gated rule effectively routes every query to evidence once any note exists ... which conflicts with PRD F-2." → Replaced `resolve_mode(requested, hit_count)` with `route_auto(question)`: narrow `PERSONAL_HISTORY_PATTERNS` route personal-history-seeking questions to evidence, everything else to teaching with passages attached for personalization (owner's three examples are verbatim test cases). Retrieval now runs in EVERY mode; only evidence treats it as the closed world. Teaching-with-citations gets a blended "general explanation + your notes" badge. Touched: Solution Statement, Scope, grounding task, test_grounding task, qa task, test_qa task, test_query_api auto cases, ChatView badge + test, acceptance criteria, edge cases, NOTES.
2. "Owner must decide whether continuing a conversation should feed prior turns into the model prompt ... or remain persistence-only." → Continuations feed bounded same-conversation history (`HistoryTurn`, `select_history`: last 6 turns / 4000 chars, oldest dropped first) into `build_messages`; router reuses the pre-check `get_conversation` turns (same ID only, never other conversations); history is dialogue context, never evidence (citations reference current passages only). Touched: grounding task, qa task (`history` param), test_qa, router task, test_query_api (forwarding + marker-isolation cases), L4 step 4 expectation, acceptance criteria, edge cases, NOTES.
3. "Move conversation creation so a new conversation row is written only after successful generation." → Added `create_conversation_with_turns` (single transaction) to the repository task; router creates the row only after `answer_question` succeeds; strengthened the atomicity test wording (new-conversation `GET` empty after 502/500) and the persist-after-generation note.
4. "Add untrusted-data framing to both system prompts ... per PRD §9." → Both system prompts state passages are delimited UNTRUSTED data never to be followed as instructions; test_grounding asserts "untrusted"+"never"+"instructions" substrings in both prompts.
5. "Reword the 'refuses without calling the model' acceptance criterion so the no-model-call proof cites only the empty-retrieval stub tests, and describe the L4 refusal step as a model-mediated zero-citation refusal." → Split into two criteria (stub-proven no-call refusal + L4 model-mediated refusal); L4 step 3 and the manual checklist now name the model-mediated path; added a matching edge-case bullet.
6. "Add a test_query_api.py case where the chat stub returns garbage in teaching mode and expects 502, and specify that the router catches QaValidationError before any generic ValueError→500 handler." → Added the teaching-garbage 502 case, the explicit exception-ordering rule in the router task, and a dedicated acceptance criterion.

Not done: nothing — all six findings (2 owner-decided + 4 routine) are addressed. No new product decisions were taken beyond the owner's two rulings; the narrow-pattern heuristic and 6-turn/4000-char bounds are documented MVP judgments inside the decided designs, tunable without architectural change.

### Post-execution note (2026-11-02, owner-requested UX change)

Owner asked to remove the mode dropdown from the Chat view: ThoughtBridge should always route intelligently instead of asking the user to pick auto/teaching/evidence. Implemented after execution + review-execution completed: `frontend/src/views/ChatView.tsx` no longer renders the `<select>` (or its `mode` state); every `postQuery` sends `mode: 'auto'` and the backend `route_auto` intent router decides per question. The per-answer grounding badge still reports the mode used. `frontend/src/views/ChatView.test.tsx` render test updated to assert the select is absent; the send-body test still asserts `mode: 'auto'`. Verified: vitest 16/16, `npm run build` green, oxlint 0/0. Backend and API contract unchanged (explicit modes still accepted server-side). This note is the only plan change — no review cycle consumed.


