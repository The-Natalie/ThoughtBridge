"""Practice Loop orchestration: assemble references → generate → evaluate.

Generation-only over injected ``chat_fn``/``search_fn``/``career_fn`` seams:
unit tests stub all three, the router passes adapters over the real Meta
client, hybrid search, and career profile. Persistence lives in the router
(qa-precedent — turns + attempt must persist in router order).

References are assembled at question time, persisted ON the attempt, and
reHYDRATED (never re-derived) at answer time — the evaluator is literally
constrained to question-time references.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.grounding import (
    CAREER_LINES_FRAMING,
    GroundingLabel,
    build_evaluation_messages,
    build_explanation_context,
    build_question_messages,
    render_career_profile_lines,
    resolve_grounding,
)
from app.db.chunks import get_chunks
from app.db.explanations import get_explanation
from app.db.facts import FactRead, get_facts_by_ids, list_accomplishments
from app.llm.extraction import CareerContext, CareerFn, no_career
from app.llm.memory import build_memory_context
from app.llm.qa import strip_fences
from app.retrieval.search import TOP_K_DEFAULT, SearchHit, excerpt_of

logger = logging.getLogger(__name__)

QUESTION_MAX_TOKENS = 8192
EVALUATION_MAX_TOKENS = 8192
MAX_PRACTICE_FACTS = 10
MAX_REFERENCE_CHARS = 12000

# (messages, max_tokens) — budget travels with the call (explainer/extraction
# convention), NOT qa's (messages) arity.
PracticeChatFn = Callable[[list[dict[str, str]], int], Awaitable[str]]
PracticeSearchFn = Callable[[str, int], list[SearchHit]]


class PracticeInputError(ValueError):
    """Request shape violates the mode/kind matrix (→ HTTP 422)."""


class UnknownReferenceError(ValueError):
    """A referenced explanation/conversation/attempt does not exist (→ 404)."""


class NoEvidenceError(ValueError):
    """No stored evidence grounds this question (→ HTTP 422)."""


class StaleReferenceError(ValueError):
    """Question-time reference rows no longer exist (→ HTTP 409)."""


class PracticeValidationError(ValueError):
    """Model output failed schema validation (→ HTTP 502)."""


class QuestionModelOut(BaseModel):
    question: str


class FeedbackModelOut(BaseModel):
    correct: list[str]
    missing: list[str]
    inaccurate: list[str]
    terminology: list[str]
    next_step: str


class EvaluationModelOut(BaseModel):
    feedback: FeedbackModelOut


@dataclass
class QuestionResult:
    question: str
    question_kind: str | None
    reference_kind: str
    reference_json: dict[str, Any]
    explanation_id: str | None


@dataclass
class EvaluationResult:
    feedback: dict[str, Any]
    grounding: str


def build_career_block(career: CareerContext) -> str:
    """Render the career profile as a question-gen system block ("" when empty).

    Follows the Phase 3 recipe in grounding.render_career_profile_lines:
    header + CAREER_LINES_FRAMING + joined lines.
    """
    lines = render_career_profile_lines(
        current_role=career.current_role,
        past_roles=career.past_roles,
        target_career=career.target_career,
        target_position=career.target_position,
    )
    if not lines:
        return ""
    return (
        "Career profile (shape emphasis from it):\n"
        + CAREER_LINES_FRAMING
        + "\n"
        + "\n".join(lines)
    )


def render_fact_block(fact: FactRead, excerpts: dict[int, str]) -> str:
    """Render one fact + its supporting chunk excerpts as reference text."""
    lines = [
        f"Fact ({fact.kind}, {fact.status}, confidence {fact.confidence:.2f}):",
        fact.summary,
    ]
    if fact.skills:
        lines.append("Skills: " + ", ".join(fact.skills))
    for chunk_id in fact.chunk_ids:
        excerpt = excerpts.get(chunk_id)
        if excerpt is not None:
            lines.append(f"Source [chunk {chunk_id}]: {excerpt}")
    return "\n".join(lines)


async def generate_question(
    *,
    mode: str,
    question_kind: str | None,
    explanation_id: str | None,
    focus: str | None,
    db_path: str,
    chat_fn: PracticeChatFn,
    search_fn: PracticeSearchFn,
    career_fn: CareerFn = no_career,
) -> QuestionResult:
    """Generate one practice question with its stored evaluation reference."""
    if mode == "learning":
        if question_kind is not None:
            raise PracticeInputError("question_kind must be null in learning mode")
        if not explanation_id:
            raise PracticeInputError("learning mode requires context.explanation_id")
        source = get_explanation(db_path, explanation_id)
        if source is None:
            raise UnknownReferenceError(f"unknown explanation: {explanation_id}")
        reference_block = "Lesson under review:\n" + build_explanation_context(source.steps)
        reference_kind = "explanation"
        reference_json: dict[str, Any] = {}
        stored_explanation_id = source.id
    elif mode == "interview":
        if question_kind not in ("experience", "technical"):
            raise PracticeInputError("interview mode requires question_kind experience|technical")
        stored_explanation_id = None
        if question_kind == "experience":
            reference_block, reference_kind, reference_json = _experience_reference(db_path, focus)
        else:
            reference_block, reference_kind, reference_json = _technical_reference(
                db_path, focus, search_fn
            )
    else:
        raise PracticeInputError(f"invalid mode: {mode!r}")

    career_block = build_career_block(career_fn())
    messages = build_question_messages(
        mode=mode,
        kind=question_kind,
        reference_block=reference_block,
        career_block=career_block,
        focus=focus,
    )
    raw = await chat_fn(messages, QUESTION_MAX_TOKENS)
    try:
        parsed = QuestionModelOut.model_validate_json(strip_fences(raw))
    except (ValueError, ValidationError) as exc:
        logger.warning("practice question validation failed: %s", exc)
        raise PracticeValidationError(f"model returned malformed question JSON: {exc}") from exc
    if not parsed.question.strip():
        raise PracticeValidationError("model returned a blank question")
    logger.info("practice question generated: mode=%s kind=%s", mode, question_kind)
    return QuestionResult(
        question=parsed.question,
        question_kind=question_kind,
        reference_kind=reference_kind,
        reference_json=reference_json,
        explanation_id=stored_explanation_id,
    )


def _experience_reference(db_path: str, focus: str | None) -> tuple[str, str, dict[str, Any]]:
    """Assemble the experience reference: newest facts + source excerpts."""
    all_facts = list_accomplishments(db_path)
    if not all_facts:
        raise NoEvidenceError("no accomplishment facts stored — extract work first")
    facts = list_accomplishments(db_path, q=focus) if focus else all_facts
    if not facts:
        raise NoEvidenceError(f"no accomplishments match focus {focus!r} ({len(all_facts)} stored)")
    blocks: list[str] = ["Accomplishment record (closed world — judge only from this):"]
    included: list[str] = []
    used_chars = len(blocks[0])
    for fact in facts[:MAX_PRACTICE_FACTS]:
        details = get_chunks(db_path, fact.chunk_ids)
        excerpts = {cid: excerpt_of(d.text) for cid, d in details.items()}
        block = render_fact_block(fact, excerpts)
        if used_chars + 1 + len(block) > MAX_REFERENCE_CHARS:
            break
        blocks.append(block)
        used_chars += 1 + len(block)
        included.append(fact.fact_id)
    if not included:
        raise NoEvidenceError("accomplishment facts exceed the reference budget")
    return "\n\n".join(blocks), "facts", {"fact_ids": included}


def _technical_reference(
    db_path: str, focus: str | None, search_fn: PracticeSearchFn
) -> tuple[str, str, dict[str, Any]]:
    """Assemble the technical reference: retrieved passages (possibly none)."""
    hits = search_fn(focus or "technical interview concepts", TOP_K_DEFAULT)
    if not hits:
        return "", "general", {"chunk_ids": []}
    details = get_chunks(db_path, [h.chunk_id for h in hits])
    blocks = ["Related passages from your notes (personal context, may be empty):"]
    included: list[int] = []
    for n, hit in enumerate(hits, start=1):
        detail = details.get(hit.chunk_id)
        if detail is None:
            logger.warning("practice dropped leg id with no chunk row: %d", hit.chunk_id)
            continue
        blocks.append(f"Passage [{n}] (chunk_id={detail.id}):\n{detail.text}")
        included.append(detail.id)
    if not included:
        return "", "general", {"chunk_ids": []}
    return "\n\n".join(blocks), "general", {"chunk_ids": included}


async def evaluate_answer(
    *,
    mode: str,
    question_kind: str | None,
    explanation_id: str | None,
    reference_json: dict[str, Any],
    answer: str,
    db_path: str,
    chat_fn: PracticeChatFn,
) -> EvaluationResult:
    """Evaluate one answer against its STORED question-time reference.

    Never retrieves fresh references (no search_fn parameter by design):
    learning rehydrates the explanation, experience rehydrates the fact ids,
    technical rehydrates the chunk ids.
    """
    if mode == "learning":
        assert explanation_id is not None  # router guarantees: learning requires it
        source = get_explanation(db_path, explanation_id)
        if source is None:
            raise UnknownReferenceError(f"unknown explanation: {explanation_id}")
        reference_block = "Lesson under review:\n" + build_explanation_context(source.steps)
        mem = build_memory_context(db_path, source.concept)
        personal_refs = source.reused_from is not None or (
            mem is not None and mem.reused_from != source.id
        )
    elif mode == "interview" and question_kind == "experience":
        fact_ids = [str(i) for i in reference_json.get("fact_ids", [])]
        facts = get_facts_by_ids(db_path, fact_ids)
        missing = [i for i in fact_ids if i not in facts]
        if missing:
            raise StaleReferenceError("question reference no longer exists; request a new question")
        chunk_ids = [c for f in fact_ids for c in facts[f].chunk_ids]
        details = get_chunks(db_path, chunk_ids)
        for chunk_id in chunk_ids:
            if chunk_id not in details:
                logger.warning("practice dropped missing chunk row: %d", chunk_id)
        blocks = ["Accomplishment record (closed world — judge only from this):"]
        for fact_id in fact_ids:
            fact = facts[fact_id]
            excerpts = {
                cid: excerpt_of(details[cid].text) for cid in fact.chunk_ids if cid in details
            }
            blocks.append(render_fact_block(fact, excerpts))
        reference_block = "\n\n".join(blocks)
        personal_refs = True
    elif mode == "interview" and question_kind == "technical":
        chunk_ids = [int(c) for c in reference_json.get("chunk_ids", [])]
        details = get_chunks(db_path, chunk_ids)
        for chunk_id in chunk_ids:
            if chunk_id not in details:
                logger.warning("practice dropped missing chunk row: %d", chunk_id)
        kept = [c for c in chunk_ids if c in details]
        if kept:
            blocks = ["Related passages from your notes (personal context, may be empty):"]
            for n, chunk_id in enumerate(kept, start=1):
                blocks.append(f"Passage [{n}] (chunk_id={chunk_id}):\n{details[chunk_id].text}")
            reference_block = "\n\n".join(blocks)
        else:
            reference_block = ""
        personal_refs = bool(kept)
    else:
        raise PracticeInputError(f"invalid mode/kind: {mode!r}/{question_kind!r}")

    messages = build_evaluation_messages(
        mode=mode, kind=question_kind, reference_block=reference_block, answer=answer
    )
    raw = await chat_fn(messages, EVALUATION_MAX_TOKENS)
    try:
        parsed = EvaluationModelOut.model_validate_json(strip_fences(raw))
    except (ValueError, ValidationError) as exc:
        logger.warning("practice evaluation validation failed: %s", exc)
        raise PracticeValidationError(f"model returned malformed feedback JSON: {exc}") from exc
    grounding: GroundingLabel = resolve_grounding(mode, question_kind, personal_refs)
    logger.info("practice answer evaluated: mode=%s kind=%s", mode, question_kind)
    return EvaluationResult(feedback=parsed.feedback.model_dump(), grounding=grounding)
