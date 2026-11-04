"""Memory selection tests: tiers, cascade, framing, repo round-trips.

Sync tmp-DB tests — no network, no embedding model, no Meta key.
"""

import uuid
from pathlib import Path

from app.db.connection import connect, init_db
from app.db.explanations import (
    ExplanationDetail,
    create_explanation,
    create_marker,
    list_explanations,
    list_markers,
    normalize_concept,
)
from app.llm.memory import (
    build_framing_note,
    build_memory_context,
    concept_tier,
    marked_rank_of,
)

MAPPING = ["X maps to Y because Z."]


def _seed(
    db: str, concept: str, version: int = 1, reused_from: str | None = None
) -> ExplanationDetail:
    steps: dict = {
        "definition": "d",
        "familiar_system": "f",
        "analogy": "a",
        "mapping": list(MAPPING),
        "walkthrough": "w",
        "placement": "p",
        "interview_ready": "i",
    }
    return create_explanation(db, concept, version, steps, list(MAPPING), "l", reused_from)


def _mark(db: str, explanation_id: str, scope: str = "explanation", step=None, note: str = ""):
    return create_marker(db, explanation_id, scope, step, note)


def _attempt(db: str, explanation_id: str, answer: str | None) -> None:
    conn = connect(db)
    try:
        with conn:
            conn.execute(
                "INSERT INTO attempts (id, mode, explanation_id, question, answer, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, "learning", explanation_id, "q?", answer, "t"),
            )
    finally:
        conn.close()


def test_normalize_concept_collapses_case_and_whitespace() -> None:
    assert normalize_concept("  PHOTOSYNTHESIS ") == "photosynthesis"
    assert normalize_concept("RAG\t\n retrieval") == "rag retrieval"
    assert normalize_concept("MiXeD  Spaces") == "mixed spaces"


def test_concept_tier_table() -> None:
    assert concept_tier("rag", "rag") == 0
    assert concept_tier("rag", "rag retrieval") == 1
    # Containment takes precedence over token overlap: "rag" is a substring of
    # "rag retrieval", so this is tier 1 (the plan text said 2 — corrected).
    assert concept_tier("rag retrieval", "rag") == 1
    assert concept_tier("ai", "air") is None
    assert concept_tier("vector retrieval", "vector indexes") == 2
    assert concept_tier("vector retrieval", "sqlalchemy loading") is None
    assert concept_tier("!!!", "rag") is None


def test_memory_empty_db_and_blank_concept_return_none(tmp_path: Path) -> None:
    db = str(tmp_path / "mem_empty.db")
    init_db(db)
    assert build_memory_context(db, "RAG") is None
    _seed(db, "RAG")
    assert build_memory_context(db, "   ") is None


def test_tier_first_unmarked_same_beats_marked_related(tmp_path: Path) -> None:
    db = str(tmp_path / "mem_tier.db")
    init_db(db)
    same = _seed(db, "RAG")
    related = _seed(db, "RAG retrieval")
    _mark(db, related.id)
    ctx = build_memory_context(db, "rag")
    assert ctx is not None
    assert ctx.reused_from == same.id
    assert "not marked as clicked" in ctx.framing_note
    assert "related concept" not in ctx.framing_note


def test_marked_beats_unmarked_same_concept(tmp_path: Path) -> None:
    db = str(tmp_path / "mem_marked.db")
    init_db(db)
    older = _seed(db, "RAG", 1)
    _seed(db, "RAG", 2)
    _mark(db, older.id)
    ctx = build_memory_context(db, "RAG")
    assert ctx is not None
    assert ctx.reused_from == older.id
    assert "worked for you before" in ctx.framing_note


def test_explanation_marker_beats_step_marker(tmp_path: Path) -> None:
    assert marked_rank_of(True, True) == 0
    assert marked_rank_of(False, True) == 1
    assert marked_rank_of(False, False) == 2
    db = str(tmp_path / "mem_rank.db")
    init_db(db)
    older = _seed(db, "RAG", 1)
    newer = _seed(db, "RAG", 2)
    _mark(db, older.id)
    _mark(db, newer.id, scope="step", step="mapping")
    ctx = build_memory_context(db, "RAG")
    assert ctx is not None
    assert ctx.reused_from == older.id


def test_reuse_count_breaks_marked_tie(tmp_path: Path) -> None:
    db = str(tmp_path / "mem_reuse.db")
    init_db(db)
    a = _seed(db, "RAG", 1)
    b = _seed(db, "RAG", 2)
    _mark(db, a.id)
    _mark(db, b.id)
    _seed(db, "RAG", 3, reused_from=a.id)
    _seed(db, "RAG", 4, reused_from=a.id)
    ctx = build_memory_context(db, "RAG")
    assert ctx is not None
    assert ctx.reused_from == a.id


def test_answered_attempts_break_reuse_tie(tmp_path: Path) -> None:
    db = str(tmp_path / "mem_attempts.db")
    init_db(db)
    a = _seed(db, "RAG", 1)
    b = _seed(db, "RAG", 2)
    _mark(db, a.id)
    _mark(db, b.id)
    _attempt(db, a.id, "my answer")
    _attempt(db, a.id, "second answer")
    _attempt(db, b.id, None)
    _attempt(db, b.id, "")
    _attempt(db, b.id, "   ")
    ctx = build_memory_context(db, "RAG")
    assert ctx is not None
    assert ctx.reused_from == a.id


def test_recency_and_determinism_break_final_ties(tmp_path: Path) -> None:
    db = str(tmp_path / "mem_recency.db")
    init_db(db)
    _seed(db, "RAG", 1)
    newer = _seed(db, "RAG", 2)
    first = build_memory_context(db, "RAG")
    second = build_memory_context(db, "RAG")
    assert first is not None and second is not None
    assert first.reused_from == newer.id
    assert second.reused_from == first.reused_from
    assert second.framing_note == first.framing_note


