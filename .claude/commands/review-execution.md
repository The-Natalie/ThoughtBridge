---
description: Review a completed execution report against its feature plan with an independent model
argument-hint: [plan-path] [execution-report-path]
---

# Review Execution: Independent Evidence Review

## Purpose

Invoke an independent reviewer model — fresh context, one API call, no
execution environment — to compare a feature plan against its execution
report, verify reported file operations against the filesystem, and save a
short checklist review. The reviewer is the owner's second set of eyes: it
identifies discrepancies, incomplete verification, failures, missing
evidence, and anything requiring attention before the owner manually
approves a deliverable.

This is an evidence reviewer, NOT another execution agent.

## Workflow Position

```
/plan-feature → /execute → /review-execution → human manual verification → /commit
```

This command is manually invoked, after `/execute` completes and before the
owner's manual verification. It is project-agnostic: all reviewer settings
(API endpoint, model, key env var, token limit) live in
`tools/review-execution.config.json`.

## Report Locations

No timestamps in filenames. Each deliverable has one execution report and
one corresponding review:

- Execution report: `.agents/execution-reports/<deliverable-name>-execution-report.md`
- Execution review: `.agents/execution-reports/reviews/<deliverable-name>-execution-report-review.md`

The deliverable name is the plan file's stem. Pre-existing timestamped
reports are preserved as-is and remain valid review inputs.

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
5. On success, return to the user the review report path AND the full
   review, quoted verbatim — it is a short checklist designed to be read in
   about a minute.
6. Do not proceed to `/commit`. Manual verification by the owner is still
   required.

## Review Format

For reference; the script enforces this shape:

- First line: `Overall: ✅ PASS` / `❌ FAIL` / `⚠️ NOT VERIFIED`
- `### Validations` — every required check with its outcome
- `### Files Created` / `### Files Modified` / `### Files Removed` —
  applicable categories only, verified against the filesystem
- `### Needs Attention` — only when there are findings
- `### Give to Muse` — one ready-to-copy follow-up prompt; omitted when nothing is delegable
- `### Your Manual Checks` — owner-only checks, each with where, numbered steps, expected result, and cleanup (`None.` when empty)

After delegated checks are appended to the execution report, rerun this
command to regenerate the review from the new evidence.

Statuses: PASS (sufficient evidence), FAIL (evidence shows failure),
NOT VERIFIED (not performed, unrecorded, or insufficient evidence).
Overall is FAIL on any demonstrated failure, else NOT VERIFIED on any
evidence gap, else PASS.

## Constraints

- Do NOT rerun tests or validation commands.
- Do NOT start servers or launch browsers.
- Do NOT install dependencies.
- Do NOT modify application code.
- Do NOT fix implementation issues.
- Do NOT modify the plan or the execution report — the reviewer never
  overwrites the report.
- Do NOT alter review content: a temp-staged review is placed at the
  canonical path byte-for-byte (step 4); replacing the previous review
  file is the only permitted change there.
- Do NOT perform automated orchestration or background monitoring.
- Do not supplement the independent review with your own second review;
  report the script's output verbatim. (If the script itself failed, report
  the failure instead — see below.)

## Configuration

`tools/review-execution.config.json` holds the reviewer settings: `api_url`
(OpenAI-compatible chat-completions endpoint), `model`, `api_key_env`,
`max_output_tokens`, and `temperature`. To use another project or provider,
edit that file — no code changes needed. The API key itself comes from the
named environment variable (falling back to `./.env`); it is never printed
or committed.

## Failure Handling

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
