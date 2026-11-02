---
description: Review a completed execution report against its feature plan with an independent model, then run the automated correction loop
argument-hint: [plan-path] [execution-report-path]
---

# Review Execution: Independent Evidence Review + Correction Loop

## Purpose

Invoke an independent reviewer model — fresh context, one API call, no
execution environment — to compare a feature plan against its execution
report, verify reported file operations against the filesystem, and save a
short checklist review. The reviewer is the owner's second set of eyes: it
identifies discrepancies, incomplete verification, failures, missing
evidence, and anything requiring attention before the owner manually
approves a deliverable.

Then automatically run the execution correction loop: actionable findings
and follow-up validations go back to the builder, fixes and evidence are
appended to the execution report, and the reviewer evaluates the updated
evidence again — up to 3 correction cycles per invocation. A confirmed failure is
actionable, not a blocker: it triggers corrections. Anything needing human
judgment stops the loop.

This is an evidence reviewer plus a bounded correction loop, NOT an
open-ended execution agent.

## Workflow Position

```
/plan-feature → /review-plan (loop, max 3) → human approves plan → /execute → /review-execution (loop, max 3) → human manual verification → /commit
```

This command is manually invoked, after `/execute` completes and before the
owner's manual verification. Invoking it starts the automated correction
loop (max 3 cycles); each cycle ends with a fresh independent review. It is
project-agnostic: all reviewer settings (API endpoint, model, key env var,
token limit) live in `tools/review-execution.config.json`.

## Report Locations

No timestamps in filenames. Each deliverable has one execution report and
one corresponding review:

- Execution report: `.agents/execution-reports/<deliverable-name>-execution-report.md`
- Execution review: `.agents/execution-reports/reviews/<deliverable-name>-execution-report-review.md`

The deliverable name is the plan file's stem. Pre-existing timestamped
reports are preserved as-is and remain valid review inputs.

Correction evidence is appended to the execution report under
`## Follow-up Validation (cycle N)` sections — one per correction cycle.
The original report contents are never edited; prior follow-up sections are
never edited or removed. Reruns automatically replace the existing review
for that deliverable.

## Arguments

`$ARGUMENTS` holds `<plan-path> <execution-report-path>` (repo-root-relative
or absolute paths).

Resolve inputs as follows:

- Both paths given: use them. If either file does not exist, stop and report
  the missing file.
- Only the execution report given: take the plan path from the report's
  `**Plan:**` header line when present; otherwise ask the user for the plan.
- Only the plan given, or neither given: if the user said "latest", use the
  newest top-level `.agents/execution-reports/*-execution-report.md` plus
  its plan header; otherwise ask the user for the missing path(s).

Never treat the literal string `$ARGUMENTS` as a file path.

## Procedure

1. Resolve the plan and execution-report paths. Verify both exist.
2. Probe whether this shell can write to the reviews directory (Muse's
   normal sandbox blocks shell writes under `.agents/`):

```bash
touch .agents/execution-reports/reviews/.write-probe && rm .agents/execution-reports/reviews/.write-probe
```

3. Run the reviewer exactly once, from the repository root:
   - Probe succeeded: save directly to the canonical location:

```bash
python3 tools/review-execution.py --plan <plan-path> --report <execution-report-path>
```

   - Probe failed with `Operation not permitted`: stage to a writable
     temporary directory, quoting the canonical path for the delegate
     prompt:

```bash
STAGE=$(mktemp -d)/reviews
STEM=$(basename <plan-path> .md)
python3 tools/review-execution.py --plan <plan-path> --report <execution-report-path> --reviews-dir "$STAGE" --final-review-path ".agents/execution-reports/reviews/${STEM}-execution-report-review.md"
```

   The script makes ONE independent reviewer API call with fresh context,
   then deterministically verifies each reported file operation against
   the filesystem, computes the overall status, and saves the short
   checklist review. It prints the review path plus the full review.
   Reruns automatically replace the existing review for that deliverable.
   The execution report (including any appended follow-up validation) is
   never modified — only the generated review is replaced.

