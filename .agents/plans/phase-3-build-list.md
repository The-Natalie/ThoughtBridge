# Phase 3 Build List — Practice Loop & Integrity (PRD §12)

**Phase goal:** The feedback loop and trust guarantees close.

**Scope rule:** PRD.md is authoritative for requirements, scope, and acceptance criteria. Plan and build only one deliverable at a time, in the order below. Do not incorporate later deliverables. If this list conflicts with the PRD, flag the discrepancy — never silently change scope.

## Ordered deliverables

### 1. Shared Practice Loop endpoints + Practice/Interview views

Implement `POST /practice/question`, `POST /practice/answer`, `GET /practice/attempts` plus Practice and Interview views (replacing the current placeholder stubs in `App.tsx`). App asks → user answers → app evaluates → actionable feedback + attempt logged. Learning mode: explain-back against the stored/taught explanation. Interview mode: each question labeled `experience` (evidence mode — claims evaluated against accomplishment facts and sources) or `technical` (teaching mode — conceptual accuracy from general knowledge, personal examples woven in when retrieval finds them). One endpoint, one feedback shape — only reference assembly and the rubric branch. `conversation_id` accepted on question (omit to start, pass back to continue); answer inherits its attempt's conversation; user answer and feedback turns persisted in order either way. Feedback shape shared: correct / missing / inaccurate / terminology help / next step, with a grounding label (`from your notes` / `general explanation` / `both`).

Scope boundaries: practice endpoints + views + attempt log only. Evaluator constrained to provided references (see deliverable 2 — plan 1+2 together or state the split). No multi-turn drill plans, no STAR structuring guidance, no delivery analysis (advanced coaching is out of scope). Iteration is turn-by-turn with a next step or single follow-up per round.

### 2. Mode-parameterized rubrics + grounding labels

Implement the per-mode/per-kind rubric branch shared by both loop modes: Learning-mode rubric judges against the taught explanation (whatever its sources); Interview-experience rubric judges claims against accomplishment facts and sources; Interview-technical rubric judges conceptual accuracy with personal-example incorporation when retrieved. Evaluator constrained to provided references (no free-form judging). Every feedback round carries the correct grounding label. Career-profile text already lands in question-gen prompts via the Phase 2 deliverable-5 contract — wire it, don't redesign it.

Scope boundaries: rubric + reference-assembly + labeling logic only. No new endpoints beyond deliverable 1's; this is the evaluation contract inside them.

### 3. Automatic conversation memory: `tb_conversation` adapter

Ingest Phase 1 turn persistence into the standard pipeline via a `tb_conversation` source adapter: conversations become SourceArtifacts, chunked with role tags, retrievable with "from a ThoughtBridge conversation" labels. Role-asymmetric grounding: user turns are candidate evidence (same status as a pasted note); assistant turns are labeled, retrievable context, never mined for facts or accomplishments; completion status requires explicit user statements. Implement `GET /conversations`, `GET /conversations/{id}` (role-labeled turns with timestamps, mode, citations), `DELETE /conversations/{id}` (full derived cascade like any other source). Indexing may be asynchronous if that simplifies implementation, provided conversations reliably become retrievable. The UI discloses that conversations are saved and retrievable.

Scope boundaries: adapter + retrieval/display + conversation endpoints. **Fallback if behind (PRD §12):** persist turns + chunk transcripts with role tags (retrieval works) and keep the role-asymmetric extraction rule in prompts, deferring polished role-aware display.

### 4. Deletion with cascade, including conversations

Implement `DELETE /artifacts/{id}` per F-10 independent-support semantics: remove the artifact's chunks, vec/FTS rows, and records left with no remaining support — all in the same transaction. Information independently supported by other retained sources stays: multi-source facts lose only the deleted source's chunk references; only facts left with zero supporting chunks are deleted. Response shape: `{"deleted": {"chunks": N, "facts": M, ...}, "unlinked": {"facts": K}}`. Conversation deletion (deliverable 3's endpoint) carries the same guarantees. **Mandatory tests:** delete-then-query proves no retrieval residue (post-delete queries never surface deleted content); no-evidence-mining test proves assistant turns never become facts/accomplishments.

Scope boundaries: deletion + cascade + residue tests only. No deduplication/merging of equivalent facts across artifacts (documented MVP limitation per F-10). No topic-wide deletion, no automatic forgetting, no editing, no redaction. Design must not complicate future span-level editing and redaction.

### 5. Checkpoint-prompt button + provenance/grounding visibility pass

Implement `GET /prompts/checkpoint` returning the static copyable prompt text (frontend also hardcodes it as fallback) plus the one-click button/modal UI. Then a provenance/grounding visibility pass across all views: "from your notes" vs. "general explanation" visually distinct everywhere; every derived item links back to its sources with the original one click away; role labels visible on conversation-derived content; status labels (proposed/rejected/completed) and confidence visible on extracted facts.

Scope boundaries: static prompt + visibility pass only. No AI generation in the checkpoint prompt, no integration. This is a product requirement, not polish (F-11).

### 6. Retrieval hardening — ONLY if measured failures (preferred stretch, not default)

Add cross-encoder rerank or HyDE-style vague-query expansion only if retrieval recall measurably fails on the 5+ vague-query spot-check against seeded data. Default is to skip this deliverable: hybrid BM25 + vector + RRF stands as built.

Scope boundaries: nothing lands here without a demonstrated recall failure and a before/after measurement. Never built speculatively.

## Validation gate (all must hold before leaving Phase 3)

- One full Learning-mode exchange produces specific, actionable feedback with the correct grounding label.
- One full Interview-mode exchange — one experience question and one technical question — each produce specific, actionable feedback with correct grounding labels.
- An in-app discussion is retrievable by a follow-up question ("what did we decide...") with role labels intact.
- Delete-then-query test passes: deleted content never surfaces; independently supported information remains.
- No-evidence-mining test passes: assistant turns never mined as evidence.

## Explicitly not in this phase

Seeded demo DB, live-deployment verification, submission README, 3-minute video, public-repo submission (all Phase 4); scored career relevance ranking beyond keyword/tag filtering (Preferred, cut per §12 order); rerank/HyDE without measured failure (deliverable 6 rule); editing, redaction, correction workflows (deferred); automated practice scheduling / FSRS (deferred — MVP uses trivial wrong → surface-again re-queue display over the attempt log).
