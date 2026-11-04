"""list_accomplishments unit tests: ordering, hydration, filters, purity.

Facts seeded via the real create_facts over real chunk rows (zero-vector
embeddings) — no network, no embedding model. Deterministic fake clock for
ordering asserts (never sleep-based).
"""

from pathlib import Path

import pytest

from app.db.artifacts import store_artifact
from app.db.chunks import get_chunks_by_artifacts
from app.db.connection import connect, init_db
from app.db.facts import FactCreate, FactLinkCreate, create_facts, list_accomplishments
from app.ingest.chunker import chunk_text


class _FakeStamp:
    def __init__(self, tick: int) -> None:
        self.tick = tick

    def isoformat(self) -> str:
        return f"2026-11-04T00:00:00.{self.tick:06d}+00:00"


class _FakeClock:
    def __init__(self) -> None:
        self.ticks = 0

    def now(self, tz=None):
        """Mirror datetime.now(tz) with incrementing stamps (test double)."""
        self.ticks += 1
        return _FakeStamp(self.ticks)


@pytest.fixture()
def _clock(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    clock = _FakeClock()
    monkeypatch.setattr("app.db.facts.datetime", clock)
    return clock


def _db(tmp_path: Path, name: str = "acc.db") -> str:
    db = str(tmp_path / name)
    init_db(db)
    return db


def _seed_chunks(db: str) -> list[int]:
    content = "Work log paragraph one.\n\nWork log paragraph two is longer."
    chunks = chunk_text(content)
    aid = store_artifact(
        db_path=db,
        source_type="note",
        title="log",
        content=content,
        content_hash="h",
        origin_json="{}",
        created_at="2026-11-04T00:00:00+00:00",
        chunks=chunks,
        embeddings=[[0.0] * 384 for _ in chunks],
    )
    return [c.id for c in get_chunks_by_artifacts(db, [aid])[aid]]


def _make(
    fact_id: str,
    kind: str,
    summary: str,
    skills: list[str],
    chunk_ids: list[int],
    status: str = "completed",
    links: list[FactLinkCreate] | None = None,
) -> tuple[str, FactCreate, list[FactLinkCreate]]:
    return (
        fact_id,
        FactCreate(
            kind=kind,
            status=status,
            summary=summary,
            skills=skills,
            confidence=0.9,
            chunk_ids=chunk_ids,
        ),
        links or [],
    )


def _counts(db: str) -> tuple[int, int, int]:
    conn = connect(db)
    try:
        facts = conn.execute("SELECT COUNT(*) AS n FROM facts").fetchone()["n"]
        chunks = conn.execute("SELECT COUNT(*) AS n FROM fact_chunks").fetchone()["n"]
        links = conn.execute("SELECT COUNT(*) AS n FROM fact_links").fetchone()["n"]
    finally:
        conn.close()
    return (facts, chunks, links)


def test_empty_db_returns_empty(tmp_path: Path, _clock: _FakeClock) -> None:
    assert list_accomplishments(_db(tmp_path)) == []


def test_only_accomplishment_kind_listed(tmp_path: Path, _clock: _FakeClock) -> None:
    db = _db(tmp_path)
    cids = _seed_chunks(db)
    create_facts(
        db_path=db,
        items=[
            _make("fact-01", "decision", "Chose retries.", ["python"], cids),
            _make("fact-02", "accomplishment", "Shipped retries.", ["python"], cids),
            _make("fact-03", "skill", "Knows backoff.", ["python"], cids),
            _make("fact-04", "problem", "Timeouts flaked.", ["python"], cids),
        ],
        model="m",
        prompt_version="extract-v1",
    )
    got = list_accomplishments(db)
    assert [f.fact_id for f in got] == ["fact-02"]


def test_newest_first_order(tmp_path: Path, _clock: _FakeClock) -> None:
    db = _db(tmp_path)
    cids = _seed_chunks(db)
    for i in range(3):
        create_facts(
            db_path=db,
            items=[_make(f"fact-0{i}", "accomplishment", f"Did thing {i}.", [], cids)],
            model="m",
            prompt_version="extract-v1",
        )
    got = list_accomplishments(db)
    assert [f.fact_id for f in got] == ["fact-02", "fact-01", "fact-00"]


def test_hydration_echoes_chunks_and_links(tmp_path: Path, _clock: _FakeClock) -> None:
    db = _db(tmp_path)
    cids = _seed_chunks(db)
    create_facts(
        db_path=db,
        items=[
            _make(
                "fact-01",
                "accomplishment",
                "Shipped retries.",
                ["python"],
                cids,
                links=[FactLinkCreate("fact-01", "fact-02", "decided")],
            ),
            _make("fact-02", "accomplishment", "Picked backoff.", ["design"], cids[:1]),
        ],
        model="m",
        prompt_version="extract-v1",
    )
    by_id = {f.fact_id: f for f in list_accomplishments(db)}
    assert by_id["fact-01"].chunk_ids == sorted(cids)
    assert [(link.to_fact, link.relation) for link in by_id["fact-01"].links] == [
        ("fact-02", "decided")
    ]
    assert by_id["fact-02"].chunk_ids == cids[:1]
    assert by_id["fact-02"].links == []


def test_q_matches_summary(tmp_path: Path, _clock: _FakeClock) -> None:
    db = _db(tmp_path)
    cids = _seed_chunks(db)
    create_facts(
        db_path=db,
        items=[
            _make("fact-01", "accomplishment", "Fixed the checkout timeout.", [], cids),
            _make("fact-02", "accomplishment", "Wrote onboarding docs.", [], cids),
        ],
        model="m",
        prompt_version="extract-v1",
    )
    got = list_accomplishments(db, q="checkout")
    assert [f.fact_id for f in got] == ["fact-01"]


def test_q_matches_skill(tmp_path: Path, _clock: _FakeClock) -> None:
    db = _db(tmp_path)
    cids = _seed_chunks(db)
    create_facts(
        db_path=db,
        items=[
            _make("fact-01", "accomplishment", "Did a thing.", ["kubernetes"], cids),
            _make("fact-02", "accomplishment", "Did another.", ["python"], cids),
        ],
        model="m",
        prompt_version="extract-v1",
    )
    got = list_accomplishments(db, q="kuber")
    assert [f.fact_id for f in got] == ["fact-01"]


def test_q_multi_term_is_and(tmp_path: Path, _clock: _FakeClock) -> None:
    db = _db(tmp_path)
    cids = _seed_chunks(db)
    create_facts(
        db_path=db,
        items=[
            _make("fact-01", "accomplishment", "Fixed checkout timeouts.", [], cids),
            _make("fact-02", "accomplishment", "Fixed login latency.", [], cids),
        ],
        model="m",
        prompt_version="extract-v1",
    )
    got = list_accomplishments(db, q="fixed checkout")
    assert [f.fact_id for f in got] == ["fact-01"]


def test_q_case_insensitive(tmp_path: Path, _clock: _FakeClock) -> None:
    db = _db(tmp_path)
    cids = _seed_chunks(db)
    create_facts(
        db_path=db,
        items=[_make("fact-01", "accomplishment", "Shipped RETRY logic.", [], cids)],
        model="m",
        prompt_version="extract-v1",
    )
    assert [f.fact_id for f in list_accomplishments(db, q="retry")] == ["fact-01"]


def test_q_no_match_returns_empty(tmp_path: Path, _clock: _FakeClock) -> None:
    db = _db(tmp_path)
    cids = _seed_chunks(db)
    create_facts(
        db_path=db,
        items=[_make("fact-01", "accomplishment", "Shipped retries.", ["python"], cids)],
        model="m",
        prompt_version="extract-v1",
    )
    assert list_accomplishments(db, q="nonsense-term") == []


def test_skill_exact_case_insensitive(tmp_path: Path, _clock: _FakeClock) -> None:
    db = _db(tmp_path)
    cids = _seed_chunks(db)
    create_facts(
        db_path=db,
        items=[
            _make("fact-01", "accomplishment", "Did a thing.", ["PostgreSQL"], cids),
            _make("fact-02", "accomplishment", "Did another.", ["python"], cids),
        ],
        model="m",
        prompt_version="extract-v1",
    )
    got = list_accomplishments(db, skill="postgresql")
    assert [f.fact_id for f in got] == ["fact-01"]


def test_skill_substring_does_not_match(tmp_path: Path, _clock: _FakeClock) -> None:
    db = _db(tmp_path)
    cids = _seed_chunks(db)
    create_facts(
        db_path=db,
        items=[_make("fact-01", "accomplishment", "Did a thing.", ["javascript"], cids)],
        model="m",
        prompt_version="extract-v1",
    )
    assert list_accomplishments(db, skill="java") == []


def test_q_and_skill_combined(tmp_path: Path, _clock: _FakeClock) -> None:
    db = _db(tmp_path)
    cids = _seed_chunks(db)
    create_facts(
        db_path=db,
        items=[
            _make("fact-01", "accomplishment", "Fixed checkout.", ["python"], cids),
            _make("fact-02", "accomplishment", "Fixed checkout.", ["go"], cids),
        ],
        model="m",
        prompt_version="extract-v1",
    )
    got = list_accomplishments(db, q="checkout", skill="go")
    assert [f.fact_id for f in got] == ["fact-02"]


def test_garbage_skills_json_treated_as_empty(tmp_path: Path, _clock: _FakeClock) -> None:
    db = _db(tmp_path)
    cids = _seed_chunks(db)
    create_facts(
        db_path=db,
        items=[_make("fact-01", "accomplishment", "Shipped retries.", ["python"], cids)],
        model="m",
        prompt_version="extract-v1",
    )
    conn = connect(db)
    try:
        with conn:
            conn.execute("UPDATE facts SET skills = 'not-json' WHERE id = 'fact-01'")
    finally:
        conn.close()
    got = list_accomplishments(db)
    assert [f.fact_id for f in got] == ["fact-01"]
    assert got[0].skills == []


def test_read_is_side_effect_free(tmp_path: Path, _clock: _FakeClock) -> None:
    db = _db(tmp_path)
    cids = _seed_chunks(db)
    create_facts(
        db_path=db,
        items=[
            _make(
                "fact-01",
                "accomplishment",
                "Shipped retries.",
                ["python"],
                cids,
                links=[FactLinkCreate("fact-01", "fact-02", "resulted_in")],
            ),
            _make("fact-02", "accomplishment", "Picked backoff.", ["design"], cids),
        ],
        model="m",
        prompt_version="extract-v1",
    )
    before = _counts(db)
    list_accomplishments(db)
    list_accomplishments(db, q="shipped")
    list_accomplishments(db, skill="python")
    assert _counts(db) == before
