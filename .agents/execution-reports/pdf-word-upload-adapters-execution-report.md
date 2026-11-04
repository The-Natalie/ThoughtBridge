# Execution Report: pdf-word-upload-adapters

Plan: `.agents/plans/pdf-word-upload-adapters.md`
Review: `.agents/plans/reviews/pdf-word-upload-adapters-plan-review.md` (Overall: ✅ APPROVED)
Started: 2026-11-04

This report records every command run, every line of output, every validation
result exactly as printed, and every deviation or issue encountered.

---

## Plan tasks

### Task 1: ADD backend/pyproject.toml — declare pypdf + python-docx

Edit: added `"pypdf"` and `"python-docx"` to `[project] dependencies`
between `pydantic-settings` and `sqlite-vec` (unpinned; `uv.lock` pins).

Validation command:

```
$ cd backend && uv sync && uv run python -c "import pypdf, docx; print(pypdf.__version__)"
```

First attempt output (exit 2 — sandbox blocked the default uv cache):

```
error: Failed to initialize cache at `/Users/natalie/.cache/uv`
  Caused by: failed to open file `/Users/natalie/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)
```

Deviation 1: all `uv` invocations in this execution run with
`UV_CACHE_DIR=/tmp/uv-cache` (cache redirect only; same resolver, same
lockfile, venv still at `backend/.venv`). Retried command:

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv sync && UV_CACHE_DIR=/tmp/uv-cache uv run python -c "import pypdf, docx; print(pypdf.__version__)"
```

Output (exit 0):

```
Resolved 112 packages in 1.52s
Downloading lxml (8.2MiB)
 Downloaded lxml
Prepared 3 packages in 997ms
Installed 3 packages in 15ms
 + lxml==6.1.3
 + pypdf==6.21.4
 + python-docx==1.2.0
6.21.4
```

API-name verification (plan Phase 1 / Task 4 IMPORTS requirement):

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run python -c "
from io import BytesIO
from pypdf import PdfReader, PdfWriter
from docx import Document
w = PdfWriter(); w.add_blank_page(100, 100)
buf = BytesIO(); w.write(buf)
r = PdfReader(BytesIO(buf.getvalue()))
print('pages:', len(r.pages), 'encrypted:', r.is_encrypted, 'text:', repr(r.pages[0].extract_text()))
d = Document(); d.add_paragraph('hi'); print('docx ok:', [p.text for p in d.paragraphs], 'tables:', len(d.tables))
"
```

Output (exit 0):

```
pages: 1 encrypted: False text: ''
docx ok: ['hi'] tables: 0
```

Task 1 result: PASS. `uv.lock` updated by `uv` (not hand-edited).
Installed: pypdf==6.21.4, python-docx==1.2.0, lxml==6.1.3 (docx dependency).

### Task 2: UPDATE backend/modal_app.py — sync deploy image deps

Edit: added `"pypdf"` and `"python-docx"` to the `.pip_install(...)`
list in the same position as pyproject. Nothing else changed.

Validation command:

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run python -c "import tomllib, re; deps=tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']; norm=lambda s: re.split(r'[<>=!~\[;\s]', s.strip().lower().replace('_','-'))[0]; pyns={norm(d) for d in deps}; mo=set(re.findall(r'\"([A-Za-z0-9_.\-\[\]>=<~!,\s]+)\"', open('modal_app.py').read().split('.pip_install(')[1].split(')')[0])); mons={norm(d) for d in mo}; assert pyns==mons, (pyns^mons); print('dep sync ok:', sorted(pyns))"
```

Output (exit 0):

```
dep sync ok: ['aiofiles', 'fastapi', 'fastembed', 'httpx', 'pydantic', 'pydantic-settings', 'pypdf', 'python-docx', 'python-multipart', 'sqlite-vec']
```

Task 2 result: PASS. (Command run with the Deviation 1
`UV_CACHE_DIR` prefix; comparison logic exactly as planned.)

### Task 3: ADD backend/app/api/ingest.py — optional pages on UploadCreated

Edits: added `pages: int | None = None` to `UploadCreated`; router
returns `pages=int(adapted.origin["pages"]) if "pages" in
adapted.origin else None`. No other router logic changed.

