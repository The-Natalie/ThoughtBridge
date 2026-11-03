"""Explanations repository: versioned lessons over the explanations table."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.db.connection import connect

logger = logging.getLogger(__name__)


@dataclass
class ExplanationDetail:
    id: str
    concept: str
    version: int
    steps: dict
    mapping: list
    limitations: str
    reused_from: str | None
    created_at: str


def create_explanation(
    db_path: str,
    concept: str,
    version: int,
    steps: dict,
    mapping: list,
    limitations: str,
    reused_from: str | None,
) -> ExplanationDetail:
    """Insert one explanation version in a single transaction; return the row."""
    explanation_id = uuid.uuid4().hex
    created_at = datetime.now(UTC).isoformat()
    steps_json = json.dumps(steps)
    mapping_json = json.dumps(mapping)
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO explanations (id, concept, version, steps, mapping,"
                " limitations, reused_from, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    explanation_id,
                    concept,
                    version,
                    steps_json,
                    mapping_json,
                    limitations,
                    reused_from,
                    created_at,
                ),
            )
    finally:
        conn.close()
    logger.info(
        "created explanation: id=%s concept=%s version=%d", explanation_id, concept, version
    )
    return ExplanationDetail(
        id=explanation_id,
        concept=concept,
        version=version,
        steps=steps,
        mapping=mapping,
        limitations=limitations,
        reused_from=reused_from,
        created_at=created_at,
    )


def get_explanation(db_path: str, explanation_id: str) -> ExplanationDetail | None:
    """Fetch one explanation by id, or None when missing."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT id, concept, version, steps, mapping, limitations, reused_from,"
            " created_at FROM explanations WHERE id = ?",
            (explanation_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return ExplanationDetail(
        id=row["id"],
        concept=row["concept"],
        version=row["version"],
        steps=json.loads(row["steps"]),
        mapping=json.loads(row["mapping"]),
        limitations=row["limitations"],
        reused_from=row["reused_from"],
        created_at=row["created_at"],
    )


def max_version_for_concept(db_path: str, concept: str) -> int:
    """Highest stored version for an exact concept string (0 when none)."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS m FROM explanations WHERE concept = ?",
            (concept,),
        ).fetchone()
    finally:
        conn.close()
    return int(row["m"])
