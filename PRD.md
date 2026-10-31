# ThoughtBridge — Product Requirements Document

**Version:** 1.2 (Hackathon MVP — post-review corrections)
**Date:** October 30, 2026
**Hackathon:** Meta AI Developer Hackathon (Indie track)
**Submission deadline:** November 4, 2026 (~9 PM ET — corroborated, not firsthand-verified)
**Status:** Draft for review — no implementation authorized by this document alone

---

## 1. Executive Summary

ThoughtBridge is an AI-powered memory and learning application for people who think differently — particularly neurodivergent technical professionals who understand systems deeply but struggle to retrieve terminology or explain their knowledge on demand, and who tend to undervalue their own accomplishments.

The product combines three capabilities over one personal knowledge foundation: **personalized learning** that teaches through familiar-system analogies and reuses explanations that worked; **work documentation** that turns raw notes into recognized accomplishments without requiring users to pre-label their own significance; and **interview preparation** grounded in the user's real knowledge and history rather than generic question banks. A shared Practice Loop (question → user answer → evaluated feedback) serves both learning and interview contexts.

The hackathon MVP delivers all three capabilities in functional but simplified form: genuine hybrid (keyword + vector) RAG over the user's own material, an eight-step analogy-based explainer with explanation memory, structured work-note extraction with provenance, career-profile-aware prioritization, grounded Q&A and interview practice, and a practice-feedback loop in both Learning and Interview modes — deployed to the cloud with a seeded demo and a 3-minute submission video.

## 2. Mission

**Mission statement:** Help people who think differently retain what they learn, recognize what they've accomplished, and communicate what they know — in interviews, meetings, and work — without being penalized for how their memory and verbal retrieval work.

**Core principles:**

1. **Never invent the user's story.** Claims about the user's work, skills, and history must trace to saved source material. AI interpretations are labeled as interpretations and can never become evidence.
2. **Retrieval without terminology.** The system meets users where they are: vague descriptions and partial memories must retrieve relevant knowledge. Forgetting a word is never treated as failing to understand.
3. **Reuse what worked.** Explanations, analogies, and connections that made something click are preserved and reused — the system builds a personal analogy library instead of starting over every session.
4. **Simplest rung that holds.** Deterministic code first, single LLM calls second, fixed workflows third — no agents, knowledge graphs, or multi-service machinery until a measured failure demands them.
5. **The user owns the meaning.** Users record raw activity without needing to recognize its significance; the system surfaces the skills and reasoning involved, with the original words always inspectable.

## 3. Target Users

**Primary persona — "User Zero" (the founder, representing the target population):**
A neurodivergent software engineer who understands technical systems through how components connect and interact, but struggles to produce textbook definitions or verbal explanations on demand, especially under interview pressure. Comfortable with Python, TypeScript, APIs, and AI tooling; already uses coding assistants daily. Currently preparing for job interviews while building real projects.

**Technical comfort level:** High for the MVP user (developer). The product vision extends to non-developer knowledge workers later, but the MVP is built and demoed by and for a technical user.

**Key needs and pain points:**

- "I fixed a SQLAlchemy loading problem last month — what did I do?" Knowledge exists but is un retrievable without exact keywords.
- "I understand RAG but can't explain it in an interview." Comprehension without reliable verbalization.
- "I just did the thing." Engineering judgment (spotting failure modes, rejecting bad approaches) goes unrecognized and undocumented.
- Interview prep from generic banks doesn't connect to real experience; résumé tools polish bullets the user never wrote down.
- Capture friction: documenting work after the fact is forgotten; documentation reminders fire at the wrong times.
- In-app discussions vanish: decisions and insights from conversations inside the tool itself are lost just like external ones.

## 4. MVP Scope

**Priority rule:** every ✅ item is Essential unless tagged **(Preferred)**. Preferred items are scheduled in phase order but cut first per §12 if earlier phases slip.

### Core Functionality

**In Scope:**

- ✅ Manual text capture (typed or pasted notes)
- ✅ Pasted coding-assistant conversations and work-session summaries
- ✅ Plain-text and Markdown file upload, feeding the same ingestion pipeline
- ✅ Hybrid retrieval (keyword + semantic) over all saved material, tolerant of missing terminology
- ✅ Grounded chat Q&A with citations to source passages
- ✅ Eight-step analogy-based explainer (definition → familiar system → full analogy → component mapping → system walkthrough → larger-process placement → interview-ready explanation → analogy limitations)
- ✅ Stored explanations with same-concept reuse in future sessions
- ✅ Shared Practice Loop in Learning mode (explain-back) and Interview mode (interview Q&A), with answer evaluation and actionable feedback in both
- ✅ Work-note extraction: problems, decisions + reasoning, accomplishments, demonstrated skills, evidence links, and proposed / rejected / completed status
- ✅ Career profile (current/previous occupation, target career or position) with minimum prioritization: profile text injected into extraction/question prompts + keyword/tag accomplishment filtering (scored relevance ranking is Preferred)
- ✅ Interview preparation grounded in stored knowledge and accomplishments
- ✅ Static, copyable coding-assistant checkpoint prompt behind a UI button
- ✅ Deletion of saved information with cascading removal of derived records; deleted content excluded from retrieval
- ✅ Visible distinction between "from your notes" content and general-explanation content
- ✅ Interactive learning: interrupt an explanation with questions, explore confusion conversationally, request alternative explanations, resume where you left off
- ✅ Explicit success markers ("This clicked") on whole explanations and individual steps/connections
- ✅ Lightweight cross-concept learner-preferences profile shaping new explanations (simplifiable to defaults + free-text if pressed)
- ✅ Interview question kinds: experience-based (evidence grounding) and technical (teaching grounding) in the shared Practice Loop
- ✅ Reasoning-chain links between extracted facts (constraints, approaches, rejections, decisions, outcomes) with per-node evidence
- ✅ Automatic conversation memory: in-app conversations saved and retrievable with role labels and provenance (minimal version with fallback per §12)

**Out of Scope (deferred):**

