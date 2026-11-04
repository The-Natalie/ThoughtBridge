"""Conversation memory tests: index → retrieve → label → cascade delete.

Tmp DBs with fake unit-vector passage embeddings (mirrors
test_retrieval.py); no network, no fastembed model.
"""

from pathlib import Path

import pytest

from app.db.artifacts import (
    delete_artifacts_cascade,
    find_conversation_artifacts,
    get_artifact_detail,
)
from app.db.attempts import create_attempt, get_attempt
from app.db.chunks import get_chunk_source_types, get_chunks_by_artifacts, search_bm25_ids
from app.db.connection import connect, init_db
from app.db.conversations import (
    create_conversation_with_turns,
    delete_conversation_cascade,
    get_conversation,
)
from app.db.facts import FactCreate, create_facts
from app.ingest.conversation_memory import index_conversation_turns
from app.ingest.pipeline import ingest_source
from app.retrieval.search import build_fts_match, hybrid_search

DIM = 384
MODEL = "BAAI/bge-small-en-v1.5"
MAXC = 500_000


@pytest.fixture
def db(tmp_path: Path) -> str:
    path = str(tmp_path / "conversation_memory.db")
    init_db(path)
    return path


def _one_hot() -> object:
    n = 0

    def embed(texts: list[str]) -> list[list[float]]:
        nonlocal n
        out = []
        for _ in texts:
            vec = [0.0] * DIM
            vec[n % DIM] = 1.0
            n += 1
            out.append(vec)
        return out

    return embed  # type: ignore[return-value]


def _seed_note(db: str, content: str, embed: object) -> str:
    return ingest_source(
        db_path=db,
        source_type="note",
        title="n",
        content=content,
        origin={"adapter": "text"},
        max_artifact_chars=MAXC,
        embedding_model=MODEL,
        embed_fn=embed,  # type: ignore[arg-type]
    ).artifact_id


def test_index_creates_tagged_artifact(db: str) -> None:
    cid, _ = create_conversation_with_turns(
        db, "qa", [("user", "u1", "evidence", "[]"), ("assistant", "a1", "evidence", "[]")]
    )
    result = index_conversation_turns(
        db_path=db,
        conversation_id=cid,
        kind="qa",
        turns=[("user", "u1"), ("assistant", "a1")],
        turn_start=0,
        max_artifact_chars=MAXC,
        embedding_model=MODEL,
        embed_fn=_one_hot(),  # type: ignore[arg-type]
    )
    assert result.chunk_count == 1
    detail = get_artifact_detail(db, result.artifact_id)
    assert detail is not None
    assert detail.source_type == "tb_conversation"
    assert detail.content == "User: u1\n\nAssistant: a1"
    assert detail.chunks[0].text == "User: u1\n\nAssistant: a1"
    assert detail.title == "u1"
    import json

    assert json.loads(detail.origin) == {
        "adapter": "tb_conversation",
        "conversation_id": cid,
        "kind": "qa",
        "turn_start": "0",
        "turn_end": "1",
    }


def test_index_then_hybrid_search_finds_user_turn(db: str) -> None:
    cid, _ = create_conversation_with_turns(
        db,
        "qa",
        [("user", "we chose quokka caching", "evidence", "[]")],
    )
    index_conversation_turns(
        db_path=db,
        conversation_id=cid,
        kind="qa",
        turns=[("user", "we chose quokka caching"), ("assistant", "noted")],
        turn_start=0,
        max_artifact_chars=MAXC,
        embedding_model=MODEL,
        embed_fn=_one_hot(),  # type: ignore[arg-type]
    )
    hits = hybrid_search(
        db_path=db,
        query="quokka",
        top_k=5,
        embedding_model=MODEL,
        embed_fn=lambda q: [1.0] + [0.0] * (DIM - 1),
    )
    assert len(hits) == 1
    assert "User:" in hits[0].excerpt
    assert "quokka" in hits[0].excerpt


