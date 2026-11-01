---
description: Execute an implementation plan
argument-hint: [path-to-plan]
---

## Execution Log Capture

Create the execution report file before starting any tasks.

Write the full verbatim output of the entire execution to `.agents/execution-reports/<deliverable-name>-execution-report.md` as you go — every command run, every line of test output, every validation result exactly as printed, every deviation or issue encountered. The deliverable name is the plan file's stem (no timestamps; one report per deliverable). If that file already exists, stop and ask the user before proceeding — never overwrite an existing report.

Do not summarize. Do not shorten. Do not omit anything.

In the terminal, only print:
- the path to the report file
- a one-line status that accurately reflects verification outcomes (e.g. "all checks passed, 0 failures, ready for /commit" — or "N verified, M partially verified/unverified/failed, see Follow-up Items" when anything is outstanding; never claim complete verification while items remain)

---

# Execute: Implement from Plan

## Plan to Execute

Read plan file: `$ARGUMENTS`

Use the approved feature plan as the source of truth. Load the relevant code files and only the supporting reference docs required for the current task.

## Execution Instructions

### 1. Read and Understand

- Read the ENTIRE plan carefully
- Understand all tasks and their dependencies
- Note the validation commands to run
- Review the testing strategy

### 2. Execute Tasks in Order

For EACH task in "Step by Step Tasks":

#### a. Navigate to the task
- Identify the file and action required
- Read existing related files if modifying

#### b. Implement the task
- Follow the detailed specifications exactly
- Maintain consistency with existing code patterns
- Follow the project's typing and documentation conventions (see CLAUDE.md)
- Follow the project's logging conventions where logging is appropriate
- Implement in small, reviewable steps
- Do not widen scope beyond the plan unless you explicitly call it out

#### c. Verify as you go
- After each file change, check syntax
- Ensure imports are correct
- Verify types are properly defined

### 3. Implement Testing Strategy

After completing implementation tasks:

- Create all test files specified in the plan
- Implement all test cases mentioned
- Follow the testing approach outlined
- Ensure tests cover edge cases

### 4. Run Validation Commands

Execute ALL validation commands from the plan in order:

```bash
# Run each command exactly as specified in plan
```

If any command fails:
- Fix the issue
- Re-run the command
- Continue only when it passes
- If a blocker cannot be resolved safely, stop and surface it rather than inventing around it

### 5. Final Verification

Before completing:

- ✅ All tasks from plan completed
- ✅ All tests created and passing
- ✅ All validation commands pass
- ✅ Code follows project conventions
- ✅ Documentation added/updated as needed
- ✅ Every acceptance criterion has a status (VERIFIED / PARTIALLY VERIFIED / UNVERIFIED / FAILED) supported by quoted evidence in this report — see Evidence Map
- ✅ PARTIALLY VERIFIED, UNVERIFIED, and FAILED criteria are listed under Follow-up Items with what remains to be checked and manual verification steps where appropriate — and the one-line status names them (e.g. "9 verified, 2 unverified, see Follow-up Items")

## End of Report Checklist

At the end of the execution report file, append:

```
## Evidence Map

Status each acceptance criterion from the plan. Implementation alone is never evidence — a criterion is VERIFIED only by recorded passing checks that establish the full criterion:

- VERIFIED: sufficient recorded evidence establishes that the criterion passed
- PARTIALLY VERIFIED: some relevant checks passed, but the full criterion was not established — state what passed and what remains
- UNVERIFIED: the criterion lacks adequate verification evidence — state what remains and give manual verification steps where appropriate
- FAILED: recorded validation demonstrates that the criterion was not met — state the failing evidence

- [criterion] → [STATUS]: [evidence: command + key output / test + count / observed behavior; or what remains + manual steps]

## Ready for Commit

- [ ] All tasks completed
- [ ] All validation commands passed
- [ ] All tests passing
- [ ] Evidence Map complete: every acceptance criterion has a status; PARTIALLY VERIFIED, UNVERIFIED, and FAILED items (if any) are named in the one-line status and detailed under Follow-up Items

## Follow-up Items

- (any deviations, edge cases, or items deferred from this execution)
- (every PARTIALLY VERIFIED, UNVERIFIED, or FAILED criterion: what remains to be checked + actionable manual verification steps where appropriate)
```

## Notes

- If you encounter issues not addressed in the plan, document them
- If you need to deviate from the plan, explain why
- If tests fail, fix implementation until they pass
- Don't skip validation steps
- Never mark a checklist or acceptance item complete on weaker evidence than the plan stated: if the evidence is weaker, status it PARTIALLY VERIFIED with the exact qualification (what was proven vs. what was claimed) instead of rewording the item to fit the evidence
- If a planned check cannot run as written, run the closest equivalent only when it tests the same assertion, quote both the deviation and the result, and qualify the Ready-for-Commit claim (e.g. "passed via equivalent procedure, see Deviation N")
- If a check cannot be performed at all, list it as NOT PERFORMED with the reason — never report it as passed. A check skipped for any reason (missing tooling, sandbox limits, optional level) must appear by name with its reason; absence from the report never means success