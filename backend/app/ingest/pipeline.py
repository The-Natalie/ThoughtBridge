"""Ingestion orchestration: cap → chunk → dim-guard → embed → persist.

Contract: the router rejects empty/blank content (422/400) before calling
here, so ``ingest_source`` may assume non-blank input in practice. If it
ever receives whitespace-only content (chunker yields ``[]``), it persists
the artifact with 0 chunks rather than failing.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from app.db.artifacts import store_artifact
from app.db.connection import check_embedding_dim
from app.ingest.adapters import UndecodableUploadError, UnsupportedSuffixError
from app.ingest.chunker import chunk_text
from app.retrieval.embedder import EMBEDDING_DIM, EmbedFn, embed_passages

logger = logging.getLogger(__name__)

__all__ = [
    "ArtifactTooLargeError",
    "IngestResult",
    "UndecodableUploadError",
    "UnsupportedSuffixError",
    "ingest_source",
]


class ArtifactTooLargeError(ValueError):
    """Content exceeds the configured `MAX_ARTIFACT_CHARS` (→ HTTP 413)."""


@dataclass
class IngestResult:
    artifact_id: str
    chunk_count: int


def ingest_source(
    *,
    db_path: str,
    source_type: str,
    title: str,
    content: str,
    origin: dict[str, str],
    max_artifact_chars: int,
    embedding_model: str,
    embed_fn: EmbedFn | None = None,
) -> IngestResult:
    """Run the full ingest for one normalized source. See module contract."""
    if len(content) > max_artifact_chars:
        raise ArtifactTooLargeError(
            f"content has {len(content)} chars, limit is {max_artifact_chars}"
        )
    chunks = chunk_text(content)
    check_embedding_dim(db_path, embedding_model, EMBEDDING_DIM)
    embed = embed_fn or functools.partial(embed_passages, model_name=embedding_model)
    vectors = embed([c.text for c in chunks])
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    created_at = datetime.now(UTC).isoformat()
    artifact_id = store_artifact(
        db_path=db_path,
        source_type=source_type,
        title=title,
        content=content,
        content_hash=content_hash,
        origin_json=json.dumps(origin, sort_keys=True),
        created_at=created_at,
        chunks=chunks,
        embeddings=vectors,
    )
    logger.info(
        "ingested artifact: id=%s type=%s chunks=%d chars=%d",
        artifact_id,
        source_type,
        len(chunks),
        len(content),
    )
    return IngestResult(artifact_id=artifact_id, chunk_count=len(chunks))
