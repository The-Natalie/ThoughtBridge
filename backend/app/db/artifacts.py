"""Artifact repository: single-transaction persist + provenance reads."""

from __future__ import annotations

import logging
import struct
import uuid
from dataclasses import dataclass, field

from app.db.connection import connect
from app.ingest.chunker import Chunk
from app.retrieval.embedder import EMBEDDING_DIM

logger = logging.getLogger(__name__)


@dataclass
class ArtifactSummary:
    id: str
    title: str
    source_type: str
    created_at: str
    chunk_count: int
    fact_count: int


@dataclass
class ArtifactChunk:
    id: int
    chunk_idx: int
    span_start: int
    span_end: int
    text: str


@dataclass
class ArtifactDetail:
    id: str
    title: str
    source_type: str
    content: str
    content_hash: str
    origin: str
    created_at: str
    chunks: list[ArtifactChunk] = field(default_factory=list)
    fact_ids: list[str] = field(default_factory=list)
    interpretation_ids: list[str] = field(default_factory=list)


def store_artifact(
    *,
    db_path: str,
    source_type: str,
    title: str,
    content: str,
    content_hash: str,
    origin_json: str,
    created_at: str,
    chunks: list[Chunk],
    embeddings: list[list[float]],
) -> str:
    """Persist an artifact with its chunks + vec rows in ONE transaction.

    Returns the new artifact id. FTS rows follow through the schema's sync
    triggers — this function never touches ``chunks_fts`` directly.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(f"{len(chunks)} chunks but {len(embeddings)} embeddings")
    for vec in embeddings:
        if len(vec) != EMBEDDING_DIM:
            raise ValueError(f"embedding dim {len(vec)} != {EMBEDDING_DIM}")
    artifact_id = uuid.uuid4().hex
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO artifacts (id, source_type, title, content, content_hash,"
                " origin, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (artifact_id, source_type, title, content, content_hash, origin_json, created_at),
            )
            for chunk, vec in zip(chunks, embeddings):
                chunk_id = conn.execute(
                    "INSERT INTO chunks (artifact_id, chunk_idx, span_start, span_end, text)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (artifact_id, chunk.chunk_idx, chunk.span_start, chunk.span_end, chunk.text),
                ).lastrowid
                conn.execute(
                    "INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
                    (chunk_id, struct.pack(f"{len(vec)}f", *vec)),
                )
    finally:
        conn.close()
    logger.info("stored artifact: id=%s chunks=%d", artifact_id, len(chunks))
    return artifact_id


def list_artifacts(db_path: str) -> list[ArtifactSummary]:
    """List artifacts with chunk counts and supported-fact counts."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT a.id, a.title, a.source_type, a.created_at,"
            " (SELECT COUNT(*) FROM chunks c WHERE c.artifact_id = a.id) AS chunk_count,"
            " (SELECT COUNT(DISTINCT fc.fact_id) FROM fact_chunks fc"
            " JOIN chunks c ON c.id = fc.chunk_id WHERE c.artifact_id = a.id) AS fact_count"
            " FROM artifacts a ORDER BY a.created_at, a.id"
        ).fetchall()
    finally:
        conn.close()
    return [
        ArtifactSummary(
            id=r["id"],
            title=r["title"],
            source_type=r["source_type"],
            created_at=r["created_at"],
            chunk_count=r["chunk_count"],
            fact_count=r["fact_count"],
        )
        for r in rows
    ]


def find_missing_artifact_ids(db_path: str, artifact_ids: list[str]) -> list[str]:
    """Return the requested ids NOT present in ``artifacts`` (order-preserving).

    One connection, one query. Used by the work router for its 404 branch.
    """
    if not artifact_ids:
        return []
    conn = connect(db_path)
    try:
        rows = conn.execute(
            f"SELECT id FROM artifacts WHERE id IN ({','.join('?' * len(artifact_ids))})",
            tuple(artifact_ids),
        ).fetchall()
    finally:
        conn.close()
    present = {r["id"] for r in rows}
    missing: list[str] = []
    for aid in artifact_ids:
        if aid not in present and aid not in missing:
            missing.append(aid)
    return missing


def get_artifact_detail(db_path: str, artifact_id: str) -> ArtifactDetail | None:
    """Full artifact row with ordered chunks and linked fact/interpretation ids."""
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
        if row is None:
            return None
        chunk_rows = conn.execute(
            "SELECT id, chunk_idx, span_start, span_end, text FROM chunks"
            " WHERE artifact_id = ? ORDER BY chunk_idx",
            (artifact_id,),
        ).fetchall()
        fact_rows = conn.execute(
            "SELECT DISTINCT fc.fact_id FROM fact_chunks fc"
            " JOIN chunks c ON c.id = fc.chunk_id WHERE c.artifact_id = ?",
            (artifact_id,),
        ).fetchall()
        interp_rows = conn.execute(
            "SELECT id FROM interpretations WHERE artifact_id = ?", (artifact_id,)
        ).fetchall()
    finally:
        conn.close()
    return ArtifactDetail(
        id=row["id"],
        title=row["title"],
        source_type=row["source_type"],
        content=row["content"],
        content_hash=row["content_hash"],
        origin=row["origin"],
        created_at=row["created_at"],
        chunks=[
            ArtifactChunk(
                id=r["id"],
                chunk_idx=r["chunk_idx"],
                span_start=r["span_start"],
                span_end=r["span_end"],
                text=r["text"],
            )
            for r in chunk_rows
        ],
        fact_ids=[r["fact_id"] for r in fact_rows],
        interpretation_ids=[r["id"] for r in interp_rows],
    )
