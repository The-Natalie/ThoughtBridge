"""SQLite connection helper — the only sanctioned path to the database."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import sqlite_vec

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class EmbeddingDimMismatchError(RuntimeError):
    """Configured embedding model/dim does not match the initialized database."""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open a connection with WAL mode, enforced FKs, and the vec0 extension loaded."""
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Upgrade pre-existing databases to the current schema version.

    Additive only, idempotent: each step checks ``PRAGMA table_info`` (the
    real guard — never the meta version value alone) and applies only when
    the column is missing. v1→v2: ``attempts.conversation_id`` +
    ``attempts.reference_json`` (both nullable; pre-migration rows read NULL).
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(attempts)")}
    added: list[str] = []
    with conn:
        if "conversation_id" not in cols:
            conn.execute(
                "ALTER TABLE attempts ADD COLUMN conversation_id TEXT"
                " REFERENCES conversations(id) ON DELETE SET NULL"
            )
            added.append("attempts.conversation_id")
        if "reference_json" not in cols:
            conn.execute("ALTER TABLE attempts ADD COLUMN reference_json TEXT")
            added.append("attempts.reference_json")
        if added:
            conn.execute("UPDATE meta SET value = '2' WHERE key = 'schema_version'")
    for column in added:
        logger.info("db migrate: added column %s", column)


def init_db(path: str | Path) -> None:
    """Create all schema objects idempotently and log an init summary."""
    conn = connect(path)
    try:
        conn.executescript(SCHEMA_PATH.read_text())
        _migrate(conn)
        tables = conn.execute(
            "SELECT COUNT(*) AS n FROM sqlite_master WHERE type IN ('table', 'trigger')"
        ).fetchone()["n"]
        meta = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}
        logger.info(
            "db init ok: %s tables/triggers, schema_version=%s, embedding=%s dim=%s",
            tables,
            meta.get("schema_version"),
            meta.get("embedding_model"),
            meta.get("embedding_dim"),
        )
    finally:
        conn.close()


def check_embedding_dim(path: str | Path, expected_model: str, expected_dim: int) -> None:
    """Refuse to proceed when the DB's embedding model/dim differs from configuration.

    The vec0 dimension is baked in at CREATE time; a mismatch means vectors in
    the table are uninterpretable under the configured model. Rebuild, don't proceed.
    """
    conn = connect(path)
    try:
        meta = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}
    finally:
        conn.close()
    if meta.get("embedding_model") != expected_model or meta.get("embedding_dim") != str(
        expected_dim
    ):
        raise EmbeddingDimMismatchError(
            f"DB has {meta.get('embedding_model')} dim={meta.get('embedding_dim')}, "
            f"expected {expected_model} dim={expected_dim}"
        )


@dataclass
class DbProbeResult:
    ok: bool
    error: str | None


def check_readable(path: str | Path) -> DbProbeResult:
    """Check DB readability with strictly no side effects (for health checks).

    Opens read-only (`mode=ro` URI) and selects `schema_version` from `meta`.
    Never calls `init_db`/`connect`, never creates files or parent dirs, never
    sets WAL mode. MVP limitation: `str(path)` is embedded in the URI as-is,
    so paths with URI-special characters (?, #, %) may misbehave.
    """
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except (FileNotFoundError, sqlite3.DatabaseError) as exc:
        error = f"cannot open database: {exc}"
        logger.warning("db probe failed: path=%s detail=%s", path, error)
        return DbProbeResult(ok=False, error=error)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    except sqlite3.DatabaseError as exc:
        error = f"database unreadable: {exc}"
        logger.warning("db probe failed: path=%s detail=%s", path, error)
        return DbProbeResult(ok=False, error=error)
    finally:
        conn.close()
    if row is None:
        error = "schema_version missing from meta table"
        logger.warning("db probe failed: path=%s detail=%s", path, error)
        return DbProbeResult(ok=False, error=error)
    return DbProbeResult(ok=True, error=None)
