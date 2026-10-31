---
name: plan-feature
description: Create a detailed implementation plan for a requested feature using the existing Deterministic Workflow.
---

Read `.claude/commands/plan-feature.md` and follow its instructions in order.

Argument handling:
- Treat `$ARGUMENTS` in the referenced command as a placeholder for the feature request supplied with this skill invocation.
- Use the user's actual feature-request text wherever `$ARGUMENTS` appears.
- Never treat the literal string `$ARGUMENTS` as the feature name or description.
- If no feature request was supplied, ask the user to describe the feature before proceeding.

Preserve the original command's planning phases, clarification requirements, output location, validation requirements, and reporting format.

Do not implement the feature. This skill creates the implementation plan only.
