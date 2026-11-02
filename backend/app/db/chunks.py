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
    """Chunk IDs nearest the query vector, best-first (smaller distance first)."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT rowid FROM chunks_vec WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (struct.pack(f"{len(query_vec)}f", *query_vec), limit),
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]
