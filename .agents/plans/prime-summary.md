# Prime Summary — ThoughtBridge

Organized by implementation phase. Current phase: **Phase 3**. Ordered build list: [.agents/plans/phase-3-build-list.md](phase-3-build-list.md).

## Phase 1 — Foundation & Retrieval (PRD §12)

**Date:** 2026-10-31
**Branch:** `main` (commit `cb0ad11` — Initial ThoughtBridge project setup)

### Project Overview

- **Purpose:** ThoughtBridge — AI-powered memory/learning app for neurodivergent thinkers: personalized analogy-based learning, work documentation with accomplishment recognition, interview prep grounded in real history.
- **Type:** Full-stack web app, currently **greenfield** — zero application code; `backend/` and `frontend/` get scaffolded in this phase.
- **Primary stack:** Python 3.12 + FastAPI/Pydantic v2, single-file SQLite (FTS5 + sqlite-vec), fastembed local embeddings, Meta Model API exclusively for LLM work, React + TS + Vite + Tailwind.
- **State:** PRD v1.2 ratified; AGENTS.md/CLAUDE.md rules written; `.env`/`.env.example` created; Meta API connectivity verified (`muse-spark-1.3`, HTTP 200).

### Architecture

- **Shape:** one pipeline, three surfaces — ingest → chunk → embed → retrieve → generate built once; Learn/Work/Practice views over it.
- **Patterns:** 4-layer provenance store (artifacts → chunks → facts → interpretations, interpretations never re-indexed); dual grounding modes (closed-world evidence vs. open-world teaching); source-adapter ingestion; schema-at-the-boundary for all LLM outputs; conversation-as-source with role-asymmetric grounding.
- **Directories:** `.agents/` + `.claude/` = owner's deterministic workflow system (commands, skills, validators); `tools/` = conversation-log tooling; `conversation-log/` = private gitignored session logs; product code goes in new `backend/` + `frontend/` dirs.

### Tech Stack

- **Languages:** Python 3.12 (Homebrew, pinned — never macOS system Python); TypeScript (frontend, at scaffolding).
- **Frameworks/libs:** FastAPI, Pydantic v2, sqlite-vec, fastembed, pypdf + python-docx (Preferred), React/Vite/Tailwind.
- **Build/package managers:** not yet chosen — expected `uv` or `venv`+`pip` (backend), `npm` (frontend); exact commands recorded in AGENTS.md at scaffolding.
- **Testing:** pytest + ruff (backend); `npm test` (frontend). Deletion-cascade and no-evidence-mining tests are mandatory per PRD.

### Core Principles

- **Anti-invention is load-bearing:** discussion never upgrades to accomplishment; assistant turns never become evidence; completion needs explicit user statements; evidence-mode silence → refusal, not speculation.
- **Conventions:** `snake_case` backend / `PascalCase` components / plural `snake_case` tables; thin routers with logic in `ingest/`/`retrieval/`/`llm/`; shared grounding contracts and citation rendering, never copied per feature.
- **Docs:** PRD is authoritative for scope; AGENTS.md for working conventions; load PRD sections on demand, never whole-PRDoc-by-default; never commit `.env`, `conversation-log/`, or real secrets.

### Current State

- **Active branch:** `main`, clean except unstaged workflow updates (`.claude/commands/prime.md`, `.claude/commands/plan-feature.md`) and untracked `.agents/plans/`.
- **Recent focus:** discovery → PRD v1.0 → review revisions v1.1 → corrections v1.2 → rules files → env files → API verification → prime.
- **Observations/concerns:** (1) No scaffold yet — implementation starts from empty `backend/`/`frontend/`; (2) Spark models burn heavy hidden reasoning tokens that consume `max_tokens` — generous token budgets required on every LLM call; (3) `.env` holds a live key and is correctly gitignored — keep it that way.
- **Constraints before implementation:** all product code must be written Oct 30–Nov 4 (competition window); Meta-only LLM via one client module; Essential/Preferred tags + cut order binding; Phase 4 (Nov 3–4) protected for demo/submission; no LangChain, no macOS work.
- **Next highest-leverage task:** `/plan-feature` for Phase 1 deliverable 1 (scaffold backend, frontend, and database schema).
- **Consult before implementing:** PRD §7 features, §10 API contracts, §12 current phase; AGENTS.md commands section (to be filled at scaffolding).