def test_get_chunk_source_types_mixed_and_empty(db: str) -> None:
    assert get_chunk_source_types(db, []) == {}
    embed = _one_hot()
    note_id = _seed_note(db, "wombat notes", embed)
    cid, _ = create_conversation_with_turns(db, "qa", [("user", "u", "evidence", "[]")])
    conv_result = index_conversation_turns(
        db_path=db,
        conversation_id=cid,
        kind="qa",
        turns=[("user", "u")],
        turn_start=0,
        max_artifact_chars=MAXC,
        embedding_model=MODEL,
        embed_fn=embed,  # type: ignore[arg-type]
    )
    grouped = get_chunks_by_artifacts(db, [note_id, conv_result.artifact_id])
    note_chunk = grouped[note_id][0].id
    conv_chunk = grouped[conv_result.artifact_id][0].id
    assert get_chunk_source_types(db, [note_chunk, conv_chunk]) == {
        note_chunk: "note",
        conv_chunk: "tb_conversation",
    }


def test_find_conversation_artifacts_filters(db: str) -> None:
    embed = _one_hot()
    _seed_note(db, "plain note", embed)
    cid_a, _ = create_conversation_with_turns(db, "qa", [("user", "a", "evidence", "[]")])
    cid_b, _ = create_conversation_with_turns(db, "interview", [("user", "b", "evidence", "[]")])
    first = index_conversation_turns(
        db_path=db,
        conversation_id=cid_a,
        kind="qa",
        turns=[("user", "a1")],
        turn_start=0,
        max_artifact_chars=MAXC,
        embedding_model=MODEL,
        embed_fn=embed,  # type: ignore[arg-type]
    )
    second = index_conversation_turns(
        db_path=db,
        conversation_id=cid_a,
        kind="qa",
        turns=[("user", "a2")],
        turn_start=1,
        max_artifact_chars=MAXC,
        embedding_model=MODEL,
        embed_fn=embed,  # type: ignore[arg-type]
    )
    other = index_conversation_turns(
        db_path=db,
        conversation_id=cid_b,
        kind="interview",
        turns=[("user", "b1")],
        turn_start=0,
        max_artifact_chars=MAXC,
        embedding_model=MODEL,
        embed_fn=embed,  # type: ignore[arg-type]
    )
    assert find_conversation_artifacts(db, cid_a) == [
        first.artifact_id,
        second.artifact_id,
    ]
    assert find_conversation_artifacts(db, cid_b) == [other.artifact_id]
    assert find_conversation_artifacts(db, "missing") == []


def test_delete_unknown_conversation_returns_none(db: str) -> None:
    assert delete_conversation_cascade(db, "nope") is None


def _vec_rowids(db: str) -> set[int]:
    conn = connect(db)
    try:
        return {r[0] for r in conn.execute("SELECT rowid FROM chunks_vec").fetchall()}
    finally:
        conn.close()


def test_delete_cascade_removes_everything_derived(db: str) -> None:
    embed = _one_hot()
    note_id = _seed_note(db, "wombat runbook", embed)
    cid, _ = create_conversation_with_turns(
        db,
        "qa",
        [
            ("user", "quokka decision", "evidence", "[]"),
            ("assistant", "ack", "evidence", "[]"),
        ],
    )
    conv_result = index_conversation_turns(
        db_path=db,
        conversation_id=cid,
        kind="qa",
        turns=[("user", "quokka decision"), ("assistant", "ack")],
        turn_start=0,
        max_artifact_chars=MAXC,
        embedding_model=MODEL,
        embed_fn=embed,  # type: ignore[arg-type]
    )
    grouped = get_chunks_by_artifacts(db, [note_id, conv_result.artifact_id])
    note_chunk = grouped[note_id][0].id
    conv_chunk = grouped[conv_result.artifact_id][0].id
    assert conv_chunk in _vec_rowids(db)
    assert conv_chunk in search_bm25_ids(db, build_fts_match("quokka"), 10)

    fact_ids = create_facts(
        db_path=db,
        items=[
            (
                "f-conv-only",
                FactCreate(
                    kind="decision",
                    status="completed",
                    summary="chose quokka",
                    skills=["judgment"],
                    confidence=0.9,
                    chunk_ids=[conv_chunk],
                ),
                [],
            ),
            (
                "f-shared",
                FactCreate(
                    kind="accomplishment",
                    status="completed",
                    summary="quokka per wombat runbook",
                    skills=["debugging"],
                    confidence=0.8,
                    chunk_ids=[conv_chunk, note_chunk],
                ),
                [],
            ),
            (
                "f-note-only",
                FactCreate(
                    kind="problem",
                    status="proposed",
                    summary="wombat flake",
                    skills=[],
                    confidence=0.5,
                    chunk_ids=[note_chunk],
                ),
                [],
            ),
        ],
        model="m",
        prompt_version="extract-v2",
    )
    assert fact_ids == ["f-conv-only", "f-shared", "f-note-only"]
    attempt_id = create_attempt(
        db,
        mode="interview",
        question_kind="experience",
        explanation_id=None,
        question="q",
        conversation_id=cid,
        reference_json={},
    )

    counts = delete_conversation_cascade(db, cid)
    assert counts is not None
    assert counts.conversation_id == cid
    assert counts.turns == 2
    assert counts.artifacts == 1
    assert counts.chunks == 1
    assert counts.facts == 1
    assert counts.unlinked_facts == 1

    assert get_conversation(db, cid) is None
    assert get_artifact_detail(db, conv_result.artifact_id) is None
    assert conv_chunk not in _vec_rowids(db)
    assert note_chunk in _vec_rowids(db)
    assert search_bm25_ids(db, build_fts_match("quokka"), 10) == []
    assert search_bm25_ids(db, build_fts_match("wombat"), 10) == [note_chunk]
    conn = connect(db)
    try:
        remaining_facts = {r[0] for r in conn.execute("SELECT id FROM facts").fetchall()}
        remaining_links = conn.execute("SELECT fact_id, chunk_id FROM fact_chunks").fetchall()
    finally:
        conn.close()
    assert remaining_facts == {"f-shared", "f-note-only"}
    assert ("f-shared", conv_chunk) not in [(r[0], r[1]) for r in remaining_links]
    assert ("f-shared", note_chunk) in [(r[0], r[1]) for r in remaining_links]
    assert get_artifact_detail(db, note_id) is not None
    attempt = get_attempt(db, attempt_id)
    assert attempt is not None
    assert attempt.conversation_id is None


