# Feature: pdf-word-upload-adapters

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Add `.pdf` (text-based only, via `pypdf`) and `.docx` (via `python-docx`) upload adapters behind the existing source-adapter seam (`adapt_upload` in `backend/app/ingest/adapters.py`), feeding the unchanged ingestion pipeline. `POST /artifacts/upload` additionally returns `pages` for PDFs (PRD §10: `{"extracted_chars": N, "pages": N?}`). This is Phase 2 deliverable 6 (Preferred, first cut candidate — but it is being built, not cut).

## User Story

As a ThoughtBridge user
I want to upload PDF and Word documents containing my notes and work history
So that their content becomes searchable, explainable, and extractable like any other ingested material

## Problem Statement

Ingestion currently accepts only typed/pasted text and `.txt`/`.md` uploads. Real user material (resumes, design docs, exported notes, papers) commonly lives in `.pdf` and `.docx` files, which are rejected with 400 today. PRD F-1 lists both as strongly preferred additions scheduled in Phase 2.

## Scope

- In scope: `.pdf` text extraction (text-based PDFs only) + page count; `.docx` paragraph + table text extraction; `pages` field on the upload response; corrupt/encrypted/blank-file 400 handling; dependency additions (`pyproject.toml` + `uv.lock` + Modal image sync); adapter + API tests; updating the two existing tests that assert pdf/docx rejection.
- Out of scope: OCR / scanned-document handling; legacy `.doc` (OLE) support; headers/footers/footnotes extraction; frontend upload UI (Capture view is still a stub — upload stays API-only); rerank/HyDE; any Essential-deliverable changes; Modal redeploy (no browser-verifiable change; image-list sync keeps the next deploy correct).

## Solution Statement

Extend `adapt_upload` to dispatch on suffix: `.txt`/`.md` keep the current UTF-8 path; `.pdf` goes through `pypdf.PdfReader` over `BytesIO` (per-page `extract_text()`, page count into `origin["pages"]`); `.docx` goes through `docx.Document` over `BytesIO` (paragraphs + tables). A new `UnparseableUploadError` (sibling of the existing adapter `ValueError`s) maps to HTTP 400 in the router. The router passes `pages` through to a new optional `UploadCreated.pages` field. Byte cap (`MAX_UPLOAD_MB`, enforced before adaptation) and char cap (`MAX_ARTIFACT_CHARS`, enforced in the pipeline on extracted text) apply unchanged — no new cap work.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: Low
**Primary Systems Affected**: `backend/app/ingest/adapters.py`, `backend/app/api/ingest.py`, backend dependencies + Modal image
**Dependencies**: `pypdf`, `python-docx` (new third-party libs); prerequisite deliverables: source-adapter ingestion (Phase 1, landed)
**Assumptions**: `uv` resolves current `pypdf`/`python-docx` releases on Python 3.12 (validate at Task 1); pypdf non-strict parsing accepts the programmatic test fixture (the test itself proves it); Modal `pip_install` accepts the same package names (validate by list comparison in the Modal sync task — same names as pyproject, pip-installable)

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `backend/app/ingest/adapters.py` (lines 13-24, 56-77) - Why: `ALLOWED_UPLOAD_SUFFIXES`, existing error types, and `adapt_upload` dispatch to extend; origin-dict metadata pattern to mirror
- `backend/app/api/ingest.py` (lines 49-52, 113-155) - Why: `UploadCreated` response model (add `pages`) and `upload_artifact` handling order (byte-cap → suffix → decode → blank) to preserve
- `backend/app/ingest/pipeline.py` (lines 45-60) - Why: char-cap check applies to extracted text unchanged; no pipeline change needed
- `backend/app/core/config.py` (lines 22-23) - Why: caps already exist as code constants with env overrides (`max_upload_mb`, `max_artifact_chars`)
- `backend/modal_app.py` (lines 32-45) - Why: pip_install list MUST be kept in sync with pyproject (see its own comment); add both packages here
- `backend/pyproject.toml` (lines 7-16) - Why: dependency declaration style (note unpinned `fastembed`, `python-multipart` — lockfile pins)
- `backend/tests/test_adapters.py` (lines 29-48) - Why: adapter test patterns to mirror; lines 40-43 assert pdf/docx rejection and MUST be updated by this deliverable
- `backend/tests/test_ingest_api.py` (lines 19-55, 123-150) - Why: stub seam (`_stub` + `_client` fixtures) and upload contract tests; `test_upload_pdf_is_400` (lines 144-150) MUST be replaced since pdf now succeeds
- `PRD.md` §7 F-1 - Why: authoritative scope (text-based PDF + docx as preferred additions, size caps)
- `PRD.md` §10 Ingest - Why: authoritative contract (`POST /artifacts/upload` → `{"extracted_chars": N, "pages": N?}`)
- `PRD.md` §12 Phase 2 - Why: deliverable placement + cut-order context
- `.agents/plans/phase-2-build-list.md` (deliverable 6) - Why: binding scope boundaries (extraction only, no OCR)
- `frontend/src/api/artifacts.ts` - Why: evidence upload is API-only (no upload fn) — no frontend change in this plan
- `frontend/src/App.tsx` (line 9) - Why: evidence Capture view is still a stub — no frontend change in this plan