### What's Next

- **Current phase:** Phase 1 — Foundation & retrieval. Goal: the pipeline lives and Meta API access is proven.
- **Build list:** [.agents/plans/phase-1-build-list.md](phase-1-build-list.md) — 6 ordered Essential deliverables (scaffold → CHECKPOINT 1 → ingestion → retrieval → grounded Q&A + turn persistence → CHECKPOINT 2), each with scope boundaries, plus the validation gate and out-of-phase exclusions.

## Phase 2 — Learning & Work (PRD §12)

**Date:** 2026-11-02
**Branch:** `main` (commit `230853b` — CHECKPOINT 2, Phase 1 complete)

### Project Overview

- **Purpose:** ThoughtBridge — AI-powered memory/learning app: analogy-based learning, work documentation with accomplishment recognition, interview prep grounded in real history.
- **Type:** Full-stack web app, past greenfield — Phase 1 pipeline live: ingest → chunk → embed → hybrid retrieve → grounded Q&A, deployed on Modal with persistent SQLite volume.
- **Primary stack:** Python 3.12 + FastAPI/Pydantic v2 (`uv`), single-file SQLite (FTS5 + sqlite-vec), fastembed BGE-small (384-dim), Meta Model API `muse-spark-1.3` via single client module, React 19 + TS + Vite + Tailwind 4.
- **State:** PRD v1.2; all 6 Phase 1 deliverables committed Nov 1–2 with plans, execution reports, and independent reviews; live URL serving chat UI.

### Architecture

- **Shape:** one pipeline, three surfaces — Learn/Work views (this phase) build on the Phase 1 pipeline; no new subsystems.
- **Patterns observed in code:** thin routers (`api/`) with logic in `ingest/`/`retrieval/`/`llm/`; shared grounding contracts in `core/grounding.py`; schema-at-the-boundary for LLM outputs (`llm/qa.py`); vector index as derived ordering only (hydration from canonical `chunks`); per-leg over-fetch + RRF fusion; append-only turn log with stable IDs.
- **Directories:** `backend/app/{api,core,db,ingest,retrieval,llm}/` + `modal_app.py` (single-URL deploy); `frontend/src/{api,views}/` with `ChatView` live and Learn/Work/Practice/Interview as placeholder stubs; `.agents/` + `.claude/` + `tools/` remain owner workflow tooling, not product.

### Tech Stack

- **Languages:** Python 3.12 (pinned, `uv`); TypeScript (frontend).
- **Frameworks/libs:** FastAPI 0.136+, Pydantic v2, sqlite-vec, fastembed, httpx (Meta client); React 19, Vite 8, Tailwind 4. `pypdf` + `python-docx` not yet installed (Phase 2 Preferred deliverable 6).
- **Build/package managers:** `uv` + `uv.lock` (backend); `npm` + `package-lock.json` (frontend). Commands in AGENTS.md verified.
- **Testing:** pytest (15 backend test files) + ruff + mypy (non-strict); vitest + oxlint (frontend). Deletion-cascade and no-evidence-mining tests still ahead (Phase 3).

### Core Principles

- **Anti-invention still load-bearing:** this phase adds extraction — discussion never upgrades to accomplishment; completion needs explicit user statements; reasoning links connect only grounded facts.
- **Conventions:** `snake_case` backend / `PascalCase` components / plural `snake_case` tables; grounding prompts shared in `core/`, never copied per feature; citation/provenance rendering shared, not per-view.
- **Docs:** PRD authoritative for scope; plans live in `.agents/plans/`, execution reports in `.agents/execution-reports/`; never commit `.env`, `conversation-log/`, or real secrets.

### Current State

