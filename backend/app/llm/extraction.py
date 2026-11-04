"""Work extraction orchestration: chunks → validate → translate → persist.

Pure orchestration over injected ``chat_fn``/``career_fn``/``persist_fn`` seams:
unit tests stub all three, the router passes the real Meta adapter, the
``no_career`` default (deliverable 5 fills the real read), and ``None`` for the
repository path. Every validation failure raises BEFORE persisting — no partial
facts, no orphan rows. An empty ``{"facts": []}`` model result is a legitimate
outcome (nothing extractable), not a failure.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, get_args

from pydantic import BaseModel, Field, ValidationError

from app.core.grounding import (
    CAREER_LINES_FRAMING,
    EXTRACTION_KINDS,
    EXTRACTION_PROMPT_VERSION,
    EXTRACTION_STATUSES,
    LINK_RELATIONS,
    NumberedPassage,
    build_extraction_messages,
    render_career_profile_lines,
)
from app.db.artifacts import find_missing_artifact_ids
from app.db.career_profile import get_career_profile
from app.db.chunks import get_chunks_by_artifacts
from app.db.facts import FactCreate, FactLinkCreate, create_facts
from app.llm.qa import strip_fences

logger = logging.getLogger(__name__)

EXTRACTION_MAX_TOKENS = 16384
MAX_EXTRACTION_CHARS = 30_000
MAX_EXTRACTION_ARTIFACTS = 20

# (messages, max_tokens) — same budgeted arity as ExplainerChatFn: the budget
# travels with the call and the router adapts.
ExtractionChatFn = Callable[[list[dict[str, str]], int], Awaitable[str]]


@dataclass
class CareerContext:
    current_role: str
    past_roles: list[str]
    target_career: str
    target_position: str


CareerFn = Callable[[], CareerContext]
PersistFn = Callable[[list[tuple[str, FactCreate, list[FactLinkCreate]]], str, str], list[str]]


class ExtractionValidationError(ValueError):
    """Model output failed schema/reference validation (→ HTTP 502)."""


class ExtractionTooLargeError(ValueError):
    """Requested chunks exceed MAX_EXTRACTION_CHARS (→ HTTP 413)."""


class UnknownArtifactError(ValueError):
    """One or more artifact ids do not exist (→ HTTP 404)."""


class EmptyExtractionError(ValueError):
    """Requested artifacts hold zero chunks (→ HTTP 422)."""


FactKind = Literal["problem", "decision", "accomplishment", "skill"]
FactStatus = Literal["proposed", "rejected", "completed"]
LinkRelation = Literal[
    "constrained_by",
    "considered",
    "rejected_because",
    "decided",
    "implemented_by",
    "resulted_in",
]

# Drift guards: the Literals above must match the grounding vocabularies.
assert set(get_args(FactKind)) == set(EXTRACTION_KINDS)
assert set(get_args(FactStatus)) == set(EXTRACTION_STATUSES)
assert set(get_args(LinkRelation)) == set(LINK_RELATIONS)


class ExtractionLinkOut(BaseModel):
    to: int
    relation: LinkRelation


class ExtractionFactOut(BaseModel):
    kind: FactKind
    status: FactStatus
    summary: str
    skills: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    chunk_ids: list[int]
    links: list[ExtractionLinkOut]


class ExtractionModelOut(BaseModel):
    facts: list[ExtractionFactOut]


@dataclass
class ExtractedLink:
    to_fact: str
    relation: str


@dataclass
class ExtractedFact:
    fact_id: str
    kind: str
    status: str
    summary: str
    skills: list[str]
    confidence: float
    chunk_ids: list[int]
    links: list[ExtractedLink]


@dataclass
class ExtractedResult:
    facts: list[ExtractedFact]


def no_career() -> CareerContext:
    """Seam default: no career profile yet (deliverable 5 fills this)."""
    return CareerContext(current_role="", past_roles=[], target_career="", target_position="")


def render_career_block(career: CareerContext) -> str:
    """Render career context as extraction-shaping instructions, or "" when empty.

    Delegates the framing + profile lines to the shared grounding contract;
    output is byte-identical to the pre-delegation implementation.
    """
    profile_lines = render_career_profile_lines(
        current_role=career.current_role,
        past_roles=career.past_roles,
        target_career=career.target_career,
        target_position=career.target_position,
    )
    if not profile_lines:
        return ""
    return "\n".join(
        [
            "Career profile (prioritize and phrase extraction toward this trajectory):",
            CAREER_LINES_FRAMING,
            *profile_lines,
        ]
    )


def read_career_context(db_path: str) -> CareerContext:
    """Seam filler: DB-backed CareerFn for the router.

    Wire as ``functools.partial(read_career_context, db_path)``.
    ``no_career`` remains the unit-test default.
    """
    profile = get_career_profile(db_path)
    return CareerContext(
        current_role=profile.current_role,
        past_roles=list(profile.past_roles),
        target_career=profile.target_career,
        target_position=profile.target_position,
    )


async def run_extraction(
    *,
    artifact_ids: list[str],
    db_path: str,
    chat_fn: ExtractionChatFn,
    career_fn: CareerFn,
    model: str,
    persist_fn: PersistFn | None = None,
) -> ExtractedResult:
    """Extract grounded facts over artifacts (single call, atomic persist)."""
    ordered_ids = list(dict.fromkeys(artifact_ids))
    missing = find_missing_artifact_ids(db_path, ordered_ids)
    if missing:
        raise UnknownArtifactError(f"unknown artifact(s): {', '.join(missing)}")

    grouped = get_chunks_by_artifacts(db_path, ordered_ids)
    ordered_chunks = [c for aid in ordered_ids for c in grouped.get(aid, [])]
    if not ordered_chunks:
        raise EmptyExtractionError("artifacts hold no chunks to extract from")
    total_chars = sum(len(c.text) for c in ordered_chunks)
    if total_chars > MAX_EXTRACTION_CHARS:
        raise ExtractionTooLargeError(
            f"extraction input has {total_chars} chars, over the"
            f" MAX_EXTRACTION_CHARS={MAX_EXTRACTION_CHARS} cap;"
            " split the artifacts across calls"
        )

    passages = [
        NumberedPassage(n=n, chunk_id=c.id, artifact_id=c.artifact_id, text=c.text)
        for n, c in enumerate(ordered_chunks, start=1)
    ]
    valid_chunk_ids = {c.id for c in ordered_chunks}
    career_block = render_career_block(career_fn())
    raw = await chat_fn(build_extraction_messages(passages, career_block), EXTRACTION_MAX_TOKENS)
    try:
        parsed = ExtractionModelOut.model_validate_json(strip_fences(raw))
    except (ValueError, ValidationError) as exc:
        logger.warning("extraction validation failed: detail=%s", exc)
        raise ExtractionValidationError(f"model returned malformed extraction JSON: {exc}") from exc

    if not parsed.facts:
        logger.info("extraction complete: artifacts=%d facts=0 links=0", len(ordered_ids))
        return ExtractedResult(facts=[])

    for i, fact in enumerate(parsed.facts):
        if not fact.summary.strip():
            raise ExtractionValidationError(f"fact {i} has a blank summary")
        if not fact.chunk_ids:
            raise ExtractionValidationError(f"fact {i} cites no chunks")
        for chunk_id in fact.chunk_ids:
            if chunk_id not in valid_chunk_ids:
                raise ExtractionValidationError(f"fact {i} cites unknown chunk_id {chunk_id}")
        for skill in fact.skills:
            if not skill.strip():
                raise ExtractionValidationError(f"fact {i} has a blank skills entry")
        for link in fact.links:
            if link.to == i:
                raise ExtractionValidationError(f"fact {i} links to itself")
            if link.to < 0 or link.to >= len(parsed.facts):
                raise ExtractionValidationError(
                    f"fact {i} links to out-of-range fact index {link.to}"
                )

    fact_ids = [uuid.uuid4().hex for _ in parsed.facts]
    items: list[tuple[str, FactCreate, list[FactLinkCreate]]] = []
    for fact_id, fact in zip(fact_ids, parsed.facts):
        links = [
            FactLinkCreate(
                from_fact_id=fact_id, to_fact_id=fact_ids[link.to], relation=link.relation
            )
            for link in fact.links
        ]
        items.append(
            (
                fact_id,
                FactCreate(
                    kind=fact.kind,
                    status=fact.status,
                    summary=fact.summary,
                    skills=list(fact.skills),
                    confidence=fact.confidence,
                    chunk_ids=list(fact.chunk_ids),
                ),
                links,
            )
        )
    if persist_fn is not None:
        stored_ids = persist_fn(items, model, EXTRACTION_PROMPT_VERSION)
    else:
        stored_ids = create_facts(
            db_path=db_path, items=items, model=model, prompt_version=EXTRACTION_PROMPT_VERSION
        )
    if stored_ids != fact_ids:
        raise ValueError("persist_fn returned ids differing from the assigned fact ids")

    link_count = sum(len(fact.links) for fact in parsed.facts)
    logger.info(
        "extraction complete: artifacts=%d facts=%d links=%d",
        len(ordered_ids),
        len(fact_ids),
        link_count,
    )
    return ExtractedResult(
        facts=[
            ExtractedFact(
                fact_id=fact_id,
                kind=fact.kind,
                status=fact.status,
                summary=fact.summary,
                skills=list(fact.skills),
                confidence=fact.confidence,
                chunk_ids=list(fact.chunk_ids),
                links=[
                    ExtractedLink(to_fact=fact_ids[link.to], relation=link.relation)
                    for link in fact.links
                ],
            )
            for fact_id, fact in zip(fact_ids, parsed.facts)
        ]
    )
