"""Conversation repository tests: create/append/get/list, idx order, ids."""

from pathlib import Path

import pytest

from app.db.connection import init_db
from app.db.conversations import (
    append_turns,
    create_conversation,
    create_conversation_with_turns,
    get_conversation,
    list_conversations,
)


@pytest.fixture
def db(tmp_path: Path) -> str:
    path = str(tmp_path / "conversations.db")
    init_db(path)
    return path


def test_create_lists_with_zero_turns(db: str) -> None:
    cid = create_conversation(db)
    assert len(cid) == 32
    summaries = list_conversations(db)
    assert len(summaries) == 1
    assert summaries[0].id == cid
    assert summaries[0].kind == "qa"
    assert summaries[0].turn_count == 0


def test_append_two_turns_order_and_roles(db: str) -> None:
    cid = create_conversation(db)
    ids = append_turns(
        db,
        cid,
        [
            ("user", "hello", "evidence", "[]"),
            ("assistant", "hi", "evidence", '[{"chunk_id": 3}]'),
        ],
    )
    detail = get_conversation(db, cid)
    assert detail is not None
    assert [t.id for t in detail.turns] == ids
    assert [t.idx for t in detail.turns] == [0, 1]
    assert [t.role for t in detail.turns] == ["user", "assistant"]
    assert detail.turns[0].citations_json == "[]"
    assert detail.turns[1].citations_json == '[{"chunk_id": 3}]'
    assert detail.turns[1].mode == "evidence"


def test_second_append_continues_idx(db: str) -> None:
    cid = create_conversation(db)
    append_turns(db, cid, [("user", "q1", "evidence", "[]")])
    append_turns(db, cid, [("assistant", "a1", "evidence", "[]")])
    detail = get_conversation(db, cid)
    assert detail is not None
    assert [t.idx for t in detail.turns] == [0, 1]


def test_create_with_turns_is_atomic(db: str) -> None:
    cid, ids = create_conversation_with_turns(
        db, "qa", [("user", "q", "teaching", "[]"), ("assistant", "a", "teaching", "[]")]
    )
    detail = get_conversation(db, cid)
    assert detail is not None
    assert detail.kind == "qa"
    assert [t.idx for t in detail.turns] == [0, 1]
    assert [t.id for t in detail.turns] == ids


def test_get_unknown_conversation_is_none(db: str) -> None:
    assert get_conversation(db, "nope" * 8) is None


def test_list_orders_by_creation(db: str) -> None:
    first = create_conversation(db)
    second = create_conversation(db)
    ids = [s.id for s in list_conversations(db)]
    assert ids == [first, second]


def test_unicode_and_newlines_survive(db: str) -> None:
    cid = create_conversation(db)
    body = "héllo\nwörld 🎉\nnewline"
    append_turns(db, cid, [("user", body, "evidence", "[]")])
    detail = get_conversation(db, cid)
    assert detail is not None
    assert detail.turns[0].content == body