- **Active branch:** `main`, clean, up to date with `origin/main`.
- **Recent focus:** Nov 1–2 completed ingestion → hybrid retrieval → grounded Q&A + turn persistence → CHECKPOINT 2 (Modal deploy, persistent volume, write→redeploy→re-query proven).
- **Observations/concerns:** (1) Schedule is tight — PRD allots Nov 1 to Phase 2 and Nov 2 to Phase 3; Phase 1 finished Nov 2, so Phases 2–3 must compress into ~2 days before Phase 4 (Nov 3–4, protected); (2) explainer/memory/profile deliverables are mutually dependent at runtime — the first plan must fix a build order (recommended: profile → memory → explainer); (3) the reference/articles guides are generic pre-hackathon workflow material, not product docs — no product guidance to extract from them.
- **Constraints before implementation:** Meta-only LLM via `app/core/meta_client.py`; generous token budgets (Spark hidden reasoning burns `max_tokens`); competition-window code only; Preferred PDF/Word adapters are the first cut if behind; Phase 4 protected for demo/submission.
- **Next highest-leverage task:** `/plan-feature` for Phase 2 deliverable 3 (learner-preferences profile — smallest, unblocks explainer prompt injection) or a combined 1–3 learning-slice plan; then work extraction (deliverable 4).
- **Consult before implementing:** PRD §7 F-3/F-4/F-13 (learning), F-5/F-6 (work), §10 Learning + Work contracts, §12 Phase 2 gate; existing `core/grounding.py`, `llm/qa.py` (schema-validation pattern to reuse), `db/schema.sql` (explanations/markers/profiles tables already exist).

### What's Next

- **Current phase:** Phase 2 — Learning & work. Goal: the two defining capabilities function.
- **Build list:** [.agents/plans/phase-2-build-list.md](phase-2-build-list.md) — 6 ordered deliverables (explainer + Learn view, explanation memory + markers, learner profile, work extraction + Work view, career profile + filtering, PDF/Word adapters Preferred), each with scope boundaries, plus the validation gate and out-of-phase exclusions.

## Phase 3 — Practice Loop & Integrity (PRD §12)

**Date:** 2026-11-04
**Branch:** `main` (commit `f5d759f` — PDF + Word upload adapters, Phase 2 complete)

### Project Overview

- **Purpose:** ThoughtBridge — AI-powered memory/learning app: analogy-based learning, work documentation with accomplishment recognition, interview prep grounded in real history.
- **Type:** Full-stack web app, Phases 1–2 complete: ingest → hybrid retrieve → grounded Q&A → eight-step explainer with memory/markers → learner profile → work extraction with reasoning chains → career profile + filtering → PDF/Word uploads, deployed on Modal.
- **Primary stack:** Python 3.12 + FastAPI/Pydantic v2 (`uv`), single-file SQLite (FTS5 + sqlite-vec), fastembed BGE-small (384-dim), Meta Model API `muse-spark-1.3` via single client module, React 19 + TS + Vite + Tailwind 4, `pypdf` + `python-docx` installed.
- **State:** PRD v1.2; all 6 Phase 2 deliverables committed with plans, execution reports, and independent reviews, plus a placement-instruction refinement (`a25b73e`); no Phase 3 plans exist yet.

### Architecture

- **Shape:** one pipeline, three surfaces — holding: Phase 3 adds the Practice Loop (third surface) plus trust guarantees (conversation memory, deletion cascade) over the existing pipeline; no new subsystems.
- **Patterns observed in code:** thin routers (`api/`: health, ingest, learn, query, retrieval, work — no practice/conversations/prompts routers yet) with logic in `ingest/`/`retrieval/`/`llm/`; shared grounding contracts in `core/grounding.py` (evidence/teaching/auto, untrusted-passage framing, history-not-evidence); schema-at-the-boundary for LLM outputs (`llm/qa.py`, `llm/explainer.py`, `llm/extraction.py`, `llm/memory.py`); per-table repositories in `db/` over `schema.sql` v1 (all Phase 3 tables — attempts, conversations/turns — already exist); single-URL Modal deploy (`modal_app.py`, persistent volume, `max_containers=1`).
- **Directories:** `backend/app/{api,core,db,ingest,retrieval,llm}/` + `modal_app.py`; `frontend/src/{api,views}/` with Chat/Learn/Work live (plus Career/Learner profile panels) and Capture/Practice/Interview still placeholder stubs; `.agents/` + `.claude/` + `tools/` remain owner workflow tooling, not product.

