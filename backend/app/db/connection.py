"""SQLite connection helper — the only sanctioned path to the database."""

from __future__ import annotations

import logging
import sqlite3
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


def init_db(path: str | Path) -> None:
    """Create all schema objects idempotently and log an init summary."""
    conn = connect(path)
    try:
        conn.executescript(SCHEMA_PATH.read_text())
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