Validation command:

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run ruff check app/api/ingest.py && UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check app/api/ingest.py
```

Output (exit 0):

```
All checks passed!
1 file already formatted
```

Task 3 result: PASS.

### Task 4: ADD backend/app/ingest/adapters.py — pdf/docx extraction + UnparseableUploadError

Edits: new `UnparseableUploadError(ValueError)`; `ALLOWED_UPLOAD_SUFFIXES`
+ `.pdf`/`.docx`; `_adapt_pdf` (whole-body try: `PdfReader(BytesIO)`,
empty-password decrypt attempt, per-page `extract_text() or ""`,
`"\n\n"`-join of non-blank pages, `origin["pages"]`) and `_adapt_docx`
(paragraphs + `" | "`-joined table rows, `"\n"`-join, no `pages`);
`adapt_upload` dispatches on suffix; txt/md path unchanged.

Validation command:

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run python -c "from app.ingest.adapters import adapt_upload, UnparseableUploadError; print('imports ok')"
```

Output (exit 0):

```
imports ok
```

Task 4 result: PASS.

### Task 5: UPDATE backend/app/api/ingest.py — map UnparseableUploadError to 400

Edits: imported `UnparseableUploadError` in the router; added it to the
400 `except` tuple in `upload_artifact`; docstring →
"Ingest a `.txt`/`.md`/`.pdf`/`.docx` file upload as a new artifact";
re-exported via `pipeline.py` (`__all__` + import, multi-line to match
ruff format).

Validation command (with Deviation 1 prefix):

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run ruff check app/ && UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check app/ && UV_CACHE_DIR=/tmp/uv-cache uv run mypy app
```

First attempt output (exit 1):

```
RUF100 [*] Unused `noqa` directive (unused: `BLE001`)
  --> app/ingest/adapters.py:75:31
   |
73 |     except UnparseableUploadError:
74 |         raise
75 |     except Exception as exc:  # noqa: BLE001 — parsers raise KeyError/TypeError/AttributeError/etc. on malformed input; all map to 400…
   |                               ^^^^^^^^^^^^^^
76 |         raise UnparseableUploadError("upload is not a readable PDF") from exc
...
RUF100 [*] Unused `noqa` directive (unused: `BLE001`)
   --> app/ingest/adapters.py:105:31
...
Found 2 errors.
[*] 2 fixable with `--fix`.
```

(full 2-file output quoted verbatim in substance; both hits are the
`# noqa: BLE001` directives added per the plan.)

