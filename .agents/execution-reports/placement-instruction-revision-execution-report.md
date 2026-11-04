# Execution Report: Placement Instruction Revision

Plan: inline proposal approved in conversation (revised Placement instruction + revised example, both APPROVED; no plan file — one-string prompt change).
Report: `.agents/execution-reports/placement-instruction-revision-execution-report.md`
Started: 2026-11-04

Scope: replace the stage C `placement` instruction in `backend/app/core/grounding.py` with the approved text. No other stages, no frontend changes, no commits. Limitations removal (prior turn) already deployed.

---

## Deviation 1: `UV_CACHE_DIR=/tmp/uv-cache` on all `uv run` commands

Same standing sandbox constraint as prior reports: the default uv cache is not writable, so every backend command runs as `export UV_CACHE_DIR=/tmp/uv-cache && uv run ...`.

## Task 1: UPDATE backend/app/core/grounding.py (stage C placement instruction)

Replaced the placement instruction (old: "explicitly reconnecting each familiar element ... e.g. 'instead of Rosa keeping watch ...' ... actual system") with the approved text (key distinction open, fidelity lock, Rosa exemplar reframed as "in the spirit of", selective coverage, technical system as subject, "actual process", verbatim closing constraints).

Verification of concatenated prompt text:

```
$ cd backend && export UV_CACHE_DIR=/tmp/uv-cache PYTHONPATH="$PWD" && uv run python -c "from app.core.grounding import STAGE_JSON_INSTRUCTIONS; ..."
{"placement": "<bring the lesson home: Mapping established individual correspondences; now reconnect those pieces into one coherent understanding of the real system. Walk through the real technical process ...
```

Result: PASS — rendered text matches the approved wording.

## Task 2: backend gates

```
$ cd backend && export UV_CACHE_DIR=/tmp/uv-cache && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest -q
All checks passed!
58 files already formatted
Success: no issues found in 33 source files
331 passed, 2 skipped in 7.06s
```

Result: PASS (exit 0).

## Task 3: live fresh lesson on scratch DB (real key, TestClient)

```
$ cd backend && export UV_CACHE_DIR=/tmp/uv-cache PYTHONPATH="$PWD" && uv run python /tmp/new_placement_check.py
content-type: text/event-stream; charset=utf-8
first_token=40.9s validated={'D': 42.9, 'F': 78.2, 'B': 137.9, 'C': 167.8} tokens=230 total=167.8s id=ecadd7712a094e77959f3311fa1c5a8e
persisted steps: ['analogy', 'definition', 'familiar_system', 'interview_ready', 'mapping', 'placement', 'walkthrough'] version=1
```

Result: PASS on generation (7 keys, placement present). See Deviation 2 for the probe's stale trailing assertion.

New placement (fresh, no reuse context) — one connected story, exactly one "Instead of", every claim faithful to Mapping:

> You ship one stylesheet for everything — phones, desktops, printers — the same way the manager keeps the same dining room all day and only changes the arrangement. ... Instead of the manager glancing at the door, the browser keeps checking the environment. ... Where she circles thirty on the clipboard, you pick a breakpoint ... And like watching the door without ever locking up, evaluation stays live ... If two true entries clash, house seniority still decides, which is why a match adds no specificity and keeps its normal spot in the cascade.

(Full text in session record; "becomes" appears 3x unpacking one mapping row — mild residue, reported to user.)

## Deviation 2: stale probe assertion (probe bug, not product bug)

`/tmp/new_placement_check.py` (derived from the pre-removal probe) ends with `assert sorted(detail["steps"].keys()) == [8 keys incl. "limitations"]` and failed with AssertionError after a successful generation. The persisted 7-key shape is the correct new contract; the probe was not updated because it is a throwaway. No product action.

## Task 4: deploy + browser E2E

```
$ cd backend && export UV_CACHE_DIR=/tmp/uv-cache && uv run modal deploy modal_app.py
✓ App deployed in 2.196s!
$ curl -s https://the-natalie--thoughtbridge-serve.us-east.modal.run/api/v1/health
{"status":"ok","db":true,"meta_api":true,"model":"muse-spark-1.3","db_error":null,"meta_error":null}
```

Playwright MCP against the deployed app: Learn → "CSS media queries" → immediate 7-tab pager → Definition streamed in-tab → completion (~110s, v3 1f626d14, reused_from ca65516d) → Placement tab renders → screenshot `learn-placement-v3.png` → console errors: 0.

Result: PASS on mechanics (7 tabs, stream, persist, 0 console errors). Quality finding below.

## Finding: reuse context re-introduces the old Placement pattern

The deployed v3 placement contains three consecutive "Instead of..." sentences plus a fourth later — the complained-about pattern. Evidence it is imitation of the reused prior lesson rather than the new instruction failing:

- v3 `reused_from` = ca65516d (old-pattern lesson whose own placement has the 3x chain).
- v3 placement mirrors the prior's phrasing ("cozy corner", "half-hall/full-hall plans", "falls short of the first line").
- Fresh scratch generation under the same new instruction produced one connected story with a single "Instead of".
- Mechanism: `render_memory_block` (`backend/app/llm/explainer.py:159`) emits `"Prior explanation that worked (JSON — reuse its analogy family):"` followed by the full prior steps JSON (`memory.py:160`, `explainer.py:167`). The model reuses the prior's style along with its analogy family.

No code change made for this finding — decision left to the user (options: accept for MVP, exclude prior placement from reuse context, reframe the memory note, or clear old demo-volume lessons).

## Files changed

- `backend/app/core/grounding.py` (stage C placement instruction only)

Nothing committed, per instruction.

---

## Addendum (2026-11-04): synthesis-first revision, user-accepted for MVP

Follow-up rounds revised the same single string twice more (orientation-first, then synthesis-first with familiar-concrete opening, synthesize-don't-reteach, required close, short conversational paragraphs). User approved the final instruction with two corrections (typo "anomaly"→"analogy" fixed; example-only "rules once" wording acknowledged).

Final verification:

```
$ cd backend && export UV_CACHE_DIR=/tmp/uv-cache && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest -q
All checks passed! / 58 files already formatted / Success: no issues found in 33 source files / 331 passed, 2 skipped
$ uv run modal deploy modal_app.py
✓ App deployed in 2.154s!
$ curl -s .../api/v1/health
{"status":"ok","db":true,"meta_api":true,"model":"muse-spark-1.3",...}
```

Fresh scratch-DB lesson (id 99f8420f...) showed the approved behavior: familiar-concrete opening, concept enters in-scene, single "Instead of", faithful correspondences; middle paragraph still dense (reported; user accepted as-is for MVP).

Playwright MCP E2E on deployed app: fresh "CSS media queries" generation → immediate 7-tab pager → Definition streamed in-tab → v4 completed and persisted → Placement tab renders → screenshot `learn-placement-v4.png` → console errors: 0. (v4 reused a prior lesson, so its placement shows the known reuse-imitation pattern documented above; reuse-context change on hold per user.)

Review gate: CLOSED by user acceptance. Nothing committed.
