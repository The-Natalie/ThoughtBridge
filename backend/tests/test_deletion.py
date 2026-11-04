"""Independent-support cascade + delete-then-query residue + no-evidence-mining wiring.

Tmp DBs with fake one-hot passage embeddings (mirrors
test_conversation_memory.py); no network, no fastembed model.
"""

import asyncio
import uuid
from pathlib import Path

import pytest

from app.core.grounding import CONVERSATION_ROLE_RULE
from app.db.artifacts import delete_artifacts_cascade, find_conversation_artifacts
from app.db.chunks import get_chunks, get_chunks_by_artifacts, search_bm25_ids
from app.db.connection import connect, init_db
from app.db.conversations import (
    create_conversation_with_turns,
    delete_conversation_cascade,
    get_conversation,
)
from app.db.facts import FactCreate, FactLinkCreate, create_facts, get_facts_by_ids
from app.ingest.adapters import ROLE_TAGS
from app.ingest.conversation_memory import index_conversation_turns
from app.ingest.pipeline import ingest_source
from app.llm.extraction import no_career, run_extraction
from app.retrieval.search import build_fts_match, hybrid_search

DIM = 384
MODEL = "BAAI/bge-small-en-v1.5"
MAXC = 500_000


@pytest.fixture
def db(tmp_path: Path) -> str:
    path = str(tmp_path / "deletion.db")
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


def _query_vec(query: str) -> list[float]:
    return [1.0] + [0.0] * (DIM - 1)


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


def _vec_rowids(db: str) -> set[int]:
    conn = connect(db)
    try:
        return {r[0] for r in conn.execute("SELECT rowid FROM chunks_vec").fetchall()}
    finally:
        conn.close()


def test_delete_artifact_unlinks_multi_source_fact(db: str) -> None:
    embed = _one_hot()
    note_a = _seed_note(db, "quokka deployment ledger", embed)
    note_b = _seed_note(db, "harbor tide schedule", embed)
    grouped = get_chunks_by_artifacts(db, [note_a, note_b])
    chunks_a = [c.id for c in grouped[note_a]]
    chunks_b = [c.id for c in grouped[note_b]]
    assert chunks_a and chunks_b
    fact1, fact2, fact3 = uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex
    create_facts(
        db_path=db,
        items=[
            (
                fact1,
                FactCreate(
                    kind="problem",
                    status="proposed",
                    summary="quokka flake",
                    skills=[],
                    confidence=0.5,
                    chunk_ids=chunks_a,
                ),
                [FactLinkCreate(from_fact_id=fact1, to_fact_id=fact2, relation="considered")],
            ),
            (
                fact2,
                FactCreate(
                    kind="decision",
                    status="completed",
                    summary="quokka per harbor schedule",
                    skills=["judgment"],
                    confidence=0.9,
                    chunk_ids=chunks_a + chunks_b,
                ),
                [FactLinkCreate(from_fact_id=fact2, to_fact_id=fact3, relation="decided")],
            ),
            (
                fact3,
                FactCreate(
                    kind="accomplishment",
                    status="completed",
                    summary="harbor schedule kept",
                    skills=["debugging"],
                    confidence=0.8,
                    chunk_ids=chunks_b,
                ),
                [],
            ),
        ],
        model="test-model",
        prompt_version="extract-v2",
    )
    counts = delete_artifacts_cascade(db, [note_a])
    assert counts == {
        "artifacts": 1,
        "chunks": len(chunks_a),
        "facts": 1,
        "unlinked_facts": 1,
    }
    surviving = get_facts_by_ids(db, [fact1, fact2, fact3])
    assert fact1 not in surviving
    assert surviving[fact2].chunk_ids == chunks_b
    assert surviving[fact3].chunk_ids == chunks_b
    conn = connect(db)
    try:
        orphan_links = conn.execute(
            "SELECT COUNT(*) AS n FROM fact_links WHERE from_fact_id = ? OR to_fact_id = ?",
            (fact1, fact1),
        ).fetchone()["n"]
        survivor_links = conn.execute(
            "SELECT relation FROM fact_links WHERE from_fact_id = ? AND to_fact_id = ?",
            (fact2, fact3),
        ).fetchall()
    finally:
        conn.close()
    assert orphan_links == 0
    assert [r["relation"] for r in survivor_links] == ["decided"]


def test_delete_artifact_removes_vec_and_fts_rows(db: str) -> None:
    embed = _one_hot()
    note_a = _seed_note(db, "quokka deployment ledger", embed)
    chunk_ids = [c.id for c in get_chunks_by_artifacts(db, [note_a])[note_a]]
    assert chunk_ids
    assert set(chunk_ids) <= _vec_rowids(db)
    assert any(
        c in search_bm25_ids(db, build_fts_match("quokka"), 10)  # type: ignore[arg-type]
        for c in chunk_ids
    )
    delete_artifacts_cascade(db, [note_a])
    assert not (set(chunk_ids) & _vec_rowids(db))
    assert search_bm25_ids(db, build_fts_match("quokka"), 10) == []  # type: ignore[arg-type]
    assert get_chunks(db, chunk_ids) == {}


