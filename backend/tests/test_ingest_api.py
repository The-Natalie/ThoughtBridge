"""Ingest API contract tests: shapes, status codes, caps, lifespan.

TestClient over tmp DBs; the router's `ingest_source` symbol is stubbed to
run the REAL pipeline + repository with fake vectors, so the suite never
downloads the fastembed model. Mirrors `test_health.py` settings isolation.
"""

import pytest
from fastapi.testclient import TestClient

import app.ingest.pipeline as pipeline_mod
from app.core.config import Settings, get_settings
from app.db.connection import EmbeddingDimMismatchError, connect, init_db
from app.main import create_app
from tests.upload_fixtures import blank_pdf_bytes, docx_bytes, minimal_pdf_bytes

DIM = 384


def fake_embed(texts: list[str]) -> list[list[float]]:
    return [[(i + 1) * 0.01] * DIM for i in range(len(texts))]


def _stub(*args: object, **kwargs: object) -> object:
    kwargs["embed_fn"] = fake_embed  # type: ignore[typeddict-item]
    return pipeline_mod.ingest_source(*args, **kwargs)  # type: ignore[arg-type]


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
    monkeypatch.setattr("app.api.ingest.get_settings", lambda: Settings(_env_file=None))
    yield
    get_settings.cache_clear()


def _client(monkeypatch: pytest.MonkeyPatch, tmp_path: object, **env: str) -> TestClient:
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    db = str(tmp_path / "api.db")
    init_db(db)
    monkeypatch.setenv("DATABASE_PATH", db)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("app.api.ingest.ingest_source", _stub)
    return TestClient(create_app())


def _lifespan_settings(monkeypatch: pytest.MonkeyPatch, db_path: str) -> None:
    monkeypatch.setenv("DATABASE_PATH", db_path)
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(_env_file=None))


def test_create_note_returns_201_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/artifacts",
        json={"source_type": "note", "title": "t", "content": "hello world note"},
    )
    assert response.status_code == 201
    body = response.json()
    assert len(body["artifact_id"]) == 32
    assert body["chunks"] >= 1


