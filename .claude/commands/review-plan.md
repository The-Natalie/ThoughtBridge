---
description: Review a feature plan against its requirements with an independent model, then run the automated correction loop
argument-hint: [plan-path] [--build-list path]
---

# Review Plan: Independent Plan Review + Correction Loop

## Purpose

Invoke an independent reviewer model — fresh context, one API call, no
execution environment — to compare a feature plan against its requirements
(PRD, phase build list, project summary), check the plan's structure
deterministically, and save a short checklist review. Then automatically run
the plan correction loop: routine technical corrections go back to the
builder, the plan is revised in place, and the reviewer evaluates it again —
up to 3 correction cycles per invocation. Anything needing human judgment stops the loop.

This is a plan reviewer, NOT an implementation agent. It never writes code.

## Workflow Position

```
/plan-feature → /review-plan (loop, max 3) → human approves plan → /execute → /review-execution (loop, max 3) → human manual verification → /commit
```

This command is manually invoked, after `/plan-feature` generates a plan and
before the owner reviews the plan. It never proceeds to `/execute` on its
own. It is project-agnostic: all reviewer settings (API endpoint, model, key
env var, token limit) live in `tools/review-plan.config.json`.

## Report Locations

No timestamps in filenames. Each plan has one review:

- Plan: `.agents/plans/<plan-stem>.md`
- Plan review: `.agents/plans/reviews/<plan-stem>-plan-review.md`

Reruns automatically replace the existing review for that plan. The plan
itself is revised in place by the builder during corrections, with every
cycle recorded under an appended `## Revision History` section — prior
revision entries are never edited or removed.

## Arguments

`$ARGUMENTS` holds `<plan-path> [--build-list <build-list-path>]`
(repo-root-relative or absolute paths).

Resolve inputs as follows:

- Plan path given: use it. If the file does not exist, stop and report the
  missing file.
- Plan path missing: if the user said "latest", use the newest
  `.agents/plans/*.md` excluding `prime-summary.md` and
  `phase-*-build-list.md`; otherwise ask the user for the path.
- Build list: `--build-list` when passed; otherwise the
  `phase-{N}-build-list.md` referenced by `.agents/plans/prime-summary.md`;
  otherwise the newest `.agents/plans/phase-*-build-list.md`; otherwise omit
  it (the script warns and reviews without it).
- Requirements doc: `PRD.md` when present, else omit it. Project summary:
  `.agents/plans/prime-summary.md` when present, else omit it.

Never treat the literal string `$ARGUMENTS` as a file path.

## Procedure

1. Resolve the plan, build-list, PRD, and project-summary paths. Verify the
   plan exists.
2. Probe whether this shell can write to the reviews directory (Muse's
   normal sandbox blocks shell writes under `.agents/`):

```bash
touch .agents/plans/reviews/.write-probe && rm .agents/plans/reviews/.write-probe
```

3. Run the reviewer exactly once per cycle, from the repository root:
   - Probe succeeded: save directly to the canonical location:

```bash
python3 tools/review-plan.py --plan <plan-path> [--build-list <build-list-path>]
```

   (Pass `--prd` / `--prime-summary` explicitly only to override the
   defaults or to pass `""` for a context file that should be skipped.)

   - Probe failed with `Operation not permitted`: stage to a writable
     temporary directory, quoting the canonical path for the builder
     prompt:

```bash
STAGE=$(mktemp -d)/reviews
STEM=$(basename <plan-path> .md)
python3 tools/review-plan.py --plan <plan-path> [--build-list <build-list-path>] --reviews-dir "$STAGE" --final-review-path ".agents/plans/reviews/${STEM}-plan-review.md"
```

   The script makes ONE independent reviewer API call with fresh context,
   then deterministically checks the plan's structure, computes the overall
   status, and saves the short checklist review. It prints the review path
   plus the full review. Reruns automatically replace the existing review
   for that plan. The plan (including any appended revision history) is
   never modified by the reviewer — only the generated review is replaced.

4. Temp-staged runs only (probe failed): place the review with the
   file-editing tool — read the generated `<plan-stem>-plan-review.md`
   from the staging directory and write its bytes verbatim to the canonical
   `.agents/plans/reviews/<plan-stem>-plan-review.md`, replacing any
   existing review. Verify by reading back the first line (`Overall: ...`).
   The canonical path is the review report path from here on. No manual
   copying, unsandboxed shell, or sandbox changes are needed.
5. Triage the review and run the correction loop (see below).
6. On stopping — approved, decision needed, blocked, or correction limit
   reached — first insert the stage summary (see below) into the canonical
   review file as its leading `## Stage Summary` section, immediately below
   the `Overall:` first line (which stays first, so placement verification
   still reads it back), with the file-editing tool, then print ONLY that
   same summary plus the plan and review paths. Details stay in the files.
   The summary is inserted once, after the loop's final review is placed:
   any later rerun replaces the review file (dropping the old summary) and
   a fresh summary is inserted when that run stops.
7. Do not proceed to `/execute`. The owner reviews the approved plan first.

## Correction Loop (automatic, max 3 correction passes per invocation)

