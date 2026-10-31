# CLAUDE.md

This file provides guidance to coding agents working with code in this repository.

## Project Overview

ThoughtBridge is an AI-powered memory and learning app for people who think differently — combining personalized analogy-based learning, work documentation with accomplishment recognition, and interview preparation grounded in the user's real knowledge. Hackathon MVP (Meta AI Developer Hackathon, Indie track): one FastAPI + SQLite pipeline with three frontend surfaces (Learn, Work, Practice/Interview). See [PRD.md](PRD.md) for full requirements (v1.2).

**Repo state:** greenfield — no application code yet. `backend/` and `frontend/` are scaffolded in PRD Phase 1. The existing `.agents/`, `.claude/`, and `tools/` directories are the owner's workflow starter and tooling, not the product.

---

## Tech Stack

| Technology | Purpose |
|------------|---------|
| Python 3.12 (Homebrew, never macOS system Python) | Backend runtime (pinned for sqlite-vec compat) |
| FastAPI + Pydantic v2 + Uvicorn | Async API backend |
| SQLite + FTS5 + sqlite-vec | Single-file store: relational + keyword + vector |
| fastembed (ONNX, CPU) | Local embeddings, zero marginal cost |
| Meta Model API (`api.meta.ai/v1`, Muse Spark) | All LLM reasoning — no other model provider |
| React + TypeScript + Vite + Tailwind | Frontend |
| pytest + ruff | Backend tests, lint/format |

Deliberately not used: LangChain/LangGraph/LlamaIndex, vector DBs, Postgres, agents, fine-tuning, custom auth.

---

## Commands

Exact commands are established during Phase 1 scaffolding and recorded here. Expected shape:

```bash
# Backend (from backend/)
pytest                  # run tests
ruff check . && ruff format --check .   # lint/format
uvicorn app.main:app --reload           # dev server

# Frontend (from frontend/)
npm run dev             # dev server
npm run build           # production build
npm test                # tests
```

---

## Project Structure

```
ThoughtBridge/
├── PRD.md              # Product requirements (authoritative for scope)
├── CLAUDE.md           # This file (authoritative for working conventions)
├── backend/
│   └── app/
│       ├── api/        # Routers: ingest, query, learn, work, practice, admin
│       ├── core/       # Config, Meta API client, grounding-mode contracts
│       ├── db/         # Schema, repositories
│       ├── ingest/     # Source adapters + chunker
│       ├── retrieval/  # Embedder, hybrid search + RRF
│       └── llm/        # Extraction, explainer, question-gen, evaluation
├── frontend/
│   └── src/
│       ├── api/        # Typed API client
│       ├── views/      # Capture, Learn, Work, Practice, Interview
│       └── components/ # Citations, feedback cards, provenance views
├── tools/              # Owner's dev tooling (not product code)
└── conversation-log/   # Private session logs — gitignored, never commit
```

---

## Architecture

One pipeline, three surfaces: ingest → chunk → embed → retrieve → generate is built once; learning, work docs, and interview prep are views over it.

- **Four layers with provenance:** SourceArtifact (immutable) → Chunk → ExtractedFact → AIInterpretation. Interpretations never re-enter the index as truth. Every derived item links to its sources.
- **Two grounding modes:** evidence mode (closed world — personal claims cite chunk/fact IDs or refuse) vs. teaching mode (open world — general knowledge plus personalization when retrieved).
- **Conversation memory:** in-app turns persist with role labels under a conversation id (Phase 1); ingested via the `tb_conversation` adapter (Phase 3). Assistant turns are never mined as evidence.
- **LLM vs. deterministic:** the model drafts; code chunks, retrieves, scores, enforces cascades, and validates every LLM output against a JSON schema at the boundary.

---

## Code Patterns

### Naming Conventions

- Backend modules and functions: `snake_case`; Pydantic models and classes: `PascalCase`.
- Frontend components and files: `PascalCase.tsx` for components, `camelCase.ts` for utilities.
- Database tables: `snake_case` plural (`artifacts`, `chunks`, `facts`, `interpretations`, `explanations`, `attempts`, `conversations`, `turns`).

### File Organization

- One FastAPI router per API area under `backend/app/api/`; business logic lives in `ingest/`, `retrieval/`, `llm/` — routers stay thin.
- Grounding-mode prompt contracts live in `backend/app/core/` and are shared, never copy-pasted per feature.
- Frontend views compose shared components; citation/provenance rendering is shared, not per-view.

### Error Handling

- Upstream Meta API failures surface as 502 with the cause — never silently swallowed or faked.
- LLM outputs that fail schema validation are rejected and logged, never partially applied.
- Speculation refusal (evidence mode with silent sources) is a normal, tested response — not an error.

---

## Testing

- **Run tests**: `pytest` (backend); `npm test` (frontend) — from the respective directories.
- **Test location**: `backend/tests/` mirroring `backend/app/`; frontend colocated or `frontend/src/__tests__/`.
- **Pattern**: deterministic behavior gets unit tests (chunking, RRF fusion, cascades, deletion residue); LLM-touching paths get contract tests (schema validation, citation presence, refusal behavior) with recorded or stubbed model responses. Deletion-cascade and no-evidence-mining tests are mandatory.

---

## Validation

```bash
# Backend
pytest && ruff check . && ruff format --check .
# Frontend
npm test && npm run build
```

Plus: dependency audit pass (`pip audit` / `npm audit`) or documented exceptions before submission.

---

## Key Files

| File | Purpose |
|------|---------|
| `PRD.md` | Authoritative scope, features (F-1–F-13), API contracts, phases |
| `backend/app/core/` | Meta API client + grounding-mode prompt contracts |
| `backend/app/db/` | Schema: 4 layers + profiles, explanations, attempts, conversations |
| `frontend/src/api/` | Typed client mirroring backend Pydantic schemas |
| `.env.example` | Non-secret config template (created at scaffolding; `.env` never committed) |

---

## On-Demand Context

| Topic | File |
|-------|------|
| Full requirements + API contracts | `PRD.md` |
| Workflow commands (plan/execute/validate) | `.agents/commands/`, `.claude/commands/` |
| Research findings behind PRD decisions | Conversation history (Oct 29–30 discovery) |

**Context loading rules:** this file is always loaded. Load `PRD.md` sections on demand per task (features §7, API §10, current phase §12) — do not paste the whole PRD into context by default. Never load `conversation-log/` contents into shared context; it is private. Workflow command files load only when invoking that workflow step.

---

## Notes

- **Deadline:** hackathon submission Nov 4, 2026 (~9 PM ET). Phase 4 (Nov 3–4) is reserved for demo + submission — protect it.
- **Meta-only LLM:** every model call goes through the single Meta API client module. Record the exact model ID in code and README at the first successful call.
- **Never commit:** `.env`, `conversation-log/`, real credentials, or employer/client data in seed/demo content.
- **Anti-invention is load-bearing:** discussion never upgrades to accomplishment; assistant turns never become evidence; completion needs explicit user statements. When in doubt, refuse and cite silence.
- **Scope guard:** the PRD's Essential/Preferred tags (§4) and cut order (§12) are binding. Preferred items cut before Essential quality suffers.
- All ThoughtBridge product code must be written Oct 30–Nov 4 (competition window); pre-existing starter/workflow files are dev tooling, not the submission.