- ❌ Voice input and transcription
- ❌ Image, screenshot, and document-image processing
- ❌ GitHub / git integration
- ❌ macOS activity capture (deferred entirely, including investigation)
- ❌ iOS integration and Windows activity capture
- ❌ Context-aware work reminders
- ❌ Advanced interview coaching (multi-turn drills, STAR structuring guidance, delivery metrics)
- ❌ Automated practice scheduling / spaced-repetition engine (FSRS or otherwise)
- ❌ Difficulty-axis classification (terminology vs. verbalization vs. conceptual) beyond stored attempts
- ❌ Full résumé and portfolio generation
- ❌ Dedicated meeting-practice functionality
- ❌ Conversational or bulk editing, redaction UI, and correction workflows
- ❌ Learning-topic exclusion preferences (practice filtering without deletion)
- ❌ Multi-user accounts and authentication
- ❌ Direct coding-assistant integrations (raw paste only)
- ❌ Automatic inference of learning preferences from behavior (explicit profile only for MVP)
- ❌ Automatic detection of explanation success from conversational cues (explicit markers only for MVP)
- ❌ Conversation-driven editing (edit-target resolution, confirmation flows, change propagation)

### Technical

**In Scope:**

- ✅ Genuine RAG: chunking, local embeddings, hybrid BM25 + vector retrieval with Reciprocal Rank Fusion
- ✅ Four-layer data model: source artifacts → chunks → extracted facts → AI interpretations, with provenance throughout
- ✅ Two grounding modes: closed-world (personal evidence) and open-world (teaching), with distinct prompt contracts
- ✅ Structured LLM outputs (JSON schema) for extraction, question generation, and answer evaluation
- ✅ Source-adapter ingestion seam so future capture methods plug in without core redesign
- ✅ Deterministic scoring, attempt logging, simple re-queue ordering, and validation at LLM boundaries

**Out of Scope:**

- ❌ Dedicated vector database or PostgreSQL (no compelling reason at single-user scale)
- ❌ Knowledge-graph database / GraphRAG layer
- ❌ LLM agent frameworks (LangChain, LangGraph, LlamaIndex, or equivalents)
- ❌ Fine-tuning of any model
- ❌ OCR for scanned documents

### Integration

**In Scope:**

- ✅ Meta Model API for all LLM reasoning (generation, extraction, evaluation)
- ✅ PDF upload (text-based PDFs only) — **(Preferred)** strongly preferred, scheduled in Phase 2, first cut if Phase 1 slips
- ✅ Word document (.docx) upload — **(Preferred)** strongly preferred, scheduled in Phase 2, first cut if Phase 1 slips

**Out of Scope:**

- ❌ Non-Meta primary models (fallback only if Meta access fails — see Risks)
- ❌ External note/doc service imports (Notion, Obsidian, etc.)
- ❌ Meeting transcription services

### Deployment

**In Scope:**

- ✅ Local-first development with an early cloud-deployment checkpoint (not left until the end)
- ✅ Single-user deployment (backend + frontend) sufficient for live demo and judging
- ✅ Seeded demo database with realistic sample content
- ✅ Public submission repo with build/run instructions, 3-minute demo video

**Out of Scope:**

- ❌ Production hardening (rate limiting, multi-region, backups beyond file copy)
- ❌ Custom domain, TLS beyond platform defaults, or app-store packaging

## 5. User Stories

**US-1 — Retrieve without terminology.** As a developer, I want to ask about something I fixed using only a vague description, so that I can recover knowledge even when I've forgotten the technical terms.
*Example: "I had a SQLAlchemy problem where something wasn't loading properly. What did I do to fix it?" → ThoughtBridge returns the relevant work note with the lazy-loading fix, citing the original passage.*

**US-2 — Learn through analogy.** As a learner, I want new concepts explained by mapping them onto systems I already understand, so that the knowledge connects to how I actually think. I can interrupt at any step to ask questions or request a different take, then resume where I left off.
*Example: "Teach me RAG" → an eight-step explanation that defines RAG literally, maps it onto a familiar system (e.g., an open-book exam with a librarian), walks through component interactions, places it in the larger LLM pipeline, and ends with an interview-ready summary plus the analogy's limits.*

**US-3 — Reuse what worked.** As a returning learner, I want ThoughtBridge to remember the explanation that made a concept click, so that I don't start over with a new analogy every time. I explicitly mark the explanation or step that made it click, so reuse favors what genuinely worked rather than what was merely saved.
*Example: asking about vector indexes a month later resurfaces the same library-catalog analogy that worked before, rather than inventing a new one.*

**US-4 — Practice explaining (Learning mode).** As a learner, I want to explain a concept in my own words and get feedback, so that I move from supported understanding toward independent recall.
*Example: after the RAG lesson, ThoughtBridge asks "Explain RAG as if to an interviewer," evaluates my answer against the stored explanation, and tells me I nailed retrieval-vs-generation but dropped the chunking step and should use the term "embeddings."*

**US-5 — Document work without self-promotion skills.** As an engineer, I want to paste raw notes about what I did without judging their importance, so that my real contributions get recognized.
*Example: pasting "Claude suggested doing it this way, but I thought it would break if the first step failed, so we changed the approach" → ThoughtBridge records the decision, flags it as demonstrating failure-mode analysis and engineering judgment, and links it to the original note.*

**US-6 — Distinguish proposed from done.** As someone who pastes long assistant conversations, I want ThoughtBridge to separate ideas discussed from work actually completed, so that my record never claims accomplishments I only considered.
*Example: a pasted session where three approaches were discussed but one implemented yields one completed fix, two rejected approaches with reasons, and no invented outcomes.*

**US-7 — Interview from real experience.** As a job seeker, I want interview questions drawn from my documented work, with feedback on my answers, so that I practice communicating what I genuinely know.
*Example: "Tell me about a difficult bug you solved" → drawn from my SQLAlchemy note; my answer is evaluated against the stored facts, and feedback notes I described the fix but forgot to mention the tradeoff I weighed.*

**US-8 — Delete cleanly.** As a privacy-conscious user, I want to delete a note and everything derived from it, so that removed information truly disappears from answers and practice.
*Example: deleting a client-related note removes its chunks, facts, and interpretations; subsequent Q&A no longer references it.*

