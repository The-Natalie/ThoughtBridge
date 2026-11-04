"""Practice API contract tests: shapes, status matrix, turn persistence.

TestClient over tmp DBs with REAL orchestration + repositories; only
`chat_completion` / `hybrid_search` / `read_career_context` are stubbed
by name. Never touches the network or the fastembed model. Mirrors
test_learn_api.py settings isolation.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.meta_client import MetaAPIError
from app.db.artifacts import store_artifact
from app.db.attempts import create_attempt
from app.db.chunks import get_chunks_by_artifacts
from app.db.connection import connect, init_db
from app.db.conversations import create_conversation, get_conversation
from app.db.explanations import create_explanation
from app.db.facts import FactCreate, create_facts
from app.ingest.chunker import chunk_text
from app.ingest.pipeline import IngestResult
from app.llm.extraction import no_career
from app.main import create_app

QUESTION_JSON = json.dumps({"question": "Explain RAG as if to an interviewer."})
FEEDBACK = {
    "correct": ["retrieval first"],
    "missing": ["chunking"],
    "inaccurate": [],
    "terminology": ["say embeddings"],
    "next_step": "Retry the full explanation.",
}
FEEDBACK_JSON = json.dumps({"feedback": FEEDBACK})


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
    monkeypatch.setattr("app.api.practice.get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(_env_file=None))
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _no_conversation_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default the conversation-index seam to a no-op (never embeds).

    Hook tests re-stub this symbol with recording stubs; every other test
    posts questions/answers without indexing side effects.
    """
    monkeypatch.setattr(
        "app.api.practice.index_conversation_turns",
        lambda **kwargs: IngestResult(artifact_id="stub-artifact", chunk_count=0),
    )


def _client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    raise_server_exceptions: bool = True,
) -> TestClient:
    db = str(tmp_path / "practice_api.db")
    init_db(db)
    monkeypatch.setenv("DATABASE_PATH", db)
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    return TestClient(create_app(), raise_server_exceptions=raise_server_exceptions)


