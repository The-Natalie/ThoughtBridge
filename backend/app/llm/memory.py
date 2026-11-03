"""Explanation memory selection — pure deterministic cascade over repository reads.

PRD F-4: before generating, retrieve past Explanations for the same concept
(and related ones by similarity); reuse is governed by explicit success
signals (markers first, then reuse count, then attempt outcomes). No network,
no model, no settings; the router partially applies ``db_path``.

Import direction is definitive and cycle-free: module level imports
``app.llm.explainer`` (types) only; ``app.db.*`` is imported ONLY inside
``build_memory_context`` (function-local). ``app/llm/explainer.py`` must NEVER
import this module.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING

from app.llm.explainer import MemoryContext

if TYPE_CHECKING:
    from app.db.explanations import ExplanationSummary

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def concept_tier(query_norm: str, cand_norm: str) -> int | None:
    """Tier a candidate concept against the normalized query concept.

    0 = same concept (normalized equality); 1 = substring containment either
    direction (guarded: shorter string must be >= 3 chars, so "AI" never
    matches "air"); 2 = word-token overlap (|Q cap C| / |Q| >= 0.5 over
    len>=2 tokens); None = unrelated (excluded from candidates).
    Both inputs must already be normalized (see ``normalize_concept``).
    """
    if query_norm == cand_norm:
        return 0
    if min(len(query_norm), len(cand_norm)) >= 3 and (
        query_norm in cand_norm or cand_norm in query_norm
    ):
        return 1
    query_tokens = {t for t in _TOKEN_RE.findall(query_norm) if len(t) >= 2}
    if not query_tokens:
        return None
    cand_tokens = {t for t in _TOKEN_RE.findall(cand_norm) if len(t) >= 2}
    if len(query_tokens & cand_tokens) / len(query_tokens) >= 0.5:
        return 2
    return None


def _epoch(created_at: str) -> float:
    """Parse a stored UTC ISO-8601 timestamp to epoch seconds (0.0 fallback)."""
    try:
        return datetime.fromisoformat(created_at).timestamp()
    except ValueError:
        return 0.0


def marked_rank_of(has_explanation_marker: bool, has_step_marker: bool) -> int:
    """Rank marker strength: 0 = whole-explanation mark, 1 = step marks only."""
    if has_explanation_marker:
        return 0
    if has_step_marker:
        return 1
    return 2


def build_framing_note(
    *,
    same_concept: bool,
    marked: bool,
    winner_id: str,
    winner_version: int,
    winner_concept: str,
    marker_note: str = "",
) -> str:
    """Render the one-paragraph reuse framing for the memory block (pure)."""
    short = winner_id[:8]
    if same_concept and marked:
        note = (
            f"This concept clicked for you before (marked explanation {short} v{winner_version})."
            " Reuse its analogy family — this worked for you before."
        )
    elif same_concept:
        note = (
            f"You studied this concept before (explanation {short} v{winner_version},"
            " not marked as clicked). Build on its analogy family only where it fits."
        )
    elif marked:
        note = (
            f"A related concept ({winner_concept!r}) clicked for you before"
            f" (marked explanation {short} v{winner_version})."
            " Its analogy family may help here — adapt it, do not force it."
        )
    else:
        note = (
            f"You studied a related concept ({winner_concept!r}) before"
            f" (explanation {short} v{winner_version})."
            " Its analogy family may help — adapt it, do not force it."
        )
    if marker_note.strip():
        note += f" Your note on what clicked: {marker_note.strip()}"
    return note


def build_memory_context(db_path: str, concept: str) -> MemoryContext | None:
    """Select the best prior explanation for `concept`, or None when none fits.

    Deterministic total order: tier ASC, marked rank ASC, reuse count DESC,
    answered-attempt count DESC, recency DESC, id ASC. Tier-0 (same concept)
    always beats related tiers.
    """
    if not concept.strip():
        return None
    from app.db.explanations import (
        get_explanation,
        list_explanations,
        list_markers,
        normalize_concept,
    )

    summaries = list_explanations(db_path)
    query_norm = normalize_concept(concept)
    ranked: list[tuple[tuple[int, int, int, int, float, str], int, ExplanationSummary]] = []
    for s in summaries:
        tier = concept_tier(query_norm, normalize_concept(s.concept))
        if tier is None:
            continue
        rank = marked_rank_of(s.has_explanation_marker, s.marked and not s.has_explanation_marker)
        key = (tier, rank, -s.reuse_count, -s.attempt_count, -_epoch(s.created_at), s.id)
        ranked.append((key, tier, s))
    if not ranked:
        return None
    _, winner_tier, winner = min(ranked, key=lambda triple: triple[0])
    detail = get_explanation(db_path, winner.id)
    if detail is None:
        logger.warning("memory dropped winner with no explanation row: %s", winner.id)
        return None
    marker_note = ""
    for m in list_markers(db_path, winner.id):
        if m.scope == "explanation" and m.note.strip():
            marker_note = m.note.strip()
    framing = build_framing_note(
        same_concept=(winner_tier == 0),
        marked=marked_rank_of(
            winner.has_explanation_marker, winner.marked and not winner.has_explanation_marker
        )
        < 2,
        winner_id=winner.id,
        winner_version=winner.version,
        winner_concept=winner.concept,
        marker_note=marker_note,
    )
    logger.info("memory selected: concept=%s winner=%s tier=%s", concept, winner.id, winner_tier)
    return MemoryContext(
        reused_from=winner.id, prior_steps=dict(detail.steps), framing_note=framing
    )
