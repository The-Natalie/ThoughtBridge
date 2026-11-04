"""Attempt repository tests: lifecycle, filters, retry rule, NULL handling."""

import json
import sqlite3
from pathlib import Path

import pytest

from app.db.attempts import create_attempt, get_attempt, list_attempts, record_answer
from app.db.connection import connect, init_db
from app.db.conversations import create_conversation
from app.db.explanations import create_explanation


@pytest.fixture()
def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "attempts.db")
    init_db(path)
    return path


@pytest.fixture()
def conv_id(db_path: str) -> str:
    return create_conversation(db_path, "learning")


@pytest.fixture()
def exp_id(db_path: str) -> str:
    return create_explanation(db_path, "RAG", 1, {"definition": "d"}, [], "", None).id


def _ask(db_path: str, conv_id: str, **over: object) -> str:
    params: dict[str, object] = {
        "mode": "learning",
        "question_kind": None,
        "explanation_id": None,
        "question": "Explain RAG.",
        "conversation_id": conv_id,
        "reference_json": {},
    }
    params.update(over)
    return create_attempt(db_path, **params)  # type: ignore[arg-type]


def test_create_get_round_trip(db_path: str, conv_id: str, exp_id: str) -> None:
    attempt_id = _ask(db_path, conv_id, explanation_id=exp_id, reference_json={"a": 1})
    detail = get_attempt(db_path, attempt_id)
    assert detail is not None
    assert detail.id == attempt_id
    assert detail.mode == "learning"
    assert detail.question_kind is None
    assert detail.explanation_id == exp_id
    assert detail.concept == "RAG"
    assert detail.question == "Explain RAG."
    assert detail.answer is None
    assert detail.feedback is None
    assert detail.grounding is None
    assert detail.needs_retry is False
    assert detail.conversation_id == conv_id
    assert detail.reference == {"a": 1}


def test_get_missing_returns_none(db_path: str) -> None:
    assert get_attempt(db_path, "nope") is None


def test_concept_null_without_explanation(db_path: str, conv_id: str) -> None:
    attempt_id = _ask(db_path, conv_id, mode="interview", question_kind="technical")
    detail = get_attempt(db_path, attempt_id)
    assert detail is not None
    assert detail.explanation_id is None
    assert detail.concept is None


def test_record_answer_fills_and_reanswer_overwrites(db_path: str, conv_id: str) -> None:
    attempt_id = _ask(db_path, conv_id)
    first = {"correct": [], "missing": ["x"], "inaccurate": [], "terminology": [], "next_step": "n"}
    assert record_answer(db_path, attempt_id, answer="a1", feedback=first, grounding="g") is True
    detail = get_attempt(db_path, attempt_id)
    assert detail is not None
    assert detail.answer == "a1"
    assert detail.feedback == first
    assert detail.grounding == "g"
    assert detail.needs_retry is True
    second = {
        "correct": ["y"],
        "missing": [],
        "inaccurate": [],
        "terminology": [],
        "next_step": "n2",
    }
    assert record_answer(db_path, attempt_id, answer="a2", feedback=second, grounding="g2") is True
    detail = get_attempt(db_path, attempt_id)
    assert detail is not None
    assert detail.answer == "a2"
    assert detail.feedback == second
    assert detail.needs_retry is False


def test_record_answer_missing_returns_false(db_path: str) -> None:
    assert record_answer(db_path, "nope", answer="a", feedback={}, grounding="g") is False


@pytest.mark.parametrize(
    ("answer", "feedback", "expected"),
    [
        ("a", {"missing": ["x"], "inaccurate": []}, True),
        ("a", {"missing": [], "inaccurate": ["y"]}, True),
        ("a", {"missing": [], "inaccurate": []}, False),
        ("a", {}, False),
        ("a", {"missing": "not-a-list"}, False),
        ("   ", {"missing": ["x"]}, False),
        (None, {"missing": ["x"]}, False),
    ],
)
def test_needs_retry_truth_table(
    db_path: str, conv_id: str, answer: object, feedback: object, expected: bool
) -> None:
    attempt_id = _ask(db_path, conv_id)
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE attempts SET answer = ?, feedback = ? WHERE id = ?",
                (answer, json.dumps(feedback), attempt_id),
            )
    finally:
        conn.close()
    detail = get_attempt(db_path, attempt_id)
    assert detail is not None
    assert detail.needs_retry is expected


def test_malformed_feedback_reads_none(db_path: str, conv_id: str) -> None:
    attempt_id = _ask(db_path, conv_id)
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE attempts SET answer = 'a', feedback = 'not-json{{' WHERE id = ?",
                (attempt_id,),
            )
    finally:
        conn.close()
    detail = get_attempt(db_path, attempt_id)
    assert detail is not None
    assert detail.feedback is None
    assert detail.needs_retry is False


def test_null_reference_reads_empty_dict(db_path: str, conv_id: str) -> None:
    attempt_id = _ask(db_path, conv_id, reference_json={"x": 1})
    conn = connect(db_path)
    try:
        with conn:
            conn.execute("UPDATE attempts SET reference_json = NULL WHERE id = ?", (attempt_id,))
    finally:
        conn.close()
    detail = get_attempt(db_path, attempt_id)
    assert detail is not None
    assert detail.reference == {}


def test_list_newest_first_and_filters(db_path: str, conv_id: str, exp_id: str) -> None:
    other_conv = create_conversation(db_path, "interview")
    first = _ask(db_path, conv_id, explanation_id=exp_id)
    second = _ask(db_path, other_conv, mode="interview", question_kind="experience", question="Q2")
    got = list_attempts(db_path)
    assert [d.id for d in got] == [second, first]
    assert [d.id for d in list_attempts(db_path, mode="learning")] == [first]
    assert [d.id for d in list_attempts(db_path, mode="interview")] == [second]
    assert [d.id for d in list_attempts(db_path, explanation_id=exp_id)] == [first]
    assert list_attempts(db_path, explanation_id="missing") == []
    assert [d.id for d in list_attempts(db_path, mode="learning", explanation_id=exp_id)] == [first]


def test_list_retry_only(db_path: str, conv_id: str) -> None:
    retry_id = _ask(db_path, conv_id, question="Q1")
    _ask(db_path, conv_id, question="Q2")
    clean_id = _ask(db_path, conv_id, question="Q3")
    record_answer(
        db_path,
        retry_id,
        answer="a",
        feedback={"missing": ["x"], "inaccurate": []},
        grounding="g",
    )
    record_answer(
        db_path, clean_id, answer="a", feedback={"missing": [], "inaccurate": []}, grounding="g"
    )
    assert [d.id for d in list_attempts(db_path, retry_only=True)] == [retry_id]


def test_create_bogus_conversation_fk_rejected(db_path: str) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        _ask(db_path, "missing-conversation")
