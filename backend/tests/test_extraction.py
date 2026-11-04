"""Extraction orchestration tests: validation, guards, seams, atomicity.

Stubbed chat/career/persist — no network, no embedding model.
Repository-backed subset uses tmp DBs via init_db.
"""

import asyncio
import json
import re
import sqlite3
from pathlib import Path

import pytest

from app.core.grounding import EXTRACTION_PROMPT_VERSION
from app.db.artifacts import store_artifact
from app.db.chunks import get_chunks_by_artifacts
from app.db.connection import connect, init_db
from app.db.facts import FactCreate, FactLinkCreate, create_facts
from app.ingest.chunker import Chunk, chunk_text
from app.llm.extraction import (
    EXTRACTION_MAX_TOKENS,
    MAX_EXTRACTION_CHARS,
    CareerContext,
    EmptyExtractionError,
    ExtractionTooLargeError,
    ExtractionValidationError,
    UnknownArtifactError,
    no_career,
    run_extraction,
)

CONTENT_A = (
    "Work log Monday. I investigated the slow checkout endpoint and found an N+1 "
    "query in the order loader. I considered adding a cache layer but rejected it "
    "because the query itself was wrong. I shipped a batched loader fix instead."
)
CONTENT_B = (
    "Work log Tuesday. I explored migrating the session store to Redis. The team "
    "has not decided yet. I also want to benchmark connection pooling next week."
)

HEX32 = re.compile(r"[0-9a-f]{32}")


def _chat_for(payloads: list[str], record: list):
    queue = list(payloads)

    async def fake(messages: list[dict[str, str]], max_tokens: int) -> str:
        record.append((messages, max_tokens))
        assert queue, "chat called more times than payloads"
        return queue.pop(0)

    return fake


async def _boom_chat(messages: list[dict[str, str]], max_tokens: int) -> str:
    raise AssertionError("chat must not be called")


def _boom_persist(items, model: str, prompt_version: str) -> list[str]:
    raise AssertionError("persist must not be called")


def _store(db: str, title: str, content: str, chunks: list[Chunk] | None = None) -> str:
    used = chunk_text(content) if chunks is None else chunks
    return store_artifact(
        db_path=db,
        source_type="note",
        title=title,
        content=content,
        content_hash="h",
        origin_json="{}",
        created_at="2026-11-03T00:00:00+00:00",
        chunks=used,
        embeddings=[[0.0] * 384 for _ in used],
    )


def _seed_artifacts(db: str) -> tuple[list[str], list[int]]:
    aids = [_store(db, "log-a", CONTENT_A), _store(db, "log-b", CONTENT_B)]
    grouped = get_chunks_by_artifacts(db, aids)
    cids = [c.id for aid in aids for c in grouped[aid]]
    assert len(cids) == 2
    return aids, cids


def _fact(chunk_ids: list[int], **overrides: object) -> dict:
    fact: dict[str, object] = {
        "kind": "accomplishment",
        "status": "completed",
        "summary": "Shipped the batched loader fix.",
        "skills": ["debugging"],
        "confidence": 0.9,
        "chunk_ids": chunk_ids,
        "links": [],
    }
    fact.update(overrides)
    return fact


def _counts(db: str) -> tuple[int, int, int]:
    conn = connect(db)
    try:
        n_facts = conn.execute("SELECT COUNT(*) AS n FROM facts").fetchone()["n"]
        n_fc = conn.execute("SELECT COUNT(*) AS n FROM fact_chunks").fetchone()["n"]
        n_fl = conn.execute("SELECT COUNT(*) AS n FROM fact_links").fetchone()["n"]
    finally:
        conn.close()
    return (n_facts, n_fc, n_fl)


def _run(**kwargs: object):
    return asyncio.run(run_extraction(**kwargs))  # type: ignore[arg-type]


