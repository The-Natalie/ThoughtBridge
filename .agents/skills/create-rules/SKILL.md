---
name: create-rules
description: Generate project-specific AGENTS.md rules using the existing Deterministic Workflow.
---

Read `.claude/commands/create-rules.md` and follow its discovery, analysis, generation, and reporting phases.

Muse-specific adaptations:

1. Generate `AGENTS.md` in the project root instead of `CLAUDE.md`.
2. Use the existing root `CLAUDE.md` as the structural template instead of `.agents/CLAUDE-template.md`.
3. Preserve the original command's required sections, conciseness, and context-loading guidance.
4. Since this project is still in planning, use the approved PRD and documented architecture decisions as primary sources.
5. Clearly distinguish planned architecture and conventions from patterns already implemented in code.
6. Do not invent dependencies, commands, architectural decisions, or coding conventions.
7. Preserve the original command's reporting format, substituting `AGENTS.md` for `CLAUDE.md`.

Do not modify or overwrite the existing `CLAUDE.md`.
Do not implement application features.