def test_delete_multi_append_conversation_removes_all_artifacts(db: str) -> None:
    embed = _one_hot()
    cid, _ = create_conversation_with_turns(db, "qa", [("user", "u0", "evidence", "[]")])
    first = index_conversation_turns(
        db_path=db,
        conversation_id=cid,
        kind="qa",
        turns=[("user", "u0"), ("assistant", "a0")],
        turn_start=0,
        max_artifact_chars=MAXC,
        embedding_model=MODEL,
        embed_fn=embed,  # type: ignore[arg-type]
    )
    second = index_conversation_turns(
        db_path=db,
        conversation_id=cid,
        kind="qa",
        turns=[("user", "u1"), ("assistant", "a1")],
        turn_start=2,
        max_artifact_chars=MAXC,
        embedding_model=MODEL,
        embed_fn=embed,  # type: ignore[arg-type]
    )
    counts = delete_conversation_cascade(db, cid)
    assert counts is not None
    assert counts.artifacts == 2
    assert counts.chunks == 2
    assert get_artifact_detail(db, first.artifact_id) is None
    assert get_artifact_detail(db, second.artifact_id) is None
    assert find_conversation_artifacts(db, cid) == []


def test_delete_conversation_without_artifacts_keeps_zeros(db: str) -> None:
    cid, _ = create_conversation_with_turns(db, "qa", [("user", "never indexed", "evidence", "[]")])
    counts = delete_conversation_cascade(db, cid)
    assert counts is not None
    assert (counts.turns, counts.artifacts, counts.chunks, counts.facts) == (1, 0, 0, 0)
    assert counts.unlinked_facts == 0
    assert get_conversation(db, cid) is None


def test_delete_artifacts_wrapper_smoke(db: str) -> None:
    assert delete_artifacts_cascade(db, []) == {
        "artifacts": 0,
        "chunks": 0,
        "facts": 0,
        "unlinked_facts": 0,
    }
    note_id = _seed_note(db, "disposable wombat", _one_hot())
    grouped = get_chunks_by_artifacts(db, [note_id])
    chunk_id = grouped[note_id][0].id
    create_facts(
        db_path=db,
        items=[
            (
                "f-gone",
                FactCreate(
                    kind="problem",
                    status="proposed",
                    summary="gone",
                    skills=[],
                    confidence=0.5,
                    chunk_ids=[chunk_id],
                ),
                [],
            ),
        ],
        model="m",
        prompt_version="extract-v2",
    )
    assert delete_artifacts_cascade(db, [note_id, note_id]) == {
        "artifacts": 1,
        "chunks": 1,
        "facts": 1,
        "unlinked_facts": 0,
    }
    assert get_artifact_detail(db, note_id) is None
