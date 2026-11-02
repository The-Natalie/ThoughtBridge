"""Hybrid retrieval: FTS5 sanitizer, RRF fusion, and search orchestration.

Retrieval is a deterministic pipeline with one model call: sanitize the
query, fail fast on embedding drift, embed the query, run the BM25 and
vector legs with over-fetched limits, fuse ranks with Reciprocal Rank
Fusion, hydrate every returned field from the canonical ``chunks`` table
(the vector index is derived ordering only), truncate excerpts, return
``top_k``.
"""

from __future__ import annotations

import functools
import logging
import re
from dataclasses import dataclass

from app.db.chunks import get_chunks, search_bm25_ids, search_vector_ids
from app.db.connection import check_embedding_dim
from app.retrieval.embedder import EMBEDDING_DIM, QueryEmbedFn, embed_query

logger = logging.getLogger(__name__)

RRF_K = 60
EXCERPT_CHARS = 300
TOP_K_DEFAULT = 8
TOP_K_MAX = 50
PER_LEG_MULT = 5
PER_LEG_MIN = 50

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


@dataclass
class RrfHit:
    chunk_id: int
    score: float
    bm25_rank: int | None
    vector_rank: int | None


@dataclass
class SearchHit:
    chunk_id: int
    artifact_id: str
    span_start: int
    span_end: int
    excerpt: str
    rrf_score: float
    bm25_rank: int | None
    vector_rank: int | None


def build_fts_match(query: str) -> str | None:
    """Build a safe FTS5 ``MATCH`` expression from raw user text.

    Word-char tokens are double-quoted and OR-joined; ``\\w`` tokens
    cannot contain ``\"`` so quoting is trivially injection-proof. OR
    (not AND) lets vague multi-term queries degrade gracefully while
    BM25's own term-weighting does the ranking. Returns ``None`` when
    the query yields no alphanumeric tokens (caller skips the BM25 leg).
    """
    tokens = [t for t in _TOKEN_RE.findall(query) if any(c.isalnum() for c in t)]
    if not tokens:
        return None
    return " OR ".join(f'"{t}"' for t in tokens)


def per_leg_limit(top_k: int) -> int:
    """Per-leg candidate limit: RRF needs deeper lists than ``top_k``."""
    return max(top_k * PER_LEG_MULT, PER_LEG_MIN)


def rrf_fuse(
    bm25_ids: list[int], vector_ids: list[int], *, k: int = RRF_K, top_k: int
) -> list[RrfHit]:
    """Fuse two ordered chunk-ID lists with Reciprocal Rank Fusion.

    Ranks are 1-indexed (first = rank 1 → ``1/(k+1)``); a chunk absent
    from a leg contributes nothing from that leg (rank ``None``).
    Rank-only: raw BM25/vector scores never enter the score. Ties break
    by chunk id ascending so results are deterministic.
    """
    bm25_ranks = {cid: rank for rank, cid in enumerate(bm25_ids, start=1)}
    vector_ranks = {cid: rank for rank, cid in enumerate(vector_ids, start=1)}
    hits: list[RrfHit] = []
    for cid in set(bm25_ids) | set(vector_ids):
        score = 0.0
        bm25_rank = bm25_ranks.get(cid)
        vector_rank = vector_ranks.get(cid)
        if bm25_rank is not None:
            score += 1.0 / (k + bm25_rank)
        if vector_rank is not None:
            score += 1.0 / (k + vector_rank)
        hits.append(RrfHit(chunk_id=cid, score=score, bm25_rank=bm25_rank, vector_rank=vector_rank))
    hits.sort(key=lambda h: (-h.score, h.chunk_id))
    return hits[:top_k]


def excerpt_of(text: str, limit: int = EXCERPT_CHARS) -> str:
    """Truncate chunk text to a bounded excerpt (plain slice + ``...``)."""
    return text if len(text) <= limit else text[:limit] + "..."


def hybrid_search(
    *,
    db_path: str,
    query: str,
    top_k: int,
    embedding_model: str,
    embed_fn: QueryEmbedFn | None = None,
) -> list[SearchHit]:
    """Run hybrid BM25 + vector search fused with RRF.

    Contract: ``query`` is non-blank and ``1 <= top_k <= TOP_K_MAX``
    (the router enforces both; this function assumes valid input).
    """
    check_embedding_dim(db_path, embedding_model, EMBEDDING_DIM)
    embed = embed_fn or functools.partial(embed_query, model_name=embedding_model)
    query_vec = embed(query)
    if len(query_vec) != EMBEDDING_DIM:
        raise ValueError(f"query embedding dim {len(query_vec)} != {EMBEDDING_DIM}")
    leg_limit = per_leg_limit(top_k)
    match_expr = build_fts_match(query)
    bm25_ids = search_bm25_ids(db_path, match_expr, leg_limit) if match_expr else []
    vector_ids = search_vector_ids(db_path, query_vec, leg_limit)
    fused = rrf_fuse(bm25_ids, vector_ids, top_k=top_k)
    hydrated = get_chunks(db_path, [h.chunk_id for h in fused])
    results: list[SearchHit] = []
    for hit in fused:
        detail = hydrated.get(hit.chunk_id)
        if detail is None:
            logger.warning("hydrate dropped leg id with no chunk row: %d", hit.chunk_id)
            continue
        results.append(
            SearchHit(
                chunk_id=hit.chunk_id,
                artifact_id=detail.artifact_id,
                span_start=detail.span_start,
                span_end=detail.span_end,
                excerpt=excerpt_of(detail.text),
                rrf_score=hit.score,
                bm25_rank=hit.bm25_rank,
                vector_rank=hit.vector_rank,
            )
        )
    logger.info(
        "hybrid search: top_k=%d bm25_hits=%d vector_hits=%d results=%d",
        top_k,
        len(bm25_ids),
        len(vector_ids),
        len(results),
    )
    return results