### New Files to Create

- `backend/tests/upload_fixtures.py` - Shared PDF/DOCX fixture builders (`minimal_pdf_bytes`, `docx_bytes`, encrypted/blank-PDF builders) imported by both test modules
- `backend/tests/__init__.py` - Only if `tests.`-package imports require it (decided empirically in the adapter-test task below, which first creates and imports the fixtures module; check for existence first)

(All other changes extend existing files: `backend/tests/test_adapters.py` and `backend/tests/test_ingest_api.py` are extended in place.)

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [pypdf stable docs](https://pypdf.readthedocs.io/en/stable/)
  - Specific section: User Guide → Extract text from PDF (`PdfReader(stream)`, `reader.pages`, `page.extract_text()` which may return `None`, `len(reader.pages)`); also `reader.is_encrypted` / `reader.decrypt("")` return semantics
  - Why: Exact extraction API for the PDF adapter (error mapping uses a broad `except Exception`, so no exception-taxonomy lookup needed). NOTE: doc-site fetches were rate-limited during planning — validate class names against the installed package (`python -c "from pypdf import PdfReader"`) before coding.
- [python-docx docs](https://python-docx.readthedocs.io/en/latest/)
  - Specific section: Quickstart/Documents → opening from a file-like object (`Document(BytesIO(raw))`), `document.paragraphs` (`p.text`), `document.tables` (rows → cells → `cell.text`)
  - Why: Exact extraction API for the docx adapter (broad `except Exception` for errors — no exception-taxonomy lookup needed). NOTE: same rate-limit caveat — validate against the installed package first.

### Patterns to Follow

**Suffix dispatch + origin metadata** (`backend/app/ingest/adapters.py:56-77`): suffix rules, MIME recorded-not-trusted, title from stem, origin carries adapter-specific strings. New code adds `.pdf`/`.docx` branches returning the same `AdaptedSource(source_type="file", ...)` shape with `origin["adapter"]` = `"pdf"` / `"docx"` (mirroring `"txt_md"`), plus `origin["pages"] = str(n)` for PDFs.

**Adapter errors are plain ValueErrors mapped in the router** (`adapters.py:18-23`, `api/ingest.py:125-129`): `UnsupportedSuffixError`/`UndecodableUploadError` → 400. New `UnparseableUploadError(ValueError)` follows identically — corrupt/encrypted files are client file problems (400), never 500s.

**Upload handling order** (`api/ingest.py` docstring + lines 113-155): byte-cap FIRST → adapt (suffix/decode/parse) → blank check → pipeline (char cap). PDF/DOCX extraction slots into the adapt step; blank extraction (e.g. scanned PDF, empty docx) falls through to the existing blank check → 400 "file content blank". No OCR, per scope.

**Test stub seam** (`test_ingest_api.py:19-55`): `_stub` runs the REAL pipeline + repository with fake vectors; `_client` builds a TestClient over a tmp DB. New upload tests reuse these fixtures verbatim — never download the fastembed model.

**Naming Conventions:** `snake_case` modules/functions, `PascalCase` models/exceptions, existing error names end in `Error`.

**Error Handling:** upstream/file problems → 4xx with cause in `detail`; never swallow. Log rejections via `logger.warning` (mirror line 128).

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation

Dependencies + contract surface: add `pypdf` + `python-docx` to `pyproject.toml` (lock via `uv`), sync the Modal image list, extend `UploadCreated` with optional `pages`. Validate installed APIs match the documented names before writing adapter code.

**Tasks:**

- Declare both packages as backend dependencies and lock
- Sync `modal_app.py` pip list (its header comment requires it)
- Add `pages: int | None = None` to `UploadCreated`
- Verify pypdf/python-docx API names against installed packages

### Phase 2: Core Implementation

Adapter extraction: suffix dispatch in `adapt_upload`, `_extract_pdf` / `_extract_docx` helpers, new `UnparseableUploadError`, router mapping + `pages` passthrough from `origin`.

**Tasks:**

- Implement PDF extraction (per-page text, page count, encrypted → error)
- Implement docx extraction (paragraphs + tables)
- Wire new error → 400 and `pages` → response in the router

### Phase 3: Integration

No new wiring — the pipeline, caps, chunking, embeddings, and artifact persistence are untouched by design. Integration work is updating the two existing tests that encode pre-deliverable rejection behavior, plus checking docs for stale upload-type mentions.

**Tasks:**

- Update `test_bad_suffixes_and_missing_filenames_raise` (pdf/docx now valid)
- Replace `test_upload_pdf_is_400` with success + corrupt-failure tests
- Grep `backend/README.md` + frontend for stale ".txt/.md only" claims; update if present

### Phase 4: Testing & Validation

Adapter unit tests (generated fixtures, no binary blobs committed) + API contract tests through the stub seam + full suite + lint/type gates.

**Tasks:**

- Adapter tests: pdf/docx success, origin shape, corrupt/encrypted/blank failures
- API tests: 201 shapes (`extracted_chars`, `pages` present for pdf / null for docx+txt), 400s, 413 char-cap on extracted text
- Full `pytest`, `ruff check` + `ruff format --check`, `mypy app`

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

### ADD backend/pyproject.toml — declare pypdf + python-docx

- **IMPLEMENT**: Add `"pypdf"` and `"python-docx"` to `[project] dependencies`, alphabetical within the existing list (after `pydantic-settings`, before `sqlite-vec`). Unpinned, mirroring `fastembed`/`python-multipart` — `uv.lock` pins. Then run `uv sync` (or `uv lock`) from `backend/` to update the lockfile.
- **PATTERN**: Dependency style — `backend/pyproject.toml:7-16`
- **IMPORTS**: None
- **GOTCHA**: Run from `backend/` (AGENTS.md). Do NOT hand-edit `uv.lock` — let `uv` write it.
- **VALIDATE**: `cd backend && uv sync && uv run python -c "import pypdf, docx; print(pypdf.__version__)"`

### UPDATE backend/modal_app.py — sync deploy image deps

- **IMPLEMENT**: Add `"pypdf"` and `"python-docx"` to the `.pip_install(...)` list in the same position as pyproject (after `pydantic-settings`, before `sqlite-vec`). Nothing else changes.
- **PATTERN**: Keep-in-sync comment — `backend/modal_app.py:32-33`
- **IMPORTS**: None
- **GOTCHA**: Modal builds with pip, not uv.lock — forgetting this breaks the next deploy. No redeploy in this deliverable (no browser-verifiable change); correctness here is verified by list comparison, not by deploying.
- **VALIDATE**: `cd backend && uv run python -c "import tomllib, re; deps=tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']; norm=lambda s: re.split(r'[<>=!~\[;\s]', s.strip().lower().replace('_','-'))[0]; pyns={norm(d) for d in deps}; mo=set(re.findall(r'\"([A-Za-z0-9_.\-\[\]>=<~!,\s]+)\"', open('modal_app.py').read().split('.pip_install(')[1].split(')')[0])); mons={norm(d) for d in mo}; assert pyns==mons, (pyns^mons); print('dep sync ok:', sorted(pyns))"`
  - Expected: exit 0, prints `dep sync ok: [...]` with `pypdf` and `python-docx` in the list (both sides parsed — pyproject via tomllib, modal via its pip_install block — and normalized for case, extras, and version specifiers before comparison; any mismatch raises AssertionError naming the symmetric difference).

### ADD backend/app/api/ingest.py — optional pages on UploadCreated

- **IMPLEMENT**: Add `pages: int | None = None` to `UploadCreated`. In `upload_artifact`, pass `pages=int(adapted.origin["pages"]) if "pages" in adapted.origin else None` into the returned `UploadCreated`. No other router logic changes in this task.
- **PATTERN**: Response model — `backend/app/api/ingest.py:49-52,151-155`
- **IMPORTS**: None
- **GOTCHA**: `origin` values are `str` — the int() conversion lives in the router, not the adapter.
- **VALIDATE**: `cd backend && uv run ruff check app/api/ingest.py && uv run ruff format --check app/api/ingest.py`

### ADD backend/app/ingest/adapters.py — pdf/docx extraction + UnparseableUploadError

- **IMPLEMENT**: (1) Add `class UnparseableUploadError(ValueError)` with docstring "Upload bytes fail format parsing (corrupt/encrypted/unsupported)." (2) Extend `ALLOWED_UPLOAD_SUFFIXES` with `.pdf`, `.docx`. (3) In `adapt_upload`, after the suffix check, branch: `.pdf` → `_adapt_pdf(filename, content_type, raw)`; `.docx` → `_adapt_docx(...)`; else existing UTF-8 path. (4) `_adapt_pdf`: wrap the WHOLE body (construction + per-page extraction) so every parser failure maps to `UnparseableUploadError` — `try: reader = PdfReader(BytesIO(raw)); if reader.is_encrypted and not reader.decrypt(""): raise UnparseableUploadError("encrypted PDFs are not supported"); texts = [(page.extract_text() or "") for page in reader.pages] except UnparseableUploadError: raise except Exception as exc: raise UnparseableUploadError("upload is not a readable PDF") from exc  # noqa: BLE001 — parsers raise KeyError/TypeError/AttributeError/etc. on malformed input; all map to 400 by design`. NOTE: `decrypt("")` returns 0/falsy when the empty password fails — treat falsy as still-encrypted. Then `content = "\n\n".join(t for t in (x.strip() for x in texts) if t)`; `origin={"adapter": "pdf", "filename":..., "suffix": ".pdf", "content_type":..., "pages": str(len(reader.pages))}`; title from stem, same as txt path. (5) `_adapt_docx`: same whole-body rule — `try: doc = Document(BytesIO(raw)); blocks = [p.text.strip() for p in doc.paragraphs]; [row blocks per table] except UnparseableUploadError: raise except Exception as exc: raise UnparseableUploadError("upload is not a valid .docx file (legacy .doc is not supported)") from exc  # noqa: BLE001 — same broad-catch rationale as PDF`; for each table, each row contributes `" | ".join(cell.text.strip() for cell in row.cells)`; `content = "\n".join(b for b in blocks if b)`; origin with `"adapter": "docx"` (no `pages` — docx has no page concept). Blank results return normally — the router's existing blank check 400s them. GUARANTEE: no `pypdf`/`docx` exception type may escape the adapter — the broad `except Exception` (after re-raising `UnparseableUploadError`) maps every parser failure, including `KeyError`/`TypeError`/`AttributeError` from malformed structures, to `UnparseableUploadError` (→ 400), never a 500.
- **PATTERN**: `adapt_upload` + origin shape — `backend/app/ingest/adapters.py:56-77`
- **IMPORTS**: `from io import BytesIO`, `from pypdf import PdfReader`, `from docx import Document`. Validate every import name against the installed packages FIRST (`uv run python -c "..."`). No parser exception imports — the broad `except Exception` deliberately avoids depending on the parsers' exception taxonomy.
- **GOTCHA**: `page.extract_text()` may return `None` (blank/image-only page) — coerce before strip. Never trust MIME. Keep helpers private (`_adapt_pdf`) — public surface stays `adapt_upload`. Headers/footers/footnotes deliberately not extracted (note in code comment).
- **VALIDATE**: `cd backend && uv run python -c "from app.ingest.adapters import adapt_upload, UnparseableUploadError; print('imports ok')"`

### UPDATE backend/app/api/ingest.py — map UnparseableUploadError to 400

- **IMPLEMENT**: Import `UnparseableUploadError` from `app.ingest.adapters` (also re-export via `app/ingest/pipeline.py` `__all__` + import, mirroring how `UndecodableUploadError`/`UnsupportedSuffixError` are re-exported there — check `pipeline.py:20,26-32`). Add it to the `except (UnsupportedSuffixError, UndecodableUploadError)` tuple in `upload_artifact`. Update the endpoint docstring "Ingest a `.txt`/`.md` file upload" → "Ingest a `.txt`/`.md`/`.pdf`/`.docx` file upload".
- **PATTERN**: Error mapping — `backend/app/api/ingest.py:125-129`; pipeline re-export — `backend/app/ingest/pipeline.py:20,26-32`
- **IMPORTS**: `UnparseableUploadError` from `app.ingest.adapters`
- **GOTCHA**: Keep handling order byte-cap → adapt → blank → pipeline. Do NOT add new status codes.
- **VALIDATE**: `cd backend && uv run ruff check app/ && uv run ruff format --check app/ && uv run mypy app`

### UPDATE backend/tests/test_adapters.py — pdf/docx now valid + new adapter tests

- **IMPLEMENT**: (1) CREATE `backend/tests/upload_fixtures.py` with public builders: `minimal_pdf_bytes(pages: list[str])` (valid 1–2 page PDF built programmatically with computed xref offsets — no committed binary, deterministic), `docx_bytes(paragraphs: list[str], tables: list[list[list[str]]])` (via `Document()` → `add_paragraph`/`add_table` → `BytesIO`), `encrypted_pdf_bytes()` (via `PdfWriter` + `.encrypt("pw")`), `blank_pdf_bytes()` (via `PdfWriter` blank page). (2) In `test_bad_suffixes_and_missing_filenames_raise`, REMOVE `"doc.pdf", "doc.docx"` from the bad list (they are valid now) and ADD a still-unsupported suffix (e.g. `"sheet.xls"`) so the test keeps covering bad suffixes. (3) ADD tests importing the builders from `tests.upload_fixtures`: pdf extracts text + `origin{"adapter":"pdf","pages":"1","suffix":".pdf"}` + title-from-stem; 2-page pdf joins with blank line + `pages=="2"`; uppercase `.PDF`/`.DOCX` adapt (suffix.lower rule); docx paragraphs + table rows (`" | "` join) extract; corrupt pdf bytes → `UnparseableUploadError`; corrupt docx bytes (`b"not a zip"`) → `UnparseableUploadError`; `.doc`-labeled-but-OLE bytes → `UnparseableUploadError`; encrypted pdf → `UnparseableUploadError`; blank-page pdf adapts with empty content (router blank-check owns the 400 — assert `adapted.content == ""` here, assert 400 at API level).
- **PATTERN**: Adapter tests — `backend/tests/test_adapters.py:15-59` (no I/O, pure function asserts)
- **IMPORTS**: `from tests.upload_fixtures import blank_pdf_bytes, docx_bytes, encrypted_pdf_bytes, minimal_pdf_bytes`, `UnparseableUploadError`. `pyproject.toml:40-42` sets `pythonpath=["."]` — verify `from tests.upload_fixtures import ...` resolves; if it does not, CREATE `backend/tests/__init__.py` (empty) and re-run. This check lives HERE (first creation/import of the module), so this task's validation passes in order.
- **GOTCHA**: If pypdf rejects the hand-built fixture, compute xref offsets programmatically (don't tweak magic numbers). Fixture builders live ONLY in `tests/upload_fixtures.py` — never duplicated into test modules.
- **VALIDATE**: `cd backend && uv run pytest tests/test_adapters.py -q`

### UPDATE backend/tests/test_ingest_api.py — replace pdf-rejection test + upload contract tests

- **IMPLEMENT**: (1) REPLACE `test_upload_pdf_is_400` with: `test_upload_pdf_returns_201_with_pages` (upload generated 2-page pdf via `files={"file": ("doc.pdf", pdf_bytes, "application/pdf")}` → 201, `extracted_chars == len(content)`, `pages == 2`, artifact retrievable via `GET /artifacts/{id}` with `origin.adapter == "pdf"`); `test_upload_docx_returns_201_without_pages` (→ 201, `pages is None`, table text present in detail content); `test_upload_corrupt_pdf_is_400` (`b"%PDF-1.4 garbage"` → 400, persists nothing — assert `GET /artifacts` == []); `test_upload_corrupt_docx_is_400`; `test_upload_blank_pdf_is_400` (blank-page pdf → 400). Reuse `_client`/`_stub` fixtures; import ALL fixture builders from `tests.upload_fixtures` (created in the previous task — the single committed location). (2) ADD `test_upload_pdf_over_char_cap_is_413` (`MAX_ARTIFACT_CHARS` tiny → pdf with more extracted chars → 413, persists nothing) proving the pipeline cap applies to extracted text. (3) ADD `test_upload_txt_pages_is_none`: upload a small `.txt` file → 201 and assert `body["pages"] is None`. (Existing `test_upload_txt_returns_201_with_extracted_chars` stays untouched as the regression anchor; the new test owns the `pages`-null assertion.)
- **PATTERN**: Upload contract tests + stub seam — `backend/tests/test_ingest_api.py:19-55,123-184`
- **IMPORTS**: `from tests.upload_fixtures import blank_pdf_bytes, docx_bytes, minimal_pdf_bytes` (module created + importability settled in the previous task — reuse as-is).
- **GOTCHA**: `files={"file": (name, bytes, mime)}` TestClient form; assert `GET /artifacts == []` on every rejection-path test (persists-nothing invariant, mirror `test_oversized_upload_persists_nothing`).
- **VALIDATE**: `cd backend && uv run pytest tests/test_ingest_api.py tests/test_adapters.py -q`

### UPDATE docs — fix stale upload-type mentions if present

- **IMPLEMENT**: Grep `backend/README.md`, `README.md`, `frontend/` for `.txt`/`.md`-only upload claims and `UploadCreated`/`extracted_chars` shapes; update any that enumerate supported types to include `.pdf`/`.docx` (+ `pages?` for pdf). If none exist, no-op with evidence.
- **PATTERN**: None (docs hygiene)
- **IMPORTS**: None
- **GOTCHA**: `.env.example` already covers pdf/docx caps ("plus .pdf/.docx when those Preferred adapters land") — do NOT touch it. Do not invent new docs.
- **VALIDATE**: `grep -rn "txt.*md\|extracted_chars" backend/README.md README.md frontend/src 2>/dev/null | grep -v node_modules; echo "grep done"`

---

## TESTING STRATEGY

Follows AGENTS.md Testing: deterministic behavior gets unit tests; no LLM-touching paths here (pure extraction + existing pipeline), so no contract/stub-model tests needed beyond the existing fake-embed seam.

### Unit Tests

`tests/test_adapters.py` (extend): suffix routing incl. uppercase; pdf text + page-count origin; multi-page join; docx paragraphs + tables; corrupt/encrypted/blank inputs → `UnparseableUploadError` / empty content. Fixtures generated in-code (programmatic minimal PDF, python-docx-built docx, pypdf-built encrypted/blank PDFs) — no binary blobs in the repo. Mirror existing style: pure-function asserts, no I/O.

### Integration Tests

`tests/test_ingest_api.py` (extend): full upload round-trips through TestClient + REAL pipeline/repository with fake vectors (existing `_stub` seam): 201 shapes for pdf (`pages: 2`) and docx (`pages: null`), `extracted_chars` correctness, detail round-trip shows extracted content + origin, rejection paths (corrupt/blank/over-cap) return 400/413 AND persist nothing. Existing txt/md tests are the regression anchor and must pass untouched (except the two rejection-behavior updates named above).

### Edge Cases

- Uppercase suffixes (`.PDF`, `.DOCX`) → adapt (suffix.lower rule)
- Corrupt bytes with pdf/docx names → 400, nothing persisted
- Legacy `.doc` (OLE) bytes named `.docx` → 400 with "legacy .doc" hint
- Encrypted PDF → 400 "encrypted PDFs are not supported"
- Image-only/scanned PDF (extract → blank) → 400 "file content blank" via existing check (no OCR — scope boundary, tested as refusal)
- Empty/whitespace-only docx → 400 blank
- Large PDF whose EXTRACTED TEXT exceeds `MAX_ARTIFACT_CHARS` → 413 (byte cap passed, char cap catches) + persists nothing
- PDF with 0 extractable pages / weird `extract_text() → None` → blank → 400, never 500
- Parser exceptions of ANY type raised at construction or mid-iteration (malformed page objects during `extract_text()`, corrupt paragraph/table traversal surfacing as `KeyError`/`TypeError`/`AttributeError`/etc.) → `UnparseableUploadError` → 400: the adapter wraps construction AND iteration in one try with a broad `except Exception` (after re-raising `UnparseableUploadError`), so no parser exception type can escape to the router as a 500
- `pages` omitted (null) for txt/md/docx responses; present for pdf

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

Every command or block MUST state its exact pass signal on an `Expected:` line.

### Level 1: Syntax & Style

```bash
cd backend && uv run ruff check . && uv run ruff format --check .
```
Expected: exit 0, "All checks passed!" + "N files left unchanged" (ruff prints per-command success; no error lines)

```bash
cd backend && uv run mypy app
```
Expected: exit 0, "Success: no issues found in N source files"

### Level 2: Unit Tests

```bash
cd backend && uv run pytest tests/test_adapters.py tests/test_ingest_api.py tests/test_ingest_pipeline.py -q
```
Expected: exit 0, "NN passed" (no failures; exact count = 6 existing adapter tests − 0 removed + ~10 new + all API tests incl. ~6 new − 1 replaced)

```bash
cd backend && uv run pytest -q
```
Expected: exit 0, all tests pass (full suite, no regressions; count printed, zero "failed"/"error")

### Level 3: Integration Tests

Covered by the TestClient suite in Level 2 (the repo's integration mechanism per AGENTS.md — in-process TestClient over tmp DBs with the real pipeline; local Uvicorn cannot run in sandbox). No separate command; the upload round-trip + persists-nothing tests ARE the integration coverage.

```bash
cd backend && uv run pytest tests/test_ingest_api.py -q -k "upload"
```
Expected: exit 0, all upload tests pass (txt/md/pdf/docx + caps + rejection paths)

### Level 4: Manual Validation

Performer: `agent` (executable in this environment via TestClient + scratch DB — the AGENTS.md equivalent procedure; no live server).

1. Agent runs a scratch-DB TestClient script from /tmp (NOT committed): build a 2-page PDF + a docx with a table via the same builders as `tests/upload_fixtures.py`, upload each through `POST /api/v1/artifacts/upload` with the REAL `ingest_source` + fake embed_fn, then `GET /artifacts/{id}` for each.
   - Expected: pdf → 201 `{"artifact_id": <32-hex>, "chunks": ≥1, "extracted_chars": N>0, "pages": 2}`; docx → 201 with `"pages": null`; detail contents contain the fixture sentences and table row text; origin shows `"adapter": "pdf"/"docx"`.
2. Agent uploads `b"not a pdf at all"` as `evil.pdf` and a `PdfWriter`-encrypted PDF through the same script.
   - Expected: both → 400 with `detail` naming the problem ("not a readable PDF" / "encrypted PDFs are not supported"); `GET /artifacts` shows only the 2 good artifacts (rejections persist nothing).

Performer: `human` — none. No UI, device, account, or judgment step exists for this deliverable (upload is API-only; Capture view remains a stub).

### Level 5: Additional Validation (Optional)

None. No MCP/browser flow applies (no frontend change; redeploy explicitly out of scope).

---

## MANUAL VERIFICATION CHECKLIST

- [ ] [agent] Upload round-trip: run the Level 4 script (steps above); expected: pdf 201 with pages=2, docx 201 with pages=null, detail contents + origins correct
- [ ] [agent] Rejection paths: run corrupt/encrypted uploads (steps above); expected: 400s with explanatory details, artifact list unchanged
- [ ] [agent] Dep sync: compare pyproject deps vs modal_app.py pip list (Task-validated command); expected: sets match, both include pypdf + python-docx
- [ ] [agent] Docs reflection: re-run the Task 8 grep; expected: no remaining ".txt/.md only" upload claim, or written confirmation none existed

## ROLLBACK CONSIDERATIONS

- Revert is a clean `git revert`: changes are additive (new branches, new error type, new optional response field, new deps). No migrations, no schema change, no data rewrite — artifacts ingested from pdf/docx remain ordinary `source_type="file"` rows readable without the new code.
- Removing the deps requires `uv sync` to rewrite `uv.lock` again; Modal image reverts with the file.
- The two updated rejection tests revert with the code (they encode new behavior).

## ACCEPTANCE CRITERIA

- [ ] `.pdf` upload returns 201 with `extracted_chars` + `pages` = page count (L2: `test_upload_pdf_returns_201_with_pages`; L4 agent script step 1)
- [ ] `.docx` upload returns 201 with `extracted_chars`, `pages` null, paragraph + table text in stored content (L2: `test_upload_docx_returns_201_without_pages`; L4 agent script step 1)
- [ ] Corrupt pdf/docx, encrypted pdf, and blank-extraction uploads return 400 and persist nothing (L2: new 400 tests; L4 agent script step 2)
- [ ] Extracted text over `MAX_ARTIFACT_CHARS` returns 413 and persists nothing (L2: `test_upload_pdf_over_char_cap_is_413`)
- [ ] `.txt`/`.md` uploads behave exactly as before incl. `pages: null` (L2/L3: existing upload tests pass unmodified; new `test_upload_txt_pages_is_none` asserts `pages is None`)
- [ ] `pypdf` + `python-docx` in `pyproject.toml`, `uv.lock`, and `modal_app.py` pip list (Manual checklist dep-sync item)
- [ ] All validation commands pass with zero errors (L1 ruff + mypy, L2 full `pytest`)
- [ ] No test-coverage threshold is stated in AGENTS.md/CLAUDE.md — note as not-applicable; new branches (pdf/docx/error paths) each have a dedicated test
- [ ] Code follows project conventions: thin router, `ValueError` adapter errors → 400, origin-dict metadata, `snake_case` (review during execute; L1 gates)
- [ ] No regressions: full suite green (L2 full `pytest`)

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

- **Design decision — `pages` via `origin`, not a new `AdaptedSource` field:** `origin` is already the adapter-specific metadata channel (`suffix`, `content_type`); adding one more key keeps `AdaptedSource`'s 4-field shape stable for the future `tb_conversation` adapter. Router converts `str → int` at the boundary.
- **Design decision — docx tables appended after paragraphs:** true document-order interleaving requires walking the OOXML body; paragraphs-then-tables is cheap, deterministic, and sufficient for search/extraction. Documented in code comment.
- **Design decision — shared `tests/upload_fixtures.py` (committed location):** all PDF/DOCX builders live here, imported by both test modules; avoids private cross-test imports and duplication. The adapter-test task (first to create/import it) verifies the `tests.` import resolves and creates an empty `tests/__init__.py` only if required.
- **Why the two existing tests MUST change:** `test_bad_suffixes_and_missing_filenames_raise` and `test_upload_pdf_is_400` encode the pre-deliverable contract (pdf/docx unsupported). This deliverable's explicit scope is to support them, so updating these assertions IS the requirement — not a regression. Flagged here so review doesn't misread the diff.
- **Security notes:** byte cap runs before parsing (DoS bound); char cap runs on extracted text (zip-bomb/decompression-bomb bound); extracted content is untrusted data under the existing prompt-injection discipline (adapters never build prompts — unchanged). `pip audit` for the new deps is a Phase 4 submission-gate item, not this plan.
- **Trade-off — no `tests/__init__.py` unless needed:** pytest rootdir imports vary; the adapter-test task decides empirically (see its IMPORTS line).
- **Out-of-scope reminders for the executor:** no OCR (scanned PDF → 400 blank is the specified behavior); no `.doc`; no headers/footers; no frontend; no redeploy.

---

## Revision History

### Cycle 1

Addressed all 5 findings from the first independent review (`.agents/plans/reviews/pdf-word-upload-adapters-plan-review.md`):

1. "Parse errors are caught only at PdfReader/Document construction, so malformed content raising during page.extract_text() or table/paragraph iteration would 500" — Rewrote the adapters task so `_adapt_pdf`/`_adapt_docx` wrap construction AND iteration in one try mapping to `UnparseableUploadError` (with `except UnparseableUploadError: raise` first so the encrypted-PDF raise passes through), added the `decrypt("")` falsy-return note, the `BadZipFile` import, the never-500 GUARANTEE line, and a matching Edge Cases bullet.
2. "The plan says no new files, yet Task 7 decides to create tests/upload_fixtures.py ... leaves undecided deliberations and a wrong 'Task 8 GOTCHA' reference" — Committed to `tests/upload_fixtures.py` as the single fixture location: listed it (+ conditional `tests/__init__.py`) under New Files, made the adapter-test task CREATE it and the API-test task import from it, deleted all deliberation passages, and updated the Notes design-decision entry.
3. "Fix the Assumptions line's undecided Modal validation wording and its incorrect 'Task 8 GOTCHA' reference" — Rewrote the Modal assumption decisively (list comparison in the Modal sync task) with a correct task reference.
4. "The criterion 'txt/md uploads incl. pages: null' cites existing tests, but the plan explicitly declines to add any pages-is-None assertion" — Added `test_upload_txt_pages_is_none` to the API-test task and referenced it in the acceptance criterion.
5. "The dep-sync command strips versions/extras only on the modal side and splits pyproject on the first ']'" — Replaced with a tomllib-based pyproject parse + normalized both-side comparison against the modal `pip_install` block, with an explicit Expected pass signal (exit 0, `dep sync ok: [...]`, AssertionError on mismatch).

Not done: nothing — all 5 corrections applied. Limitation: the replacement dep-sync one-liner is long and was not executed (correction step runs no commands); the executor's Task validation run is its first execution.

### Cycle 2

Addressed all 3 residual findings from the second independent review (rewritten review file, same path):

1. "The rewritten dep-sync one-liner builds `{list}`, a set containing a list, so it raises TypeError: unhashable type before any comparison runs" — Replaced `py={tomllib.load(...)['project']['dependencies']}` + `list(py)[0]` with a direct `deps=tomllib.load(...)['project']['dependencies']` binding and `pyns={norm(d) for d in deps}`; modal-side parse and Expected line unchanged.
2. "The never-500 guarantee is contradicted by catch tuples limited to PdfReadError/ValueError and PackageNotFoundError/BadZipFile/ValueError, while malformed files can raise KeyError, TypeError, AttributeError" — Switched both adapter try/excepts to `except UnparseableUploadError: raise` + broad `except Exception` with `# noqa: BLE001` and a design rationale comment (repo enables BLE001 — precedent: `modal_app.py` blind catch); dropped the parser exception imports from the task IMPORTS; updated the GUARANTEE line, Edge Cases bullet, and Relevant Documentation entries to match.
3. "The test_adapters task imports `tests.upload_fixtures`, but whether `tests/__init__.py` is needed is only decided in the later API-test task" — Moved the import-resolution check + conditional `__init__.py` creation into the adapter-test task's IMPORTS line; updated the New Files entry, Notes design-decision + trade-off lines, and the API-test task IMPORTS (now reuses as-is).

Not done: nothing — all 3 corrections applied. Limitation: as in Cycle 1, no commands were executed during correction; the fixed one-liner's first execution is the executor's Task validation run.
