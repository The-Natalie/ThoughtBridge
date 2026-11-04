"""Work API contract tests: extract shape, guard matrix, round-trip persistence.

TestClient over tmp DBs; `run_extraction` / `chat_completion` stubbed
per-test. Never touches the network or the fastembed model. Mirrors
test_learn_api.py settings isolation.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.meta_client import MetaAPIError
from app.db.artifacts import store_artifact
from app.db.career_profile import update_career_profile
from app.db.connection import connect, init_db
from app.db.facts import FactCreate, FactLinkCreate, create_facts
from app.ingest.chunker import chunk_text
from app.llm.extraction import (
    EmptyExtractionError,
    ExtractedFact,
    ExtractedLink,
    ExtractedResult,
    ExtractionTooLargeError,
    ExtractionValidationError,
    UnknownArtifactError,
)
from app.main import create_app

DEV_LOG = (
    "Work log. I fixed the checkout timeout by adding a retry with backoff. "
    "I considered doubling the timeout instead but rejected it because retries "
    "handle transient faults better. I still need to add metrics for retry counts."
)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    for var in (
        "MODEL_API_KEY",
        "META_MODEL",
        "DATABASE_PATH",
        "EMBEDDING_MODEL",
        "MAX_UPLOAD_MB",
        "MAX_ARTIFACT_CHARS",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("app.api.work.get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(_env_file=None))
    yield
    get_settings.cache_clear()


def _client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    db = str(tmp_path / "work_api.db")
    init_db(db)
    monkeypatch.setenv("DATABASE_PATH", db)
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    return TestClient(create_app())


def _store(db: str, content: str = DEV_LOG) -> tuple[str, list[int]]:
    chunks = chunk_text(content)
    aid = store_artifact(
        db_path=db,
        source_type="note",
        title="dev log",
        content=content,
        content_hash="h",
        origin_json="{}",
        created_at="2026-11-03T00:00:00+00:00",
        chunks=chunks,
        embeddings=[[0.0] * 384 for _ in chunks],
    )
    conn = connect(db)
    try:
        rows = conn.execute(
            "SELECT id FROM chunks WHERE artifact_id = ? ORDER BY chunk_idx", (aid,)
        ).fetchall()
    finally:
        conn.close()
    return aid, [r["id"] for r in rows]


def _seeded_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, seed_fn):
    """TestClient over a tmp DB pre-seeded via repo fns; returns (client, db_path)."""
    db = str(tmp_path / "work_api_seeded.db")
    init_db(db)
    seed_fn(db)
    monkeypatch.setenv("DATABASE_PATH", db)
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    return TestClient(create_app()), db


def _extracted() -> ExtractedResult:
    return ExtractedResult(
        facts=[
            ExtractedFact(
                fact_id="a" * 32,
                kind="problem",
                status="completed",
                summary="Checkout timeout.",
                skills=["debugging"],
                confidence=0.9,
                chunk_ids=[1],
                links=[],
            ),
            ExtractedFact(
                fact_id="b" * 32,
                kind="accomplishment",
                status="completed",
                summary="Added retry with backoff.",
                skills=["python"],
                confidence=0.8,
                chunk_ids=[1],
                links=[ExtractedLink(to_fact="a" * 32, relation="decided")],
            ),
        ]
    )


def test_extract_happy_path_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)

    async def fake_run(**kwargs: object) -> ExtractedResult:
        return _extracted()

    monkeypatch.setattr("app.api.work.run_extraction", fake_run)
    response = client.post("/api/v1/work/extract", json={"artifact_ids": ["x" * 32]})
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"facts"}
    assert len(body["facts"]) == 2
    assert set(body["facts"][0].keys()) == {
        "fact_id",
        "kind",
        "status",
        "summary",
        "skills",
        "confidence",
        "chunk_ids",
        "links",
    }
    assert set(body["facts"][1]["links"][0].keys()) == {"to_fact", "relation"}
    assert body["facts"][1]["links"][0]["to_fact"] == "a" * 32


def test_extract_empty_or_missing_ids_422(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)

    async def boom(**kwargs: object) -> ExtractedResult:
        raise AssertionError("run_extraction must not be called")

    monkeypatch.setattr("app.api.work.run_extraction", boom)
    assert client.post("/api/v1/work/extract", json={"artifact_ids": []}).status_code == 422
    assert client.post("/api/v1/work/extract", json={}).status_code == 422


def test_extract_unknown_artifact_404(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)

    async def boom(**kwargs: object) -> ExtractedResult:
        raise UnknownArtifactError("unknown artifact(s): dead")

    monkeypatch.setattr("app.api.work.run_extraction", boom)
    response = client.post("/api/v1/work/extract", json={"artifact_ids": ["dead"]})
    assert response.status_code == 404
    assert "dead" in response.json()["detail"]


def test_extract_empty_422(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)

    async def boom(**kwargs: object) -> ExtractedResult:
        raise EmptyExtractionError("artifacts hold no chunks to extract from")

    monkeypatch.setattr("app.api.work.run_extraction", boom)
    response = client.post("/api/v1/work/extract", json={"artifact_ids": ["x" * 32]})
    assert response.status_code == 422


def test_extract_too_large_413(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)

    async def boom(**kwargs: object) -> ExtractedResult:
        raise ExtractionTooLargeError("over the MAX_EXTRACTION_CHARS=30000 cap")

    monkeypatch.setattr("app.api.work.run_extraction", boom)
    response = client.post("/api/v1/work/extract", json={"artifact_ids": ["x" * 32]})
    assert response.status_code == 413


def test_extract_validation_error_502(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)

    async def boom(**kwargs: object) -> ExtractedResult:
        raise ExtractionValidationError("model returned malformed extraction JSON")

    monkeypatch.setattr("app.api.work.run_extraction", boom)
    response = client.post("/api/v1/work/extract", json={"artifact_ids": ["x" * 32]})
    assert response.status_code == 502


def test_extract_meta_error_502(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)

    async def boom(**kwargs: object) -> ExtractedResult:
        raise MetaAPIError(502, "meta down")

    monkeypatch.setattr("app.api.work.run_extraction", boom)
    response = client.post("/api/v1/work/extract", json={"artifact_ids": ["x" * 32]})
    assert response.status_code == 502


def test_extract_round_trip_persists(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    box: dict = {}

    def seed(db: str) -> None:
        aid, cids = _store(db)
        box["aid"] = aid
        box["cids"] = cids

    client, db = _seeded_client(monkeypatch, tmp_path, seed)
    cids = box["cids"]
    payload = {
        "facts": [
            {
                "kind": "accomplishment",
                "status": "completed",
                "summary": "Fixed the checkout timeout with retry + backoff.",
                "skills": ["debugging"],
                "confidence": 0.9,
                "chunk_ids": [cids[0]],
                "links": [],
            },
            {
                "kind": "decision",
                "status": "rejected",
                "summary": "Rejected doubling the timeout: retries handle transients better.",
                "skills": ["systems thinking"],
                "confidence": 0.8,
                "chunk_ids": [cids[0]],
                "links": [{"to": 0, "relation": "rejected_because"}],
            },
            {
                "kind": "problem",
                "status": "proposed",
                "summary": "Retry-count metrics still missing.",
                "skills": [],
                "confidence": 0.7,
                "chunk_ids": [cids[0]],
                "links": [{"to": 0, "relation": "resulted_in"}],
            },
        ]
    }

    async def fake_chat(*, api_key: str, model: str, messages: list, **kw: object) -> str:
        return json.dumps(payload)

    monkeypatch.setattr("app.api.work.chat_completion", fake_chat)
    response = client.post("/api/v1/work/extract", json={"artifact_ids": [box["aid"]]})
    assert response.status_code == 200
    body = response.json()
    assert [f["status"] for f in body["facts"]] == ["completed", "rejected", "proposed"]
    conn = connect(db)
    try:
        fact_rows = conn.execute("SELECT id FROM facts").fetchall()
        link_rows = conn.execute("SELECT from_fact_id, to_fact_id FROM fact_links").fetchall()
        n_fc = conn.execute("SELECT COUNT(*) AS n FROM fact_chunks").fetchone()["n"]
    finally:
        conn.close()
    stored_ids = {r["id"] for r in fact_rows}
    assert {f["fact_id"] for f in body["facts"]} == stored_ids
    assert len(link_rows) == 2
    assert all(r["to_fact_id"] in stored_ids for r in link_rows)
    assert n_fc == 3


def test_extract_missing_key_502(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    box: dict = {}

    def seed(db: str) -> None:
        box["aid"] = _store(db)[0]

    client, _db = _seeded_client(monkeypatch, tmp_path, seed)
    monkeypatch.delenv("MODEL_API_KEY")
    # NOTE: the Settings object is built per-request from the environment, so
    # deleting the var after client creation still yields an empty key.
    response = client.post("/api/v1/work/extract", json={"artifact_ids": [box["aid"]]})
    assert response.status_code == 502
    assert "MODEL_API_KEY" in response.json()["detail"]


def test_extract_whitespace_ids_422(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)

    async def boom(**kwargs: object) -> ExtractedResult:
        raise AssertionError("run_extraction must not be called")

    monkeypatch.setattr("app.api.work.run_extraction", boom)
    response = client.post("/api/v1/work/extract", json={"artifact_ids": ["   ", ""]})
    assert response.status_code == 422
    assert response.json()["detail"] == "artifact_ids must not be empty"


def test_profile_get_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.get("/api/v1/profile")
    assert response.status_code == 200
    assert response.json() == {
        "current_role": "",
        "past_roles": [],
        "target_career": "",
        "target_position": "",
    }


def test_profile_put_full_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    body = {
        "current_role": "Backend engineer",
        "past_roles": ["QA analyst", "Support engineer"],
        "target_career": "Engineering management",
        "target_position": "Staff backend engineer",
    }
    response = client.put("/api/v1/profile", json=body)
    assert response.status_code == 200
    assert response.json() == body


def test_profile_put_partial_merge(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    client.put(
        "/api/v1/profile",
        json={"current_role": "Backend engineer", "target_position": "Staff"},
    )
    response = client.put("/api/v1/profile", json={"past_roles": ["QA analyst"]})
    assert response.status_code == 200
    assert response.json() == {
        "current_role": "Backend engineer",
        "past_roles": ["QA analyst"],
        "target_career": "",
        "target_position": "Staff",
    }


def test_profile_put_empty_noop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    client.put("/api/v1/profile", json={"current_role": "Backend engineer"})
    response = client.put("/api/v1/profile", json={})
    assert response.status_code == 200
    assert response.json()["current_role"] == "Backend engineer"


def test_profile_put_strips_blank_roles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.put(
        "/api/v1/profile",
        json={"current_role": "  Backend engineer  ", "past_roles": ["  QA  ", "", "   "]},
    )
    assert response.status_code == 200
    assert response.json()["current_role"] == "Backend engineer"
    assert response.json()["past_roles"] == ["QA"]


def test_profile_put_nonstring_role_422(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.put("/api/v1/profile", json={"past_roles": ["ok", 7]})
    assert response.status_code == 422


def test_profile_put_nonstring_scalar_422(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.put("/api/v1/profile", json={"current_role": 7})
    assert response.status_code == 422


def test_profile_get_after_put_persists(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    client.put("/api/v1/profile", json={"target_career": "Management"})
    response = client.get("/api/v1/profile")
    assert response.status_code == 200
    assert response.json()["target_career"] == "Management"


def _seed_acc(db: str) -> dict:
    """Two accomplishments (old/new) + one decision; deterministic created_at."""
    _, cids = _store(db)
    create_facts(
        db_path=db,
        items=[
            (
                "acc-old",
                FactCreate(
                    kind="accomplishment",
                    status="completed",
                    summary="Fixed the checkout timeout.",
                    skills=["python"],
                    confidence=0.9,
                    chunk_ids=[cids[0]],
                ),
                [FactLinkCreate("acc-old", "dec-1", "decided")],
            ),
            (
                "acc-new",
                FactCreate(
                    kind="accomplishment",
                    status="completed",
                    summary="Wrote onboarding docs.",
                    skills=["writing"],
                    confidence=0.8,
                    chunk_ids=[cids[0]],
                ),
                [],
            ),
            (
                "dec-1",
                FactCreate(
                    kind="decision",
                    status="completed",
                    summary="Chose retries over longer timeouts.",
                    skills=[],
                    confidence=0.7,
                    chunk_ids=[cids[0]],
                ),
                [],
            ),
        ],
        model="m",
        prompt_version="extract-v1",
    )
    conn = connect(db)
    try:
        with conn:
            conn.execute(
                "UPDATE facts SET created_at = '2026-11-01T00:00:00+00:00' WHERE id = 'acc-old'"
            )
            conn.execute(
                "UPDATE facts SET created_at = '2026-11-03T00:00:00+00:00' WHERE id = 'acc-new'"
            )
    finally:
        conn.close()
    return {"cids": cids}


def _table_counts(db: str) -> tuple[int, int, int]:
    conn = connect(db)
    try:
        facts = conn.execute("SELECT COUNT(*) AS n FROM facts").fetchone()["n"]
        chunks = conn.execute("SELECT COUNT(*) AS n FROM fact_chunks").fetchone()["n"]
        links = conn.execute("SELECT COUNT(*) AS n FROM fact_links").fetchone()["n"]
    finally:
        conn.close()
    return (facts, chunks, links)


def test_accomplishments_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.get("/api/v1/work/accomplishments")
    assert response.status_code == 200
    assert response.json() == []


def test_accomplishments_shape_order_kinds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client, _db = _seeded_client(monkeypatch, tmp_path, _seed_acc)
    response = client.get("/api/v1/work/accomplishments")
    assert response.status_code == 200
    body = response.json()
    assert [f["fact_id"] for f in body] == ["acc-new", "acc-old"]
    assert set(body[0].keys()) == {
        "fact_id",
        "kind",
        "status",
        "summary",
        "skills",
        "confidence",
        "chunk_ids",
        "links",
    }
    assert body[1]["links"][0] == {"to_fact": "dec-1", "relation": "decided"}
    assert all(f["kind"] == "accomplishment" for f in body)


def test_accomplishments_q_narrows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client, _db = _seeded_client(monkeypatch, tmp_path, _seed_acc)
    response = client.get("/api/v1/work/accomplishments", params={"q": "checkout"})
    assert response.status_code == 200
    assert [f["fact_id"] for f in response.json()] == ["acc-old"]


def test_accomplishments_blank_q_422(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.get("/api/v1/work/accomplishments?q=%20%20")
    assert response.status_code == 422
    assert response.json()["detail"] == "q filter must not be blank"


def test_accomplishments_skill_narrows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client, _db = _seeded_client(monkeypatch, tmp_path, _seed_acc)
    response = client.get("/api/v1/work/accomplishments", params={"skill": "writing"})
    assert response.status_code == 200
    assert [f["fact_id"] for f in response.json()] == ["acc-new"]


def test_accomplishments_blank_skill_422(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.get("/api/v1/work/accomplishments?skill=%20")
    assert response.status_code == 422
    assert response.json()["detail"] == "skill filter must not be blank"


def test_accomplishments_q_skill_combined(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client, _db = _seeded_client(monkeypatch, tmp_path, _seed_acc)
    response = client.get("/api/v1/work/accomplishments", params={"q": "docs", "skill": "writing"})
    assert response.status_code == 200
    assert [f["fact_id"] for f in response.json()] == ["acc-new"]
    response = client.get("/api/v1/work/accomplishments", params={"q": "docs", "skill": "python"})
    assert response.status_code == 200
    assert response.json() == []


def test_accomplishments_reads_preserve_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, db = _seeded_client(monkeypatch, tmp_path, _seed_acc)
    before = _table_counts(db)
    client.get("/api/v1/work/accomplishments")
    client.get("/api/v1/work/accomplishments", params={"q": "checkout"})
    client.get("/api/v1/work/accomplishments", params={"skill": "python"})
    assert _table_counts(db) == before


def _canned_extract(cids: list[int]) -> str:
    return json.dumps(
        {
            "facts": [
                {
                    "kind": "accomplishment",
                    "status": "completed",
                    "summary": "Fixed the checkout timeout.",
                    "skills": ["python"],
                    "confidence": 0.9,
                    "chunk_ids": [cids[0]],
                    "links": [],
                }
            ]
        }
    )


def test_extract_wires_career_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    box: dict = {}

    def seed(db: str) -> None:
        aid, cids = _store(db)
        box["aid"] = aid
        box["cids"] = cids
        update_career_profile(db, None, None, None, "Staff backend engineer")

    client, _db = _seeded_client(monkeypatch, tmp_path, seed)
    recorded: list = []

    async def fake_chat(*, messages: list, **kw: object) -> str:
        recorded.extend(messages)
        return _canned_extract(box["cids"])

    monkeypatch.setattr("app.api.work.chat_completion", fake_chat)
    response = client.post("/api/v1/work/extract", json={"artifact_ids": [box["aid"]]})
    assert response.status_code == 200
    assert "Staff backend engineer" in "\n".join(m["content"] for m in recorded)


def test_extract_empty_profile_no_career_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    box: dict = {}

    def seed(db: str) -> None:
        aid, cids = _store(db)
        box["aid"] = aid
        box["cids"] = cids

    client, _db = _seeded_client(monkeypatch, tmp_path, seed)
    recorded: list = []

    async def fake_chat(*, messages: list, **kw: object) -> str:
        recorded.extend(messages)
        return _canned_extract(box["cids"])

    monkeypatch.setattr("app.api.work.chat_completion", fake_chat)
    response = client.post("/api/v1/work/extract", json={"artifact_ids": [box["aid"]]})
    assert response.status_code == 200
    assert all("Career profile" not in m["content"] for m in recorded)
