"""Pure retrieval unit tests: sanitizer, RRF math, excerpts, per-leg formula.

No DB, no model, no settings — every test runs in milliseconds.
"""

import pytest

from app.retrieval.search import (
    EXCERPT_CHARS,
    RRF_K,
    build_fts_match,
    excerpt_of,
    per_leg_limit,
    rrf_fuse,
)


def test_build_fts_match_joins_quoted_tokens_with_or() -> None:
    assert build_fts_match("lazy loading fix") == '"lazy" OR "loading" OR "fix"'


@pytest.mark.parametrize(
    "raw",
    [
        "cat AND dog",
        "a OR b NOT c",
        '"unbalanced quote',
        "prefix*",
        "col:term",
        "NEAR(foo bar)",
        "(a b)",
        '^ sheer "quotes" \\ backslash',
    ],
)
def test_build_fts_match_quotes_every_token(raw: str) -> None:
    """Operators/punctuation from user text must never leak in unquoted."""
    expr = build_fts_match(raw)
    assert expr is not None
    parts = expr.split(" OR ")
    assert len(parts) >= 1
    for part in parts:
        assert part.startswith('"') and part.endswith('"')
        assert '"' not in part[1:-1]


@pytest.mark.parametrize("raw", ["", "   ", "???", "___", "... !!!"])
def test_build_fts_match_returns_none_without_alnum_tokens(raw: str) -> None:
    assert build_fts_match(raw) is None


def test_build_fts_match_preserves_unicode_tokens() -> None:
    assert build_fts_match("café naïve 日本語") == '"café" OR "naïve" OR "日本語"'


def test_build_fts_match_preserves_case() -> None:
    assert build_fts_match("SelectInLoad") == '"SelectInLoad"'


def test_rrf_fuse_two_leg_score_is_sum_of_reciprocals() -> None:
    (hit,) = rrf_fuse([1], [1], top_k=1)
    assert hit.chunk_id == 1
    assert hit.score == pytest.approx(2 / (RRF_K + 1))
    assert (hit.bm25_rank, hit.vector_rank) == (1, 1)


def test_rrf_fuse_single_leg_score_with_none_rank() -> None:
    (hit,) = rrf_fuse([1], [], top_k=5)
    assert hit.score == pytest.approx(1 / (RRF_K + 1))
    assert (hit.bm25_rank, hit.vector_rank) == (1, None)


def test_rrf_fuse_ranks_are_one_indexed() -> None:
    """First position scores 1/(k+1), never 1/k — 0-indexing would reweight."""
    (hit,) = rrf_fuse([7], [], top_k=1)
    assert hit.score == pytest.approx(1 / (RRF_K + 1))
    assert hit.score != pytest.approx(1 / RRF_K)


def test_rrf_fuse_both_legs_outranks_single_leg() -> None:
    # doc1 = 1/61 ≈ .01639; doc2 = 1/62 + 1/61 ≈ .03279 → [2, 1].
    fused = rrf_fuse([1, 2], [2], top_k=2)
    assert [h.chunk_id for h in fused] == [2, 1]
    assert fused[0].score == pytest.approx(1 / 62 + 1 / 61)


def test_rrf_fuse_tie_breaks_by_chunk_id_ascending() -> None:
    fused = rrf_fuse([1, 2], [2, 1], top_k=2)
    assert fused[0].score == pytest.approx(fused[1].score)
    assert [h.chunk_id for h in fused] == [1, 2]


def test_rrf_fuse_truncates_to_top_k_in_order() -> None:
    fused = rrf_fuse([1, 2, 3, 4, 5], [5, 4, 3, 2, 1], top_k=2)
    assert len(fused) == 2
    assert fused[0].score >= fused[1].score


def test_rrf_fuse_empty_inputs() -> None:
    assert rrf_fuse([], [], top_k=5) == []
    solo = rrf_fuse([], [3, 4], top_k=5)
    assert [(h.chunk_id, h.vector_rank, h.bm25_rank) for h in solo] == [
        (3, 1, None),
        (4, 2, None),
    ]


def test_rrf_fuse_honors_k_param() -> None:
    (hit,) = rrf_fuse([1], [], k=0, top_k=1)
    assert hit.score == pytest.approx(1.0)


def test_excerpt_of_short_text_unchanged() -> None:
    assert excerpt_of("hello") == "hello"


def test_excerpt_of_exact_boundary_unchanged() -> None:
    text = "x" * EXCERPT_CHARS
    assert excerpt_of(text) == text


def test_excerpt_of_long_text_truncates_with_dots() -> None:
    text = "y" * (EXCERPT_CHARS + 1)
    out = excerpt_of(text)
    assert out == text[:EXCERPT_CHARS] + "..."
    assert len(out) == EXCERPT_CHARS + 3


def test_per_leg_limit_formula() -> None:
    assert per_leg_limit(8) == 50
    assert per_leg_limit(1) == 50
    assert per_leg_limit(50) == 250


def test_pure_helpers_are_deterministic() -> None:
    assert build_fts_match("lazy loading fix") == build_fts_match("lazy loading fix")
    first = rrf_fuse([1, 2], [2, 3], top_k=3)
    second = rrf_fuse([1, 2], [2, 3], top_k=3)
    assert first == second