def _db_of(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> str:
    return str(tmp_path / "practice_api.db")


def _stubs(monkeypatch: pytest.MonkeyPatch, payloads: list[str], hits: list | None = None):
    queue = list(payloads)

    async def fake_chat(**kwargs: Any) -> str:
        assert queue, "chat called more times than payloads"
        return queue.pop(0)

    def fake_search(**kwargs: Any) -> list:
        return hits if hits is not None else []

    monkeypatch.setattr("app.api.practice.chat_completion", fake_chat)
    monkeypatch.setattr("app.api.practice.hybrid_search", fake_search)
    monkeypatch.setattr("app.api.practice.read_career_context", lambda db_path: no_career())


def _seed_explanation(db: str) -> str:
    return create_explanation(
        db, "RAG", 1, {"definition": "RAG retrieves then generates."}, [], "", None
    ).id


def _seed_fact(db: str, summary: str = "Shipped batched loader") -> str:
    used = chunk_text("Work log. Shipped the batched loader fix for checkout.")
    aid = store_artifact(
        db_path=db,
        source_type="note",
        title="log",
        content="Work log. Shipped the batched loader fix for checkout.",
        content_hash="h",
        origin_json="{}",
        created_at="2026-11-03T00:00:00+00:00",
        chunks=used,
        embeddings=[[0.0] * 384 for _ in used],
    )
    grouped = get_chunks_by_artifacts(db, [aid])
    cids = [c.id for c in grouped[aid]]
    (fid,) = create_facts(
        db_path=db,
        items=[
            (
                f"fact-{summary[:4]}",
                FactCreate(
                    kind="accomplishment",
                    status="completed",
                    summary=summary,
                    skills=["python"],
                    confidence=0.9,
                    chunk_ids=cids,
                ),
                [],
            )
        ],
        model="m",
        prompt_version="p",
    )
    return fid


def test_question_learning_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    db = _db_of(monkeypatch, tmp_path)
    exp_id = _seed_explanation(db)
    _stubs(monkeypatch, [QUESTION_JSON])
    response = client.post(
        "/api/v1/practice/question",
        json={"mode": "learning", "context": {"explanation_id": exp_id}},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "attempt_id",
        "question",
        "question_kind",
        "reference_kind",
        "conversation_id",
    }
    assert body["question"] == "Explain RAG as if to an interviewer."
    assert body["question_kind"] is None
    assert body["reference_kind"] == "explanation"
    detail = get_conversation(db, body["conversation_id"])
    assert detail is not None
    assert detail.kind == "learning"
    assert [(t.role, t.mode) for t in detail.turns] == [
        ("user", "learning"),
        ("assistant", "learning"),
    ]
    assert detail.turns[0].content.startswith("Practice (learning):")
    assert detail.turns[1].content == body["question"]


def test_question_interview_experience_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    db = _db_of(monkeypatch, tmp_path)
    _seed_fact(db)
    _stubs(monkeypatch, [QUESTION_JSON])
    response = client.post(
        "/api/v1/practice/question",
        json={"mode": "interview", "question_kind": "experience", "context": {}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["question_kind"] == "experience"
    assert body["reference_kind"] == "facts"
    detail = get_conversation(db, body["conversation_id"])
    assert detail is not None
    assert detail.kind == "interview"
    assert detail.turns[0].mode == "interview:experience"


def test_question_technical_empty_focus_legal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    _stubs(monkeypatch, [QUESTION_JSON])
    response = client.post(
        "/api/v1/practice/question",
        json={"mode": "interview", "question_kind": "technical"},
    )
    assert response.status_code == 200
    assert response.json()["reference_kind"] == "general"


def test_question_continues_conversation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    db = _db_of(monkeypatch, tmp_path)
    exp_id = _seed_explanation(db)
    _stubs(monkeypatch, [QUESTION_JSON, QUESTION_JSON])
    first = client.post(
        "/api/v1/practice/question",
        json={"mode": "learning", "context": {"explanation_id": exp_id}},
    ).json()
    second = client.post(
        "/api/v1/practice/question",
        json={
            "mode": "learning",
            "context": {"explanation_id": exp_id},
            "conversation_id": first["conversation_id"],
        },
    ).json()
    assert second["conversation_id"] == first["conversation_id"]
    assert second["attempt_id"] != first["attempt_id"]
    detail = get_conversation(db, first["conversation_id"])
    assert detail is not None
    assert len(detail.turns) == 4


def test_question_unknown_conversation_404(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    _stubs(monkeypatch, [])
    response = client.post(
        "/api/v1/practice/question",
        json={
            "mode": "interview",
            "question_kind": "technical",
            "conversation_id": "missing",
        },
    )
    assert response.status_code == 404


def test_question_learning_with_kind_422(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    db = _db_of(monkeypatch, tmp_path)
    exp_id = _seed_explanation(db)
    _stubs(monkeypatch, [])
    response = client.post(
        "/api/v1/practice/question",
        json={
            "mode": "learning",
            "question_kind": "technical",
            "context": {"explanation_id": exp_id},
        },
    )
    assert response.status_code == 422


def test_question_interview_kindless_422(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    _stubs(monkeypatch, [])
    response = client.post("/api/v1/practice/question", json={"mode": "interview"})
    assert response.status_code == 422


def test_question_unknown_explanation_404(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    _stubs(monkeypatch, [])
    response = client.post(
        "/api/v1/practice/question",
        json={"mode": "learning", "context": {"explanation_id": "missing"}},
    )
    assert response.status_code == 404


def test_question_overlong_focus_422(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    _stubs(monkeypatch, [])
    response = client.post(
        "/api/v1/practice/question",
        json={
            "mode": "interview",
            "question_kind": "technical",
            "context": {"focus": "x" * 2001},
        },
    )
    assert response.status_code == 422


def test_question_zero_facts_experience_422(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    _stubs(monkeypatch, [])
    response = client.post(
        "/api/v1/practice/question",
        json={"mode": "interview", "question_kind": "experience"},
    )
    assert response.status_code == 422
    assert "extract work first" in response.json()["detail"]


def test_question_meta_error_502(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    db = _db_of(monkeypatch, tmp_path)
    exp_id = _seed_explanation(db)

    async def boom(**kwargs: Any) -> str:
        raise MetaAPIError(500, "upstream down")

    monkeypatch.setattr("app.api.practice.chat_completion", boom)
    monkeypatch.setattr("app.api.practice.hybrid_search", lambda **k: [])
    monkeypatch.setattr("app.api.practice.read_career_context", lambda db_path: no_career())
    response = client.post(
        "/api/v1/practice/question",
        json={"mode": "learning", "context": {"explanation_id": exp_id}},
    )
    assert response.status_code == 502


def test_question_malformed_model_output_502(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    db = _db_of(monkeypatch, tmp_path)
    exp_id = _seed_explanation(db)
    _stubs(monkeypatch, ["junk{{{"])
    response = client.post(
        "/api/v1/practice/question",
        json={"mode": "learning", "context": {"explanation_id": exp_id}},
    )
    assert response.status_code == 502


def test_answer_happy_path_inherits_conversation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    db = _db_of(monkeypatch, tmp_path)
    exp_id = _seed_explanation(db)
    _stubs(monkeypatch, [QUESTION_JSON, FEEDBACK_JSON])
    asked = client.post(
        "/api/v1/practice/question",
        json={"mode": "learning", "context": {"explanation_id": exp_id}},
    ).json()
    response = client.post(
        "/api/v1/practice/answer",
        json={"attempt_id": asked["attempt_id"], "answer": "RAG fetches passages first."},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"feedback", "grounding"}
    assert set(body["feedback"].keys()) == {
        "correct",
        "missing",
        "inaccurate",
        "terminology",
        "next_step",
    }
    assert body["feedback"] == FEEDBACK
    assert body["grounding"] == "general explanation"
    detail = get_conversation(db, asked["conversation_id"])
    assert detail is not None
    assert [(t.role, t.mode) for t in detail.turns] == [
        ("user", "learning"),
        ("assistant", "learning"),
        ("user", "learning"),
        ("assistant", "learning"),
    ]
    assert detail.turns[2].content == "RAG fetches passages first."
    assert "Practice feedback:" in detail.turns[3].content
    assert "Retry the full explanation." in detail.turns[3].content


def test_answer_blank_422(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    _stubs(monkeypatch, [])
    response = client.post("/api/v1/practice/answer", json={"attempt_id": "x", "answer": "   "})
    assert response.status_code == 422


def test_answer_unknown_attempt_404(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    _stubs(monkeypatch, [])
    response = client.post("/api/v1/practice/answer", json={"attempt_id": "missing", "answer": "a"})
    assert response.status_code == 404


def test_answer_stale_reference_409(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    db = _db_of(monkeypatch, tmp_path)
    conv = create_conversation(db, "interview")
    attempt_id = create_attempt(
        db,
        mode="interview",
        question_kind="experience",
        explanation_id=None,
        question="Q?",
        conversation_id=conv,
        reference_json={"fact_ids": ["gone"]},
    )
    _stubs(monkeypatch, [])
    response = client.post(
        "/api/v1/practice/answer", json={"attempt_id": attempt_id, "answer": "a"}
    )
    assert response.status_code == 409


def test_answer_reanswer_overwrites_and_appends(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    db = _db_of(monkeypatch, tmp_path)
    exp_id = _seed_explanation(db)
    second_feedback = dict(FEEDBACK, missing=[])
    _stubs(monkeypatch, [QUESTION_JSON, FEEDBACK_JSON, json.dumps({"feedback": second_feedback})])
    asked = client.post(
        "/api/v1/practice/question",
        json={"mode": "learning", "context": {"explanation_id": exp_id}},
    ).json()
    first = client.post(
        "/api/v1/practice/answer",
        json={"attempt_id": asked["attempt_id"], "answer": "thin answer"},
    )
    assert first.status_code == 200
    second = client.post(
        "/api/v1/practice/answer",
        json={"attempt_id": asked["attempt_id"], "answer": "fuller answer"},
    )
    assert second.status_code == 200
    assert second.json()["feedback"]["missing"] == []
    detail = get_conversation(db, asked["conversation_id"])
    assert detail is not None
    assert len(detail.turns) == 6
    history = client.get("/api/v1/practice/attempts").json()
    assert len(history) == 1
    assert history[0]["answer"] == "fuller answer"
    assert history[0]["needs_retry"] is False


def test_answer_null_conversation_creates_fresh(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    db = _db_of(monkeypatch, tmp_path)
    exp_id = _seed_explanation(db)
    conv = create_conversation(db, "learning")
    attempt_id = create_attempt(
        db,
        mode="learning",
        question_kind=None,
        explanation_id=exp_id,
        question="Q?",
        conversation_id=conv,
        reference_json={},
    )
    conn = connect(db)
    try:
        with conn:
            conn.execute("UPDATE attempts SET conversation_id = NULL WHERE id = ?", (attempt_id,))
    finally:
        conn.close()
    _stubs(monkeypatch, [FEEDBACK_JSON])
    response = client.post(
        "/api/v1/practice/answer", json={"attempt_id": attempt_id, "answer": "a"}
    )
    assert response.status_code == 200
    conn = connect(db)
    try:
        count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    finally:
        conn.close()
    assert count == 2


def test_attempts_list_shape_and_filters(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    db = _db_of(monkeypatch, tmp_path)
    exp_id = _seed_explanation(db)
    _seed_fact(db)
    _stubs(monkeypatch, [QUESTION_JSON, FEEDBACK_JSON, QUESTION_JSON, FEEDBACK_JSON])
    learning = client.post(
        "/api/v1/practice/question",
        json={"mode": "learning", "context": {"explanation_id": exp_id}},
    ).json()
    client.post(
        "/api/v1/practice/answer",
        json={"attempt_id": learning["attempt_id"], "answer": "thin"},
    )
    interview = client.post(
        "/api/v1/practice/question",
        json={"mode": "interview", "question_kind": "experience"},
    ).json()
    client.post(
        "/api/v1/practice/answer", json={"attempt_id": interview["attempt_id"], "answer": "full"}
    )
    history = client.get("/api/v1/practice/attempts").json()
    assert len(history) == 2
    assert set(history[0].keys()) == {
        "id",
        "mode",
        "question_kind",
        "explanation_id",
        "concept",
        "question",
        "answer",
        "feedback",
        "grounding",
        "needs_retry",
        "created_at",
    }
    assert history[0]["id"] == interview["attempt_id"]
    assert history[1]["concept"] == "RAG"
    assert [a["id"] for a in client.get("/api/v1/practice/attempts?mode=learning").json()] == [
        learning["attempt_id"]
    ]
    assert [
        a["id"] for a in client.get(f"/api/v1/practice/attempts?explanation_id={exp_id}").json()
    ] == [learning["attempt_id"]]
    assert [a["id"] for a in client.get("/api/v1/practice/attempts?retry_only=true").json()] == [
        interview["attempt_id"],
        learning["attempt_id"],
    ]


def test_attempts_blank_explanation_filter_422(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.get("/api/v1/practice/attempts?explanation_id=%20%20")
    assert response.status_code == 422


def test_attempts_bad_mode_422(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.get("/api/v1/practice/attempts?mode=coaching")
    assert response.status_code == 422


def test_attempts_malformed_feedback_serves_null(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    db = _db_of(monkeypatch, tmp_path)
    conv = create_conversation(db, "learning")
    garbage = create_attempt(
        db,
        mode="learning",
        question_kind=None,
        explanation_id=None,
        question="Q1",
        conversation_id=conv,
        reference_json={},
    )
    partial = create_attempt(
        db,
        mode="learning",
        question_kind=None,
        explanation_id=None,
        question="Q2",
        conversation_id=conv,
        reference_json={},
    )
    conn = connect(db)
    try:
        with conn:
            conn.execute(
                "UPDATE attempts SET answer='a', feedback='not-json{{' WHERE id = ?", (garbage,)
            )
            conn.execute(
                "UPDATE attempts SET answer='a', feedback=? WHERE id = ?",
                (json.dumps({"correct": ["x"]}), partial),
            )
    finally:
        conn.close()
    response = client.get("/api/v1/practice/attempts")
    assert response.status_code == 200
    rows = {r["id"]: r for r in response.json()}
    assert rows[garbage]["feedback"] is None
    assert rows[partial]["feedback"] is None
    assert rows[garbage]["answer"] == "a"


def _record_index(monkeypatch: pytest.MonkeyPatch) -> list:
    calls: list = []

    def fake(**kwargs: Any) -> IngestResult:
        calls.append(kwargs)
        return IngestResult(artifact_id="rec-artifact", chunk_count=1)

    monkeypatch.setattr("app.api.practice.index_conversation_turns", fake)
    return calls


def test_question_indexes_with_mode_kind_and_turn_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    db = _db_of(monkeypatch, tmp_path)
    exp_id = _seed_explanation(db)
    _stubs(monkeypatch, [QUESTION_JSON, QUESTION_JSON])
    calls = _record_index(monkeypatch)
    first = client.post(
        "/api/v1/practice/question",
        json={"mode": "learning", "context": {"explanation_id": exp_id}},
    ).json()
    client.post(
        "/api/v1/practice/question",
        json={
            "mode": "learning",
            "context": {"explanation_id": exp_id},
            "conversation_id": first["conversation_id"],
        },
    )
    assert [c["turn_start"] for c in calls] == [0, 2]
    assert all(c["kind"] == "learning" for c in calls)
    assert all(c["conversation_id"] == first["conversation_id"] for c in calls)
    assert [r for r, _ in calls[0]["turns"]] == ["user", "assistant"]
    assert calls[0]["turns"][1][1] == first["question"]


def test_question_interview_indexes_interview_kind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client(monkeypatch, tmp_path)
    db = _db_of(monkeypatch, tmp_path)
    _seed_fact(db)
    _stubs(monkeypatch, [QUESTION_JSON])
    calls = _record_index(monkeypatch)
    body = client.post(
        "/api/v1/practice/question",
        json={"mode": "interview", "question_kind": "experience", "context": {}},
    ).json()
    assert len(calls) == 1
    assert calls[0]["kind"] == "interview"
    assert calls[0]["conversation_id"] == body["conversation_id"]
    assert calls[0]["turn_start"] == 0


def test_answer_indexes_in_attempt_conversation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.db.conversations import get_conversation as read_conversation

    client = _client(monkeypatch, tmp_path)
    db = _db_of(monkeypatch, tmp_path)
    exp_id = _seed_explanation(db)
    _stubs(monkeypatch, [QUESTION_JSON, FEEDBACK_JSON])
    calls = _record_index(monkeypatch)
    asked = client.post(
        "/api/v1/practice/question",
        json={"mode": "learning", "context": {"explanation_id": exp_id}},
    ).json()
    pre = read_conversation(db, asked["conversation_id"])
    assert pre is not None
    pre_count = len(pre.turns)
    response = client.post(
        "/api/v1/practice/answer",
        json={"attempt_id": asked["attempt_id"], "answer": "RAG fetches passages first."},
    )
    assert response.status_code == 200
    assert len(calls) == 2
    assert calls[1]["conversation_id"] == asked["conversation_id"]
    assert calls[1]["turn_start"] == pre_count
    assert calls[1]["turns"][0] == ("user", "RAG fetches passages first.")


def test_answer_null_conversation_indexes_fresh_at_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.db.attempts import get_attempt
    from app.db.conversations import list_conversations

    client = _client(monkeypatch, tmp_path)
    db = _db_of(monkeypatch, tmp_path)
    exp_id = _seed_explanation(db)
    _stubs(monkeypatch, [FEEDBACK_JSON])
    calls = _record_index(monkeypatch)
    attempt_id = create_attempt(
        db,
        mode="learning",
        question_kind=None,
        explanation_id=exp_id,
        question="Q?",
        conversation_id=None,  # type: ignore[arg-type]
        reference_json={},
    )
    response = client.post(
        "/api/v1/practice/answer", json={"attempt_id": attempt_id, "answer": "my answer"}
    )
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["turn_start"] == 0
    assert calls[0]["kind"] == "learning"
    convos = list_conversations(db)
    assert len(convos) == 1
    assert calls[0]["conversation_id"] == convos[0].id
    assert get_attempt(db, attempt_id) is not None


def test_answer_deleted_conversation_recovers_fresh(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.db.conversations import delete_conversation_cascade
    from app.db.conversations import get_conversation as read_conv

    client = _client(monkeypatch, tmp_path)
    db = _db_of(monkeypatch, tmp_path)
    exp_id = _seed_explanation(db)
    _stubs(monkeypatch, [QUESTION_JSON, FEEDBACK_JSON])
    calls = _record_index(monkeypatch)
    asked = client.post(
        "/api/v1/practice/question",
        json={"mode": "learning", "context": {"explanation_id": exp_id}},
    ).json()
    assert delete_conversation_cascade(db, asked["conversation_id"]) is not None
    response = client.post(
        "/api/v1/practice/answer", json={"attempt_id": asked["attempt_id"], "answer": "a"}
    )
    assert response.status_code == 200
    assert len(calls) == 2
    assert calls[1]["turn_start"] == 0
    assert calls[1]["conversation_id"] != asked["conversation_id"]
    fresh = read_conv(db, calls[1]["conversation_id"])
    assert fresh is not None
    assert [t.idx for t in fresh.turns] == [0, 1]


def test_answer_index_failure_500_with_attempt_recorded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.db.attempts import get_attempt

    client = _client(monkeypatch, tmp_path, raise_server_exceptions=False)
    db = _db_of(monkeypatch, tmp_path)
    exp_id = _seed_explanation(db)
    _stubs(monkeypatch, [QUESTION_JSON, FEEDBACK_JSON])
    asked = client.post(
        "/api/v1/practice/question",
        json={"mode": "learning", "context": {"explanation_id": exp_id}},
    ).json()

    def boom(**kwargs: Any) -> IngestResult:
        raise RuntimeError("embed boom")

    monkeypatch.setattr("app.api.practice.index_conversation_turns", boom)
    response = client.post(
        "/api/v1/practice/answer", json={"attempt_id": asked["attempt_id"], "answer": "a"}
    )
    assert response.status_code == 500
    attempt = get_attempt(db, asked["attempt_id"])
    assert attempt is not None
    assert attempt.answer == "a"
    assert attempt.feedback is not None
