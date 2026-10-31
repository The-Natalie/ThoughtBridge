---
name: execute
description: Execute an approved implementation plan using the existing Deterministic Workflow, including validation and execution reporting.
---

Read `.claude/commands/execute.md` and follow its instructions in order.

Argument handling:
- Treat `$ARGUMENTS` in the referenced command as a placeholder for the plan-file path supplied with this skill invocation.
- Substitute the user's actual plan-file path wherever `$ARGUMENTS` appears.
- Never treat the literal string `$ARGUMENTS` as a file path.
- If no plan path was supplied, ask the user for it before proceeding.
- If the supplied plan file does not exist, stop and report the missing file.

Preserve the original command's execution sequence, validation requirements, failure handling, reporting requirements, and human approval checkpoints.

Create the execution report before beginning implementation, as required by the original command. Record commands, outputs, validation results, and deviations verbatim.

Do not automatically invoke `/commit` or commit changes.

After execution, follow the original command's terminal-output restriction: return only the execution report path and a one-line status.