def test_create_paste_and_summary_return_201(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    client = _client(monkeypatch, tmp_path)
    for source_type in ("paste", "summary"):
        response = client.post(
            "/api/v1/artifacts",
            json={"source_type": source_type, "title": "", "content": "some content here"},
        )
        assert response.status_code == 201


def test_bad_source_type_is_422(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/artifacts",
        json={"source_type": "email", "title": "t", "content": "x"},
    )
    assert response.status_code == 422


def test_empty_and_blank_content_are_422(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    client = _client(monkeypatch, tmp_path)
    assert (
        client.post(
            "/api/v1/artifacts",
            json={"source_type": "note", "title": "t", "content": ""},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/artifacts",
            json={"source_type": "note", "title": "t", "content": "   \n  "},
        ).status_code
        == 422
    )


def test_over_char_cap_is_413(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    client = _client(monkeypatch, tmp_path, MAX_ARTIFACT_CHARS="10")
    response = client.post(
        "/api/v1/artifacts",
        json={"source_type": "note", "title": "t", "content": "x" * 50},
    )
    assert response.status_code == 413


def test_upload_txt_returns_201_with_extracted_chars(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/artifacts/upload", files={"file": ("note.txt", b"upload body", "text/plain")}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["chunks"] >= 1
    assert body["extracted_chars"] == len("upload body")


def test_upload_md_uppercase_returns_201(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/artifacts/upload", files={"file": ("LOG.MD", b"# log", "text/markdown")}
    )
    assert response.status_code == 201


def test_upload_pdf_returns_201_with_pages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/artifacts/upload",
        files={
            "file": ("doc.pdf", minimal_pdf_bytes(["alpha page", "beta page"]), "application/pdf")
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["chunks"] >= 1
    assert body["extracted_chars"] == len("alpha page\n\nbeta page")
    assert body["pages"] == 2
    detail = client.get(f"/api/v1/artifacts/{body['artifact_id']}").json()
    assert detail["content"] == "alpha page\n\nbeta page"
    assert detail["origin"]["adapter"] == "pdf"
    assert detail["origin"]["pages"] == "2"


def test_upload_docx_returns_201_without_pages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    client = _client(monkeypatch, tmp_path)
    raw = docx_bytes(["gamma para"], [[["h1", "h2"], ["v1", "v2"]]])
    response = client.post(
        "/api/v1/artifacts/upload",
        files={
            "file": (
                "notes.docx",
                raw,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["chunks"] >= 1
    assert body["extracted_chars"] == len("gamma para\nh1 | h2\nv1 | v2")
    assert body["pages"] is None
    detail = client.get(f"/api/v1/artifacts/{body['artifact_id']}").json()
    assert detail["content"] == "gamma para\nh1 | h2\nv1 | v2"
    assert detail["origin"]["adapter"] == "docx"


def test_upload_corrupt_pdf_is_400(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/artifacts/upload",
        files={"file": ("evil.pdf", b"%PDF-1.4 garbage", "application/pdf")},
    )
    assert response.status_code == 400
    assert "readable PDF" in response.json()["detail"]
    assert client.get("/api/v1/artifacts").json() == []


def test_upload_corrupt_docx_is_400(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/artifacts/upload",
        files={"file": ("evil.docx", b"not a zip", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "not a valid .docx" in response.json()["detail"]
    assert client.get("/api/v1/artifacts").json() == []


def test_upload_blank_pdf_is_400(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/artifacts/upload",
        files={"file": ("blank.pdf", blank_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "file content blank"
    assert client.get("/api/v1/artifacts").json() == []


def test_upload_pdf_over_char_cap_is_413(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    client = _client(monkeypatch, tmp_path, MAX_ARTIFACT_CHARS="10")
    response = client.post(
        "/api/v1/artifacts/upload",
        files={
            "file": ("big.pdf", minimal_pdf_bytes(["way more than ten chars"]), "application/pdf")
        },
    )
    assert response.status_code == 413
    assert client.get("/api/v1/artifacts").json() == []


def test_upload_txt_pages_is_none(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/artifacts/upload", files={"file": ("note.txt", b"plain text", "text/plain")}
    )
    assert response.status_code == 201
    assert response.json()["pages"] is None


def test_upload_invalid_utf8_is_400(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/artifacts/upload",
        files={"file": ("bad.txt", b"\xff\xfe bad", "text/plain")},
    )
    assert response.status_code == 400


def test_zero_mb_cap_413s_nonempty_but_400s_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    client = _client(monkeypatch, tmp_path, MAX_UPLOAD_MB="0")
    assert (
        client.post(
            "/api/v1/artifacts/upload", files={"file": ("a.txt", b"hi", "text/plain")}
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/api/v1/artifacts/upload", files={"file": ("a.txt", b"", "text/plain")}
        ).status_code
        == 400
    )


def test_upload_blank_file_is_400(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/artifacts/upload", files={"file": ("w.txt", b"   \n  ", "text/plain")}
    )
    assert response.status_code == 400


def test_list_artifacts_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    client = _client(monkeypatch, tmp_path)
    client.post(
        "/api/v1/artifacts",
        json={"source_type": "note", "title": "listed", "content": "listed body"},
    )
    response = client.get("/api/v1/artifacts")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["title"] == "listed"
    assert items[0]["chunk_count"] >= 1
    assert items[0]["fact_count"] == 0


def test_get_artifact_detail_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    client = _client(monkeypatch, tmp_path)
    content = "round trip body text"
    created = client.post(
        "/api/v1/artifacts",
        json={"source_type": "note", "title": "rt", "content": content},
    ).json()
    response = client.get(f"/api/v1/artifacts/{created['artifact_id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["content"] == content
    assert body["chunks"][0]["span"] == [0, len(content)]
    assert body["fact_ids"] == []
    assert body["interpretation_ids"] == []


def test_get_unknown_artifact_is_404(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.get("/api/v1/artifacts/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "artifact not found"}


def test_openapi_contains_ingest_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    client = _client(monkeypatch, tmp_path)
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/artifacts" in paths
    assert "/api/v1/artifacts/upload" in paths
    assert "/api/v1/artifacts/{artifact_id}" in paths


def test_oversized_upload_persists_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    client = _client(monkeypatch, tmp_path, MAX_UPLOAD_MB="0")
    assert (
        client.post(
            "/api/v1/artifacts/upload", files={"file": ("a.txt", b"hi", "text/plain")}
        ).status_code
        == 413
    )
    assert client.get("/api/v1/artifacts").json() == []


def test_lifespan_fresh_init(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    target = tmp_path / "sub" / "fresh.db"
    _lifespan_settings(monkeypatch, str(target))
    with TestClient(create_app()) as client:
        assert target.exists()
        conn = connect(str(target))
        try:
            row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        finally:
            conn.close()
        assert row is not None
        assert client.get("/health").status_code == 200


def test_lifespan_dim_mismatch_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    target = str(tmp_path / "tampered.db")
    init_db(target)
    conn = connect(target)
    try:
        with conn:
            conn.execute("UPDATE meta SET value = 'other' WHERE key = 'embedding_model'")
    finally:
        conn.close()
    _lifespan_settings(monkeypatch, target)
    with pytest.raises(EmbeddingDimMismatchError), TestClient(create_app()):
        pass


def test_exact_boundary_bytes(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    client = _client(monkeypatch, tmp_path, MAX_UPLOAD_MB="1", MAX_ARTIFACT_CHARS="2097152")
    ok = client.post(
        "/api/v1/artifacts/upload",
        files={"file": ("edge.txt", b"a" * 1048576, "text/plain")},
    )
    assert ok.status_code == 201
    over = client.post(
        "/api/v1/artifacts/upload",
        files={"file": ("edge.txt", b"b" * 1048577, "text/plain")},
    )
    assert over.status_code == 413
    assert len(client.get("/api/v1/artifacts").json()) == 1


def test_exact_boundary_chars(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    client = _client(monkeypatch, tmp_path, MAX_ARTIFACT_CHARS="10")
    assert (
        client.post(
            "/api/v1/artifacts",
            json={"source_type": "note", "title": "t", "content": "x" * 10},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/artifacts",
            json={"source_type": "note", "title": "t", "content": "x" * 11},
        ).status_code
        == 413
    )
    assert len(client.get("/api/v1/artifacts").json()) == 1
