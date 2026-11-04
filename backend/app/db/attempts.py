"""Attempt repository: practice-loop rows over the attempts table.

One row per asked question: created with the question + stored evaluation
reference, updated when the user answers (re-answering overwrites —
supports "retry the full explanation" on one question). ``needs_retry`` is
computed deterministically at read: answered AND (``missing`` or
``inaccurate`` non-empty). Unanswered attempts are pending, not retry.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.db.connection import connect

logger = logging.getLogger(__name__)


@dataclass
class AttemptDetail:
    id: str
    mode: str
    question_kind: str | None
    explanation_id: str | None
    concept: str | None
    question: str
    answer: str | None
    feedback: dict[str, Any] | None
    grounding: str | None
    needs_retry: bool
    conversation_id: str | None
    reference: dict[str, Any]
    created_at: str


def _parse_json_dict(raw: str | None) -> dict[str, Any] | None:
    """Parse stored JSON defensively: malformed/non-dict → None, never raises."""
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _needs_retry(answer: str | None, feedback: dict[str, Any] | None) -> bool:
    """Retry rule: answered AND missing-or-inaccurate non-empty (MVP re-queue)."""
    if answer is None or not answer.strip():
        return False
    if feedback is None:
        return False
    missing = feedback.get("missing")
    inaccurate = feedback.get("inaccurate")
    return (isinstance(missing, list) and len(missing) > 0) or (
        isinstance(inaccurate, list) and len(inaccurate) > 0
    )


def _row_to_detail(row: Any) -> AttemptDetail:
    feedback = _parse_json_dict(row["feedback"])
    reference = _parse_json_dict(row["reference_json"]) or {}
    return AttemptDetail(
        id=row["id"],
        mode=row["mode"],
        question_kind=row["question_kind"],
        explanation_id=row["explanation_id"],
        concept=row["concept"],
        question=row["question"],
        answer=row["answer"],
        feedback=feedback,
        grounding=row["grounding"],
        needs_retry=_needs_retry(row["answer"], feedback),
        conversation_id=row["conversation_id"],
        reference=reference,
        created_at=row["created_at"],
    )


_ATTEMPT_COLS = (
    "a.id, a.mode, a.question_kind, a.explanation_id, e.concept AS concept,"
    " a.question, a.answer, a.feedback, a.grounding, a.conversation_id,"
    " a.reference_json, a.created_at"
)
_ATTEMPT_FROM = "FROM attempts a LEFT JOIN explanations e ON e.id = a.explanation_id"


def create_attempt(
    db_path: str,
    *,
    mode: str,
    question_kind: str | None,
    explanation_id: str | None,
    question: str,
    conversation_id: str,
    reference_json: dict[str, Any],
) -> str:
    """Insert one attempt row in a single transaction; return its id."""
    attempt_id = uuid.uuid4().hex
    created_at = datetime.now(UTC).isoformat()
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO attempts (id, mode, question_kind, explanation_id,"
                " question, conversation_id, reference_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    attempt_id,
                    mode,
                    question_kind,
                    explanation_id,
                    question,
                    conversation_id,
                    json.dumps(reference_json),
                    created_at,
                ),
            )
    finally:
        conn.close()
    logger.info("created attempt: id=%s mode=%s kind=%s", attempt_id, mode, question_kind)
    return attempt_id


def record_answer(
    db_path: str,
    attempt_id: str,
    *,
    answer: str,
    feedback: dict[str, Any],
    grounding: str,
) -> bool:
    """Set answer/feedback/grounding on an attempt; False when missing.

    Overwrites on re-answer (latest answer wins); the router appends new
    turns for every answer call.
    """
    conn = connect(db_path)
    try:
        with conn:
            cursor = conn.execute(
                "UPDATE attempts SET answer = ?, feedback = ?, grounding = ? WHERE id = ?",
                (answer, json.dumps(feedback), grounding, attempt_id),
            )
    finally:
        conn.close()
    updated = cursor.rowcount > 0
    logger.info("recorded answer: attempt=%s updated=%s", attempt_id, updated)
    return updated


def get_attempt(db_path: str, attempt_id: str) -> AttemptDetail | None:
    """Fetch one attempt with its concept, or None when missing."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            f"SELECT {_ATTEMPT_COLS} {_ATTEMPT_FROM} WHERE a.id = ?", (attempt_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return _row_to_detail(row)


def list_attempts(
    db_path: str,
    *,
    mode: str | None = None,
    explanation_id: str | None = None,
    retry_only: bool = False,
) -> list[AttemptDetail]:
    """List attempts newest-first with optional filters (all AND-combined).

    ``mode``/``explanation_id`` filter in SQL (None = no constraint);
    ``retry_only`` filters to ``needs_retry`` in Python. The router owns
    validation (blank explanation_id → 422 before reaching here).
    """
    clauses: list[str] = []
    params: list[str] = []
    if mode is not None:
        clauses.append("a.mode = ?")
        params.append(mode)
    if explanation_id is not None:
        clauses.append("a.explanation_id = ?")
        params.append(explanation_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            f"SELECT {_ATTEMPT_COLS} {_ATTEMPT_FROM} {where} ORDER BY a.created_at DESC, a.id ASC",
            params,
        ).fetchall()
    finally:
        conn.close()
    details = [_row_to_detail(r) for r in rows]
    if retry_only:
        details = [d for d in details if d.needs_retry]
    return details
