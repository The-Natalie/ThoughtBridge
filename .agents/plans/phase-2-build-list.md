# Phase 2 Build List — Learning & Work (PRD §12)

**Phase goal:** The two defining capabilities function.

**Scope rule:** PRD.md is authoritative for requirements, scope, and acceptance criteria. Plan and build only one deliverable at a time, in the order below. Do not incorporate later deliverables. If this list conflicts with the PRD, flag the discrepancy — never silently change scope.

## Ordered deliverables

### 1. Interactive eight-step explainer endpoint + Learn view

Implement `POST /learn/explain` (multi-stage generation, not single-shot) producing all eight F-3 stages — definition, familiar-system connection, complete-system analogy, component mapping, walkthrough, placement, interview-ready explanation, limitations — as a versioned Explanation record (mapping JSON + limits stored). Learn view renders the lesson stepwise and interruptibly: the user can ask questions or explore confusion at any step (answered via `POST /query` with `context.explanation_id`, no new Q&A contract), request an alternative take on the current step (persisted as a new version), and resume where they left off. Every new explanation is shaped by the learner profile (deliverable 3) and prior stored explanations (deliverable 2).

Scope boundaries: explainer + Learn view only. Explanation-memory retrieval/marked-reuse behavior is deliverable 2; profile injection needs only the deliverable-3 read path to exist (build order handles this only if 2–3 land first — see note below). No practice, no extraction.

**Build-order note:** deliverables 1–3 are mutually dependent at runtime (explainer reads memory + profile) but separable at the contract level. Recommended implementation order: 3 (profile store + read path) → 2 (memory retrieval + markers) → 1 (explainer consuming both), or 1 with stubbed read paths finalized by 2–3. The plan for deliverable 1 must state which order it assumes.

### 2. Explanation memory: same-concept retrieval + "clicked" markers

Before generating, the explainer retrieves past Explanations for the same concept (and related ones by similarity). Reuse is governed by explicit success signals: the authoritative signal is the user's "This clicked" marker, settable on a whole explanation or on individual steps/connections; secondary signals are reuse count and linked practice-attempt outcomes. Marked explanations are offered first ("this worked for you before") or injected as context so the successful analogy family is reused. Implement `GET /learn/explanations`, `GET /learn/explanations/{id}`, `POST /learn/explanations/{id}/markers` + marker UI. Learning conversations stay preserved verbatim via conversation memory (F-12, Phase 3) — preservation must never be confused with success classification.

Scope boundaries: retrieval + markers + reuse injection only. Attempt-outcome linkage reads the attempts table but the Practice Loop itself is Phase 3. No new generation contracts.

### 3. Learner-preferences profile record + prompt injection + basic UI

Implement `GET /learn/profile` / `PUT /learn/profile`: emphasis preferences for the explanation dimensions (familiar-system grounding, explicit component mapping, larger-process placement, interaction walkthroughs, terminology bridging — defaulting on, matching the eight-step framework) plus free-text "how I learn best." Injected into every new explanation; user-editable via basic UI. Simplifiable to defaults + free-text if pressed.

Scope boundaries: explicit profile only. Automatic inference from behavior is deferred (out of scope).

### 4. Work extraction endpoint + Work view

Implement `POST /work/extract` over artifact IDs: structured LLM output (JSON-schema-validated at the boundary) yielding problems, decisions + reasoning, accomplishments, demonstrated skills, evidence links (chunk IDs), per-item status (proposed / rejected / completed), and typed reasoning links (`constrained_by`, `considered`, `rejected_because`, `decided`, `implemented_by`, `resulted_in`) with per-node evidence. Work view renders results reviewably with provenance. Anti-invention rules are load-bearing: extraction never upgrades discussion into accomplishment, never invents steps or outcomes, rejected approaches with reasons are first-class records. Career-profile text injected into extraction prompts (deliverable 5 read path).

Scope boundaries: extraction + display only. No deduplication/merging of equivalent facts across artifacts (documented MVP limitation per F-10). No editing, redaction, or correction workflows (deferred).

### 5. Career profile CRUD + prompt injection + accomplishment filtering

Implement `GET /profile` / `PUT /profile`: current/previous occupation, target career or specific position. Minimum required behavior: profile CRUD, profile text injected into extraction and question-generation prompts, and keyword/tag filtering of accomplishments (`GET /work/accomplishments` with query-time relevance filter). Users can conversationally redirect irrelevant questions in the meantime. Scored relevance ranking is Preferred, not required. Retention is always independent of relevance (ranking is query-time only).

Scope boundaries: profile + injection + filtering only. Question-gen prompt injection lands here as a prompt-contract change; the Practice Loop endpoints consuming it are Phase 3.

### 6. PDF + Word upload adapters (Preferred)

Add `.pdf` (text-based only, via `pypdf`) and `.docx` (via `python-docx`) adapters behind the existing source-adapter seam, feeding the same ingestion pipeline (`POST /artifacts/upload` returns `extracted_chars`, `pages?`). Size caps enforced as code constants with env overrides.

Scope boundaries: text extraction into the existing pipeline only. No OCR, no scanned-document handling. **First cut candidate:** cut this deliverable first if Phase 1 slip has compressed the schedule (per §12 cut order); cutting it must not affect any Essential deliverable.

## Validation gate (all must hold before leaving Phase 2)

- Teach → interrupt with a question → resume round-trip works on one concept.
- A marked explanation is reused on repeat concept request (marked preferred over unmarked).
- Extraction over a real pasted dev log shows correct proposed/rejected/completed split and a traversable reasoning chain on inspection.
- Learner profile persists and observably shapes a new explanation; career profile persists and filters accomplishments.

## Explicitly not in this phase

Practice Loop, question-gen/evaluation endpoints, `question_kind` (Phase 3); `tb_conversation` pipeline ingestion, deletion cascade, checkpoint-prompt button (Phase 3); rerank/HyDE (Phase 3 stretch only if measured failures); seeded demo DB, video, submission README (Phase 4).
