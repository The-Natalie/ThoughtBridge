# Prime Summary — ThoughtBridge

Organized by implementation phase. Current phase: **Phase 1**. Ordered build list: [.agents/plans/phase-1-build-list.md](phase-1-build-list.md).

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
