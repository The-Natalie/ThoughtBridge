"""Leg + hybrid-search integration: real SQLite/FTS5/vec0, stubbed vectors.

Passage stubs are stateful (counter-based) so multi-artifact seeds get
distinct deterministic vectors; query stubs mirror the same schemes.
The suite never touches fastembed except the gated recall test.
"""

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from app.db.chunks import search_bm25_ids, search_vector_ids
from app.db.connection import EmbeddingDimMismatchError, init_db
from app.db.connection import (
    connect as real_connect,
)
from app.ingest.pipeline import ingest_source
from app.retrieval.search import RRF_K, build_fts_match, hybrid_search

DIM = 384
MODEL = "BAAI/bge-small-en-v1.5"
MAXC = 500_000
EXCERPT_LEN_GUARD = 300

INJECTIONS = [
    "cat AND dog",
    "a OR b NOT c",
    '"unbalanced quote',
    "prefix*",
    "col:term",
    "NEAR(foo bar)",
    "(a b)",
    '^ sheer "quotes" \\ backslash',
]


@pytest.fixture()
def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "retrieval.db")
    init_db(path)
    return path


@pytest.fixture()
def one_hot() -> Callable[[list[str]], list[list[float]]]:
    """Stateful passage stub: chunk n (seed order) → unit vector n."""
    n = 0

    def stub(texts: list[str]) -> list[list[float]]:
        nonlocal n
        out = []
        for _ in texts:
            vec = [0.0] * DIM
            vec[n % DIM] = 1.0
            n += 1
            out.append(vec)
        return out

    return stub


def unit(j: int) -> list[float]:
    vec = [0.0] * DIM
    vec[j % DIM] = 1.0
    return vec


def seed(
    db_path: str,
    notes: list[tuple[str, str]],
    embed: Callable[[list[str]], list[list[float]]],
) -> list[str]:
    ids = []
    for title, content in notes:
        result = ingest_source(
            db_path=db_path,
            source_type="note",
            title=title,
            content=content,
            origin={"adapter": "text"},
            max_artifact_chars=MAXC,
            embedding_model=MODEL,
            embed_fn=embed,
        )
        ids.append(result.artifact_id)
    return ids


def chunk_ids(db_path: str) -> list[int]:
    conn = real_connect(db_path)
    try:
        return [r[0] for r in conn.execute("SELECT id FROM chunks ORDER BY id")]
    finally:
        conn.close()


def test_bm25_leg_orders_exact_term_chunk_first(
    db_path: str, one_hot: Callable[[list[str]], list[list[float]]]
) -> None:
    seed(
        db_path,
        [
            ("a", "Fixed the lazy loading problem with selectinload on the query."),
            ("b", "Postgres index tuning cut p99 response time in half."),
            ("c", "My sourdough starter doubled after feeding it rye flour."),
        ],
        one_hot,
    )
    first, _, _ = chunk_ids(db_path)
    assert search_bm25_ids(db_path, "selectinload", 10)[0] == first


def test_vector_leg_orders_stub_nearest_first(
    db_path: str, one_hot: Callable[[list[str]], list[list[float]]]
) -> None:
    seed(db_path, [("a", "alpha"), ("b", "beta"), ("c", "gamma")], one_hot)
    _, second, _ = chunk_ids(db_path)
    assert search_vector_ids(db_path, unit(1), 10)[0] == second


def test_bm25_leg_honors_limit(
    db_path: str, one_hot: Callable[[list[str]], list[list[float]]]
) -> None:
    seed(db_path, [("a", "shared record one"), ("b", "shared record two")], one_hot)
    assert len(search_bm25_ids(db_path, '"shared"', 1)) == 1


@pytest.mark.parametrize("raw", INJECTIONS)
def test_sanitizer_output_accepted_by_real_fts(
    db_path: str, one_hot: Callable[[list[str]], list[list[float]]], raw: str
) -> None:
    seed(db_path, [("a", "some ordinary content here")], one_hot)
    expr = build_fts_match(raw)
    if expr is None:
        return
    search_bm25_ids(db_path, expr, 10)  # must not raise OperationalError