def test_framing_note_wordings() -> None:
    marked_same = build_framing_note(
        same_concept=True,
        marked=True,
        winner_id="abc123",
        winner_version=3,
        winner_concept="RAG",
    )
    assert "worked for you before" in marked_same
    assert "related concept" not in marked_same
    assert "v3" in marked_same
    unmarked_same = build_framing_note(
        same_concept=True,
        marked=False,
        winner_id="abc123",
        winner_version=1,
        winner_concept="RAG",
    )
    assert "not marked as clicked" in unmarked_same
    assert "worked for you before" not in unmarked_same
    marked_related = build_framing_note(
        same_concept=False,
        marked=True,
        winner_id="abc123",
        winner_version=2,
        winner_concept="RAG retrieval",
    )
    assert "related concept" in marked_related
    assert "worked for you before" not in marked_related
    unmarked_related = build_framing_note(
        same_concept=False,
        marked=False,
        winner_id="abc123",
        winner_version=2,
        winner_concept="RAG retrieval",
    )
    assert "related concept" in unmarked_related
    assert "clicked for you before" not in unmarked_related
    with_note = build_framing_note(
        same_concept=True,
        marked=True,
        winner_id="abc123",
        winner_version=1,
        winner_concept="RAG",
        marker_note="librarian!",
    )
    assert with_note.endswith("Your note on what clicked: librarian!")
    blank_note = build_framing_note(
        same_concept=True,
        marked=True,
        winner_id="abc123",
        winner_version=1,
        winner_concept="RAG",
        marker_note="  ",
    )
    assert "Your note" not in blank_note


def test_prior_steps_is_a_copy(tmp_path: Path) -> None:
    db = str(tmp_path / "mem_copy.db")
    init_db(db)
    seeded = _seed(db, "RAG")
    _mark(db, seeded.id)
    first = build_memory_context(db, "RAG")
    assert first is not None
    assert first.prior_steps == seeded.steps
    first.prior_steps["definition"] = "MUTATED"
    second = build_memory_context(db, "RAG")
    assert second is not None
    assert second.prior_steps == seeded.steps
    assert second.prior_steps["definition"] == "d"


def test_regen_rows_do_not_pollute_reuse_counts(tmp_path: Path) -> None:
    db = str(tmp_path / "mem_d8.db")
    init_db(db)
    source = _seed(db, "RAG", 1)
    regen_style = _seed(db, "RAG", 2)
    assert regen_style.reused_from is None
    counts = {s.id: s.reuse_count for s in list_explanations(db)}
    assert counts == {source.id: 0, regen_style.id: 0}
    _seed(db, "RAG", 3, reused_from=source.id)
    counts = {s.id: s.reuse_count for s in list_explanations(db)}
    assert counts[source.id] == 1


def test_create_and_list_markers_roundtrip(tmp_path: Path) -> None:
    db = str(tmp_path / "mem_markers.db")
    init_db(db)
    seeded = _seed(db, "RAG")
    m1 = _mark(db, seeded.id, note="n1")
    m2 = _mark(db, seeded.id, scope="step", step="mapping", note="n2")
    markers = list_markers(db, seeded.id)
    assert [m.id for m in markers] == [m1.id, m2.id]
    assert (markers[0].scope, markers[0].step, markers[0].note) == ("explanation", None, "n1")
    assert (markers[1].scope, markers[1].step, markers[1].note) == ("step", "mapping", "n2")
    assert markers[0].explanation_id == seeded.id
    assert list_markers(db, "0" * 32) == []


def test_list_explanations_summaries_counts_and_filter(tmp_path: Path) -> None:
    db = str(tmp_path / "mem_list.db")
    init_db(db)
    a = _seed(db, "RAG", 1)
    b = _seed(db, "RAG", 2)
    c = _seed(db, "SQLAlchemy", 1)
    _mark(db, a.id)
    _mark(db, a.id, scope="step", step="analogy")
    _mark(db, b.id, scope="step", step="mapping")
    child = _seed(db, "RAG", 3, reused_from=a.id)
    _attempt(db, a.id, "ans")
    rows = list_explanations(db)
    assert [r.id for r in rows] == [child.id, c.id, b.id, a.id]
    by_id = {r.id: r for r in rows}
    assert (by_id[a.id].reuse_count, by_id[a.id].marked) == (1, True)
    assert by_id[a.id].has_explanation_marker is True
    assert (by_id[a.id].marker_count, by_id[a.id].attempt_count) == (2, 1)
    assert by_id[b.id].has_explanation_marker is False
    assert (by_id[b.id].marked, by_id[b.id].marker_count) == (True, 1)
    assert (by_id[c.id].marked, by_id[c.id].reuse_count, by_id[c.id].attempt_count) == (
        False,
        0,
        0,
    )
    filtered = list_explanations(db, "  rag ")
    assert {r.id for r in filtered} == {a.id, b.id, child.id}
    assert list_explanations(db, "nope") == []


def test_only_unrelated_returns_none_and_related_falls_back(tmp_path: Path) -> None:
    db = str(tmp_path / "mem_unrelated.db")
    init_db(db)
    _seed(db, "SQLAlchemy")
    assert build_memory_context(db, "RAG") is None
    vec = _seed(db, "vector indexes")
    ctx = build_memory_context(db, "vector retrieval")
    assert ctx is not None
    assert ctx.reused_from == vec.id
    assert "related concept" in ctx.framing_note
