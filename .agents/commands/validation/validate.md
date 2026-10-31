Run comprehensive validation of the project to ensure all tests, type checks, linting, and deployments are working correctly.

The project declares its own commands: read them from `CLAUDE.md` (`## Commands` / `## Validation`) and from the `## VALIDATION COMMANDS` section of the feature plan. Those are the source of truth. The commands shown under each step below are **examples from a Python + uv + FastAPI project** - substitute the project's own.

Execute the steps in sequence and report results. If the project has no tooling for a step, skip it and say so explicitly rather than reporting it as passed.

## 1. Test Suite

Run the project's test command.

Example (Python + uv + pytest):

```bash
uv run pytest -v
```

**Expected:** zero failures and zero errors. Report the actual pass/fail counts produced by this run - do not compare against a fixed total.

## 2. Type Checking

Run the project's type checker(s), if it has any, against its source root.

Example (Python + uv):

```bash
uv run mypy <source-dir>
```

```bash
uv run pyright <source-dir>
```

**Expected:** zero errors. If the project has no type checker, state that and skip this step.

## 3. Linting

Run the project's linter and format check.

Example (Python + uv + ruff):

```bash
uv run ruff check .
```

**Expected:** zero violations.

## 4. Local Runtime Check

Only if the project has a runnable entry point (server, CLI, desktop app). For libraries and plain scripts with no entry point, skip this step and say so.

Start it with the project's own start command, on the port or entry point its configuration declares - never a hard-coded one.

Example (Python + FastAPI + uvicorn):

```bash
uv run uvicorn <app-module>:app --port <configured-port> &
```

Wait for startup, then exercise the entry point the project documents and confirm the response the project documents - status code, body, and any headers it guarantees.

Example:

```bash
curl -s -i http://localhost:<configured-port>/<documented-path> | head -10
```

**Expected:** the documented response. A CLI equivalent is running the documented command (e.g. `--help` or a smoke subcommand) and confirming its documented output.

Stop anything you started before moving on.

Example (stopping the backgrounded server above):

```bash
lsof -ti:<configured-port> | xargs kill -9 2>/dev/null || true
```

## 5. Summary Report

After all validations complete, provide a summary report with:

- Total tests passed/failed
- Type checking status (or "not applicable")
- Linting status
- Local runtime status (or "not applicable")
- Any steps skipped, and why
- Any errors or warnings encountered
- Overall health assessment (PASS/FAIL)

**Format the report clearly with sections and status indicators (✅/❌)**