**US-9 — Recall in-app conversations.** As a user, I want ThoughtBridge to remember discussions we had inside the app, so that past decisions and insights stay retrievable without manual importing.
*Example: "What did we decide about the retrieval architecture?" → retrieves last week's in-app discussion, showing my statements and the assistant's suggestions with clear role labels.*

**Technical stories:**

- **TS-1.** As the developer, I want all LLM calls to go through one client module targeting the Meta Model API, so that model usage is auditable for the hackathon's Meta-tooling criterion and swappable if needed.
- **TS-2.** As the developer, I want ingestion behind a source-adapter interface (every adapter produces the same SourceArtifact), so that macOS capture, git, and other integrations can be added post-hackathon without touching chunking, retrieval, or generation.
- **TS-3.** As the developer, I want a seeded demo database and one-command local startup, so that judges and reviewers can run the full loop (capture → retrieve → learn → practice → interview) in minutes.
- **TS-4.** As the developer, I want the conversation turn log to be append-only with stable IDs on every record and explicit derivation edges, so that future conversation-driven editing stays tractable without redesign.

## 6. Core Architecture & Patterns

**Guiding shape: one pipeline, three surfaces.** Ingest → chunk → embed → retrieve → generate is built once. Personalized learning, work documentation, and interview prep are three UX surfaces over that pipeline — not three subsystems. This is the central scope-control decision that makes the deadline feasible.

**Four-layer data model (with provenance throughout):**

1. **SourceArtifact** — immutable original bytes: notes, pastes, uploads. Stores content hash, source type, timestamps, and origin metadata. Never modified after creation (MVP); deletion cascades downward per F-10 independent-support semantics.
2. **Chunk** — searchable passages derived from artifacts, with `(artifact_id, span, chunk_idx)`. Embeddings are computed from original text, never from AI summaries. Each chunk is indexed in both FTS5 (keyword) and a vec0 table (vector).
3. **ExtractedFact** — structured LLM output (problems, decisions, accomplishments, skills, status: proposed/rejected/completed) with model name, prompt version, confidence, and foreign keys to supporting chunks.
4. **AIInterpretation** — explanations, summaries, feedback, and other generated content, explicitly typed. Interpretations cite chunk/fact IDs and are **never embedded back as ground truth** — they cannot become evidence of accomplishments.

**Two grounding modes (different contracts, enforced in prompts and validated in code):**

- **Evidence mode (closed world):** for anything about the user's work, skills, or history. The model may use only retrieved source material; every claim must cite chunk/fact IDs; it must refuse to speculate when sources are silent. Governs extraction, grounded Q&A over personal content, and Interview-mode evaluation.
- **Teaching mode (open world):** for explaining concepts. The model may draw on general knowledge, and must incorporate the user's stored explanations, analogies, and related experience when retrieval finds them. Teaching a new concept must never be blocked by an empty knowledge base. Governs the explainer and Learning-mode evaluation (judged against the taught explanation, whatever its sources).

**Interview question kinds (same loop, per-kind grounding):** Interview-mode practice labels each question `experience` or `technical`. Experience questions run evidence mode (claims evaluated against accomplishment facts and sources). Technical questions run teaching mode (conceptual accuracy from general knowledge, personal examples woven in when retrieval finds them). One endpoint, one feedback shape — only reference assembly and the rubric branch.

**Reasoning chains:** extracted facts carry optional typed links (`constrained_by`, `considered`, `rejected_because`, `decided`, `implemented_by`, `resulted_in`) so Problem → constraints → approaches → rejection reasons → decision → implementation → outcome is traversable. Every node keeps its own chunk evidence; links connect only extracted, grounded facts — intermediate steps and outcomes are never synthesized.

**Learner profile:** a lightweight cross-concept record (emphasis preferences defaulting to the eight-step framework, plus free-text "how I learn best") injected into every new explanation. Per-concept Explanation records remain the reuse mechanism; the profile is what carries across concepts. Automatic inference is deferred.

**Retrieval:** hybrid BM25 (FTS5) + dense vectors (sqlite-vec), fused with Reciprocal Rank Fusion, top-k into the prompt. Optional cross-encoder rerank and HyDE-style vague-query expansion are preferred stretch items, added only if measured recall fails — not upfront.

