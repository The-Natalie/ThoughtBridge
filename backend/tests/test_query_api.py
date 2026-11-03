"""Query API contract tests: shapes, modes, conversations, status matrix.

TestClient over tmp DBs seeded DIRECTLY via the real pipeline with fake
passage vectors; the router's `hybrid_search` symbol is stubbed to run the
REAL search + legs + FTS with a fake query vector, and `chat_completion`
is stubbed per-test with canned JSON (recording received messages).
Mirrors `test_retrieval_api.py` settings isolation. Default suite never
downloads the fastembed model and never touches the network.
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.retrieval.search as search_mod
from app.core.config import Settings, get_settings
from app.core.grounding import REFUSAL_ANSWER
from app.core.meta_client import MetaAPIError
from app.db.connection import init_db
from app.ingest.pipeline import ingest_source
from app.main import create_app

DIM = 384
MODEL = "BAAI/bge-small-en-v1.5"
MAXC = 500_000
CANARY = "canary-key-q"
SEED = [("s", "The deploy pipeline uses Modal with a persistent volume.")]


def fake_query(text: str) -> list[float]:
    return [1.0] + [0.0] * (DIM - 1)


def _search_stub(*args: object, **kwargs: object) -> object:
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
    monkeypatch.setattr("app.api.query.get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(_env_file=None))
    yield
    get_settings.cache_clear()


def _client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    seed_notes: list[tuple[str, str]] | None = None,
) -> TestClient:
    db = str(tmp_path / "query_api.db")
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

    for title, content in seed_notes if seed_notes is not None else SEED:
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
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    monkeypatch.setattr("app.api.query.hybrid_search", _search_stub)
    return TestClient(create_app())


def stub_chat(
    monkeypatch: pytest.MonkeyPatch,
    payload: str = json.dumps({"answer": "canned", "citations": []}),
    record: list | None = None,
    exc: Exception | None = None,
) -> None:
    async def fake_chat(*, api_key: str, model: str, messages: list, **kw: Any) -> str:
        if record is not None:
            record.append(messages)
        if exc is not None:
            raise exc
        return payload

    monkeypatch.setattr("app.api.query.chat_completion", fake_chat)


def db_of(monkeypatch: pytest.MonkeyPatch) -> str:
    return os.environ["DATABASE_PATH"]


def test_evidence_happy_path_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    stub_chat(monkeypatch, json.dumps({"answer": "Modal volume [1]", "citations": [1]}))
    response = client.post(
        "/api/v1/query", json={"question": "Where does the SQLite file live?", "mode": "evidence"}
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"answer", "citations", "mode_used", "conversation_id"}
    assert body["mode_used"] == "evidence"
    assert body["answer"] == "Modal volume [1]"
    assert len(body["citations"]) == 1
    assert set(body["citations"][0].keys()) == {"chunk_id", "artifact_id", "span", "excerpt"}
    assert "persistent volume" in body["citations"][0]["excerpt"]
    assert len(body["conversation_id"]) == 32


def test_conversation_start_persists_two_turns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    stub_chat(monkeypatch)
    cid = client.post("/api/v1/query", json={"question": "hi?"}).json()["conversation_id"]
    detail = client.get(f"/api/v1/conversations/{cid}").json()
    assert detail["kind"] == "qa"
    assert [t["idx"] for t in detail["turns"]] == [0, 1]
    assert [t["role"] for t in detail["turns"]] == ["user", "assistant"]
    assert detail["turns"][0]["content"] == "hi?"
    assert detail["turns"][1]["content"] == "canned"


def test_conversation_continue_appends(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    stub_chat(monkeypatch)
    cid = client.post("/api/v1/query", json={"question": "one?"}).json()["conversation_id"]
    again = client.post("/api/v1/query", json={"question": "two?", "conversation_id": cid})
    assert again.json()["conversation_id"] == cid
    detail = client.get(f"/api/v1/conversations/{cid}").json()
    assert [t["idx"] for t in detail["turns"]] == [0, 1, 2, 3]
    assert [t["role"] for t in detail["turns"]] == ["user", "assistant", "user", "assistant"]


def test_unknown_conversation_is_404(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    stub_chat(monkeypatch)
    response = client.post("/api/v1/query", json={"question": "hi?", "conversation_id": "0" * 32})
    assert response.status_code == 404
    assert response.json() == {"detail": "conversation not found"}


@pytest.mark.parametrize("question", ["", "   "])
def test_blank_question_is_422(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, question: str
) -> None:
    client = _client(monkeypatch, tmp_path)
    stub_chat(monkeypatch)
    response = client.post("/api/v1/query", json={"question": question})
    assert response.status_code == 422


@pytest.mark.parametrize("top_k", [0, 51, -1])
def test_top_k_out_of_range_is_422(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, top_k: int
) -> None:
    client = _client(monkeypatch, tmp_path)
    stub_chat(monkeypatch)
    response = client.post("/api/v1/query", json={"question": "hi?", "top_k": top_k})
    assert response.status_code == 422


def test_top_k_max_boundary_is_200(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    stub_chat(monkeypatch)
    response = client.post("/api/v1/query", json={"question": "hi?", "top_k": 50})
    assert response.status_code == 200


def test_invalid_mode_is_422(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    stub_chat(monkeypatch)
    response = client.post("/api/v1/query", json={"question": "hi?", "mode": "nope"})
    assert response.status_code == 422


def test_context_unknown_explanation_id_404s(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    stub_chat(monkeypatch)
    response = client.post(
        "/api/v1/query",
        json={"question": "hi?", "context": {"explanation_id": "1" * 32}},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "explanation not found"


def test_auto_personal_routes_evidence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    stub_chat(monkeypatch, json.dumps({"answer": "you shipped X [1]", "citations": [1]}))
    response = client.post("/api/v1/query", json={"question": "What did I accomplish?"})
    assert response.status_code == 200
    assert response.json()["mode_used"] == "evidence"


def test_auto_conceptual_routes_teaching_with_passages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    record: list = []
    stub_chat(monkeypatch, json.dumps({"answer": "general explanation", "citations": []}), record)
    response = client.post("/api/v1/query", json={"question": "Explain what an event loop is"})
    assert response.status_code == 200
    body = response.json()
    assert body["mode_used"] == "teaching"
    assert body["citations"] == []
    assert "Passage [1]" in record[0][-1]["content"]


def test_evidence_empty_db_refuses_without_chat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path, [])
    called = False

    async def boom(*, api_key: str, model: str, messages: list, **kw: Any) -> str:
        nonlocal called
        called = True
        raise AssertionError("chat must not be called")

    monkeypatch.setattr("app.api.query.chat_completion", boom)
    response = client.post("/api/v1/query", json={"question": "anything?", "mode": "evidence"})
    assert response.status_code == 200
    assert response.json()["answer"] == REFUSAL_ANSWER
    assert response.json()["citations"] == []
    assert called is False


def test_meta_down_is_502(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    stub_chat(monkeypatch, exc=MetaAPIError(503, "boom"))
    response = client.post("/api/v1/query", json={"question": "Explain this", "mode": "teaching"})
    assert response.status_code == 502
    assert "boom" in response.json()["detail"]


def test_teaching_garbage_is_502(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    stub_chat(monkeypatch, "not json")
    response = client.post("/api/v1/query", json={"question": "Explain this", "mode": "teaching"})
    assert response.status_code == 502
    assert "malformed" in response.json()["detail"]


def test_no_key_evidence_empty_db_still_refuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path, [])
    monkeypatch.delenv("MODEL_API_KEY")
    response = client.post("/api/v1/query", json={"question": "anything?", "mode": "evidence"})
    assert response.status_code == 200
    assert response.json()["answer"] == REFUSAL_ANSWER


def test_no_key_teaching_path_is_502(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path, [])
    monkeypatch.delenv("MODEL_API_KEY")
    stub_chat(monkeypatch)
    response = client.post("/api/v1/query", json={"question": "Explain this", "mode": "teaching"})
    assert response.status_code == 502
    assert "MODEL_API_KEY" in response.json()["detail"]


def test_failure_on_new_conversation_persists_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    stub_chat(monkeypatch, exc=MetaAPIError(503, "boom"))
    response = client.post("/api/v1/query", json={"question": "Explain this", "mode": "teaching"})
    assert response.status_code == 502
    assert client.get("/api/v1/conversations").json() == []


def test_failure_on_continue_appends_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    stub_chat(monkeypatch)
    cid = client.post("/api/v1/query", json={"question": "one?"}).json()["conversation_id"]
    stub_chat(monkeypatch, exc=MetaAPIError(503, "boom"))
    response = client.post("/api/v1/query", json={"question": "two?", "conversation_id": cid})
    assert response.status_code == 502
    detail = client.get(f"/api/v1/conversations/{cid}").json()
    assert len(detail["turns"]) == 2


def test_continue_passes_history_to_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    record: list = []
    stub_chat(monkeypatch, json.dumps({"answer": "first answer", "citations": []}), record)
    cid = client.post("/api/v1/query", json={"question": "first question?"}).json()[
        "conversation_id"
    ]
    client.post("/api/v1/query", json={"question": "And then?", "conversation_id": cid})
    assert len(record) == 2
    roles = [m["role"] for m in record[1]]
    assert roles == ["system", "system", "user", "assistant", "user"]
    assert record[1][2]["content"] == "first question?"
    assert record[1][3]["content"] == "first answer"


def test_other_conversation_turns_never_leak(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    record: list = []
    stub_chat(monkeypatch, record=record)
    client.post("/api/v1/query", json={"question": "marker-zebra-42?"})
    cid_a = client.post("/api/v1/query", json={"question": "hello A?"}).json()["conversation_id"]
    client.post("/api/v1/query", json={"question": "follow-up A?", "conversation_id": cid_a})
    dumped = json.dumps(record[-1])
    assert "marker-zebra-42" not in dumped
    assert "hello A?" in dumped


def test_list_conversations_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    stub_chat(monkeypatch)
    cid = client.post("/api/v1/query", json={"question": "hi?"}).json()["conversation_id"]
    items = client.get("/api/v1/conversations").json()
    assert len(items) == 1
    assert set(items[0].keys()) == {"id", "kind", "created_at", "turn_count"}
    assert items[0]["id"] == cid
    assert items[0]["kind"] == "qa"
    assert items[0]["turn_count"] == 2


def test_get_unknown_conversation_is_404(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.get("/api/v1/conversations/" + "0" * 32)
    assert response.status_code == 404
    assert response.json() == {"detail": "conversation not found"}


def test_key_canary_never_in_bodies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setenv("MODEL_API_KEY", CANARY)
    stub_chat(monkeypatch, json.dumps({"answer": "ok [1]", "citations": [1]}))
    ok_body = client.post(
        "/api/v1/query", json={"question": "Where is it?", "mode": "evidence"}
    ).text
    assert CANARY not in ok_body
    stub_chat(monkeypatch, exc=MetaAPIError(503, "boom"))
    err_body = client.post(
        "/api/v1/query", json={"question": "Explain this", "mode": "teaching"}
    ).text
    assert CANARY not in err_body


def test_openapi_contains_query_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/query" in paths
    assert "/api/v1/conversations" in paths
    assert "/api/v1/conversations/{conversation_id}" in paths
