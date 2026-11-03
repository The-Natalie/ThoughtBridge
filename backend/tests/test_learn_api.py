"""Learn API contract tests: explain shapes, version reads, regen, status matrix.

TestClient over tmp DBs; `generate_explanation` / `regenerate_step` /
`get_explanation` / `chat_completion` / `hybrid_search` stubbed per-test.
Never touches the network or the fastembed model. Mirrors
test_query_api.py settings isolation.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.grounding import STEP_KEYS
from app.core.meta_client import MetaAPIError
from app.db.connection import init_db
from app.db.explanations import ExplanationDetail
from app.llm.explainer import ExplainedResult, ExplainerValidationError
from app.main import create_app

STEPS = {
    "definition": "d",
    "familiar_system": "f",
    "analogy": "a",
    "mapping": ["X maps to Y because Z."],
    "walkthrough": "w",
    "placement": "p",
    "interview_ready": "i",
    "limitations": "l",
}


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
    monkeypatch.setattr("app.api.learn.get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr("app.api.query.get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(_env_file=None))
    yield
    get_settings.cache_clear()


def _client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    db = str(tmp_path / "learn_api.db")
    init_db(db)
    monkeypatch.setenv("DATABASE_PATH", db)
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    return TestClient(create_app())


def _explained(**overrides: object) -> ExplainedResult:
    params: dict[str, object] = {
        "explanation_id": "exp-1",
        "reused_from": None,
        "steps": dict(STEPS),
    }
    params.update(overrides)
    return ExplainedResult(**params)  # type: ignore[arg-type]


def _detail(**overrides: object) -> ExplanationDetail:
    params: dict[str, object] = {
        "id": "exp-1",
        "concept": "RAG",
        "version": 1,
        "steps": dict(STEPS),
        "mapping": list(STEPS["mapping"]),  # type: ignore[arg-type]
        "limitations": "l",
        "reused_from": None,
        "created_at": "t",
    }
    params.update(overrides)
    return ExplanationDetail(**params)  # type: ignore[arg-type]


def test_explain_happy_path_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)

    async def fake_generate(**kwargs: object) -> ExplainedResult:
        return _explained()

    monkeypatch.setattr("app.api.learn.generate_explanation", fake_generate)
    response = client.post(
        "/api/v1/learn/explain",
        json={"concept": "RAG", "familiar_system_hint": "library"},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"explanation_id", "reused_from", "steps"}
    assert sorted(body["steps"].keys()) == sorted(STEP_KEYS)
    assert body["explanation_id"] == "exp-1"
    assert body["reused_from"] is None


def test_explain_blank_concept_422(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post("/api/v1/learn/explain", json={"concept": "   "})
    assert response.status_code == 422


def test_explain_validation_error_502(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)

    async def boom(**kwargs: object) -> ExplainedResult:
        raise ExplainerValidationError("stage B returned malformed JSON")

    monkeypatch.setattr("app.api.learn.generate_explanation", boom)
    response = client.post("/api/v1/learn/explain", json={"concept": "RAG"})
    assert response.status_code == 502


def test_explain_meta_error_502(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)

    async def boom(**kwargs: object) -> ExplainedResult:
        raise MetaAPIError(502, "meta down")

    monkeypatch.setattr("app.api.learn.generate_explanation", boom)
    response = client.post("/api/v1/learn/explain", json={"concept": "RAG"})
    assert response.status_code == 502


def test_get_explanation_happy_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr("app.api.learn.get_explanation", lambda db_path, eid: _detail())
    response = client.get("/api/v1/learn/explanations/exp-1")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "id",
        "concept",
        "version",
        "steps",
        "mapping",
        "limitations",
        "reused_from",
        "created_at",
    }
    assert body["concept"] == "RAG"
    assert body["version"] == 1


def test_get_explanation_unknown_404(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr("app.api.learn.get_explanation", lambda db_path, eid: None)
    response = client.get("/api/v1/learn/explanations/" + "0" * 32)
    assert response.status_code == 404
    assert response.json()["detail"] == "explanation not found"


def test_regenerate_happy_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr("app.api.learn.get_explanation", lambda db_path, eid: _detail())

    async def fake_regen(**kwargs: object) -> ExplainedResult:
        return _explained(explanation_id="exp-2", reused_from=None)

    monkeypatch.setattr("app.api.learn.regenerate_step", fake_regen)
    response = client.post("/api/v1/learn/explanations/exp-1/regenerate", json={"step": "analogy"})
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"explanation_id", "reused_from", "steps"}
    assert body["explanation_id"] == "exp-2"
    assert body["reused_from"] is None
    assert sorted(body["steps"].keys()) == sorted(STEP_KEYS)


def test_regenerate_unknown_source_404(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr("app.api.learn.get_explanation", lambda db_path, eid: None)
    response = client.post(
        "/api/v1/learn/explanations/" + "0" * 32 + "/regenerate", json={"step": "analogy"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "explanation not found"


def test_regenerate_invalid_step_422(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr("app.api.learn.get_explanation", lambda db_path, eid: _detail())
    response = client.post("/api/v1/learn/explanations/exp-1/regenerate", json={"step": "bogus"})
    assert response.status_code == 422
    for key in STEP_KEYS:
        assert key in response.json()["detail"]


def test_query_context_unknown_explanation_404(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr("app.api.query.get_explanation", lambda db_path, eid: None)
    response = client.post(
        "/api/v1/query",
        json={"question": "hi?", "context": {"explanation_id": "0" * 32}},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "explanation not found"


def test_query_context_forces_teaching(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr("app.api.query.get_explanation", lambda db_path, eid: _detail())
    monkeypatch.setattr("app.api.query.hybrid_search", lambda **kwargs: [])
    record: list = []

    async def fake_chat(*, api_key: str, model: str, messages: list, **kw: object) -> str:
        record.append(messages)
        return json.dumps({"answer": "lesson answer", "citations": []})

    monkeypatch.setattr("app.api.query.chat_completion", fake_chat)
    response = client.post(
        "/api/v1/query",
        json={
            "question": "What did I accomplish?",
            "mode": "evidence",
            "context": {"explanation_id": "exp-1"},
        },
    )
    assert response.status_code == 200
    assert response.json()["mode_used"] == "teaching"
    assert len(record) == 1
    assert any(
        "In-progress eight-step lesson" in m["content"] for m in record[0] if m["role"] == "system"
    )
