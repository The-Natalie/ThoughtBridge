"""DB init tests: schema objects, FTS5/vec0 behavior, cascades, F-10 join counting."""

import sqlite3
import struct
from pathlib import Path

import pytest

from app.db.connection import (
    EmbeddingDimMismatchError,
    check_embedding_dim,
    connect,
    init_db,
)

DIM = 384


def _pack(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    init_db(path)
    init_db(path)  # idempotency: second init must be a no-op success
    return path


def test_all_schema_objects_exist(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'trigger')"
            )
        }
    finally:
        conn.close()
    for expected in (
        "meta",
        "artifacts",
        "chunks",
        "chunks_fts",
        "chunks_vec",
        "facts",
        "fact_chunks",
        "fact_links",
        "interpretations",
        "explanations",
        "explanation_markers",
        "attempts",
        "conversations",
        "turns",
        "career_profile",
        "learner_profile",
        "chunks_fts_insert",
        "chunks_fts_delete",
        "chunks_fts_update",
    ):
        assert expected in names


def test_vec_insert_query_rowid_alignment(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO artifacts (id, source_type, title, content, content_hash,"
                " origin, created_at) VALUES ('a1', 'note', 't', 'body', 'h', '{}', 'now')"
            )
            chunk_id = conn.execute(
                "INSERT INTO chunks (artifact_id, chunk_idx, span_start, span_end, text)"
                " VALUES ('a1', 0, 0, 4, 'body')"
            ).lastrowid
            vec = [0.0] * DIM
            vec[0] = 1.0
            conn.execute(
                "INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
                (chunk_id, _pack(vec)),
            )
            row = conn.execute(
                "SELECT rowid FROM chunks_vec WHERE embedding MATCH ? ORDER BY distance LIMIT 1",
                (_pack(vec),),
            ).fetchone()
    finally:
        conn.close()
    assert row[0] == chunk_id  # vec0 rowid alignment by construction


def test_fts_insert_update_delete_transitions(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO artifacts (id, source_type, title, content, content_hash,"
                " origin, created_at) VALUES ('a1', 'note', 't', 'body', 'h', '{}', 'now')"
            )
            chunk_id = conn.execute(
                "INSERT INTO chunks (artifact_id, chunk_idx, span_start, span_end, text)"
                " VALUES ('a1', 0, 0, 20, 'sqlalchemy lazy loading fix')"
            ).lastrowid

            def hits(term: str) -> list[int]:
                return [
                    r[0]
                    for r in conn.execute(
                        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?", (term,)
                    )
                ]

            assert hits("sqlalchemy") == [chunk_id]
            conn.execute(
                "UPDATE chunks SET text = 'postgres index tuning' WHERE id = ?", (chunk_id,)
            )
            assert hits("sqlalchemy") == []
            assert hits("postgres") == [chunk_id]
            conn.execute("DELETE FROM chunks WHERE id = ?", (chunk_id,))
            assert hits("postgres") == []
    finally:
        conn.close()


def test_artifact_delete_cascades_to_chunks(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO artifacts (id, source_type, title, content, content_hash,"
                " origin, created_at) VALUES ('a1', 'note', 't', 'body', 'h', '{}', 'now')"
            )
            conn.execute(
                "INSERT INTO chunks (artifact_id, chunk_idx, span_start, span_end, text)"
                " VALUES ('a1', 0, 0, 4, 'body')"
            )
            conn.execute("DELETE FROM artifacts WHERE id = 'a1'")
            remaining = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    finally:
        conn.close()
    assert remaining == 0


def test_fact_chunks_supports_f10_counting(db_path: Path) -> None:
    """A fact with 2 chunk refs survives losing one (F-10 independent support)."""
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO artifacts (id, source_type, title, content, content_hash,"
                " origin, created_at) VALUES ('a1', 'note', 't', 'b1', 'h', '{}', 'now')"
            )
            conn.execute(
                "INSERT INTO artifacts (id, source_type, title, content, content_hash,"
                " origin, created_at) VALUES ('a2', 'note', 't', 'b2', 'h', '{}', 'now')"
            )
            c1 = conn.execute(
                "INSERT INTO chunks (artifact_id, chunk_idx, span_start, span_end, text)"
                " VALUES ('a1', 0, 0, 2, 'b1')"
            ).lastrowid
            c2 = conn.execute(
                "INSERT INTO chunks (artifact_id, chunk_idx, span_start, span_end, text)"
                " VALUES ('a2', 0, 0, 2, 'b2')"
            ).lastrowid
            conn.execute(
                "INSERT INTO facts (id, kind, status, summary, created_at)"
                " VALUES ('f1', 'accomplishment', 'completed', 'did it', 'now')"
            )
            conn.execute("INSERT INTO fact_chunks (fact_id, chunk_id) VALUES ('f1', ?)", (c1,))
            conn.execute("INSERT INTO fact_chunks (fact_id, chunk_id) VALUES ('f1', ?)", (c2,))
            conn.execute("DELETE FROM artifacts WHERE id = 'a1'")
            support = conn.execute(
                "SELECT COUNT(*) FROM fact_chunks WHERE fact_id = 'f1'"
            ).fetchone()[0]
            fact_alive = conn.execute("SELECT COUNT(*) FROM facts WHERE id = 'f1'").fetchone()[0]
    finally:
        conn.close()
    assert support == 1  # a2's chunk reference survives
    assert fact_alive == 1


def test_check_embedding_dim_rejects_mismatch(db_path: Path) -> None:
    check_embedding_dim(db_path, "BAAI/bge-small-en-v1.5", 384)  # must not raise
    with pytest.raises(EmbeddingDimMismatchError):
        check_embedding_dim(db_path, "other-model", 768)


def test_turn_role_check_enforced(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO conversations (id, kind, created_at) VALUES ('c1', 'qa', 'now')"
            )
            conn.execute(
                "INSERT INTO turns (id, conversation_id, idx, role, content, created_at)"
                " VALUES ('t1', 'c1', 0, 'user', 'hi', 'now')"
            )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO turns (id, conversation_id, idx, role, content, created_at)"
                    " VALUES ('t2', 'c1', 1, 'system', 'x', 'now')"
                )
    finally:
        conn.close()