def test_happy_path_shape_single_call_budget(tmp_path: Path) -> None:
    db = str(tmp_path / "ex1.db")
    init_db(db)
    aids, cids = _seed_artifacts(db)
    payload = {
        "facts": [
            _fact([cids[0]], kind="problem", status="completed", summary="Slow checkout."),
            _fact(
                [cids[0]],
                kind="decision",
                status="rejected",
                summary="Rejected the cache layer: the query was wrong.",
                links=[{"to": 0, "relation": "rejected_because"}],
            ),
            _fact(
                [cids[1]],
                kind="accomplishment",
                status="completed",
                summary="Shipped the batched loader.",
                links=[{"to": 1, "relation": "decided"}],
            ),
        ]
    }
    record: list = []
    captured: dict = {}

    def persist(items, model: str, prompt_version: str) -> list[str]:
        captured["items"] = items
        captured["model"] = model
        captured["prompt_version"] = prompt_version
        return [fid for fid, _, _ in items]

    result = _run(
        artifact_ids=aids,
        db_path=db,
        chat_fn=_chat_for([json.dumps(payload)], record),
        career_fn=no_career,
        model="test-model",
        persist_fn=persist,
    )
    assert len(record) == 1
    assert [budget for _, budget in record] == [EXTRACTION_MAX_TOKENS]
    assert len(result.facts) == 3
    assert all(HEX32.fullmatch(f.fact_id) for f in result.facts)
    assert len({f.fact_id for f in result.facts}) == 3
    assert result.facts[0].chunk_ids == [cids[0]]
    assert result.facts[2].chunk_ids == [cids[1]]
    assert result.facts[1].links[0].to_fact == result.facts[0].fact_id
    assert result.facts[1].links[0].relation == "rejected_because"
    assert result.facts[2].links[0].to_fact == result.facts[1].fact_id
    systems = [m for m in record[0][0] if m["role"] == "system"]
    assert len(systems) == 1


def test_persist_receives_model_and_prompt_version(tmp_path: Path) -> None:
    db = str(tmp_path / "ex2.db")
    init_db(db)
    aids, cids = _seed_artifacts(db)
    captured: dict = {}

    def persist(items, model: str, prompt_version: str) -> list[str]:
        captured["model"] = model
        captured["prompt_version"] = prompt_version
        return [fid for fid, _, _ in items]

    _run(
        artifact_ids=aids,
        db_path=db,
        chat_fn=_chat_for([json.dumps({"facts": [_fact([cids[0]])]})], []),
        career_fn=no_career,
        model="model-xyz",
        persist_fn=persist,
    )
    assert captured == {"model": "model-xyz", "prompt_version": EXTRACTION_PROMPT_VERSION}
    assert EXTRACTION_PROMPT_VERSION == "extract-v2"


def test_malformed_json_raises_and_skips_persist(tmp_path: Path) -> None:
    db = str(tmp_path / "ex3.db")
    init_db(db)
    aids, _ = _seed_artifacts(db)
    with pytest.raises(ExtractionValidationError, match="malformed"):
        _run(
            artifact_ids=aids,
            db_path=db,
            chat_fn=_chat_for(["not json"], []),
            career_fn=no_career,
            model="m",
            persist_fn=_boom_persist,
        )


def test_unknown_chunk_id_raises_naming_id(tmp_path: Path) -> None:
    db = str(tmp_path / "ex4.db")
    init_db(db)
    aids, cids = _seed_artifacts(db)
    with pytest.raises(ExtractionValidationError, match="9999"):
        _run(
            artifact_ids=aids,
            db_path=db,
            chat_fn=_chat_for([json.dumps({"facts": [_fact([cids[0], 9999])]})], []),
            career_fn=no_career,
            model="m",
            persist_fn=_boom_persist,
        )


def test_empty_chunk_ids_raises(tmp_path: Path) -> None:
    db = str(tmp_path / "ex5.db")
    init_db(db)
    aids, _ = _seed_artifacts(db)
    with pytest.raises(ExtractionValidationError, match="cites no chunks"):
        _run(
            artifact_ids=aids,
            db_path=db,
            chat_fn=_chat_for([json.dumps({"facts": [_fact([])]})], []),
            career_fn=no_career,
            model="m",
            persist_fn=_boom_persist,
        )


def test_blank_summary_raises(tmp_path: Path) -> None:
    db = str(tmp_path / "ex6.db")
    init_db(db)
    aids, cids = _seed_artifacts(db)
    with pytest.raises(ExtractionValidationError, match="blank summary"):
        _run(
            artifact_ids=aids,
            db_path=db,
            chat_fn=_chat_for([json.dumps({"facts": [_fact([cids[0]], summary="  ")]})], []),
            career_fn=no_career,
            model="m",
            persist_fn=_boom_persist,
        )


def test_confidence_out_of_range_raises(tmp_path: Path) -> None:
    db = str(tmp_path / "ex7.db")
    init_db(db)
    aids, cids = _seed_artifacts(db)
    for bad in (-0.1, 1.5):
        with pytest.raises(ExtractionValidationError, match="malformed"):
            _run(
                artifact_ids=aids,
                db_path=db,
                chat_fn=_chat_for([json.dumps({"facts": [_fact([cids[0]], confidence=bad)]})], []),
                career_fn=no_career,
                model="m",
                persist_fn=_boom_persist,
            )


