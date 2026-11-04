"""Learner-preferences repository: single-row reads/writes over learner_profile.

Canonical owner of EMPHASIS_KEYS (PRD F-13 / PRD section 10 order). Import
direction is definitive and cycle-free: ``app/llm/explainer.py`` imports this
module at module level (established explainer -> db direction), so this
module must NEVER import ``app.llm.*`` at any level.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.db.connection import connect

logger = logging.getLogger(__name__)

EMPHASIS_KEYS: tuple[str, ...] = (
    "familiar_systems",
    "component_mapping",
    "process_placement",
    "interactions",
    "terminology_bridge",
)


def default_emphasis() -> dict[str, bool]:
    """Fresh all-True emphasis dict (never share a mutable default)."""
    return {key: True for key in EMPHASIS_KEYS}


@dataclass
class LearnerProfile:
    emphasis: dict[str, bool]
    how_i_learn: str


def _merge_emphasis(raw: object) -> dict[str, bool]:
    """Merge a stored emphasis value over defaults, dropping unknown keys.

    Non-dict values and non-bool entries fall back to True per key.
    """
    if not isinstance(raw, dict):
        return default_emphasis()
    return {key: (raw[key] if isinstance(raw.get(key), bool) else True) for key in EMPHASIS_KEYS}


def get_learner_profile(db_path: str) -> LearnerProfile:
    """Read the single-row profile; pure read returning defaults when unset.

    A missing row (fresh DB) yields all-True emphasis + "" WITHOUT writing.
    Malformed stored JSON falls back to defaults with a warning, never a 500.
    """
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT emphasis, how_i_learn FROM learner_profile WHERE id = 1",
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return LearnerProfile(emphasis=default_emphasis(), how_i_learn="")
    try:
        parsed = json.loads(row["emphasis"])
    except (ValueError, TypeError) as exc:
        logger.warning("learner profile emphasis unparsable, using defaults: %s", exc)
        return LearnerProfile(emphasis=default_emphasis(), how_i_learn=row["how_i_learn"] or "")
    how_i_learn = row["how_i_learn"]
    return LearnerProfile(
        emphasis=_merge_emphasis(parsed),
        how_i_learn=how_i_learn if isinstance(how_i_learn, str) else "",
    )


def update_learner_profile(
    db_path: str,
    emphasis: dict[str, bool] | None,
    how_i_learn: str | None,
) -> LearnerProfile:
    """Merge-update the single-row profile (upsert id = 1); return the merged row.

    None arguments are skipped, so ``update_learner_profile(db, None, None)``
    is a valid no-op returning the current profile.
    """
    current = get_learner_profile(db_path)
    merged_emphasis = dict(current.emphasis)
    if emphasis is not None:
        for key, value in emphasis.items():
            if key in merged_emphasis:
                merged_emphasis[key] = value
    merged_text = current.how_i_learn if how_i_learn is None else how_i_learn
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO learner_profile (id, emphasis, how_i_learn)"
                " VALUES (1, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET"
                " emphasis = excluded.emphasis, how_i_learn = excluded.how_i_learn",
                (json.dumps(merged_emphasis), merged_text),
            )
    finally:
        conn.close()
    logger.info(
        "updated learner profile: emphasis=%s how_i_learn_chars=%d",
        merged_emphasis,
        len(merged_text),
    )
    return LearnerProfile(emphasis=merged_emphasis, how_i_learn=merged_text)
