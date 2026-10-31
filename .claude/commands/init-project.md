# Initialize Project

Set up and start the project locally.

Use the commands this project declares in `CLAUDE.md` (`## Commands`).

**If the required setup commands are not documented there, stop - do not guess and do not run anything.** Inspect the project's actual configuration (manifests such as `pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`, `Gemfile`; lockfiles; declared scripts; container and service definitions), then report:

- which setup commands are missing or undetermined
- what the project's configuration actually shows
- the command or options most likely appropriate, and why

Ask the user to confirm before proceeding.

The commands below are **examples from a Python + uv + FastAPI + PostgreSQL project** - substitute the project's own, and skip any step that does not apply.

## 1. Create Environment File

```bash
cp .env.example .env
```

Creates your local environment configuration from the example template. Skip if the project has no `.env.example`.

## 2. Install Dependencies

Run the install command for the project's package manager.

Example (Python + uv):

```bash
uv sync
```

Other examples: `npm install` / `pnpm install` / `bun install` (package.json), `pip install -r requirements.txt`, `go mod download`, `cargo build`.

## 3. Start Backing Services

Only if the project needs them (database, cache, queue). Use the project's own service definitions, images, and ports.

Example (Docker Compose):

```bash
docker-compose up -d db
```

## 4. Run Database Migrations

Only if the project has migrations. Use its migration tool.

Example (Alembic):

```bash
uv run alembic upgrade head
```

## 5. Start the Application

Start it with the project's own dev command, on its configured port.

Example (FastAPI + uvicorn):

```bash
uv run uvicorn <app-module>:app --reload --port <configured-port>
```

## 6. Validate Setup

Exercise the entry point the project documents and confirm the response the project documents.

Example:

```bash
curl -s http://localhost:<configured-port>/<health-path>
```

## Access Points

List the URLs and ports this project actually serves, taken from its configuration - for example an API docs page, a health endpoint, and any backing service ports.

## Cleanup

Stop the app (Ctrl+C) and any backing services you started.

Example:

```bash
docker-compose down
```
