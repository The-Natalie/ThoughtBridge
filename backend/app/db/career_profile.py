"""Career-profile repository: single-row reads/writes over career_profile.

Mirrors ``app/db/learner_profile.py`` (PRD F-6 / PRD section 10 field order).
Import direction is definitive and cycle-free: ``app/llm/extraction.py``
imports this module at module level (established llm -> db direction), so
this module must NEVER import ``app.llm.*`` at any level.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.db.connection import connect

logger = logging.getLogger(__name__)


@dataclass
class CareerProfile:
    current_role: str
    past_roles: list[str]
    target_career: str
    target_position: str


def _clean_roles(raw: object) -> list[str]:
    """Clean a stored past_roles value: list of stripped non-blank strings.

    Non-list values, or any non-string entry, fall back to [] (never a 500).
    """
    if not isinstance(raw, list):
        return []
    if any(not isinstance(role, str) for role in raw):
        return []
    return [role.strip() for role in raw if role.strip()]


def _clean_scalar(raw: object) -> str:
    """Clean a stored scalar: the string itself, else "" (never a 500)."""
    return raw if isinstance(raw, str) else ""


def get_career_profile(db_path: str) -> CareerProfile:
    """Read the single-row profile; pure read returning defaults when unset.

    A missing row (fresh DB) yields all-empty defaults WITHOUT writing.
    Malformed stored JSON falls back to defaults with a warning, never a 500.
    """
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT current_role, past_roles, target_career, target_position"
            " FROM career_profile WHERE id = 1",
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return CareerProfile(current_role="", past_roles=[], target_career="", target_position="")
    try:
        parsed = json.loads(row["past_roles"])
    except (ValueError, TypeError) as exc:
        logger.warning("career profile past_roles unparsable, using defaults: %s", exc)
        return CareerProfile(
            current_role=_clean_scalar(row["current_role"]),
            past_roles=[],
            target_career=_clean_scalar(row["target_career"]),
            target_position=_clean_scalar(row["target_position"]),
        )
    return CareerProfile(
        current_role=_clean_scalar(row["current_role"]),
        past_roles=_clean_roles(parsed),
        target_career=_clean_scalar(row["target_career"]),
        target_position=_clean_scalar(row["target_position"]),
    )


def update_career_profile(
    db_path: str,
    current_role: str | None,
    past_roles: list[str] | None,
    target_career: str | None,
    target_position: str | None,
) -> CareerProfile:
    """Merge-update the single-row profile (upsert id = 1); return the merged row.

    None arguments are skipped, so all-None is a valid no-op returning the
    current profile. Scalars are stripped; past roles are stripped with
    blanks dropped.
    """
    current = get_career_profile(db_path)
    merged_role = current.current_role if current_role is None else current_role.strip()
    merged_roles = (
        current.past_roles
        if past_roles is None
        else [role.strip() for role in past_roles if role.strip()]
    )
    merged_career = current.target_career if target_career is None else target_career.strip()
    merged_position = (
        current.target_position if target_position is None else target_position.strip()
    )
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO career_profile"
                " (id, current_role, past_roles, target_career, target_position)"
                " VALUES (1, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET"
                " current_role = excluded.current_role,"
                " past_roles = excluded.past_roles,"
                " target_career = excluded.target_career,"
                " target_position = excluded.target_position",
                (merged_role, json.dumps(merged_roles), merged_career, merged_position),
            )
    finally:
        conn.close()
    logger.info(
        "updated career profile: current_role_chars=%d past_roles=%d target_career_chars=%d",
        len(merged_role),
        len(merged_roles),
        len(merged_career),
    )
    return CareerProfile(
        current_role=merged_role,
        past_roles=merged_roles,
        target_career=merged_career,
        target_position=merged_position,
    )
