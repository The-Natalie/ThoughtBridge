"""Grounded Q&A orchestration: retrieve → route → generate → validate → cite.

Pure orchestration over injected ``search_fn``/``chat_fn`` seams: unit tests
stub both, the router passes adapters over the real hybrid search and Meta
client. Refusal is a normal result, never an exception — except teaching
mode with malformed model output, which is a genuine upstream failure.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from app.core.grounding import (
    REFUSAL_ANSWER,
    HistoryTurn,
    ModeUsed,
    NumberedPassage,
    QueryMode,
    build_messages,
    build_refusal,
    route_auto,
)
from app.db.chunks import get_chunks
from app.retrieval.search import SearchHit, excerpt_of

logger = logging.getLogger(__name__)

SearchFn = Callable[[str, int], list[SearchHit]]
ChatFn = Callable[[list[dict[str, str]]], Awaitable[str]]


class QaValidationError(ValueError):
    """Teaching-mode model output failed schema validation (→ HTTP 502)."""


class QaModelOut(BaseModel):
    answer: str
    citations: list[int]


@dataclass
class CitationHit:
    chunk_id: int
    artifact_id: str
    span_start: int
    span_end: int
    excerpt: str


@dataclass
class QaResult:
    answer: str
    citations: list[CitationHit]
    mode_used: ModeUsed


def strip_fences(text: str) -> str:
    """Remove one ```json ... ``` wrapper when the model adds fences."""
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        inner = stripped[3:-3].strip()
        if inner.lower().startswith("json"):
            inner = inner[4:].strip()
        return inner
    return stripped


async def answer_question(
    *,
    question: str,
    mode: QueryMode,
    top_k: int,
    db_path: str,
    search_fn: SearchFn,
    chat_fn: ChatFn,
    history: tuple[HistoryTurn, ...] = (),
) -> QaResult:
    """Answer one question with citations; see module contract."""
    hits = search_fn(question, top_k)
    mode_used: ModeUsed = route_auto(question) if mode == "auto" else mode
    if mode_used == "evidence" and not hits:
        logger.warning("query refused: mode=evidence hits=0 reason=empty retrieval")
        return QaResult(answer=build_refusal(), citations=[], mode_used="evidence")

    details = get_chunks(db_path, [h.chunk_id for h in hits])
    passages: list[NumberedPassage] = []
    for n, hit in enumerate(hits, start=1):
        detail = details.get(hit.chunk_id)
        if detail is None:
            logger.warning("qa dropped leg id with no chunk row: %d", hit.chunk_id)
            continue
        passages.append(
            NumberedPassage(
                n=n, chunk_id=detail.id, artifact_id=detail.artifact_id, text=detail.text
            )
        )
    by_number = {p.n: p for p in passages}

    raw = await chat_fn(build_messages(mode_used, question, passages, history))
    try:
        parsed = QaModelOut.model_validate_json(strip_fences(raw))
    except (ValueError, ValidationError) as exc:
        if mode_used == "evidence":
            logger.warning("query refused: mode=evidence reason=unparseable model output")
            return QaResult(answer=build_refusal(), citations=[], mode_used="evidence")
        logger.warning("qa validation failed: mode=teaching detail=%s", exc)
        raise QaValidationError(f"model returned malformed Q&A JSON: {exc}") from exc

    citations: list[CitationHit] = []
    for number in parsed.citations:
        passage = by_number.get(number)
        if passage is None:
            logger.warning("qa dropped out-of-range citation: %d", number)
            continue
        detail = details[passage.chunk_id]
        citations.append(
            CitationHit(
                chunk_id=detail.id,
                artifact_id=detail.artifact_id,
                span_start=detail.span_start,
                span_end=detail.span_end,
                excerpt=excerpt_of(detail.text),
            )
        )
    if mode_used == "evidence" and not citations:
        logger.warning("query refused: mode=evidence reason=zero valid citations")
        return QaResult(answer=REFUSAL_ANSWER, citations=[], mode_used="evidence")
    logger.info("query answered: mode=%s citations=%d", mode_used, len(citations))
    return QaResult(answer=parsed.answer, citations=citations, mode_used=mode_used)
