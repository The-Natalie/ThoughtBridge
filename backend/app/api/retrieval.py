"""Retrieval endpoints — thin router over chunk reads + hybrid search (PRD §10).

Test seam: ``hybrid_search`` is imported BY NAME so tests can
``monkeypatch.setattr(\"app.api.retrieval.hybrid_search\", stub)`` (mirrors
the ingest-router pipeline seam). The stub wraps the real search with a
fake ``embed_fn``; the default suite never downloads the fastembed model.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.db.chunks import get_chunks
from app.db.connection import EmbeddingDimMismatchError
from app.retrieval.search import TOP_K_DEFAULT, TOP_K_MAX, hybrid_search

logger = logging.getLogger(__name__)

router = APIRouter(tags=["retrieval"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=TOP_K_DEFAULT, ge=1, le=TOP_K_MAX)


class SearchHitOut(BaseModel):
    chunk_id: int
    artifact_id: str
    span: list[int]
    excerpt: str
    rrf_score: float
    bm25_rank: int | None
    vector_rank: int | None


class SearchResponse(BaseModel):
    results: list[SearchHitOut]


class ChunkOut(BaseModel):
    id: int
    artifact_id: str
    chunk_idx: int
    span: list[int]
    text: str


@router.post("/retrieval/search", response_model=SearchResponse)
def search(body: SearchRequest) -> SearchResponse:
    """Ranked hybrid retrieval over chunks (inspection endpoint)."""
    if not body.query.strip():
        logger.warning("search rejected: blank query")
        raise HTTPException(status_code=422, detail="query must not be blank")
    settings = get_settings()
    try:
        hits = hybrid_search(
            db_path=settings.database_path,
            query=body.query,
            top_k=body.top_k,
            embedding_model=settings.embedding_model,
            embed_fn=None,
        )
    except EmbeddingDimMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    return SearchResponse(
        results=[
            SearchHitOut(
                chunk_id=h.chunk_id,
                artifact_id=h.artifact_id,
                span=[h.span_start, h.span_end],
                excerpt=h.excerpt,
                rrf_score=h.rrf_score,
                bm25_rank=h.bm25_rank,
                vector_rank=h.vector_rank,
            )
            for h in hits
        ]
    )


@router.get("/chunks/{chunk_id}", response_model=ChunkOut)
def get_chunk_endpoint(chunk_id: int) -> ChunkOut:
    """Full chunk text plus artifact link (citation target)."""
    detail = get_chunks(get_settings().database_path, [chunk_id]).get(chunk_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chunk not found")
    return ChunkOut(
        id=detail.id,
        artifact_id=detail.artifact_id,
        chunk_idx=detail.chunk_idx,
        span=[detail.span_start, detail.span_end],
        text=detail.text,
    )