def test_bad_enums_raise(tmp_path: Path) -> None:
    db = str(tmp_path / "ex8.db")
    init_db(db)
    aids, cids = _seed_artifacts(db)
    bads = [
        _fact([cids[0]], kind="nope"),
        _fact([cids[0]], status="nope"),
        _fact([cids[0]], links=[{"to": 0, "relation": "nope"}]),
    ]
    for bad in bads:
        with pytest.raises(ExtractionValidationError, match="malformed"):
            _run(
                artifact_ids=aids,
                db_path=db,
                chat_fn=_chat_for([json.dumps({"facts": [bad]})], []),
                career_fn=no_career,
                model="m",
                persist_fn=_boom_persist,
            )


def test_dangling_link_raises(tmp_path: Path) -> None:
    db = str(tmp_path / "ex9.db")
    init_db(db)
    aids, cids = _seed_artifacts(db)
    with pytest.raises(ExtractionValidationError, match="out-of-range"):
        _run(
            artifact_ids=aids,
            db_path=db,
            chat_fn=_chat_for(
                [
                    json.dumps(
                        {"facts": [_fact([cids[0]], links=[{"to": 5, "relation": "decided"}])]}
                    )
                ],
                [],
            ),
            career_fn=no_career,
            model="m",
            persist_fn=_boom_persist,
        )


def test_self_link_raises(tmp_path: Path) -> None:
    db = str(tmp_path / "ex10.db")
    init_db(db)
    aids, cids = _seed_artifacts(db)
    with pytest.raises(ExtractionValidationError, match="itself"):
        _run(
            artifact_ids=aids,
            db_path=db,
            chat_fn=_chat_for(
                [
                    json.dumps(
                        {"facts": [_fact([cids[0]], links=[{"to": 0, "relation": "decided"}])]}
                    )
                ],
                [],
            ),
            career_fn=no_career,
            model="m",
            persist_fn=_boom_persist,
        )


def test_empty_facts_ok_and_skips_persist(tmp_path: Path) -> None:
    db = str(tmp_path / "ex11.db")
    init_db(db)
    aids, _ = _seed_artifacts(db)
    result = _run(
        artifact_ids=aids,
        db_path=db,
        chat_fn=_chat_for([json.dumps({"facts": []})], []),
        career_fn=no_career,
        model="m",
        persist_fn=_boom_persist,
    )
    assert result.facts == []
    assert _counts(db) == (0, 0, 0)


def test_unknown_artifact_never_calls_chat(tmp_path: Path) -> None:
    db = str(tmp_path / "ex12.db")
    init_db(db)
    aids, _ = _seed_artifacts(db)
    with pytest.raises(UnknownArtifactError, match="missing-id"):
        _run(
            artifact_ids=[*aids, "missing-id"],
            db_path=db,
            chat_fn=_boom_chat,
            career_fn=no_career,
            model="m",
            persist_fn=_boom_persist,
        )


def test_over_cap_never_calls_chat(tmp_path: Path) -> None:
    db = str(tmp_path / "ex13.db")
    init_db(db)
    aid = _store(db, "big", "alpha beta " * 3000)
    assert sum(len(c.text) for c in get_chunks_by_artifacts(db, [aid])[aid]) > MAX_EXTRACTION_CHARS
    with pytest.raises(ExtractionTooLargeError, match="MAX_EXTRACTION_CHARS"):
        _run(
            artifact_ids=[aid],
            db_path=db,
            chat_fn=_boom_chat,
            career_fn=no_career,
            model="m",
            persist_fn=_boom_persist,
        )


def test_career_block_reaches_prompt(tmp_path: Path) -> None:
    db = str(tmp_path / "ex14.db")
    init_db(db)
    aids, cids = _seed_artifacts(db)
    career = CareerContext(
        current_role="backend dev",
        past_roles=["intern"],
        target_career="staff engineer",
        target_position="TARGET-POSITION-XYZ",
    )
    record: list = []
    _run(
        artifact_ids=aids,
        db_path=db,
        chat_fn=_chat_for([json.dumps({"facts": [_fact([cids[0]])]})], record),
        career_fn=lambda: career,
        model="m",
        persist_fn=lambda items, model, pv: [fid for fid, _, _ in items],
    )
    systems = [m["content"] for m in record[0][0] if m["role"] == "system"]
    assert len(systems) == 2
    assert "TARGET-POSITION-XYZ" in systems[1]
    assert "staff engineer" in systems[1]


def test_real_repository_atomic_success_and_failure(tmp_path: Path) -> None:
    db = str(tmp_path / "ex15.db")
    init_db(db)
    aids, cids = _seed_artifacts(db)
    good = {
        "facts": [
            _fact([cids[0]]),
            _fact([cids[1]], links=[{"to": 0, "relation": "decided"}]),
        ]
    }

    async def run(payload: str):
        return await run_extraction(
            artifact_ids=aids,
            db_path=db,
            chat_fn=_chat_for([payload], []),
            career_fn=no_career,
            model="m",
        )

    result = asyncio.run(run(json.dumps(good)))
    assert len(result.facts) == 2
    assert _counts(db) == (2, 2, 1)

    with pytest.raises(ExtractionValidationError):
        asyncio.run(run("junk"))
    assert _counts(db) == (2, 2, 1)