### Tech Stack

- **Languages:** Python 3.12 (pinned, `uv`); TypeScript (frontend).
- **Frameworks/libs:** FastAPI 0.136+, Pydantic v2, sqlite-vec, fastembed, httpx (Meta client), `pypdf` + `python-docx`; React 19, Vite 8, Tailwind 4.
- **Build/package managers:** `uv` + `uv.lock` (backend); `npm` + `package-lock.json` (frontend). Commands in AGENTS.md verified.
- **Testing:** pytest (26 backend test files) + ruff + mypy (non-strict); vitest (11 frontend test files) + oxlint. Deletion-cascade and no-evidence-mining tests are this phase's mandatory additions.

### Core Principles

- **Anti-invention at peak load:** this phase adds conversation mining (role-asymmetric: user turns candidate evidence, assistant turns never evidence) and deletion (independent-support cascade) — the two most load-bearing trust guarantees; both need dedicated tests, not just prompt text.
- **Conventions:** `snake_case` backend / `PascalCase` components / plural `snake_case` tables; grounding prompts shared in `core/`, never copied per feature; citation/provenance rendering shared, not per-view; upstream Meta failures → 502 with cause, never swallowed.
- **Docs:** PRD authoritative for scope; plans in `.agents/plans/`, execution reports in `.agents/execution-reports/`; never commit `.env`, `conversation-log/`, or real secrets.

### Current State

- **Active branch:** `main`, clean, up to date with `origin/main`.
- **Recent focus:** Phase 2 completed in full — explainer → explanation memory → learner profile → work extraction → career profile → PDF/Word adapters (all Preferred work landed, nothing cut), plus a Learn streaming/placement refinement.
- **Observations/concerns:** (1) **Deadline is today** (Nov 4, ~9 PM ET) and both Phase 3 (Practice Loop + integrity) and Phase 4 (seeded demo, deploy verification, README, 3-min video, submission) are outstanding — Phase 4 was supposed to be reserved Nov 3–4 and that buffer is gone; (2) no `practice.py`, `conversations`, or checkpoint-prompt routers exist yet and Practice/Interview views are still stubs — the entire third surface is greenfield; (3) the attempts/conversations/turns tables already exist in schema v1, so Phase 3 is pure API + LLM + UI work with no migration needed.
- **Constraints before implementation:** Meta-only LLM via `app/core/meta_client.py`; generous token budgets (Spark hidden reasoning burns `max_tokens`); competition-window code only; deliverable 6 (rerank/HyDE) lands only on measured recall failure — default skip; conversation-memory fallback available if behind (turns + chunked transcripts with role tags, polished display deferred); sandbox blocks local servers — verify via TestClient + redeploy + Playwright-against-deployed per AGENTS.md.
- **Next highest-leverage task:** `/plan-feature` for Phase 3 deliverables 1–2 (shared Practice Loop endpoints + mode-parameterized rubrics — the only remaining user-facing surface, and the demo's third capability); then conversation memory (3) and deletion cascade (4) as the trust-guarantee slice.
- **Consult before implementing:** PRD §7 F-7/F-8 (Practice Loop, interview surface) + F-10/F-12 (deletion, conversation memory), §10 Practice + Conversations contracts, §12 Phase 3 gate; existing `core/grounding.py`, `llm/qa.py` (schema-validation pattern), `db/conversations.py`, `db/explanations.py` (attempt-outcome linkage), `frontend/src/App.tsx` (view stubs to replace).

### What's Next

- **Current phase:** Phase 3 — Practice Loop & integrity. Goal: the feedback loop and trust guarantees close.
- **Build list:** [.agents/plans/phase-3-build-list.md](phase-3-build-list.md) — 6 ordered deliverables (Practice Loop endpoints + views, mode-parameterized rubrics, `tb_conversation` memory adapter, deletion cascade + residue tests, checkpoint-prompt button + provenance pass, retrieval hardening only on measured failure), each with scope boundaries, plus the validation gate and out-of-phase exclusions.
