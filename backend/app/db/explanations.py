"""Explanations repository: versioned lessons over the explanations table."""

from __future__ import annotations

import json
import logging
import re
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


def normalize_concept(concept: str) -> str:
    """Normalize a concept string for same-concept matching (single owner).

    Collapses whitespace runs and casefolds, so "  PHOTOSYNTHESIS " matches
    "Photosynthesis". Pure stdlib. Defined here (not in llm/) because this
    repo owns concept-matching semantics — and because app/llm/explainer.py
    already imports this module, this file must never import app.llm.*.
    """
    return re.sub(r"\s+", " ", concept.strip()).casefold()


@dataclass
class Marker:
    id: str
    explanation_id: str
    scope: str
    step: str | None
    note: str
    created_at: str


@dataclass
class ExplanationSummary:
    id: str
    concept: str
    version: int
    created_at: str
    reused_from: str | None
    reuse_count: int
    marked: bool
    has_explanation_marker: bool
    marker_count: int
    attempt_count: int


def create_marker(
    db_path: str,
    explanation_id: str,
    scope: str,
    step: str | None,
    note: str,
) -> Marker:
    """Insert one "clicked" marker event in a single transaction; return the row.

    Assumes validated input (the router validates scope/step). Duplicates are
    allowed: each call is one event, and "marked" is an EXISTS query.
    """
    marker_id = uuid.uuid4().hex
    created_at = datetime.now(UTC).isoformat()
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO explanation_markers (id, explanation_id, scope, step, note,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (marker_id, explanation_id, scope, step, note, created_at),
            )
    finally:
        conn.close()
    logger.info(
        "created marker: id=%s explanation=%s scope=%s step=%s",
        marker_id,
        explanation_id,
        scope,
        step,
    )
    return Marker(
        id=marker_id,
        explanation_id=explanation_id,
        scope=scope,
        step=step,
        note=note,
        created_at=created_at,
    )


def list_markers(db_path: str, explanation_id: str) -> list[Marker]:
    """All markers for one explanation, chronological (history order)."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, explanation_id, scope, step, note, created_at"
            " FROM explanation_markers WHERE explanation_id = ?"
            " ORDER BY created_at ASC, id ASC",
            (explanation_id,),
        ).fetchall()
    finally:
        conn.close()
    return [
        Marker(
            id=r["id"],
            explanation_id=r["explanation_id"],
            scope=r["scope"],
            step=r["step"],
            note=r["note"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


def list_explanations(db_path: str, concept_filter: str | None = None) -> list[ExplanationSummary]:
    """Summaries of stored explanations with aggregate success signals.

    One connection, four queries: base rows newest-first, reuse counts,
    marker aggregates, answered-attempt counts. `concept_filter` applies
    normalized same-concept equality in Python (tier-0 only).
    """
    conn = connect(db_path)
    try:
        base = conn.execute(
            "SELECT id, concept, version, created_at, reused_from FROM explanations"
            " ORDER BY created_at DESC, id ASC"
        ).fetchall()
        reuse_rows = conn.execute(
            "SELECT reused_from, COUNT(*) AS n FROM explanations"
            " WHERE reused_from IS NOT NULL GROUP BY reused_from"
        ).fetchall()
        marker_rows = conn.execute(
            "SELECT explanation_id, scope, COUNT(*) AS n FROM explanation_markers"
            " GROUP BY explanation_id, scope"
        ).fetchall()
        attempt_rows = conn.execute(
            "SELECT explanation_id, COUNT(*) AS n FROM attempts"
            " WHERE explanation_id IS NOT NULL AND TRIM(COALESCE(answer, '')) <> ''"
            " GROUP BY explanation_id"
        ).fetchall()
    finally:
        conn.close()
    reuse_counts = {r["reused_from"]: r["n"] for r in reuse_rows}
    marker_counts: dict[str, int] = {}
    explanation_marked: set[str] = set()
    for r in marker_rows:
        marker_counts[r["explanation_id"]] = marker_counts.get(r["explanation_id"], 0) + r["n"]
        if r["scope"] == "explanation":
            explanation_marked.add(r["explanation_id"])
    attempt_counts = {r["explanation_id"]: r["n"] for r in attempt_rows}
    wanted = normalize_concept(concept_filter) if concept_filter is not None else None
    summaries: list[ExplanationSummary] = []
    for r in base:
        if wanted is not None and normalize_concept(r["concept"]) != wanted:
            continue
        summaries.append(
            ExplanationSummary(
                id=r["id"],
                concept=r["concept"],
                version=r["version"],
                created_at=r["created_at"],
                reused_from=r["reused_from"],
                reuse_count=reuse_counts.get(r["id"], 0),
                marked=r["id"] in marker_counts,
                has_explanation_marker=r["id"] in explanation_marked,
                marker_count=marker_counts.get(r["id"], 0),
                attempt_count=attempt_counts.get(r["id"], 0),
            )
        )
    return summaries
