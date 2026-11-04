"""Practice Loop endpoints — thin router over llm/practice + attempts (PRD §10).

`POST /practice/question` generates one mode-parameterized question and
persists its attempt + turns; `POST /practice/answer` evaluates an answer
against the attempt's STORED reference and persists answer + feedback turns
in the attempt's conversation; `GET /practice/attempts` lists the attempt
log with deterministic re-queue filtering.

Test seams: ``generate_question``, ``evaluate_answer``, ``chat_completion``,
``hybrid_search``, ``read_career_context``, ``get_explanation``,
``create_attempt``, ``record_answer``, ``get_attempt``, ``list_attempts``,
``get_conversation``, ``create_conversation_with_turns``, ``append_turns``,
``get_settings``, and ``index_conversation_turns`` are imported BY NAME so
tests can ``monkeypatch.setattr("app.api.practice.<name>", stub)``
(mirrors the learn/query/work router seams).
"""

from __future__ import annotations

import functools
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.core.grounding import build_practice_request_turn, render_feedback_text
from app.core.meta_client import DEFAULT_META_MODEL, MetaAPIError, chat_completion
from app.db.attempts import AttemptDetail, create_attempt, get_attempt, list_attempts, record_answer
from app.db.connection import EmbeddingDimMismatchError
from app.db.conversations import append_turns, create_conversation_with_turns, get_conversation
from app.db.explanations import get_explanation
from app.ingest.conversation_memory import index_conversation_turns
from app.llm.extraction import read_career_context
from app.llm.practice import (
    NoEvidenceError,
    PracticeInputError,
    PracticeValidationError,
    StaleReferenceError,
    UnknownReferenceError,
    evaluate_answer,
    generate_question,
)
from app.retrieval.search import hybrid_search

logger = logging.getLogger(__name__)

router = APIRouter(tags=["practice"])


class PracticeQuestionContext(BaseModel):
    explanation_id: str | None = None
    focus: str | None = Field(default=None, max_length=2000)


class QuestionRequest(BaseModel):
    mode: Literal["learning", "interview"]
    question_kind: Literal["experience", "technical"] | None = None
    context: PracticeQuestionContext | None = None
    conversation_id: str | None = None


class QuestionResponse(BaseModel):
    attempt_id: str
    question: str
    question_kind: str | None
    reference_kind: str
    conversation_id: str


class AnswerRequest(BaseModel):
    attempt_id: str
    answer: str


class FeedbackOut(BaseModel):
    correct: list[str]
    missing: list[str]
    inaccurate: list[str]
    terminology: list[str]
    next_step: str


class AnswerResponse(BaseModel):
    feedback: FeedbackOut
    grounding: str


class AttemptOut(BaseModel):
    id: str
    mode: str
    question_kind: str | None
    explanation_id: str | None
    concept: str | None
    question: str
    answer: str | None
    feedback: FeedbackOut | None
    grounding: str | None
    needs_retry: bool
    created_at: str


def _make_chat_fn(settings, model_wanted: str):
    """Build the (messages, budget) chat closure over the Meta client."""

    async def chat_fn(messages: list[dict[str, str]], max_tokens: int) -> str:
        key = settings.model_api_key.get_secret_value()
        if not key:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="MODEL_API_KEY not configured",
            )
        return await chat_completion(
            api_key=key, model=model_wanted, messages=messages, max_tokens=max_tokens
        )

    return chat_fn


def _turn_mode_label(mode: str, kind: str | None) -> str:
    return mode if kind is None else f"{mode}:{kind}"


