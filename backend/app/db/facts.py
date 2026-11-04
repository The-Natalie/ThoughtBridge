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


@dataclass
class FactLinkRead:
    to_fact: str
    relation: str


@dataclass
class FactRead:
    fact_id: str
    kind: str
    status: str
    summary: str
    skills: list[str]
    confidence: float
    chunk_ids: list[int]
    links: list[FactLinkRead]
    created_at: str


def _clean_skills(raw: str) -> list[str]:
    """Parse a stored skills JSON array defensively (never raises)."""
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [skill for skill in parsed if isinstance(skill, str)]


def _matches_q(summary: str, skills: list[str], q: str) -> bool:
    """Every whitespace-split term (casefold) appears in summary or a skill."""
    haystacks = [summary.casefold(), *(skill.casefold() for skill in skills)]
    return all(any(term in hay for hay in haystacks) for term in q.split())


def _matches_skill(skills: list[str], skill: str) -> bool:
    """Some skill casefold-equals the wanted tag (exact match, not substring)."""
    wanted = skill.strip().casefold()
    return any(entry.casefold() == wanted for entry in skills)


def get_facts_by_ids(db_path: str, ids: list[str]) -> dict[str, FactRead]:
    """Fetch facts by id with evidence + links, keyed by fact id.

    Mirrors ``list_accomplishments`` hydration; any kind (the reader stays
    general — callers own kind expectations). Missing ids are absent from
    the result (callers detect them for stale-reference handling). Empty
    ``ids`` returns ``{}`` without querying.
    """
    if not ids:
        return {}
    placeholders = ", ".join("?" for _ in ids)
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, kind, status, summary, skills, confidence, created_at"
            f" FROM facts WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
        chunk_rows = conn.execute(
            "SELECT fact_id, chunk_id FROM fact_chunks"
            f" WHERE fact_id IN ({placeholders}) ORDER BY chunk_id",
            ids,
        ).fetchall()
        link_rows = conn.execute(
            "SELECT from_fact_id, to_fact_id, relation FROM fact_links"
            f" WHERE from_fact_id IN ({placeholders}) ORDER BY to_fact_id, relation",
            ids,
        ).fetchall()
    finally:
        conn.close()
    chunks_by_fact: dict[str, list[int]] = {}
    for row in chunk_rows:
        chunks_by_fact.setdefault(row["fact_id"], []).append(row["chunk_id"])
    links_by_fact: dict[str, list[FactLinkRead]] = {}
    for row in link_rows:
        links_by_fact.setdefault(row["from_fact_id"], []).append(
            FactLinkRead(to_fact=row["to_fact_id"], relation=row["relation"])
        )
    return {
        row["id"]: FactRead(
            fact_id=row["id"],
            kind=row["kind"],
            status=row["status"],
            summary=row["summary"],
            skills=_clean_skills(row["skills"]),
            confidence=row["confidence"],
            chunk_ids=chunks_by_fact.get(row["id"], []),
            links=links_by_fact.get(row["id"], []),
            created_at=row["created_at"],
        )
        for row in rows
    }


def list_accomplishments(
    db_path: str,
    *,
    q: str | None = None,
    skill: str | None = None,
) -> list[FactRead]:
    """List kind='accomplishment' facts, newest first, with evidence + links.

    Pure read (zero writes): retention is independent of relevance. ``q``
    and ``skill`` are query-time-only filters (AND-combined); ``None`` means
    no constraint. The router rejects blank filters before they reach here;
    a blank ``q`` would vacuously match everything and a blank ``skill``
    would match nothing, so callers must validate first.
    """
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, kind, status, summary, skills, confidence, created_at"
            " FROM facts WHERE kind = 'accomplishment'"
            " ORDER BY created_at DESC, id ASC",
        ).fetchall()
        chunk_rows = conn.execute(
            "SELECT fact_id, chunk_id FROM fact_chunks ORDER BY chunk_id",
        ).fetchall()
        link_rows = conn.execute(
            "SELECT from_fact_id, to_fact_id, relation FROM fact_links"
            " ORDER BY to_fact_id, relation",
        ).fetchall()
    finally:
        conn.close()
    chunks_by_fact: dict[str, list[int]] = {}
    for row in chunk_rows:
        chunks_by_fact.setdefault(row["fact_id"], []).append(row["chunk_id"])
    links_by_fact: dict[str, list[FactLinkRead]] = {}
    for row in link_rows:
        links_by_fact.setdefault(row["from_fact_id"], []).append(
            FactLinkRead(to_fact=row["to_fact_id"], relation=row["relation"])
        )
    results: list[FactRead] = []
    for row in rows:
        skills = _clean_skills(row["skills"])
        if q is not None and not _matches_q(row["summary"], skills, q):
            continue
        if skill is not None and not _matches_skill(skills, skill):
            continue
        results.append(
            FactRead(
                fact_id=row["id"],
                kind=row["kind"],
                status=row["status"],
                summary=row["summary"],
                skills=skills,
                confidence=row["confidence"],
                chunk_ids=chunks_by_fact.get(row["id"], []),
                links=links_by_fact.get(row["id"], []),
                created_at=row["created_at"],
            )
        )
    return results