def test_hybrid_both_legs_agreeing_wins(
    db_path: str, one_hot: Callable[[list[str]], list[list[float]]]
) -> None:
    seed(
        db_path,
        [
            ("a", "Fixed the lazy loading problem with selectinload on the query."),
            ("b", "Postgres index tuning cut p99 response time in half."),
            ("c", "My sourdough starter doubled after feeding it rye flour."),
        ],
        one_hot,
    )
    (first, _, _) = chunk_ids(db_path)
    fused = hybrid_search(
        db_path=db_path,
        query="selectinload",
        top_k=3,
        embedding_model=MODEL,
        embed_fn=lambda q: unit(0),
    )
    assert fused[0].chunk_id == first
    assert (fused[0].bm25_rank, fused[0].vector_rank) == (1, 1)


def test_hybrid_fusion_math_end_to_end(
    db_path: str, one_hot: Callable[[list[str]], list[list[float]]]
) -> None:
    # A: BM25 rank 1 (only match) + vector rank 2 → 1/61 + 1/62 ≈ .03253.
    # B: BM25 miss + vector rank 1 → 1/61 ≈ .01639. Order: [A, B].
    seed(db_path, [("a", "selectinload fix"), ("b", "unrelated sourdough note")], one_hot)
    id_a, id_b = chunk_ids(db_path)
    fused = hybrid_search(
        db_path=db_path,
        query="selectinload",
        top_k=2,
        embedding_model=MODEL,
        embed_fn=lambda q: unit(1),
    )
    assert [h.chunk_id for h in fused] == [id_a, id_b]
    assert fused[0].rrf_score == pytest.approx(1 / (RRF_K + 1) + 1 / (RRF_K + 2))
    assert fused[1].rrf_score == pytest.approx(1 / (RRF_K + 1))
    assert fused[1].bm25_rank is None


def test_hybrid_top_k_truncation(
    db_path: str, one_hot: Callable[[list[str]], list[list[float]]]
) -> None:
    seed(db_path, [(f"n{i}", f"record number {i}") for i in range(5)], one_hot)
    fused = hybrid_search(
        db_path=db_path,
        query="record",
        top_k=2,
        embedding_model=MODEL,
        embed_fn=lambda q: unit(0),
    )
    assert len(fused) == 2
    assert fused[0].rrf_score >= fused[1].rrf_score


def test_hybrid_empty_db_returns_empty(db_path: str) -> None:
    assert (
        hybrid_search(
            db_path=db_path,
            query="anything",
            top_k=5,
            embedding_model=MODEL,
            embed_fn=lambda q: unit(0),
        )
        == []
    )


def test_hybrid_fts_miss_degrades_to_vector(
    db_path: str, one_hot: Callable[[list[str]], list[list[float]]]
) -> None:
    seed(db_path, [("a", "alpha content"), ("b", "beta content")], one_hot)
    fused = hybrid_search(
        db_path=db_path,
        query="zzzqqq nonexistent terms",
        top_k=5,
        embedding_model=MODEL,
        embed_fn=lambda q: unit(0),
    )
    assert len(fused) == 2
    assert all(h.bm25_rank is None for h in fused)
    assert all(h.vector_rank is not None for h in fused)


def test_hybrid_no_token_query_is_vector_only(
    db_path: str, one_hot: Callable[[list[str]], list[list[float]]]
) -> None:
    seed(db_path, [("a", "alpha content"), ("b", "beta content")], one_hot)
    fused = hybrid_search(
        db_path=db_path,
        query="???",
        top_k=5,
        embedding_model=MODEL,
        embed_fn=lambda q: unit(1),
    )
    assert len(fused) == 2
    assert all(h.bm25_rank is None for h in fused)


def test_hybrid_hydrate_order_spans_and_excerpts(
    db_path: str, one_hot: Callable[[list[str]], list[list[float]]]
) -> None:
    long_text = "selectinload " + "x" * 400
    seed(db_path, [("long", long_text), ("short", "tiny note")], one_hot)
    fused = hybrid_search(
        db_path=db_path,
        query="selectinload",
        top_k=5,
        embedding_model=MODEL,
        embed_fn=lambda q: unit(0),
    )
    assert [h.rrf_score for h in fused] == sorted([h.rrf_score for h in fused], reverse=True)
    long_hit = next(h for h in fused if len(h.excerpt) > EXCERPT_LEN_GUARD)
    assert long_hit.excerpt == long_text[:300] + "..."
    conn = real_connect(db_path)
    try:
        row = conn.execute(
            "SELECT span_start, span_end, text FROM chunks WHERE id = ?",
            (long_hit.chunk_id,),
        ).fetchone()
    finally:
        conn.close()
    assert (long_hit.span_start, long_hit.span_end) == (row[0], row[1])
    assert row[2] == long_text


