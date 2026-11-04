"""Facts repository: single-transaction writes over facts + fact_chunks + fact_links."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from app.db.connection import connect

logger = logging.getLogger(__name__)


@dataclass
class FactCreate:
    kind: str
    status: str
    summary: str
    skills: list[str]
    confidence: float
    chunk_ids: list[int]


@dataclass
class FactLinkCreate:
    from_fact_id: str
    to_fact_id: str
    relation: str


def create_facts(
    *,
    db_path: str,
    items: list[tuple[str, FactCreate, list[FactLinkCreate]]],
    model: str,
    prompt_version: str,
) -> list[str]:
    """Insert facts with evidence + links in ONE transaction; return ids in order.

    Each item is ``(pre-assigned fact id, fact, outgoing links)`` — the caller
    (the extraction orchestrator) owns id generation so link translation and
    response assembly share one id set. Link rows insert only after all fact
    rows exist (self-join FKs); identical ``(from, to, relation)`` triples are
    deduped first so the link PK can never abort the transaction. Empty
    ``items`` is a no-op returning ``[]``.
    """
    if not items:
        return []
    created_at = datetime.now(UTC).isoformat()
    link_rows: list[tuple[str, str, str]] = []
    seen_links: set[tuple[str, str, str]] = set()
    conn = connect(db_path)
    try:
        with conn:
            for fact_id, fact, links in items:
                conn.execute(
                    "INSERT INTO facts (id, kind, status, summary, skills, confidence,"
                    " model, prompt_version, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        fact_id,
                        fact.kind,
                        fact.status,
                        fact.summary,
                        json.dumps(fact.skills),
                        fact.confidence,
                        model,
                        prompt_version,
                        created_at,
                    ),
                )
                for chunk_id in fact.chunk_ids:
                    conn.execute(
                        "INSERT INTO fact_chunks (fact_id, chunk_id) VALUES (?, ?)",
                        (fact_id, chunk_id),
                    )
                for link in links:
                    triple = (link.from_fact_id, link.to_fact_id, link.relation)
                    if triple not in seen_links:
                        seen_links.add(triple)
                        link_rows.append(triple)
            for from_id, to_id, relation in link_rows:
                conn.execute(
                    "INSERT INTO fact_links (from_fact_id, to_fact_id, relation) VALUES (?, ?, ?)",
                    (from_id, to_id, relation),
                )
    finally:
        conn.close()
    logger.info(
        "created facts: count=%d links=%d model=%s prompt=%s",
        len(items),
        len(link_rows),
        model,
        prompt_version,
    )
    return [fact_id for fact_id, _, _ in items]