**Conversation memory:** in-app conversations (learning discussions, grounded Q&A, interview practice) are automatically saved with role-labeled turns, timestamps, and citations, and ingested through a `tb_conversation` source adapter into the standard pipeline — chunked with role tags, retrievable with "from a ThoughtBridge conversation" labels. Indexing may be asynchronous if that simplifies implementation, provided conversations reliably become retrievable. Role-asymmetric grounding: user turns are candidate evidence (the user's own words, same status as a pasted note); assistant turns are labeled context, never mined for facts or accomplishments. Completion status requires explicit user statements of completion — proposals and AI suggestions default to proposed until the user confirms. The turn log is append-only; every record keeps a stable ID; all derivations are explicit edges.

**LLM-vs-deterministic split:** the LLM drafts (extraction, explanations, questions, feedback); deterministic code chunks, embeds, retrieves, logs practice attempts and orders simple re-queues, aggregates scores, enforces cascades, and validates every LLM output against a JSON schema at the boundary. No agentic loops; fixed single calls and short fixed sequences only. (Automated practice scheduling is deferred; MVP re-queueing is a trivial wrong → surface-again rule over the attempt log.)

**Proposed directory structure** (to be finalized at scaffolding; routine implementation detail):

```
backend/
  app/
    api/            # FastAPI routers: ingest, query, learn, work, practice, admin
    core/           # config, Meta API client, grounding-mode prompt contracts
    db/             # schema, migrations, repositories (artifacts, chunks, facts, ...)
    ingest/         # source adapters (text, paste, txt/md, pdf, docx) + chunker
    retrieval/      # embedder (fastembed), hybrid search + RRF, rerank (stretch)
    llm/            # extraction, explainer, question-gen, evaluation (schema-validated)
frontend/
  src/
    api/            # typed API client
    views/          # Capture, Learn, Work, Practice, Interview
    components/     # citations, feedback cards, checkpoint-prompt modal, provenance view
```

**Key patterns:** source-adapter ingestion; schema-at-the-boundary for all LLM outputs; citations as first-class data (chunk/fact IDs rendered in the UI); practice as a mode-parameterized loop, not two features; vector index treated as a derived, rebuildable artifact of the canonical SQLite store; interactive stepwise learning over contextual Q&A; explicit success markers as the authoritative reuse signal; conversation-as-source with role-asymmetric grounding.

## 7. Tools/Features

**F-1 — Capture & ingest.** Text box (typed/pasted), conversation/session-summary paste, .txt/.md upload; PDF (.pdf, text-based) and Word (.docx) upload as strongly preferred additions. Every input becomes a SourceArtifact with provenance, then chunks + embeddings + FTS entries. Size caps on uploads; a visible note that pasted content is stored verbatim (secret caution, not a blocker).

**F-2 — Grounded Q&A (chat).** Natural-language questions over all saved material. Retrieval runs hybrid search; generation runs in evidence mode for personal content (citations required, no speculation) and may consult teaching mode only when the question is conceptual. Every answer renders clickable citations to source passages, and the original note is always one click away.

**F-3 — Eight-step explainer (interactive).** Generates the founder's learning sequence: (1) short literal definition, (2) connection to a familiar system, (3) complete-system analogy, (4) explicit component mapping, (5) interaction walkthrough, (6) larger-process placement (before/after), (7) interview-ready technical explanation, (8) analogy limitations. Multi-stage generation (not single-shot); output stored as a versioned Explanation record with mapping and limits. The lesson is stepwise and interruptible: the user can ask questions or explore confusion at any step (answered in teaching mode with the in-progress explanation as context), request an alternative take on the current step (persisted as a new version), and resume where they left off. Every new explanation is shaped by the learner profile (F-13) and prior stored explanations.

**F-4 — Explanation memory, success markers & reuse.** Before generating, the explainer retrieves past Explanations for the same concept (and related ones by similarity). Reuse is governed by explicit success signals: the authoritative signal is the user's "This clicked" marker, settable on a whole explanation or on individual steps/connections; secondary signals are reuse count and linked practice-attempt outcomes. Marked explanations are offered first ("this worked for you before") or injected as context so the successful analogy family is reused. Separately, learning conversations are preserved verbatim through conversation memory (F-12) — a user-generated analogy or insight stays retrievable even when never marked, but preservation must never be confused with success classification.

**F-5 — Work extraction, reasoning chains & accomplishment recognition.** Runs structured extraction over artifacts into problems, decisions + reasoning, accomplishments, demonstrated skills, evidence links, and per-item status (proposed / rejected / completed) — plus typed links between facts preserving reasoning chains (Problem → constraints → approaches → rejection reasons → decision → implementation → outcome). Rejected approaches with their reasons are first-class records: spotting failure modes and tradeoffs counts as engineering contribution. Results are reviewable with provenance; links connect only grounded facts; extraction never upgrades discussion into accomplishment and never invents steps or outcomes.

**F-6 — Career profile & prioritization.** Profile fields: current/previous occupation, target career or specific position. Minimum required behavior: profile CRUD, profile text injected into extraction and question-generation prompts, and keyword/tag filtering of accomplishments; users can conversationally redirect irrelevant questions in the meantime. Scored relevance ranking is Preferred, not required. Retention is always independent of relevance (ranking is query-time only).

**F-7 — Practice Loop (shared, both modes).** App asks → user answers → app evaluates → actionable feedback + attempt logged. Learning mode: explain-back against the stored/taught explanation. Interview mode: each question labeled `experience` (claims evaluated against accomplishment facts and sources — evidence mode) or `technical` (conceptual accuracy from general knowledge, personal examples incorporated when retrieved — teaching mode). Same endpoint, mode-parameterized rubric and reference assembly; feedback shape shared (correct / missing / inaccurate / terminology help / next step) with a grounding label (`from your notes` / `general explanation` / `both`).

**F-8 — Interview prep surface.** Interview-mode Practice Loop sessions (both question kinds) plus grounded Q&A over stored knowledge. The loop iterates turn-by-turn and each feedback round includes a next step or single follow-up question — iteration is not coaching. Explicitly excluded "advanced coaching": structured multi-turn drill plans, STAR-framework structuring guidance, and delivery analysis.

**F-9 — Checkpoint-prompt button.** One click displays a predefined, copyable prompt asking a coding assistant to summarize work performed, problems encountered/resolved, decisions + reasoning, and accomplishments/skills demonstrated. The user pastes the response into ThoughtBridge manually. Static text; no AI generation, no integration.

**F-10 — Deletion with cascade.** Delete an artifact (or account-level wipe) and its exclusively dependent records — chunks, vec/FTS rows, and any facts, interpretations, explanations, and attempts left with no remaining support — are removed in the same transaction. Information independently supported by other retained sources remains available: deletion removes the deleted source's chunk references from multi-source facts and deletes only facts left with zero supporting chunks. MVP limitation (documented, not fixed): extraction calls produce per-call fact records and the MVP does not deduplicate or merge equivalent facts across artifacts, so duplicates may exist and cross-artifact sharing arises only when one extraction call spans multiple artifacts. No topic-wide deletion, no automatic forgetting, no editing. Design must not complicate future span-level editing and redaction.

**F-11 — Provenance & grounding visibility.** UI consistently shows what came "from your notes" (with citations) versus general explanation, and every derived item links back to its sources. This is a product requirement, not polish: the grounding distinction must be visible to the user.

**F-12 — Automatic conversation memory.** Every in-app conversation (learning discussions, grounded Q&A, interview practice) is automatically saved — no manual import or per-conversation approval — with role labels, timestamps, mode, and citations, and ingested via the `tb_conversation` adapter into the standard pipeline. User turns are candidate evidence; assistant turns are labeled, retrievable context, never mined for facts or accomplishments; completion status requires explicit user statements. Indexing may be asynchronous provided conversations reliably become retrievable. Deleting a conversation removes its artifact and derived rows like any other source. The UI discloses that conversations are saved and retrievable.

**F-13 — Learner-preferences profile.** A lightweight cross-concept record: emphasis preferences for the explanation dimensions (familiar-system grounding, explicit component mapping, larger-process placement, interaction walkthroughs, terminology bridging — defaulting on, matching the eight-step framework) plus free-text "how I learn best." Injected into every new explanation; user-editable. Automatic inference from behavior is deferred.

## 8. Technology Stack

**Backend:**

- Python **3.12** (pinned — matches the dev environment and avoids a reported sqlite-vec packaging concern on 3.13; use Homebrew/pyenv Python on macOS, not system Python)
- FastAPI (current stable, async) + Pydantic v2 + Uvicorn
- SQLite (single `.db` file) with FTS5 + `sqlite-vec` (vec0 virtual tables) for hybrid retrieval
- `fastembed` (ONNX, CPU) for local embeddings, BGE-small-class default (~90 MB, zero marginal cost); upgrade path to EmbeddingGemma-class models if build-time verification allows
- `httpx`-based or OpenAI-SDK-compatible client for the Meta Model API (`https://api.meta.ai/v1`, Muse Spark models)
- `pypdf` (text-based PDFs) + `python-docx` (.docx) for preferred uploads
- `pytest` for tests; `ruff` for lint/format (type checking per repo convention at scaffolding)

**Frontend:**

- React + TypeScript + Vite + Tailwind CSS (current stable at scaffolding)
- Typed API client generated against or hand-mirrored from backend Pydantic schemas
- Static hosting for the demo (e.g., Vercel or equivalent; finalized at deploy checkpoint)

**AI / inference:**

- Meta Model API (Muse Spark family) for **all** LLM reasoning: extraction, explanation, question generation, answer evaluation, grounded Q&A. Target the default `muse-spark` model family available to the participant key; exact model ID recorded in code and README at first successful call.
- Local embeddings only (no embedding API spend, no data egress for indexing).
- Llama-via-Baseten reserved strictly as a fallback if Meta API access fails (see Risks), not a second primary.

**Infrastructure:**

- Local development first (SQLite file, Vite dev server, Uvicorn).
- Early cloud checkpoint for the backend; Modal is the leading option (Python-native, `@modal.asgi_app`, persistent volume for the `.db`, scale-to-zero) but not finalized — the deploy checkpoint decides based on what works fastest with a persistent SQLite file.
- Seed-on-boot strategy as backup wherever the filesystem is ephemeral.

**Deliberately not adopted:** LangChain / LangGraph / LlamaIndex, dedicated vector databases, PostgreSQL, Redis/Kafka, Kubernetes/multi-service compose, fine-tuning, custom auth, Next.js SSR, OCR tooling.

## 9. Security & Configuration

**Authentication/authorization:** none for the MVP — single-user local + demo deployment. Multi-user accounts and auth are explicitly deferred. The demo deployment must not expose any real private data (seeded sample content only).

**Configuration management:**

- `MODEL_API_KEY` — ThoughtBridge-dedicated Meta Model API key (participant to create; distinct from the existing Muse Code and Playground keys). Loaded from environment / `.env` (gitignored; `.env.example` committed with non-secret placeholders).
- `DATABASE_PATH` — SQLite file location (default `./data/thoughtbridge.db`).
- `EMBEDDING_MODEL` — fastembed model name (default BGE-small-class).
- `META_MODEL` — Muse Spark model ID (recorded at first successful call).
- Upload caps (`MAX_UPLOAD_MB`, `MAX_ARTIFACT_CHARS`) as code constants with env overrides.

**Security scope — in:**

- Secrets hygiene: pasted/uploaded content is stored verbatim by design, so the UI warns users not to paste secrets; seed/demo data must contain no real credentials; `.env` never committed.
- Automatic-capture transparency: the UI discloses that in-app conversations are automatically saved and retrievable; conversation artifacts delete with full cascade like any other source (F-12).
- Untrusted-input discipline: all imported material (notes, pastes, uploads, assistant transcripts) is treated as **untrusted data, never as instructions** — ingestion and prompts are constructed so imported text cannot override system behavior (prompt-injection awareness in prompt design and review).
- Provenance integrity: originals immutable in MVP; derived data always traceable; deletion cascades verified by test.
- Dependency sanity: pinned Python (3.12), lockfile for backend deps, `pip audit`/`npm audit` pass at submission time (or documented exceptions).

**Security scope — out (deferred):** user authentication, per-user data isolation, encryption at rest beyond platform defaults, secret-detection/redaction automation, audit logging, rate limiting, penetration testing.

**Deployment considerations:** SQLite persistence is the main deploy risk (ephemeral filesystems) — mitigated by persistent volume or seed-on-boot (decided at the early deploy checkpoint). Frontend static hosting is low-risk. No employer or client data in any deployed or recorded artifact.

## 10. API Specification

Base URL `/api/v1`. JSON everywhere. No auth (single-user MVP). Error shape: `{"detail": "..."}` (FastAPI default) with 4xx for client errors, 502 for upstream Meta API failures (surfaced, never silently swallowed).

**Health & admin**

- `GET /health` → `{"status": "ok", "db": true, "meta_api": true|false}` (Meta reachability checked, failures reported honestly)

**Ingest**

- `POST /artifacts` — create from text. Body: `{"source_type": "note|paste|summary", "title": "...", "content": "..."}` → `201 {"artifact_id": "uuid", "chunks": 12}`
- `POST /artifacts/upload` — multipart file (`.txt`, `.md`; `.pdf`, `.docx` when preferred uploads land) → same shape, plus `{"extracted_chars": N, "pages": N?}`
- `GET /artifacts` — list with provenance metadata (id, title, source type, created at, chunk/fact counts)
- `GET /artifacts/{id}` — full original content + derived summary (chunks, facts, interpretations linked)
- `DELETE /artifacts/{id}` — cascade delete per F-10 independent-support semantics: removes the artifact's chunks, vec/FTS rows, and records left with no remaining support; multi-source facts lose only the deleted source's chunk references → `200 {"deleted": {"chunks": N, "facts": M, ...}, "unlinked": {"facts": K}}`

**Retrieval & Q&A**

- `POST /query` — grounded chat Q&A. Body: `{"question": "...", "mode": "evidence|teaching|auto", "top_k": 8, "context": {"explanation_id": "uuid|null"}, "conversation_id": "uuid|null"}` → `{"answer": "...", "citations": [{"chunk_id": "...", "artifact_id": "...", "span": [s, e], "excerpt": "..."}], "mode_used": "evidence", "conversation_id": "uuid"}` (`context.explanation_id` scopes answers to an in-progress explanation for interrupt-and-resume learning; omit `conversation_id` to start a new conversation, pass it back to continue — user turn and assistant turn persisted in order either way)
- `GET /chunks/{id}` — chunk text + artifact link (citation target)

**Learning**

- `POST /learn/explain` — eight-step explainer. Body: `{"concept": "RAG", "familiar_system_hint": "optional"}` → `{"explanation_id": "uuid", "reused_from": "uuid|null", "steps": {"definition": "...", "familiar_system": "...", "analogy": "...", "mapping": [...], "walkthrough": "...", "placement": "...", "interview_ready": "...", "limitations": "..."}}` (all eight F-3 stages: definition, familiar-system connection, complete-system analogy, component mapping, walkthrough, placement, interview-ready explanation, limitations)
- `GET /learn/explanations` — list stored explanations (concept, created at, reuse count, success signals)
- `GET /learn/explanations/{id}` — full versioned explanation with mapping JSON and limits
- `POST /learn/explanations/{id}/markers` — set a "clicked" marker. Body: `{"scope": "explanation|step", "step": "mapping|null", "note": "optional"}` → `201 {"marker_id": "uuid", "scope": "..."}`
- `GET /learn/profile` / `PUT /learn/profile` — learner-preferences profile: `{"emphasis": {"familiar_systems": true, "component_mapping": true, "process_placement": true, "interactions": true, "terminology_bridge": true}, "how_i_learn": "free text"}`

**Work**

- `POST /work/extract` — run extraction over artifacts. Body: `{"artifact_ids": ["..."]}` → `{"facts": [{"fact_id": "...", "kind": "problem|decision|accomplishment|skill", "status": "proposed|rejected|completed", "summary": "...", "skills": [...], "confidence": 0.0-1.0, "chunk_ids": [...], "links": [{"to_fact": "...", "relation": "constrained_by|considered|rejected_because|decided|implemented_by|resulted_in"}]}]}`
- `GET /work/accomplishments` — list/filter (query-time relevance filter optional) with evidence links
- `GET /profile` / `PUT /profile` — career profile: `{"current_role": "...", "past_roles": [...], "target_career": "...", "target_position": "..."}`

**Practice Loop (shared)**

- `POST /practice/question` — Body: `{"mode": "learning|interview", "question_kind": "experience|technical (interview only)", "context": {"explanation_id": "..."} | {"focus": "optional topic/role hint"}, "conversation_id": "uuid|null"}` → `{"attempt_id": "uuid", "question": "...", "question_kind": "experience|technical|null", "reference_kind": "explanation|facts|general", "conversation_id": "uuid"}` (omit `conversation_id` to start a new conversation, pass it back to continue)
- `POST /practice/answer` — Body: `{"attempt_id": "uuid", "answer": "..."}` → `{"feedback": {"correct": [...], "missing": [...], "inaccurate": [...], "terminology": [...], "next_step": "..."}, "grounding": "from your notes|general explanation|both"}` (inherits its conversation from the attempt — no `conversation_id` needed; user answer and feedback turns persisted in order)
- `GET /practice/attempts` — attempt history per concept/mode (feeds future scheduling; MVP uses simple re-queue display)

**Checkpoint prompt**

- `GET /prompts/checkpoint` — returns the static copyable prompt text (also hardcoded in the frontend as fallback)

**Conversations (automatic capture — no dedicated create endpoint)**

Conversations are created implicitly through the write path above: `POST /query` and `POST /practice/question` accept an optional `conversation_id` (omit to start, pass back to continue); `POST /practice/answer` inherits its attempt's conversation. Every call persists its user turn and resulting assistant turn in order with role labels, timestamps, mode, and citations.

- `GET /conversations` — list auto-saved in-app conversations (id, kind: learning|qa|interview, started at, turn counts)
- `GET /conversations/{id}` — role-labeled turns with timestamps, mode, and citations
- `DELETE /conversations/{id}` — removes the conversation artifact with full derived cascade (same guarantees as artifact deletion)

Example — evaluation response:

```json
{
  "feedback": {
    "correct": ["Described retrieval as fetching relevant passages before generation"],
    "missing": ["The chunking step", "Why embeddings are computed from originals"],
    "inaccurate": [],
    "terminology": ["Use 'embeddings' for the vectors; 'tokens' means something else here"],
    "next_step": "Re-explain how chunks become vectors, then retry the full explanation."
  },
  "grounding": "both"
}
```

## 11. Success Criteria

**MVP success definition:** By November 4, a judge can run ThoughtBridge (live deployment preferred, one-command local run acceptable), capture a note, ask a vague question and get a cited answer, learn a concept through the eight-step explainer, interrupt the lesson with a question and resume, see a past explanation reused, paste a work session and get extracted accomplishments with proposed/rejected/completed status, complete one Learning-mode and one Interview-mode practice exchange with actionable feedback, recall an earlier in-app discussion, and delete content with visible cascade — all in the 3-minute demo video, with all LLM reasoning performed by Meta models.

**Functional requirements:**

- ✅ One successful Meta Model API call verified as the first development checkpoint
- ✅ Text/paste/txt-md ingest produces chunks, embeddings, and FTS entries with provenance
- ✅ Vague natural-language query retrieves the right passage without exact keywords (demonstrated on seeded data)
- ✅ Every personal-content answer carries citations; speculation refusal works when sources are silent
- ✅ Eight-step explainer produces all steps including mapping and limitations; output stored and reusable
- ✅ Stored explanation is offered/reused on repeat concept request, marked explanations preferred
- ✅ Extraction yields problems, decisions, accomplishments, skills, evidence links, and status labels on real pasted logs
- ✅ Career profile persists and influences prioritization prompts/filtering
- ✅ Practice Loop works end-to-end in both modes with structured feedback and logged attempts
- ✅ Deletion removes an artifact's exclusively dependent rows and unlinks multi-source references; independently supported information remains; post-delete queries never surface deleted content (test-verified)
- ✅ Checkpoint-prompt button displays copyable static text
- ✅ Stepwise explainer supports interrupt-with-question and resume; regenerated step alternatives persist as versions
- ✅ "This clicked" markers stored at explanation and step level; reuse prefers marked explanations; unmarked exchanges preserved via conversation memory without success classification
- ✅ Learner-preferences profile persists and shapes new explanations
- ✅ Interview practice supports experience questions (evidence-grounded) and technical questions (teaching-grounded) with correct grounding labels
- ✅ Extracted facts carry reasoning links; chains traversable with per-node evidence; no invented steps or outcomes
- ✅ In-app conversations auto-saved with role labels and retrievable ("what did we decide..."); assistant turns never mined as evidence (test-verified)
- ✅ Cloud deployment checkpoint reached before the app is "otherwise complete"
- ✅ Seeded demo database + public repo + README + 3-minute video submitted on time

**Quality indicators:** extraction accuracy judged by inspection on real dev logs (errors visible via provenance, not silent); retrieval recall spot-checked on 5+ vague queries against seeded data; no invented accomplishments in any demo output; `pytest` + lint pass; dependency audit pass or documented exceptions.

**User experience goals:** capture in under 30 seconds; answer with visible citations in one view; original source always one click from any derived item; "from your notes" vs. "general explanation" visually distinct; practice feedback specific enough to act on (names the missing point and the term to use).

## 12. Implementation Phases

Day 0 is Friday Oct 30; submission is Wednesday Nov 4 (~9 PM ET). Four phases; each ends with a validation gate. Cut order if behind (agreed): (1) advanced coaching depth — already out; (2) career ranking sophistication (profile fields stay); (3) PDF/Word uploads; (4) HyDE vague-query mode. Conversation-memory fallback if Phase 1–2 slip: persist turns + chunk transcripts with role tags (retrieval works) and keep the role-asymmetric extraction rule in prompts, deferring polished role-aware display. Untouchable core: ingest → retrieve → explain → extract → Practice Loop.

**Phase 1 — Foundation & retrieval (Oct 30–31). Goal:** the pipeline lives and Meta API access is proven.

- ✅ Deliverables:
  - ✅ Scaffold backend (FastAPI) + frontend (React/TS) + SQLite schema (4 layers + profile + explanations + attempts + conversations/turns with stable IDs and role labels)
  - ✅ First successful Meta Model API call (CHECKPOINT 1 — blocks all LLM work)
  - ✅ Source-adapter ingestion: text/paste/txt-md → artifacts → chunks → fastembed embeddings → FTS5 + vec0
  - ✅ Hybrid retrieval (BM25 + vector + RRF) with top-k inspection endpoint
  - ✅ Grounded Q&A endpoint + minimal chat UI with citations; every exchange persisted as ordered, role-labeled turns under a conversation id (conversation-memory foundation — pipeline ingestion of conversations lands in Phase 3, no chat rework)
  - ✅ Cloud-deploy checkpoint (CHECKPOINT 2 — backend reachable with persistent or seeded DB)
- Validation: vague query over seeded notes returns the right cited passage; conversation turns persisted with stable ids and role labels; `/health` reports Meta reachability honestly; deployed URL serves the chat view.

**Phase 2 — Learning & work (Nov 1). Goal:** the two defining capabilities function.

- ✅ Deliverables:
  - ✅ Interactive eight-step explainer endpoint + Learn view (multi-stage generation, versioned Explanation records, interrupt/resume via contextual Q&A, step regeneration as new versions)
  - ✅ Explanation memory: same-concept retrieval offered first / injected as context, marked explanations preferred; "clicked" markers endpoint + UI (explanation + step level)
  - ✅ Learner-preferences profile record + prompt injection + basic UI (simplifiable to defaults + free-text)
  - ✅ Work extraction endpoint + Work view (problems, decisions, accomplishments, skills, evidence, status labels, typed reasoning links)
  - ✅ Career profile CRUD; profile fed into extraction and question-gen prompts + basic accomplishment filtering (scored ranking Preferred)
  - ✅ PDF + Word upload adapters (Preferred; scheduled here because cheap — first cut candidate if Phase 1 slipped)
- Validation: teach → interrupt with a question → resume round-trip on one concept; marked explanation reused on repeat request; extraction over a real pasted dev log shows correct proposed/rejected/completed split and a traversable reasoning chain on inspection.

**Phase 3 — Practice Loop & integrity (Nov 2). Goal:** the feedback loop and trust guarantees close.

- ✅ Deliverables:
  - ✅ Shared Practice Loop endpoints + Practice/Interview views (question-gen, evaluation, feedback cards, attempt log) in both modes, with interview `question_kind` (experience/technical) and per-kind grounding
  - ✅ Mode-parameterized rubrics; evaluator constrained to provided references; grounding label on feedback
  - ✅ Automatic conversation memory: `tb_conversation` adapter over Phase 1 turn persistence, role-labeled retrieval + display (fallback per above if behind)
  - ✅ Deletion with cascade, including conversations (+ tests proving no retrieval residue and no evidence mining from assistant turns)
  - ✅ Checkpoint-prompt button; provenance/grounding visibility pass across views (including role labels and grounding distinctions)
  - ✅ Retrieval hardening only if measured failures: rerank or HyDE (preferred stretch, not default)
- Validation: one full Learning-mode and one full Interview-mode exchange (one experience, one technical question) each produce specific, actionable feedback with correct grounding labels; an in-app discussion is retrievable by a follow-up question; delete-then-query test passes.

**Phase 4 — Demo & submission (Nov 3–4). Goal:** a submission that demos itself.

- ✅ Deliverables:
  - ✅ Seeded demo database (realistic, secret-free) exercising capture → retrieve → learn → practice → interview → conversation recall
  - ✅ Live deployment verified end-to-end (or documented one-command local fallback)
  - ✅ Submission README (what it is, Meta tech used, run instructions, window-built statement)
  - ✅ 3-minute demo video + public repo + member names submitted before the deadline
- Validation: cold run-through (fresh clone → running demo) succeeds; video covers all three capabilities; submission checklist complete with buffer time.

## 13. Future Considerations

**Post-MVP integrations (participant-confirmed order):** macOS activity capture first (via the source-adapter seam — no core redesign), then iOS integration, then GitHub integration, then Windows activity capture.

**Learning & practice:** FSRS-style automated scheduling over the stored attempt log; difficulty-axis classification (terminology vs. verbalization vs. conceptual); analogy-family matching across concepts; automatic inference of learning preferences; automatic success detection from conversational cues; learning-topic exclusion preferences (stop practicing without deleting history).

**Career & interview:** advanced interview coaching (multi-turn drills, STAR structuring, delivery feedback); résumé bullet, portfolio case-study, and performance-review generation from verified facts; meeting-practice mode.

**Capture & editing:** voice notes, screenshots/documents/error-message capture, git commit/PR ingestion, direct coding-assistant integrations, context-aware reminders; conversation-driven editing (edit-target resolution, confirmation flows, versioned writes, dependent-record propagation) plus span-level editing and redaction (e.g., remove a client name without losing the accomplishment).

**Platform:** multi-user accounts + auth, per-user isolation, Postgres migration only if multi-user scale demands it, knowledge-graph layer only if multi-hop queries measurably fail, production hardening.

## 14. Risks & Mitigations

1. **Breadth vs. ~5 days (highest risk).** Three capabilities + RAG + frontend + deploy + video from a greenfield repo, plus review-driven additions (interactive learning, markers, reasoning links, conversation memory). *Mitigation:* one-pipeline-three-surfaces architecture; additions are refinements inside scheduled phase work, not new systems; agreed cut order with an untouchable core and a conversation-memory fallback; Phase 4 reserved entirely for demo/submission; daily scope check against the phase gates.
2. **Meta API access or credits fail at the last mile.** Account is active but the ThoughtBridge key doesn't exist yet; credit/pricing specifics are press-sourced, not verified. *Mitigation:* dedicated key creation + one successful call is CHECKPOINT 1 on day 1 — nothing LLM-dependent starts before it; Llama-via-Baseten held as emergency fallback (would weaken the Meta-tooling story, so genuinely last resort); local embeddings keep indexing free regardless.
3. **Extraction accuracy on long, messy logs — now incl. reasoning links and conversation roles.** Proposed/rejected/completed status, link relations, and accomplishment detection can misfire; assistant turns could leak into evidence. *Mitigation:* chunk-level extraction with visible confidence + provenance so errors are inspectable; status labels and role labels user-visible; demo seeded with verified-good examples; anti-invention rules (discussion never upgrades to accomplishment; assistant turns never mined as evidence; completion needs explicit user statements) enforced in prompts, covered by tests, and reviewed in outputs.
4. **"Generic chatbot" perception in judging.** Rules discourage generic chatbot apps (participant-confirmed intent). *Mitigation:* frame and demo as a grounded work-memory + learning system — citations, provenance views, explanation reuse, and evidence-mode refusals are the visible differentiators; README and video lead with the memory/evidence story, not chat.
5. **SQLite persistence on serverless deploy.** Ephemeral filesystems can wipe the `.db`. *Mitigation:* early deploy checkpoint (Phase 1, not Phase 4) decides between persistent volume vs. seed-on-boot; local one-command run kept as a working fallback so deployment can never block the demo.

## 15. Appendix

**Research basis:** five-track parallel research (Oct 29–30, 2026) covering architecture patterns, technologies, nine comparable-product categories, hackathon requirements, and MVP feasibility, plus synthesis. Key verified findings baked into this PRD: 3-layer/4-table provenance store; hybrid BM25+vector+RRF as the convergent personal-KB stack; FSRS v6 as scheduler state-of-the-art (deferred, attempt log preserves the option); analogy pedagogy requiring explicit mapping + limitations; Anthropic simplicity ladder (deterministic → single call → fixed workflow → agent); sqlite-vec + FTS5 sufficiency to ~1M chunks.

**Key links:**

- Hackathon details (JS-rendered; fetch returns app shell only): <https://cerebralvalley.ai/e/meta-ai-developer-hackathon/details>
- Meta event page: <https://dev.meta.ai/events/global-hackathon>
- Meta Model API base URL: `https://api.meta.ai/v1` (OpenAI-SDK-compatible)
- sqlite-vec: `pip install sqlite-vec` (Apache-2.0; needs non-system Python on macOS)
- fastembed (local ONNX embeddings): default BGE-small-class
- Participant judging-notes repo (secondhand rules source): <https://github.com/sholaola23/meta-hackathon-2026>

**Assumptions (called out, not verified):** exact deadline time (Nov 4 ~9 PM ET, corroborated by 2+ participant sources); judging weights (30/25/25/20, press + participant corroborated); $150 API credit figure (waiver-cited, 3 sources); prize splits; "only Oct 26–Nov 4 work counts" (participant-sourced); non-Meta-model co-use permissibility (unknown — PRD avoids the question by using Meta for all LLM work); Meta embedding/rate-limit specifics (sidestepped via local embeddings).

**Repository note:** the workspace currently contains the participant's deterministic workflow starter (commits predate the hackathon), conversation-log tooling, and private logs. All ThoughtBridge application code will be written Oct 30–Nov 4 in new directories; the submission README will state the app was built during the competition window. `conversation-log/` is gitignored and stays private.

**Decisions log (from discovery):** Indie track; Meta-for-all-LLM-work; shared Practice Loop essential in both modes; two grounding modes (closed evidence / open teaching); PDF+Word preferred and scheduled early; career profile essential, ranking preferred; macOS capture fully deferred with adapter seam; deletion-with-cascade required, editing/redaction deferred; cut order agreed (§12).

**Decisions log (from PRD review, Oct 30):** interactive stepwise learning with interrupt/resume; explicit "clicked" markers (explanation + step) as authoritative success signal, unmarked exchanges preserved without success classification; lightweight learner-preferences profile (defaults = eight-step framework), inference deferred; interview `question_kind` (experience/technical) with per-kind grounding in the shared loop; typed reasoning links between facts; automatic conversation memory via `tb_conversation` adapter with role-asymmetric grounding and async-indexing allowance; iteration-vs-coaching boundary; Essential/Preferred priority tags; "scheduling" reworded to attempt logging + re-queue ordering.



