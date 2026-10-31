# Phase 1 Build List — Foundation & Retrieval (PRD §12)

**Phase goal:** The pipeline lives and Meta API access is proven.

**Scope rule:** PRD.md is authoritative for requirements, scope, and acceptance criteria. Plan and build only one deliverable at a time, in the order below. Do not incorporate later deliverables. If this list conflicts with the PRD, flag the discrepancy — never silently change scope.

## Ordered deliverables (all Essential, all required to pass the gate)

### 1. Scaffold backend, frontend, and database schema

Stand up `backend/` (FastAPI + Pydantic v2 project layout per PRD §6: `api/`, `core/`, `db/`, `ingest/`, `retrieval/`, `llm/`), `frontend/` (React + TS + Vite + Tailwind), and the SQLite schema covering the 4 provenance layers (artifacts, chunks, facts, interpretations) plus career profile, explanations, attempts, and conversations/turns with stable IDs and role labels. Establish package managers, test runners, and lint configs; record exact commands in AGENTS.md.

Scope boundaries: project skeleton + schema only. No ingestion, retrieval, or UI behavior beyond placeholder views needed to prove the scaffold runs.

### 2. CHECKPOINT 1 — Meta Model API client wiring

Wire the pre-verified Meta Model API access (`muse-spark-1.3`, HTTP 200 confirmed manually) into the app's single Meta client module in `backend/app/core/`. Record the exact model ID in code. `/health` reports Meta reachability honestly (surfaced failures, never silent).

Scope boundaries: connectivity + health reporting only. No LLM features yet. Blocks all LLM-dependent work.

### 3. Source-adapter ingestion

Implement the source-adapter seam plus adapters for typed/pasted text and `.txt`/`.md` uploads: inputs → SourceArtifacts (immutable, hashed, provenance metadata) → chunks with `(artifact_id, span, chunk_idx)` → fastembed embeddings (original text only) → FTS5 + vec0 index rows. Enforce `MAX_UPLOAD_MB` / `MAX_ARTIFACT_CHARS`.

Scope boundaries: text/paste/txt-md only. PDF/Word adapters are Preferred Phase 2 work. No retrieval or generation.

### 4. Hybrid retrieval

Implement BM25 (FTS5) + dense-vector (sqlite-vec) search fused with Reciprocal Rank Fusion, with a top-k inspection endpoint returning chunk IDs, scores, and excerpts. Vector index treated as a derived, rebuildable artifact.

Scope boundaries: retrieval only — no answer generation. No reranker, no HyDE (both stay stretch unless measured recall fails).

### 5. Grounded Q&A + minimal chat UI with turn persistence

Implement `POST /query` (evidence/teaching/auto modes, citations with chunk IDs, speculation refusal in evidence mode) and a minimal chat UI rendering answers with clickable citations. Every exchange persisted as ordered, role-labeled turns under a `conversation_id` (omit to start, pass back to continue) — the conversation-memory foundation.

Scope boundaries: Q&A + turn persistence only. Pipeline ingestion of conversations (`tb_conversation` adapter, Phase 3) is out; no chat rework may be required later. No explainer, no practice, no extraction.

### 6. CHECKPOINT 2 — Cloud-deploy checkpoint

Backend reachable at a public URL with a persistent or seeded database (Modal leads; decided by what works fastest with a persistent SQLite file, seed-on-boot as backup). Deployed URL serves the chat view end to end.

Scope boundaries: reachability + persistence decision only. No production hardening, no custom domain, no demo seeding (Phase 4).

## Validation gate (all must hold before leaving Phase 1)

- A vague query over seeded notes returns the right cited passage.
- Conversation turns persisted with stable ids and role labels.
- `/health` reports Meta reachability honestly.
- Deployed URL serves the chat view.

## Explicitly not in this phase

Explainer, success markers, learner profile, work extraction, career profile, PDF/Word uploads (all Phase 2); Practice Loop, `question_kind`, conversation-pipeline ingestion, deletion cascade (Phase 3); seeded demo DB, video, submission README (Phase 4).