Deviation 2: the plan's `# noqa: BLE001` (with and without trailing
prose — both forms tried) is RUF100-unused in this repo. Diagnosis:
`ruff check modal_app.py` → "All checks passed!" (its logging-only
handler's bare noqa stands), so BLE001 is evaluated but exempts
handlers that re-raise — both new handlers end in
`raise ... from exc`, making any BLE001 noqa unused. Fix: removed both
noqa directives, kept the design rationale as plain comments. The broad
`except Exception` itself is unchanged.

Re-run output (exit 0):

```
All checks passed!
34 files already formatted
Success: no issues found in 34 source files
```

Task 5 result: PASS (via Deviation 2 for the noqa form).

### Task 6: UPDATE backend/tests/test_adapters.py — pdf/docx now valid + new adapter tests

Edits: CREATED `backend/tests/upload_fixtures.py` (`minimal_pdf_bytes`,
`docx_bytes`, `encrypted_pdf_bytes`, `blank_pdf_bytes`); updated
`test_bad_suffixes_and_missing_filenames_raise` (pdf/docx removed from
the bad list, `sheet.xls`/`slides.pptx` added); added 9 tests (pdf
extract + origin, multi-page join, uppercase suffixes, docx
paragraphs+tables, corrupt pdf/docx, OLE-as-docx, encrypted pdf,
blank-page pdf).

Import check: `from tests.upload_fixtures import ...` resolves WITHOUT
`tests/__init__.py` (namespace packages via `pythonpath=["."]`), so no
`__init__.py` was created — decided empirically per the plan.

Validation command:

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_adapters.py -q
```

Output (exit 0):

```
................                                                         [100%]
16 passed in 0.26s
```

Task 6 result: PASS (7 pre-existing incl. 1 updated + 9 new).

### Task 7: UPDATE backend/tests/test_ingest_api.py — replace pdf-rejection test + upload contract tests

Edits: REPLACED `test_upload_pdf_is_400` with
`test_upload_pdf_returns_201_with_pages` (201, `extracted_chars`,
`pages == 2`, detail round-trip incl. origin), and ADDED
`test_upload_docx_returns_201_without_pages` (`pages is None`, table
text), `test_upload_corrupt_pdf_is_400`, `test_upload_corrupt_docx_is_400`,
`test_upload_blank_pdf_is_400` (each asserting the detail message +
persists-nothing), `test_upload_pdf_over_char_cap_is_413`, and
`test_upload_txt_pages_is_none`. Fixture imports are top-level
(`from tests.upload_fixtures import ...`), matching repo test
convention. `test_upload_txt_returns_201_with_extracted_chars`
untouched.

Validation command:

```
$ cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_ingest_api.py tests/test_adapters.py -q
```

Output (exit 0):

```
..........................................                               [100%]
42 passed in 1.64s
```

Task 7 result: PASS (16 adapter + 26 API: 19 pre-existing incl.
1 replaced + 7 new).

### Task 8: UPDATE docs — fix stale upload-type mentions if present

Validation command:

```
$ grep -rn "txt.*md\|extracted_chars" backend/README.md README.md frontend/src 2>/dev/null | grep -v node_modules; echo "grep done"
```

Output (exit 0):

```
grep done
```

No matches. Verified not a false no-op: all three paths exist, and a
broader `grep -rln "upload"` over the same paths hits only:

```
frontend/src/App.tsx:9:  { id: 'capture', label: 'Capture', blurb: 'Capture view — coming in Phase 1.3 (notes, pastes, uploads).' },
```

which enumerates no file types (Capture stub blurb) — nothing stale.
`.env.example` untouched per the plan's GOTCHA.

Task 8 result: PASS (no-op with evidence).

---

## Validation

All commands run from `backend/` with the Deviation 1 `UV_CACHE_DIR`
prefix (omitted below for brevity except where first shown; every `uv`
invocation in this execution used it).

### Level 1: Syntax & Style

```
$ uv run ruff check . && uv run ruff format --check .
```

First attempt output (exit 1): `ruff check` → "All checks passed!";
`ruff format --check` → 2 files would be reformatted
(`tests/test_ingest_api.py`, `tests/upload_fixtures.py` — my new test
code). Fixed with `uv run ruff format` on those two files (repo
convention; formatter applied to new code only, no hand-formatting
games).

Re-run output (exit 0):

```
2 files reformatted
All checks passed!
62 files already formatted
```

```
$ uv run mypy app
```

Output (exit 0):

```
Success: no issues found in 34 source files
```

Level 1 result: PASS.

### Level 2: Unit Tests

```
$ uv run pytest tests/test_adapters.py tests/test_ingest_api.py tests/test_ingest_pipeline.py -q
```

Output (exit 0):

```
....................................................s                    [100%]
52 passed, 1 skipped in 1.69s
```

(The 1 skip is pre-existing in `tests/test_ingest_pipeline.py`, outside
this deliverable; my two files show 0 skipped — Task 7 output "42
passed" with no skip.)

```
$ uv run pytest -q
```

Output (exit 0):

```
........................................................................ [ 18%]
........................................................................ [ 36%]
..........................s............................................. [ 54%]
........................................................................ [ 73%]
.........................s.............................................. [ 91%]
..................................                                       [100%]
392 passed, 2 skipped in 10.09s
```

Level 2 result: PASS (392 passed, 2 pre-existing skips outside this
deliverable's files).

### Level 3: Integration Tests

```
$ uv run pytest tests/test_ingest_api.py -q -k "upload"
```

Output (exit 0):

```
............                                                             [100%]
12 passed, 14 deselected in 0.92s
```

Level 3 result: PASS (12 upload tests: txt/md/pdf/docx + caps +
rejection paths).

### Level 4: Manual Validation (agent)

Script: `/tmp/l4_pdf_docx_check.py` (NOT committed; TestClient over a
scratch DB at a fresh `mkdtemp`, real pipeline + fake vectors via the
test-suite stub pattern).

```
$ cd backend && PYTHONPATH=. UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync python /tmp/l4_pdf_docx_check.py
```

Output (exit 0):

```
2026-11-04 03:15:54.281 Python[46234:15199474] 2026-11-04 03:15:54.281260 [W:onnxruntime:Default, telemetry_1ds.cc:600 operator()] Failed to persist telemetry device ID; using an in-memory identifier
invalid pdf header: b'not a'
EOF marker not found
upload rejected: upload is not a readable PDF
upload rejected: encrypted PDFs are not supported
pdf: 201 {'artifact_id': '5764a66588df4a1c837b944d952a5ba7', 'chunks': 1, 'extracted_chars': 17, 'pages': 2}
pdf detail content: 'L4 alpha\n\nL4 beta'
pdf detail origin: {'adapter': 'pdf', 'content_type': 'application/pdf', 'filename': 'l4.pdf', 'pages': '2', 'suffix': '.pdf'}
docx: 201 {'artifact_id': '11e01a6bff6847488a2b9b2248b71e9a', 'chunks': 1, 'extracted_chars': 15, 'pages': None}
docx detail content: 'L4 para\nc1 | c2'
docx detail origin: {'adapter': 'docx', 'content_type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'filename': 'l4.docx', 'suffix': '.docx'}
corrupt: 400 {'detail': 'upload is not a readable PDF'}
encrypted: 400 {'detail': 'encrypted PDFs are not supported'}
artifacts: [('5764a665', 'l4', 1), ('11e01a6b', 'l4', 1)]
scratch db: /var/folders/j4/7vlzcfqj1cg9ppspqr8vh6h00000gn/T/l4-pdf-docx-lk8bhgq4/l4.db
```

(Stderr noise is expected: onnxruntime telemetry warning from the
fastembed import, pypdf's own corrupt-input warnings, and the router's
`logger.warning` rejection lines — all handled, none fatal.)

Level 4 step 1: PASS (pdf 201 pages=2 with exact content/origin; docx
201 pages=null with paragraph + table-row content).
Level 4 step 2: PASS (corrupt + encrypted → 400 with explanatory
details; artifact list holds only the 2 good uploads).

No `human` steps exist for this deliverable (plan: upload is API-only).

### Level 5: Additional Validation

NOT_PERFORMED (none applies — no frontend change; redeploy explicitly
out of scope per the plan).

### Manual verification checklist (from plan)

- [x] [agent] Upload round-trip — L4 step 1 output above: pdf 201
  pages=2, docx 201 pages=null, detail contents + origins correct.
- [x] [agent] Rejection paths — L4 step 2 output above: 400s with
  explanatory details, artifact list unchanged (2 good only).
- [x] [agent] Dep sync — Task 2 output: `dep sync ok: [..., 'pypdf',
  'python-docx', ...]`, pyproject/modal sets match.
- [x] [agent] Docs reflection — Task 8 grep: no remaining ".txt/.md
  only" upload claim (only the typeless Capture stub blurb).

### Changed files (`git status --short`, `git diff --stat`)

```
M backend/app/api/ingest.py
M backend/app/ingest/adapters.py
M backend/app/ingest/pipeline.py
M backend/modal_app.py
M backend/pyproject.toml
M backend/tests/test_adapters.py
M backend/tests/test_ingest_api.py
M backend/uv.lock
?? backend/tests/upload_fixtures.py
```

(Plus the untracked plan, review, and this report under `.agents/`.)
8 files changed, 321 insertions(+), 8 deletions(-). No collateral:
`uv.lock` (+52 lines for pypdf/python-docx/lxml) written by `uv` only.

---

## Evidence Map

- `.pdf` upload returns 201 with `extracted_chars` + `pages` = page count → VERIFIED: L2 `test_upload_pdf_returns_201_with_pages` passed (in the 42-test Task 7 run and the 392-test full run); L4 script: `pdf: 201 {... 'extracted_chars': 17, 'pages': 2}` + detail content/origin match.
- `.docx` upload returns 201 with `extracted_chars`, `pages` null, paragraph + table text in stored content → VERIFIED: L2 `test_upload_docx_returns_201_without_pages` passed; L4 script: `docx: 201 {... 'extracted_chars': 15, 'pages': None}`, detail `'L4 para\nc1 | c2'`.
- Corrupt pdf/docx, encrypted pdf, and blank-extraction uploads return 400 and persist nothing → VERIFIED: L2 `test_upload_corrupt_pdf_is_400`, `test_upload_corrupt_docx_is_400`, `test_upload_blank_pdf_is_400` passed (each asserting message + empty artifact list); adapter-level encrypted/OLE tests passed; L4 script: `corrupt: 400`, `encrypted: 400`, artifacts list unchanged (2 good only).
- Extracted text over `MAX_ARTIFACT_CHARS` returns 413 and persists nothing → VERIFIED: L2 `test_upload_pdf_over_char_cap_is_413` passed.
- `.txt`/`.md` uploads behave exactly as before incl. `pages: null` → VERIFIED: pre-existing txt/md upload tests passed unmodified in the full 392-test run; new `test_upload_txt_pages_is_none` (`pages is None`) passed.
- `pypdf` + `python-docx` in `pyproject.toml`, `uv.lock`, and `modal_app.py` pip list → VERIFIED: Task 2 dep-sync check `dep sync ok: [... 'pypdf', 'python-docx', ...]` (tomllib parse + normalized both-side comparison, exit 0); Task 1 installed pypdf==6.21.4, python-docx==1.2.0 via `uv sync` (lock written by uv).
- All validation commands pass with zero errors → VERIFIED: L1 ruff check + format-check + mypy outputs above (exit 0); L2 full `pytest` 392 passed (exit 0).
- No test-coverage threshold stated; new branches each have a dedicated test → VERIFIED (not-applicable noted): AGENTS.md/CLAUDE.md state no threshold; pdf/docx/error/blank/encrypted/uppercase/0-cap paths each have ≥1 dedicated test (9 new adapter + 7 new API tests).
- Code follows project conventions → VERIFIED: thin router (2-line response addition + 1 except-tuple entry), `ValueError` adapter errors → 400, origin-dict metadata, `snake_case`; L1 gates green.
- No regressions: full suite green → VERIFIED: `uv run pytest -q` → 392 passed, 2 skipped (both skips pre-existing, outside this deliverable's files), 0 failed.

## Ready for Commit

- [x] All tasks completed
- [x] All validation commands passed
- [x] All tests passing
- [x] Evidence Map complete: every acceptance criterion has a status; PARTIALLY VERIFIED, UNVERIFIED, and FAILED items (if any) are named in the one-line status and detailed under Follow-up Items

## Follow-up Items

- Deviation 1: `UV_CACHE_DIR=/tmp/uv-cache` prefix on all `uv` invocations (sandbox blocks `~/.cache/uv` writes). Same resolver/lockfile/venv; no behavioral impact.
- Deviation 2: plan-specified `# noqa: BLE001` removed — RUF100-flagged as unused because BLE001 exempts re-raising handlers (verified: `ruff check modal_app.py` passes with its logging-only handler's noqa). Broad `except Exception` unchanged; rationale kept as plain comments.
- Formatting: `ruff format` applied to the two new/edited test files during L1 (repo convention; new code only).
- `pip audit` for the new deps stays a Phase 4 submission-gate item per the plan's security notes — not run here.
- No redeploy performed (out of scope per plan — no browser-verifiable change). Next Modal deploy picks up pypdf + python-docx via the synced pip list.
- L4 stderr noise (onnxruntime telemetry warning, pypdf corrupt-input warnings) is expected library chatter, not a defect.

---

## Follow-up Validation (cycle 1)

Reviewer finding (first independent execution review, Overall
NOT_VERIFIED): "`backend/app/ingest/pipeline.py`: Re-export of
UnparseableUploadError was reported but not directly evidenced." All 16
validation checks passed; this was the sole gap. No code fix required —
direct evidence produced below.

Command (run from `backend/`):

```
$ grep -n "UnparseableUploadError" app/ingest/pipeline.py && UV_CACHE_DIR=/tmp/uv-cache uv run python -c "from app.ingest.pipeline import UnparseableUploadError; from app.ingest.adapters import UnparseableUploadError as A; print('re-export ok:', UnparseableUploadError is A)"
```

Output (exit 0):

```
22:    UnparseableUploadError,
34:    "UnparseableUploadError",
2026-11-04 03:20:04.606 Python[46631:15203825] 2026-11-04 03:20:04.606733 [W:onnxruntime:Default, telemetry_1ds.cc:600 operator()] Failed to persist telemetry device ID; using an in-memory identifier
re-export ok: True
```

(The onnxruntime line is the known telemetry stderr noise from the
fastembed import, also seen in L4.)

Evidence: `pipeline.py` line 22 imports `UnparseableUploadError` from
`app.ingest.adapters`, line 34 lists it in `__all__`, and the runtime
import check confirms the re-exported symbol IS the adapter's object
(`is` → True). No files modified in this cycle; no re-validation suite
needed (evidence-only, zero code impact).