One correction cycle = one builder revision pass recorded as a
`### Cycle N` entry under the plan's `## Revision History`. Numbering
continues across invocations (the next N follows the highest existing
one); historical entries are never edited, removed, or renumbered — and
never consume the current run's budget. Each invocation gets 3 fresh
correction passes with a review after each, i.e. up to 4 reviews total —
the cap stops a fourth correction, never a verification. Each cycle ends
with a fresh independent review — the reviewer never approves its own
changes.

Track the budget mechanically with the review script (no API call).
At invocation start, run:

```bash
python3 tools/review-plan.py --loop-state --plan <plan-path>
```

and note `cycles_total` as this run's starting count. Before every
correction pass, re-query with `--run-start <starting count>`; proceed
only when `corrections_remaining` is above zero, and use
`next_cycle_number` for the new entry. When `corrections_remaining` is
zero and the review still needs revision, stop with `Correction Limit
Reached`.

After every review, triage in this order:

1. **Needs Decision — stop.** `### Needs Decision` is non-empty, or any
   check is `NOT_VERIFIED` for lack of assessable evidence: ambiguous or
   conflicting requirements, scope/architecture/functionality/UX/cost
   impact, or a product-judgment tradeoff. Print the summary with status
   `Needs Decision` and stop. Never revise around an escalation, and never
   silently redefine requirements to make it go away.
2. **Reviewer failure — stop.** The script errored (missing files, missing
   API key, API error, context overflow, unusable reviewer output, or a
   failed canonical write after temp staging). Print the summary with
   status `Blocked`, reporting the cause, and stop. Do not retry inside
   this loop.
3. **Approved — stop.** Overall is `APPROVED`. Print the summary with
   status `Approved` and stop.
4. **Needs revision — correct or stop.** Overall is `NEEDS_REVISION`:
   - Query `--loop-state` with this run's starting count: if
     `corrections_remaining` is zero, print the summary with status
     `Correction Limit Reached` and stop.
   - Otherwise the builder applies every correction in `### Give to
     Builder` that is routine and technical: edit the plan in place, then
     append a `### Cycle N` entry (N = `next_cycle_number` from the query)
     under `## Revision History` (create the section at the plan's end
     when absent) quoting which findings were
     addressed, what changed, and anything not done with its reason.
     Prior revision entries are never edited. Then rerun from step 3 for a
     fresh independent review.
   - A correction that turns out to need human judgment (ambiguous
     requirement, scope effect, product tradeoff) is not applied: record
     it in the revision entry as escalated and stop with `Needs Decision`.
   - Genuinely unverifiable items are recorded, not retried: note them in
     the revision entry and stop with `Needs Decision` when they are all
     that remains.

Corrections never touch code, never touch files other than the plan, never
commit, and never proceed to `/execute`.

## Review Format

For reference; the script enforces this shape:

- First line: `Overall: ✅ APPROVED` / `🔁 NEEDS_REVISION` / `🧭 NEEDS_DECISION`
- `### Structure` — deterministic template checks (sections, task
  validations, pass signals, criteria, checklist labels)
- `### Checks` — reviewer assessments (alignment, completeness, scope,
  criteria, validation quality, prerequisites, design effectiveness)
- `### Needs Attention` — only when there are actionable findings
- `### Needs Decision` — only when there are escalations; stops the loop.
  Owner-only questions surface here, not in a manual-checks section.
- `### Give to Builder` — one ready-to-copy correction prompt; omitted when
  nothing is actionable

Plus the agent-inserted `## Stage Summary` immediately below the Overall
line (step 6).

Overall is `NEEDS_DECISION` on any escalation or unassessable check, else
`NEEDS_REVISION` on any structural or assessment failure or actionable
finding, else `APPROVED`.

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
Files: <plan path> | <review path>
```

## Constraints

- The review step is pure: it does NOT modify the plan, run tests, start
  servers or browsers, install dependencies, or write code. A temp-staged
  review is placed at the canonical path byte-for-byte (step 4); replacing
  the previous review file is the only permitted change there, except
  inserting the `## Stage Summary` block once at loop end (step 6).
- The correction step revises ONLY the plan file and appends ONLY to its
  `## Revision History`. It does NOT fix code, modify requirements docs,
  or supplement the independent review with its own second review.
- Do NOT perform automated orchestration or background monitoring beyond
  this loop's bounded synchronous cycles.
- Do NOT proceed to `/execute`. Do NOT invoke `/commit`.

## Configuration

`tools/review-plan.config.json` holds the reviewer settings: `provider`
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

- Missing plan file: stop and report which file is missing.
- Missing API key: tell the user to set the configured env var or add it to
  `./.env`; stop with `Blocked`.
- Review placement failed (temp-staged run): the generated review exists
  only at the staging path — report that path, state the canonical review
  was NOT updated, and stop with `Blocked`. Never report success without a
  verified canonical write.
- Unusable reviewer output (no valid JSON): report it; stop with `Blocked`.
  No partial review file is written on failure.
- API error: report the status/message; stop with `Blocked`.
- Context overflow: the script refuses to truncate evidence and writes no
  review. Report that the inputs exceed the model's context; stop with
  `Blocked`.
- Output budget exhausted mid-review: tell the user to raise
  `max_output_tokens` in the config and retry; stop with `Blocked`.
