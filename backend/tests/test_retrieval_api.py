"""Retrieval API contract tests: shapes, top_k, status matrix, openapi.

TestClient over tmp DBs seeded DIRECTLY via the real pipeline with fake
passage vectors (seeding via POST would invoke real fastembed); the
router's `hybrid_search` symbol is stubbed to run the REAL search + legs
+ FTS with a fake query vector, so the suite never downloads the model.
Mirrors `test_ingest_api.py` settings isolation.
"""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.retrieval.search as search_mod
from app.core.config import Settings, get_settings
from app.db.connection import connect, init_db
from app.ingest.pipeline import ingest_source
from app.main import create_app

DIM = 384
MODEL = "BAAI/bge-small-en-v1.5"
MAXC = 500_000


def fake_query(text: str) -> list[float]:
    return [1.0] + [0.0] * (DIM - 1)


def _stub(*args: object, **kwargs: object) -> object:
    kwargs["embed_fn"] = fake_query  # type: ignore[typeddict-item]
    return search_mod.hybrid_search(*args, **kwargs)  # type: ignore[arg-type]


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
    monkeypatch.setattr("app.api.retrieval.get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(_env_file=None))
    yield
    get_settings.cache_clear()


def _client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    seed_notes: list[tuple[str, str]] | None = None,
) -> TestClient:
    db = str(tmp_path / "retrieval_api.db")
    init_db(db)
    n = 0

    def one_hot(texts: list[str]) -> list[list[float]]:
        nonlocal n
        out = []
        for _ in texts:
            vec = [0.0] * DIM
            vec[n % DIM] = 1.0
            n += 1
            out.append(vec)
        return out

    for title, content in seed_notes if seed_notes is not None else [("a", "alpha note")]:
        ingest_source(
            db_path=db,
            source_type="note",
            title=title,
            content=content,
            origin={"adapter": "text"},
            max_artifact_chars=MAXC,
            embedding_model=MODEL,
            embed_fn=one_hot,
        )
    monkeypatch.setenv("DATABASE_PATH", db)
    monkeypatch.setattr("app.api.retrieval.hybrid_search", _stub)
    return TestClient(create_app())


def first_chunk_id(db: str) -> int:
    conn = connect(db)
    try:
        return int(conn.execute("SELECT id FROM chunks ORDER BY id LIMIT 1").fetchone()[0])
    finally:
        conn.close()


def db_of(monkeypatch: pytest.MonkeyPatch) -> str:
    return os.environ["DATABASE_PATH"]


def test_search_returns_200_with_exact_hit_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/v1/retrieval/search", json={"query": "alpha"})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert set(results[0].keys()) == {
        "chunk_id",
        "artifact_id",
        "span",
        "excerpt",
        "rrf_score",
        "bm25_rank",
        "vector_rank",
    }
    assert len(results[0]["span"]) == 2


def test_search_default_top_k_is_8(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path, [(f"n{i}", f"record number {i}") for i in range(10)])
    response = client.post("/api/v1/retrieval/search", json={"query": "record"})
    assert response.status_code == 200
    assert len(response.json()["results"]) == 8


def test_search_explicit_top_k(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path, [(f"n{i}", f"record number {i}") for i in range(5)])
    response = client.post("/api/v1/retrieval/search", json={"query": "record", "top_k": 2})
    assert response.status_code == 200
    assert len(response.json()["results"]) == 2


@pytest.mark.parametrize("top_k", [0, 51, -1])
def test_search_top_k_out_of_range_is_422(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, top_k: int
) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/v1/retrieval/search", json={"query": "alpha", "top_k": top_k})
    assert response.status_code == 422


def test_search_top_k_max_boundary_is_200(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/v1/retrieval/search", json={"query": "alpha", "top_k": 50})
    assert response.status_code == 200


@pytest.mark.parametrize("query", ["", "   "])
def test_search_blank_query_is_422(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, query: str
) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/v1/retrieval/search", json={"query": query})
    assert response.status_code == 422


@pytest.mark.parametrize("query", ['" OR "1"="1', "*", "AND NOT ("])
def test_search_injection_query_returns_200(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, query: str
) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/v1/retrieval/search", json={"query": query})
    assert response.status_code == 200
    assert isinstance(response.json()["results"], list)


def test_search_empty_db_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path, [])
    response = client.post("/api/v1/retrieval/search", json={"query": "anything"})
    assert response.status_code == 200
    assert response.json() == {"results": []}


def test_get_chunk_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    content = "round trip chunk body"
    client = _client(monkeypatch, tmp_path, [("rt", content)])
    cid = first_chunk_id(db_of(monkeypatch))
    response = client.get(f"/api/v1/chunks/{cid}")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"id", "artifact_id", "chunk_idx", "span", "text"}
    assert body["id"] == cid
    assert body["text"] == content
    assert body["span"] == [0, len(content)]
    assert body["chunk_idx"] == 0


def test_get_unknown_chunk_is_404(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.get("/api/v1/chunks/999999")
    assert response.status_code == 404
    assert response.json() == {"detail": "chunk not found"}


def test_get_chunk_non_int_is_422(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    assert client.get("/api/v1/chunks/abc").status_code == 422


def test_openapi_contains_retrieval_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/retrieval/search" in paths
    assert "/api/v1/chunks/{chunk_id}" in paths


def test_dim_mismatch_search_is_500(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    conn = connect(db_of(monkeypatch))
    try:
        with conn:
            conn.execute("UPDATE meta SET value = 'other' WHERE key = 'embedding_model'")
    finally:
        conn.close()
    response = client.post("/api/v1/retrieval/search", json={"query": "alpha"})
    assert response.status_code == 500
    assert "dim=" in response.json()["detail"]