4. Temp-staged runs only (probe failed): place the review with the
   file-editing tool — read the generated
   `<deliverable-name>-execution-report-review.md` from the staging
   directory and write its bytes verbatim to the canonical
   `.agents/execution-reports/reviews/<deliverable-name>-execution-report-review.md`,
   replacing any existing review. Verify by reading back the first line
   (`Overall: ...`). The canonical path is the review report path from
   here on. No manual copying, unsandboxed shell, or sandbox changes are
   needed.
5. Triage the review and run the correction loop (see below).
6. On stopping — approved, decision needed, blocked, or correction limit
   reached — first insert the stage summary (see below) into the canonical
   review file as its leading `## Stage Summary` section, immediately below
   the `Overall:` first line (which stays first, so placement verification
   still reads it back), with the file-editing tool, then print ONLY that
   same summary plus the execution report and review paths. Details stay in
   the files. The summary is inserted once, after the loop's final review
   is placed: any later rerun replaces the review file (dropping the old
   summary) and a fresh summary is inserted when that run stops.
7. Do not proceed to `/commit`. Manual verification by the owner is still
   required.

## Correction Loop (automatic, max 3 correction passes per invocation)

One correction cycle = one builder pass recorded as a
`## Follow-up Validation (cycle N)` section appended to the execution
report. Numbering continues across invocations (the next N follows the
highest existing one, with a legacy unnumbered `## Follow-up Validation`
section counting as cycle 1); historical sections are never edited,
removed, or renumbered — and never consume the current run's budget. Each
invocation gets 3 fresh correction passes with a review after each, i.e.
up to 4 reviews total — the cap stops a fourth correction, never a
verification. Each cycle ends with a fresh independent review — the
reviewer never approves its own changes.

Track the budget mechanically with the review script (no API call).
At invocation start, run:

```bash
python3 tools/review-execution.py --loop-state --plan <plan-path> --report <execution-report-path>
```

and note `cycles_total` as this run's starting count. Before every
correction pass, re-query with `--run-start <starting count>`; proceed
only when `corrections_remaining` is above zero, and use
`next_cycle_number` for the new section. When `corrections_remaining` is
zero and the review still needs work, stop with `Correction Limit
Reached`.

After every review, triage in this order. A confirmed failure, an
environmental blocker, and insufficient verification evidence are different
conditions — never conflate them:

1. **Needs Decision — stop.** A correction would affect feature scope,
   architecture, functionality, UX, or meaningful cost; requirements are
   ambiguous or conflicting; or a tradeoff needs product judgment. Also
   stop here when all actionable items are resolved but owner-only
   `### Your Manual Checks` remain. Print the summary with status `Needs
   Decision` and stop. When in doubt whether a correction is routine,
   escalate. The reviewer must not silently redefine requirements.
2. **Reviewer failure — stop.** The script errored (missing files, missing
   API key, API error, context overflow, unusable reviewer output, or a
   failed canonical write after temp staging). Print the summary with
   status `Blocked`, reporting the cause, and stop. Do not retry inside
   this loop.
3. **Approved — stop.** Overall is `PASS`. Print the summary with status
   `Approved` and stop.
4. **Actionable — correct or stop.** Overall is `FAIL` (demonstrated
   failure) or `NOT_VERIFIED` with a non-empty `### Give to Muse` prompt:
   - Query `--loop-state` with this run's starting count: if
     `corrections_remaining` is zero, print the summary with status
     `Correction Limit Reached` and stop.
   - Otherwise the builder performs the delegated validations and the
     routine technical fixes they imply: run tests, inspect files, start
     and stop temporary servers, use available browser automation, and fix
     routine defects confined to the plan's scope — then re-run the
     affected validations so every fix has recorded evidence. Append all
     results under a new `## Follow-up Validation (cycle N)` section
     (N = `next_cycle_number` from the query) at the end of the execution
     report, preserving the original contents
     exactly: actual commands, exit statuses, concise outputs, and
     limitations. Then rerun from step 3 for a fresh independent review.
   - Builder-phase authorization supersedes the delegate prompt's standing
     no-fix clause within this loop only: routine fixes plus validations
     are authorized; unrelated changes and commits remain prohibited.
