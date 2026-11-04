"""Chunk repository: read-only retrieval primitives over the SQLite store."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from app.db.connection import connect


@dataclass
class ChunkDetail:
    id: int
    artifact_id: str
    chunk_idx: int
    span_start: int
    span_end: int
    text: str


def get_chunks(db_path: str, ids: list[int]) -> dict[int, ChunkDetail]:
    """Batch-hydrate chunks by id in ONE connection, keyed by id."""
    if not ids:
        return {}
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, artifact_id, chunk_idx, span_start, span_end, text FROM chunks"
            f" WHERE id IN ({','.join('?' * len(ids))})",
            tuple(ids),
        ).fetchall()
    finally:
        conn.close()
    return {
        r["id"]: ChunkDetail(
            id=r["id"],
            artifact_id=r["artifact_id"],
            chunk_idx=r["chunk_idx"],
            span_start=r["span_start"],
            span_end=r["span_end"],
            text=r["text"],
        )
        for r in rows
    }


def get_chunks_by_artifacts(db_path: str, artifact_ids: list[str]) -> dict[str, list[ChunkDetail]]:
    """Hydrate chunks for a set of artifacts in ONE connection, keyed by artifact.

    Each artifact's chunks are ordered by ``chunk_idx``. Every requested id
    appears in the mapping; ids with no chunks (including unknown ids) map to
    ``[]`` — existence is the caller's job (see ``find_missing_artifact_ids``).
    """
    if not artifact_ids:
        return {}
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, artifact_id, chunk_idx, span_start, span_end, text FROM chunks"
            f" WHERE artifact_id IN ({','.join('?' * len(artifact_ids))})"
            " ORDER BY artifact_id, chunk_idx",
            tuple(artifact_ids),
        ).fetchall()
    finally:
        conn.close()
    grouped: dict[str, list[ChunkDetail]] = {aid: [] for aid in artifact_ids}
    for r in rows:
        grouped[r["artifact_id"]].append(
            ChunkDetail(
                id=r["id"],
                artifact_id=r["artifact_id"],
                chunk_idx=r["chunk_idx"],
                span_start=r["span_start"],
                span_end=r["span_end"],
                text=r["text"],
            )
        )
    return grouped


def search_bm25_ids(db_path: str, match_expr: str, limit: int) -> list[int]:
    """Chunk IDs matching the FTS5 expression, best-first (lower bm25 first)."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?"
            " ORDER BY bm25(chunks_fts) LIMIT ?",
            (match_expr, limit),
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]


def search_vector_ids(db_path: str, query_vec: list[float], limit: int) -> list[int]:
    """Chunk IDs nearest the query vector, best-first (smaller distance first).

    Uses the canonical ``k = ?`` KNN constraint (not a bare parameterized
    LIMIT): some SQLite builds do not propagate a bound LIMIT to the vec0
    module, which then rejects the query ("A LIMIT or 'k = ?' constraint is
    required"). Found via Modal deploy (CHECKPOINT 2).
    """
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT rowid FROM chunks_vec WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (struct.pack(f"{len(query_vec)}f", *query_vec), limit),
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]