def _attempt_to_out(detail: AttemptDetail) -> AttemptOut:
    """Map a repository row to API shape; bad stored feedback → null, never raises."""
    feedback_out: FeedbackOut | None = None
    if detail.feedback is not None:
        try:
            feedback_out = FeedbackOut.model_validate(detail.feedback)
        except ValidationError:
            logger.warning("attempt %s has malformed stored feedback; serving null", detail.id)
            feedback_out = None
    return AttemptOut(
        id=detail.id,
        mode=detail.mode,
        question_kind=detail.question_kind,
        explanation_id=detail.explanation_id,
        concept=detail.concept,
        question=detail.question,
        answer=detail.answer,
        feedback=feedback_out,
        grounding=detail.grounding,
        needs_retry=detail.needs_retry,
        created_at=detail.created_at,
    )


@router.post("/practice/question", response_model=QuestionResponse)
async def post_question(body: QuestionRequest) -> QuestionResponse:
    """Generate one practice question; persist its attempt + turns."""
    context = body.context or PracticeQuestionContext()
    focus = context.focus.strip() if context.focus and context.focus.strip() else None
    settings = get_settings()
    db_path = settings.database_path
    embedding_model = settings.embedding_model
    model_wanted = settings.meta_model or DEFAULT_META_MODEL

    existing = None
    if body.conversation_id is not None:
        existing = get_conversation(db_path, body.conversation_id)
        if existing is None:
            logger.warning(
                "practice question rejected: unknown conversation %s", body.conversation_id
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found"
            )

    def search_fn(query: str, top_k: int):  # stub seam: hybrid_search by name
        return hybrid_search(
            db_path=db_path,
            query=query,
            top_k=top_k,
            embedding_model=embedding_model,
            embed_fn=None,
        )

    try:
        result = await generate_question(
            mode=body.mode,
            question_kind=body.question_kind,
            explanation_id=context.explanation_id,
            focus=focus,
            db_path=db_path,
            chat_fn=_make_chat_fn(settings, model_wanted),
            search_fn=search_fn,
            career_fn=functools.partial(read_career_context, db_path),
        )
    except (PracticeInputError, NoEvidenceError) as exc:
        logger.warning("practice question rejected: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UnknownReferenceError as exc:
        logger.warning("practice question rejected: %s", exc)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (PracticeValidationError, MetaAPIError) as exc:
        logger.warning("practice question failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except (EmbeddingDimMismatchError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    if body.mode == "learning" and result.explanation_id is not None:
        source = get_explanation(db_path, result.explanation_id)
        concept = source.concept if source is not None else result.explanation_id
        descriptor = f"explain back the lesson on '{concept}'"
    elif focus:
        descriptor = f"answer a {result.question_kind} question about '{focus}'"
    else:
        descriptor = f"answer a {result.question_kind} question"
    mode_label = _turn_mode_label(body.mode, result.question_kind)
    request_turn = build_practice_request_turn(body.mode, result.question_kind, descriptor)
    turns: list[tuple[str, str, str | None, str]] = [
        ("user", request_turn, mode_label, "[]"),
        ("assistant", result.question, mode_label, "[]"),
    ]
    # Turns persist BEFORE the attempt row: the attempt's conversation_id FK
    # requires the conversation to exist (new-conversation path).
    if existing is None:
        kind = "learning" if body.mode == "learning" else "interview"
        conversation_id, _ = create_conversation_with_turns(db_path, kind, turns)
    else:
        append_turns(db_path, existing.id, turns)
        conversation_id = existing.id
    attempt_id = create_attempt(
        db_path,
        mode=body.mode,
        question_kind=result.question_kind,
        explanation_id=result.explanation_id,
        question=result.question,
        conversation_id=conversation_id,
        reference_json=result.reference_json,
    )
    index_conversation_turns(
        db_path=db_path,
        conversation_id=conversation_id,
        kind="learning" if body.mode == "learning" else "interview",
        turns=[(t[0], t[1]) for t in turns],
        turn_start=0 if existing is None else len(existing.turns),
        max_artifact_chars=settings.max_artifact_chars,
        embedding_model=embedding_model,
        embed_fn=None,
    )
    logger.info(
        "practice question served: mode=%s kind=%s attempt=%s conversation=%s",
        body.mode,
        result.question_kind,
        attempt_id,
        conversation_id,
    )
    return QuestionResponse(
        attempt_id=attempt_id,
        question=result.question,
        question_kind=result.question_kind,
        reference_kind=result.reference_kind,
        conversation_id=conversation_id,
    )


@router.post("/practice/answer", response_model=AnswerResponse)
async def post_answer(body: AnswerRequest) -> AnswerResponse:
    """Evaluate one answer against its attempt's stored reference."""
    if not body.answer.strip():
        logger.warning("practice answer rejected: blank answer")
        raise HTTPException(status_code=422, detail="answer must not be blank")
    settings = get_settings()
    db_path = settings.database_path
    model_wanted = settings.meta_model or DEFAULT_META_MODEL

    attempt = get_attempt(db_path, body.attempt_id)
    if attempt is None:
        logger.warning("practice answer rejected: unknown attempt %s", body.attempt_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="attempt not found")

    try:
        result = await evaluate_answer(
            mode=attempt.mode,
            question_kind=attempt.question_kind,
            explanation_id=attempt.explanation_id,
            reference_json=attempt.reference,
            answer=body.answer,
            db_path=db_path,
            chat_fn=_make_chat_fn(settings, model_wanted),
        )
    except PracticeInputError as exc:
        logger.warning("practice answer rejected: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UnknownReferenceError as exc:
        logger.warning("practice answer rejected: %s", exc)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StaleReferenceError as exc:
        logger.warning("practice answer rejected: %s", exc)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (PracticeValidationError, MetaAPIError) as exc:
        logger.warning("practice answer failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    record_answer(
        db_path,
        attempt.id,
        answer=body.answer,
        feedback=result.feedback,
        grounding=result.grounding,
    )
    mode_label = _turn_mode_label(attempt.mode, attempt.question_kind)
    turns: list[tuple[str, str, str | None, str]] = [
        ("user", body.answer, mode_label, "[]"),
        ("assistant", render_feedback_text(result.feedback), mode_label, "[]"),
    ]
    kind = "learning" if attempt.mode == "learning" else "interview"
    existing = (
        get_conversation(db_path, attempt.conversation_id)
        if attempt.conversation_id is not None
        else None
    )
    if existing is None:
        # Fresh conversation: the attempt never had one, or its conversation
        # was deleted — persist + index at turn 0.
        conversation_id, _ = create_conversation_with_turns(db_path, kind, turns)
        turn_start = 0
    else:
        append_turns(db_path, existing.id, turns)
        conversation_id = existing.id
        turn_start = len(existing.turns)
    index_conversation_turns(
        db_path=db_path,
        conversation_id=conversation_id,
        kind=kind,
        turns=[(t[0], t[1]) for t in turns],
        turn_start=turn_start,
        max_artifact_chars=settings.max_artifact_chars,
        embedding_model=settings.embedding_model,
        embed_fn=None,
    )
    logger.info("practice answer served: attempt=%s grounding=%s", attempt.id, result.grounding)
    return AnswerResponse(
        feedback=FeedbackOut.model_validate(result.feedback), grounding=result.grounding
    )


@router.get("/practice/attempts", response_model=list[AttemptOut])
def list_attempts_endpoint(
    mode: Literal["learning", "interview"] | None = Query(default=None),
    explanation_id: str | None = Query(default=None),
    retry_only: bool = Query(default=False),
) -> list[AttemptOut]:
    """List practice attempts, newest first, with optional filters."""
    if explanation_id is not None and not explanation_id.strip():
        logger.warning("attempts list rejected: blank explanation_id filter")
        raise HTTPException(status_code=422, detail="explanation_id filter must not be blank")
    return [
        _attempt_to_out(detail)
        for detail in list_attempts(
            get_settings().database_path,
            mode=mode,
            explanation_id=explanation_id,
            retry_only=retry_only,
        )
    ]