def test_hybrid_per_leg_overfetch_surfaces_deep_vector_hit(db_path: str) -> None:
    n = 0

    def graded(texts: list[str]) -> list[list[float]]:
        nonlocal n
        out = []
        for _ in texts:
            out.append([float(n + 1)] + [0.0] * (DIM - 1))
            n += 1
        return out

    notes = [(f"n{i}", f"ordinary filler note {i}") for i in range(5)]
    notes[3] = ("target", "Fixed the lazy loading problem with selectinload.")
    seed(db_path, notes, graded)
    target_id = chunk_ids(db_path)[3]
    fused = hybrid_search(
        db_path=db_path,
        query="selectinload",
        top_k=2,
        embedding_model=MODEL,
        embed_fn=lambda q: [0.5] + [0.0] * (DIM - 1),
    )
    target = next(h for h in fused if h.chunk_id == target_id)
    assert (target.bm25_rank, target.vector_rank) == (1, 4)


def test_hybrid_dim_guard_fails_before_embedding(
    db_path: str, one_hot: Callable[[list[str]], list[list[float]]]
) -> None:
    seed(db_path, [("a", "alpha")], one_hot)
    conn = real_connect(db_path)
    try:
        with conn:
            conn.execute("UPDATE meta SET value = 'other' WHERE key = 'embedding_model'")
    finally:
        conn.close()
    called: list[str] = []

    def spy(text: str) -> list[float]:
        called.append(text)
        return unit(0)

    with pytest.raises(EmbeddingDimMismatchError):
        hybrid_search(
            db_path=db_path,
            query="alpha",
            top_k=5,
            embedding_model=MODEL,
            embed_fn=spy,
        )
    assert called == []


def test_hybrid_wrong_dim_query_vector_rejected(
    db_path: str, one_hot: Callable[[list[str]], list[list[float]]]
) -> None:
    seed(db_path, [("a", "alpha")], one_hot)
    with pytest.raises(ValueError, match="dim"):
        hybrid_search(
            db_path=db_path,
            query="alpha",
            top_k=5,
            embedding_model=MODEL,
            embed_fn=lambda q: [0.0] * 128,
        )


def test_hybrid_drops_leg_ids_with_no_chunk_row(
    db_path: str,
    one_hot: Callable[[list[str]], list[list[float]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed(db_path, [("a", "alpha content")], one_hot)
    monkeypatch.setattr("app.retrieval.search.search_vector_ids", lambda *a, **k: [999999])
    monkeypatch.setattr("app.retrieval.search.search_bm25_ids", lambda *a, **k: [])
    assert (
        hybrid_search(
            db_path=db_path,
            query="alpha",
            top_k=5,
            embedding_model=MODEL,
            embed_fn=lambda q: unit(0),
        )
        == []
    )


@pytest.mark.skipif(
    os.environ.get("TB_REAL_EMBEDDINGS") != "1", reason="needs network + ~90MB model"
)
def test_real_vague_recall_retrieves_right_passage(db_path: str) -> None:
    ids = seed(
        db_path,
        [
            ("SQLAlchemy fix", "Fixed the lazy loading problem by adding selectinload."),
            ("Postgres tuning", "Postgres index tuning cut p99 response time in half."),
            ("RAG note", "Retrieval augmented generation fetches passages before writing."),
            ("Sourdough", "My sourdough starter doubled after feeding it rye flour."),
        ],
        None,  # type: ignore[arg-type]
    )
    fused = hybrid_search(
        db_path=db_path,
        query="my database query was slow because related rows loaded one by one, what was the fix",
        top_k=3,
        embedding_model=MODEL,
        embed_fn=None,
    )
    assert ids[0] in [h.artifact_id for h in fused]