def test_delete_then_query_never_surfaces_deleted_content(db: str) -> None:
    embed = _one_hot()
    note_a = _seed_note(db, "quokka deployment ledger", embed)
    note_b = _seed_note(db, "harbor tide schedule", embed)
    delete_artifacts_cascade(db, [note_a])
    gone = hybrid_search(
        db_path=db,
        query="quokka deployment ledger",
        top_k=8,
        embedding_model=MODEL,
        embed_fn=_query_vec,  # type: ignore[arg-type]
    )
    assert [h.artifact_id for h in gone if h.artifact_id == note_a] == []
    kept = hybrid_search(
        db_path=db,
        query="harbor tide schedule",
        top_k=8,
        embedding_model=MODEL,
        embed_fn=_query_vec,  # type: ignore[arg-type]
    )
    assert any(h.artifact_id == note_b for h in kept)


def test_delete_conversation_then_query_never_surfaces_turns(db: str) -> None:
    cid, _ = create_conversation_with_turns(
        db,
        "qa",
        [
            ("user", "the zephyrfield decision is final", "evidence", "[]"),
            ("assistant", "noted", "evidence", "[]"),
        ],
    )
    index_conversation_turns(
        db_path=db,
        conversation_id=cid,
        kind="qa",
        turns=[("user", "the zephyrfield decision is final"), ("assistant", "noted")],
        turn_start=0,
        max_artifact_chars=MAXC,
        embedding_model=MODEL,
        embed_fn=_one_hot(),  # type: ignore[arg-type]
    )
    assert find_conversation_artifacts(db, cid) != []
    counts = delete_conversation_cascade(db, cid)
    assert counts is not None
    assert get_conversation(db, cid) is None
    assert find_conversation_artifacts(db, cid) == []
    hits = hybrid_search(
        db_path=db,
        query="zephyrfield decision",
        top_k=8,
        embedding_model=MODEL,
        embed_fn=_query_vec,  # type: ignore[arg-type]
    )
    assert hits == []


def test_delete_conversation_artifact_directly_keeps_conversation_row(db: str) -> None:
    cid, _ = create_conversation_with_turns(
        db,
        "qa",
        [
            ("user", "the zephyrfield decision is final", "evidence", "[]"),
            ("assistant", "noted", "evidence", "[]"),
        ],
    )
    index_conversation_turns(
        db_path=db,
        conversation_id=cid,
        kind="qa",
        turns=[("user", "the zephyrfield decision is final"), ("assistant", "noted")],
        turn_start=0,
        max_artifact_chars=MAXC,
        embedding_model=MODEL,
        embed_fn=_one_hot(),  # type: ignore[arg-type]
    )
    artifact_ids = find_conversation_artifacts(db, cid)
    assert len(artifact_ids) == 1
    counts = delete_artifacts_cascade(db, artifact_ids)
    assert counts["artifacts"] == 1
    assert counts["chunks"] >= 1
    detail = get_conversation(db, cid)
    assert detail is not None
    assert [t.content for t in detail.turns] == [
        "the zephyrfield decision is final",
        "noted",
    ]


def test_no_evidence_mining_rule_reaches_extraction_model(db: str) -> None:
    """PROVES: the shared role rule + literal role tags reach the extraction model.

    LIMITATIONS: does not prove the model obeys the rule. Behavioral
    obedience is observed in the L4 live-model spot-check only, which is
    non-deterministic and non-gating by design. No deterministic behavioral
    enforcement exists or is claimed (owner decision 2026-11-04:
    prompt-based enforcement from deliverable 3 stands for the MVP).
    """
    user_text = "we discussed auth options for the service"
    assistant_text = "I suggest migrating the auth service to OAuth2 with PKCE"
    cid, _ = create_conversation_with_turns(
        db,
        "qa",
        [
            ("user", user_text, "evidence", "[]"),
            ("assistant", assistant_text, "evidence", "[]"),
        ],
    )
    index_conversation_turns(
        db_path=db,
        conversation_id=cid,
        kind="qa",
        turns=[("user", user_text), ("assistant", assistant_text)],
        turn_start=0,
        max_artifact_chars=MAXC,
        embedding_model=MODEL,
        embed_fn=_one_hot(),  # type: ignore[arg-type]
    )
    artifact_ids = find_conversation_artifacts(db, cid)
    assert len(artifact_ids) == 1

    captured: list[list[dict[str, str]]] = []

    async def fake_chat(messages: list[dict[str, str]], max_tokens: int) -> str:
        captured.append(messages)
        return '{"facts": []}'

    result = asyncio.run(
        run_extraction(
            artifact_ids=artifact_ids,
            db_path=db,
            chat_fn=fake_chat,  # type: ignore[arg-type]
            career_fn=no_career,
            model="test-model",
        )
    )
    assert result.facts == []
    assert len(captured) == 1
    system_text = "\n".join(m["content"] for m in captured[0] if m["role"] == "system")
    user_message = "\n".join(m["content"] for m in captured[0] if m["role"] == "user")
    assert CONVERSATION_ROLE_RULE in system_text
    assert f"{ROLE_TAGS['user']} {user_text}" in user_message
    assert f"{ROLE_TAGS['assistant']} {assistant_text}" in user_message
