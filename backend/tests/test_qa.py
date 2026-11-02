"""Q&A orchestration tests: routing, refusal, validation, citation mapping.

Stubbed search/chat/get_chunks — no DB, no network, no embedding model.
"""

import asyncio
import json

import pytest

from app.core.grounding import REFUSAL_ANSWER, HistoryTurn
from app.db.chunks import ChunkDetail
from app.llm.qa import QaValidationError, answer_question
from app.retrieval.search import SearchHit


def _hit(chunk_id: int) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        artifact_id=f"a{chunk_id}",
        span_start=0,
        span_end=10,
        excerpt="excerpt",
        rrf_score=0.1,
        bm25_rank=1,
        vector_rank=None,
    )


def _rows() -> dict[int, ChunkDetail]:
    return {
        1: ChunkDetail(
            id=1, artifact_id="a1", chunk_idx=0, span_start=0, span_end=10, text="alpha body"
        ),
        2: ChunkDetail(
            id=2, artifact_id="a2", chunk_idx=0, span_start=0, span_end=10, text="beta body"
        ),
    }


def _run(monkeypatch: pytest.MonkeyPatch, **kwargs: object) -> object:
    monkeypatch.setattr("app.llm.qa.get_chunks", lambda db_path, ids: _rows())
    params: dict[str, object] = {
        "question": "q",
        "mode": "evidence",
        "top_k": 8,
        "db_path": ":memory:",
        "search_fn": lambda q, k: [],
    }
    params.update(kwargs)
    return asyncio.run(answer_question(**params))  # type: ignore[arg-type]


def _chat(payload: str, record: list | None = None):
    async def fake(messages: list[dict[str, str]]) -> str:
        if record is not None:
            record.append(messages)
        return payload

    return fake


def test_evidence_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(
        monkeypatch,
        search_fn=lambda q, k: [_hit(1), _hit(2)],
        chat_fn=_chat(json.dumps({"answer": "A [1] [2]", "citations": [1, 2]})),
    )
    assert result.mode_used == "evidence"
    assert result.answer == "A [1] [2]"
    assert [(c.chunk_id, c.excerpt) for c in result.citations] == [
        (1, "alpha body"),
        (2, "beta body"),
    ]
    assert result.citations[0].artifact_id == "a1"
    assert (result.citations[1].span_start, result.citations[1].span_end) == (0, 10)


def test_evidence_empty_hits_never_calls_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(messages: list[dict[str, str]]) -> str:
        raise AssertionError("chat must not be called")

    result = _run(monkeypatch, search_fn=lambda q, k: [], chat_fn=boom)
    assert result.answer == REFUSAL_ANSWER
    assert result.citations == []
    assert result.mode_used == "evidence"


def test_evidence_model_returns_no_citations_is_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _run(
        monkeypatch,
        search_fn=lambda q, k: [_hit(1)],
        chat_fn=_chat(json.dumps({"answer": "unsourced", "citations": []})),
    )
    assert result.answer == REFUSAL_ANSWER
    assert result.citations == []


def test_evidence_hallucinated_citation_dropped_to_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _run(
        monkeypatch,
        search_fn=lambda q, k: [_hit(1)],
        chat_fn=_chat(json.dumps({"answer": "A [9]", "citations": [9]})),
    )
    assert result.answer == REFUSAL_ANSWER
    assert result.citations == []


def test_evidence_mixed_citations_keep_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(
        monkeypatch,
        search_fn=lambda q, k: [_hit(1)],
        chat_fn=_chat(json.dumps({"answer": "A [1]", "citations": [1, 9]})),
    )
    assert result.answer == "A [1]"
    assert [c.chunk_id for c in result.citations] == [1]


def test_teaching_empty_hits_calls_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    record: list = []
    result = _run(
        monkeypatch,
        mode="teaching",
        question="Explain what an event loop is",
        search_fn=lambda q, k: [],
        chat_fn=_chat(json.dumps({"answer": "general", "citations": []}), record),
    )
    assert result.answer == "general"
    assert result.mode_used == "teaching"
    assert len(record) == 1


def test_auto_routes_personal_to_evidence_without_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(messages: list[dict[str, str]]) -> str:
        raise AssertionError("chat must not be called")

    result = _run(
        monkeypatch,
        mode="auto",
        question="What did I accomplish at Sesame?",
        search_fn=lambda q, k: [],
        chat_fn=boom,
    )
    assert result.mode_used == "evidence"
    assert result.answer == REFUSAL_ANSWER


def test_auto_routes_conceptual_to_teaching_with_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record: list = []
    result = _run(
        monkeypatch,
        mode="auto",
        question="Explain what an event loop is",
        search_fn=lambda q, k: [_hit(1)],
        chat_fn=_chat(json.dumps({"answer": "general", "citations": []}), record),
    )
    assert result.mode_used == "teaching"
    assert result.answer == "general"
    assert "Passage [1]" in record[0][-1]["content"]


def test_history_forwarded_to_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    record: list = []
    history = (
        HistoryTurn(role="user", content="first q"),
        HistoryTurn(role="assistant", content="first a"),
    )
    _run(
        monkeypatch,
        mode="teaching",
        question="follow-up?",
        search_fn=lambda q, k: [],
        chat_fn=_chat(json.dumps({"answer": "ok", "citations": []}), record),
        history=history,
    )
    roles = [m["role"] for m in record[0]]
    assert roles == ["system", "system", "user", "assistant", "user"]
    assert record[0][2]["content"] == "first q"


def test_teaching_garbage_json_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(QaValidationError):
        _run(
            monkeypatch,
            mode="teaching",
            question="Explain what an event loop is",
            search_fn=lambda q, k: [],
            chat_fn=_chat("not json at all"),
        )


def test_evidence_garbage_json_is_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(
        monkeypatch,
        search_fn=lambda q, k: [_hit(1)],
        chat_fn=_chat("not json at all"),
    )
    assert result.answer == REFUSAL_ANSWER
    assert result.citations == []


def test_fenced_json_response_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(
        monkeypatch,
        mode="teaching",
        question="Explain what an event loop is",
        search_fn=lambda q, k: [],
        chat_fn=_chat('```json\n{"answer": "fenced", "citations": []}\n```'),
    )
    assert result.answer == "fenced"
