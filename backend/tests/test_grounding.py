"""Grounding contract tests: routing, message shapes, history bounds, refusal.

Pure unit tests — no DB, no model, no settings. Structural substring
assertions only; prompt prose stays tunable.
"""

import pytest

from app.core.grounding import (
    EVIDENCE_SYSTEM_PROMPT,
    MAX_HISTORY_CHARS,
    MAX_HISTORY_TURNS,
    QA_JSON_INSTRUCTIONS,
    REFUSAL_ANSWER,
    TEACHING_SYSTEM_PROMPT,
    HistoryTurn,
    NumberedPassage,
    build_messages,
    build_refusal,
    route_auto,
    select_history,
)


@pytest.mark.parametrize(
    "question",
    [
        "What did I accomplish at Sesame?",
        "Tell me about my experience with RAG",
        "What are my skills?",
        "Where did I work in 2024?",
    ],
)
def test_route_auto_personal_history_is_evidence(question: str) -> None:
    assert route_auto(question) == "evidence"


@pytest.mark.parametrize(
    "question",
    [
        "Explain what an event loop is",
        "Explain event loops using something I've worked on",
        "What is a vector database?",
        "How do embeddings work?",
    ],
)
def test_route_auto_conceptual_is_teaching(question: str) -> None:
    assert route_auto(question) == "teaching"


def _passages() -> list[NumberedPassage]:
    return [
        NumberedPassage(n=1, chunk_id=11, artifact_id="a1", text="first passage"),
        NumberedPassage(n=2, chunk_id=22, artifact_id="a2", text="second passage"),
    ]


def test_build_messages_evidence_shape() -> None:
    messages = build_messages("evidence", "what did I do?", _passages())
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "only" in messages[0]["content"].lower()
    assert "JSON" in messages[0]["content"]
    user = messages[1]["content"]
    assert "Passage [1]" in user
    assert "Passage [2]" in user
    assert "chunk_id=11" in user
    assert "what did I do?" in user


def test_build_messages_history_inserted_in_order() -> None:
    history = (
        HistoryTurn(role="user", content="first q"),
        HistoryTurn(role="assistant", content="first a"),
    )
    messages = build_messages("teaching", "follow-up?", _passages(), history)
    assert [m["role"] for m in messages] == ["system", "system", "user", "assistant", "user"]
    assert messages[2]["content"] == "first q"
    assert messages[3]["content"] == "first a"
    assert "follow-up?" in messages[4]["content"]


def test_build_messages_teaching_allows_empty_passages() -> None:
    messages = build_messages("teaching", "what is RAG?", [])
    assert "general knowledge" in messages[0]["content"].lower()
    assert "what is RAG?" in messages[1]["content"]


@pytest.mark.parametrize("prompt", [EVIDENCE_SYSTEM_PROMPT, TEACHING_SYSTEM_PROMPT])
def test_system_prompts_frame_passages_as_untrusted(prompt: str) -> None:
    assert "untrusted" in prompt
    assert "never" in prompt
    assert "instructions" in prompt


def test_select_history_caps_turn_count() -> None:
    turns = [HistoryTurn(role="user", content=f"q{i}") for i in range(8)]
    selected = select_history(turns)
    assert len(selected) == MAX_HISTORY_TURNS
    assert [t.content for t in selected] == [f"q{i}" for i in range(2, 8)]


def test_select_history_caps_chars_oldest_first() -> None:
    turns = [
        HistoryTurn(role="user", content="x" * (MAX_HISTORY_CHARS - 10)),
        HistoryTurn(role="assistant", content="y" * 20),
    ]
    selected = select_history(turns)
    assert [t.content for t in selected] == ["y" * 20]


def test_select_history_empty() -> None:
    assert select_history([]) == []


def test_build_refusal_names_silent_notes() -> None:
    assert build_refusal() == REFUSAL_ANSWER
    assert "notes" in REFUSAL_ANSWER


def test_json_instructions_name_contract() -> None:
    assert "answer" in QA_JSON_INSTRUCTIONS
    assert "citations" in QA_JSON_INSTRUCTIONS