def test_create_facts_rollback_on_bad_link(tmp_path: Path) -> None:
    db = str(tmp_path / "ex16.db")
    init_db(db)
    _seed_artifacts(db)
    fact = FactCreate(
        kind="problem", status="proposed", summary="s", skills=[], confidence=0.5, chunk_ids=[1]
    )
    items = [
        (
            "f" * 32,
            fact,
            [FactLinkCreate(from_fact_id="f" * 32, to_fact_id="0" * 32, relation="decided")],
        )
    ]
    with pytest.raises(sqlite3.IntegrityError):
        create_facts(db_path=db, items=items, model="m", prompt_version="extract-v1")
    assert _counts(db) == (0, 0, 0)


def test_duplicate_ids_processed_once(tmp_path: Path) -> None:
    db = str(tmp_path / "ex17.db")
    init_db(db)
    aids, cids = _seed_artifacts(db)
    record: list = []
    _run(
        artifact_ids=[aids[0], aids[0], aids[1]],
        db_path=db,
        chat_fn=_chat_for([json.dumps({"facts": [_fact([cids[0]])]})], record),
        career_fn=no_career,
        model="m",
        persist_fn=lambda items, model, pv: [fid for fid, _, _ in items],
    )
    assert len(record) == 1
    user_content = record[0][0][-1]["content"]
    assert user_content.count("Passage [") == 2


def test_cap_boundary_exact_allowed_one_over_rejected(tmp_path: Path) -> None:
    db = str(tmp_path / "ex18.db")
    init_db(db)
    half = MAX_EXTRACTION_CHARS // 2
    exact_chunks = [
        Chunk(text="a" * half, span_start=0, span_end=half, chunk_idx=0),
        Chunk(text="b" * half, span_start=half, span_end=2 * half, chunk_idx=1),
    ]
    exact_id = _store(db, "exact", "x", chunks=exact_chunks)
    over_chunks = [
        Chunk(text="a" * (half + 1), span_start=0, span_end=half + 1, chunk_idx=0),
        Chunk(text="b" * half, span_start=half + 1, span_end=2 * half + 1, chunk_idx=1),
    ]
    over_id = _store(db, "over", "x", chunks=over_chunks)
    grouped = get_chunks_by_artifacts(db, [exact_id, over_id])
    exact_cid = grouped[exact_id][0].id

    record: list = []
    result = _run(
        artifact_ids=[exact_id],
        db_path=db,
        chat_fn=_chat_for([json.dumps({"facts": [_fact([exact_cid])]})], record),
        career_fn=no_career,
        model="m",
        persist_fn=lambda items, model, pv: [fid for fid, _, _ in items],
    )
    assert len(record) == 1
    assert len(result.facts) == 1

    with pytest.raises(ExtractionTooLargeError, match="MAX_EXTRACTION_CHARS"):
        _run(
            artifact_ids=[over_id],
            db_path=db,
            chat_fn=_boom_chat,
            career_fn=no_career,
            model="m",
            persist_fn=_boom_persist,
        )


def test_duplicate_link_triples_store_single_row(tmp_path: Path) -> None:
    db = str(tmp_path / "ex19.db")
    init_db(db)
    aids, cids = _seed_artifacts(db)
    payload = {
        "facts": [
            _fact([cids[0]]),
            _fact(
                [cids[1]],
                links=[
                    {"to": 0, "relation": "decided"},
                    {"to": 0, "relation": "decided"},
                ],
            ),
        ]
    }

    async def run():
        return await run_extraction(
            artifact_ids=aids,
            db_path=db,
            chat_fn=_chat_for([json.dumps(payload)], []),
            career_fn=no_career,
            model="m",
        )

    result = asyncio.run(run())
    assert len(result.facts[1].links) == 2
    assert _counts(db) == (2, 2, 1)


def test_zero_chunk_artifact_never_calls_chat(tmp_path: Path) -> None:
    db = str(tmp_path / "ex20.db")
    init_db(db)
    aid = _store(db, "empty", "", chunks=[])
    with pytest.raises(EmptyExtractionError, match="no chunks"):
        _run(
            artifact_ids=[aid],
            db_path=db,
            chat_fn=_boom_chat,
            career_fn=no_career,
            model="m",
            persist_fn=_boom_persist,
        )
