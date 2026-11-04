"""Conversation repository: append-only turn log over conversations/turns."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.db.artifacts import _delete_artifacts_cascade_conn
from app.db.connection import connect

logger = logging.getLogger(__name__)


@dataclass
class TurnDetail:
    id: str
    conversation_id: str
    idx: int
    role: str
    content: str
    mode: str | None
    citations_json: str
    created_at: str


@dataclass
class ConversationDetail:
    id: str
    kind: str
    created_at: str
    turns: list[TurnDetail] = field(default_factory=list)


@dataclass
class ConversationSummary:
    id: str
    kind: str
    created_at: str
    turn_count: int


def create_conversation(db_path: str, kind: str = "qa") -> str:
    """Insert a conversation header row and return its id."""
    conversation_id = uuid.uuid4().hex
    created_at = datetime.now(UTC).isoformat()
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO conversations (id, kind, created_at) VALUES (?, ?, ?)",
                (conversation_id, kind, created_at),
            )
    finally:
        conn.close()
    logger.info("created conversation: id=%s kind=%s", conversation_id, kind)
    return conversation_id


def append_turns(
    db_path: str,
    conversation_id: str,
    turns: list[tuple[str, str, str | None, str]],
) -> list[str]:
    """Append turns in ONE transaction with sequential idx; return turn ids."""
    conn = connect(db_path)
    try:
        with conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(idx), -1) AS m FROM turns WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            next_idx = int(row["m"]) + 1
            ids = []
            for role, content, mode, citations_json in turns:
                turn_id = uuid.uuid4().hex
                conn.execute(
                    "INSERT INTO turns (id, conversation_id, idx, role, content, mode,"
                    " citations, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        turn_id,
                        conversation_id,
                        next_idx,
                        role,
                        content,
                        mode,
                        citations_json,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                ids.append(turn_id)
                next_idx += 1
    finally:
        conn.close()
    logger.info("appended turns: conversation=%s count=%d", conversation_id, len(ids))
    return ids


def create_conversation_with_turns(
    db_path: str,
    kind: str,
    turns: list[tuple[str, str, str | None, str]],
) -> tuple[str, list[str]]:
    """Create a conversation plus its turns in ONE transaction.

    The router's new-conversation path calls this AFTER successful generation
    so a failed generation persists nothing — no empty conversation rows.
    """
    conversation_id = uuid.uuid4().hex
    created_at = datetime.now(UTC).isoformat()
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO conversations (id, kind, created_at) VALUES (?, ?, ?)",
                (conversation_id, kind, created_at),
            )
            ids = []
            for idx, (role, content, mode, citations_json) in enumerate(turns):
                turn_id = uuid.uuid4().hex
                conn.execute(
                    "INSERT INTO turns (id, conversation_id, idx, role, content, mode,"
                    " citations, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        turn_id,
                        conversation_id,
                        idx,
                        role,
                        content,
                        mode,
                        citations_json,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                ids.append(turn_id)
    finally:
        conn.close()
    logger.info(
        "created conversation with turns: id=%s kind=%s count=%d",
        conversation_id,
        kind,
        len(ids),
    )
    return conversation_id, ids


def get_conversation(db_path: str, conversation_id: str) -> ConversationDetail | None:
    """Fetch a conversation with its turns ordered by idx, or None."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if row is None:
            return None
        turn_rows = conn.execute(
            "SELECT id, conversation_id, idx, role, content, mode, citations, created_at"
            " FROM turns WHERE conversation_id = ? ORDER BY idx",
            (conversation_id,),
        ).fetchall()
    finally:
        conn.close()
    return ConversationDetail(
        id=row["id"],
        kind=row["kind"],
        created_at=row["created_at"],
        turns=[
            TurnDetail(
                id=r["id"],
                conversation_id=r["conversation_id"],
                idx=r["idx"],
                role=r["role"],
                content=r["content"],
                mode=r["mode"],
                citations_json=r["citations"],
                created_at=r["created_at"],
            )
            for r in turn_rows
        ],
    )


@dataclass
class ConversationDeleteCounts:
    conversation_id: str
    turns: int
    artifacts: int
    chunks: int
    facts: int
    unlinked_facts: int


def delete_conversation_cascade(
    db_path: str, conversation_id: str
) -> ConversationDeleteCounts | None:
    """Delete a conversation, its turns, and its indexed artifacts in ONE transaction.

    Returns None when the conversation does not exist. Artifact deletion runs
    through the shared cascade core (``_delete_artifacts_cascade_conn`` — the
    private cross-module import is deliberate so deliverable 4 reuses the
    exact same semantics); turns cascade via FK and linked attempts keep
    their rows with ``conversation_id`` NULLed (practice history stays
    independently available). Never touches explanations (no linkage).
    """
    conn = connect(db_path)
    try:
        with conn:
            row = conn.execute(
                "SELECT id FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            if row is None:
                return None
            turns = conn.execute(
                "SELECT COUNT(*) AS n FROM turns WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()["n"]
            artifact_ids = [
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM artifacts"
                    " WHERE json_extract(origin, '$.adapter') = 'tb_conversation'"
                    " AND json_extract(origin, '$.conversation_id') = ?"
                    " ORDER BY created_at, id",
                    (conversation_id,),
                ).fetchall()
            ]
            counts = _delete_artifacts_cascade_conn(conn, artifact_ids)
            conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    finally:
        conn.close()
    result = ConversationDeleteCounts(
        conversation_id=conversation_id,
        turns=turns,
        artifacts=counts["artifacts"],
        chunks=counts["chunks"],
        facts=counts["facts"],
        unlinked_facts=counts["unlinked_facts"],
    )
    logger.info(
        "deleted conversation: id=%s turns=%d artifacts=%d chunks=%d facts=%d unlinked=%d",
        conversation_id,
        turns,
        result.artifacts,
        result.chunks,
        result.facts,
        result.unlinked_facts,
    )
    return result


def list_conversations(db_path: str) -> list[ConversationSummary]:
    """List conversations with turn counts, oldest first."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT c.id, c.kind, c.created_at,"
            " (SELECT COUNT(*) FROM turns t WHERE t.conversation_id = c.id) AS turn_count"
            " FROM conversations c ORDER BY c.created_at, c.id"
        ).fetchall()
    finally:
        conn.close()
    return [
        ConversationSummary(
            id=r["id"], kind=r["kind"], created_at=r["created_at"], turn_count=r["turn_count"]
        )
        for r in rows
    ]