5. **Blocked or unverifiable — record once, then stop.** A check the
   environment prevents (sandbox denial, missing tooling, credentials, or
   access the builder lacks) is attempted once, then recorded with its
   exact command, error, and exit status — print the summary with status
   `Blocked` and stop. Genuinely unverifiable items (no procedure could
   establish them, or only the owner can attest) are recorded, never
   retried — print the summary with status `Needs Decision` and stop when
   they are all that remains. Blocked and unverifiable findings are
   reported, never silently approved and never retried across cycles.

## Review Format

For reference; the script enforces this shape:

- First line: `Overall: ✅ PASS` / `❌ FAIL` / `⚠️ NOT VERIFIED`
- `### Validations` — every required check with its outcome
- `### Files Created` / `### Files Modified` / `### Files Removed` —
  applicable categories only, verified against the filesystem
- `### Needs Attention` — only when there are findings
- `### Give to Muse` — one ready-to-copy follow-up prompt; omitted when nothing is delegable
- `### Your Manual Checks` — owner-only checks, each with where, numbered steps, expected result, and cleanup (`None.` when empty)

Plus the agent-inserted `## Stage Summary` immediately below the Overall
line (step 6).

Statuses: PASS (sufficient evidence), FAIL (evidence shows failure —
actionable, triggers corrections), NOT VERIFIED (not performed, unrecorded,
or insufficient evidence — delegable when the builder can produce the
evidence, otherwise recorded once and reported). Overall is FAIL on any
demonstrated failure, else NOT VERIFIED on any evidence gap, else PASS.
`Blocked` is never a review status: it is the loop status when the
environment prevents progress.

## Stage Summary (saved to the review file and printed — keep it to 5–10 lines)

At loop end, insert this block into the canonical review file as its
leading section immediately below the `Overall:` line, then print the
identical block in the terminal:

```
## Stage Summary

**Status:** <Approved | Needs Decision | Blocked | Correction Limit Reached>
**Corrections:** <what was fixed across cycles, 1–2 lines; "None" if none>
**Remaining issues:** <only unresolved items, 1 line each; "None" if none>
**My next action:** <the single concrete owner action>
Files: <execution report path> | <review path>
```

## Constraints

- The review step is pure: it does NOT rerun tests, start servers or
  browsers, install dependencies, modify code, fix issues, or modify the
  plan or the execution report. A temp-staged review is placed at the
  canonical path byte-for-byte (step 4); replacing the previous review
  file is the only permitted change there, except inserting the
  `## Stage Summary` block once at loop end (step 6).
- The correction step appends ONLY `## Follow-up Validation (cycle N)`
  sections to the execution report and makes ONLY routine fixes confined
  to the plan's scope, each with re-validation evidence. It does NOT edit
  original report contents, make unrelated changes, or supplement the
  independent review with its own second review.
- Do NOT perform automated orchestration or background monitoring beyond
  this loop's bounded synchronous cycles.
- Do NOT invoke `/commit`. Manual verification by the owner is still
  required.

## Configuration

`tools/review-execution.config.json` holds the reviewer settings: `provider`
(`anthropic` for Claude, the default, or `openai` for OpenAI-compatible
chat-completions endpoints), `api_url`, `model`, `api_key_env`,
`max_output_tokens`, and `temperature` (used by the `openai` provider
only). To use another project or provider, edit that file — no code
changes needed; Muse Wonder remains available as provider `openai` with
api_url `https://api.meta.ai/v1/chat/completions`, model `muse-wonder-1.0`,
and key env var `MODEL_API_KEY`. The API key itself comes from the named
environment variable (falling back to `./.env`); it is never printed or
committed.

## Failure Handling

All failures below stop the loop with status `Blocked`:

- Missing input file: stop and report which file is missing.
- Missing API key: tell the user to set the configured env var or add it to
  `./.env`; stop.
- Review placement failed (temp-staged run): the generated review exists
  only at the staging path — report that path, state the canonical review
  was NOT updated, and stop. Never report success without a verified
  canonical write.
- Unusable reviewer output (no valid JSON): report it; stop. No partial
  review file is written on failure.
- API error: report the status/message; stop.
- Context overflow: the script refuses to truncate evidence and writes no
  review. Report that the inputs exceed the model's context; stop.
- Output budget exhausted mid-review: tell the user to raise
  `max_output_tokens` in the config and retry.
