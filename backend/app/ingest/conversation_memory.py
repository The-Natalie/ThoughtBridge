"""Conversation memory indexing: one turn-append becomes one artifact.

Contract: routers call :func:`index_conversation_turns` AFTER turn
persistence with exactly the newly appended turns. Each call produces one
``tb_conversation`` artifact via the standard :func:`ingest_source`
pipeline — old turns are never re-indexed, so chunk IDs stay stable
forever and fact/attempt references never churn.
"""

from __future__ import annotations

from app.ingest.adapters import adapt_conversation
from app.ingest.pipeline import IngestResult, ingest_source
from app.retrieval.embedder import EmbedFn

__all__ = ["index_conversation_turns"]


def index_conversation_turns(
    *,
    db_path: str,
    conversation_id: str,
    kind: str,
    turns: list[tuple[str, str]],
    turn_start: int,
    max_artifact_chars: int,
    embedding_model: str,
    embed_fn: EmbedFn | None = None,
) -> IngestResult:
    """Index one turn-append as a role-tagged conversation artifact.

    ``turns`` holds ``(role, content)`` pairs in append order; ``turn_start``
    is the first appended turn's ``idx`` (0 on the new-conversation path).
    """
    adapted = adapt_conversation(conversation_id, kind, turns, turn_start)
    return ingest_source(
        db_path=db_path,
        source_type=adapted.source_type,
        title=adapted.title,
        content=adapted.content,
        origin=adapted.origin,
        max_artifact_chars=max_artifact_chars,
        embedding_model=embedding_model,
        embed_fn=embed_fn,
    )
