---
description: Prime agent with codebase understanding
---

# Prime: Load Project Context

## Objective

Build comprehensive understanding of the codebase by analyzing structure, documentation, and key files. Rebuild working context at the start of a fresh session without beginning implementation.

## Process

### 1. Analyze Project Structure

List all tracked files:
!`git ls-files`

Show directory structure:
If `tree` is available, run: `tree -L 3 -I 'node_modules|__pycache__|.git|dist|build'`
Otherwise, work from the tracked-file list above.

### 2. Read Core Documentation

- Read the PRD.md or similar spec file
- Read CLAUDE.md or similar global rules file
- Read README files at project root and major directories
- Read any architecture documentation
- If the project has a datastore, read its schema or migration config (Drizzle, Prisma, Alembic, plain SQL migrations, etc.)
- Read only the most relevant files from `.agents/reference/` and `.agents/articles/`

### 3. Identify Key Files

Based on the structure, identify and read:
- Main entry points (main.py, index.ts, app.py, etc.)
- Core configuration files (pyproject.toml, package.json, tsconfig.json)
- Key model/schema definitions
- Important service or controller files

### 4. Understand Current State

Check recent activity:
!`git log -10 --oneline`

Check current branch and status:
!`git status`

## Output Report
Write this summary to `.agents/plans/prime-summary.md`.

Organize the file by implementation phase:
- If the file does not exist, create it.
- If the current phase already has a summary, replace only that phase's summary with the new one.
- If the current phase does not have a summary, append it under a heading identifying the phase.
- Preserve all other phases' summaries.

Provide a concise summary covering:

### Project Overview
- Purpose and type of application
- Primary technologies and frameworks
- Current version/state

### Architecture
- Overall structure and organization
- Key architectural patterns identified
- Important directories and their purposes

### Tech Stack
- Languages and versions
- Frameworks and major libraries
- Build tools and package managers
- Testing frameworks

### Core Principles
- Code style and conventions observed
- Documentation standards
- Testing approach

### Current State
- Active branch
- Recent changes or development focus
- Any immediate observations or concerns
- Constraints that will matter before implementation
- The next highest-leverage recommended task or phase
- Files or docs that should be consulted before implementation

### What's Next
- Identify the current implementation phase based on the PRD and project progress.
- Confirm exactly what we are going to build for the current phase, including an ordered list of deliverables with their titles, descriptions, and scope boundaries.
- Write the complete build list to `.agents/plans/phase-{N}-build-list.md`, replacing `{N}` with the current phase number. Create or overwrite the file for the current phase.
- Include the current phase and the path to its build-list file in `prime-summary.md`. Do not duplicate the full deliverable list there.


**Make this summary easy to scan - use bullet points and clear headers.**