"""Learning endpoints — thin router over llm/explainer + explanations.

`POST /learn/explain` runs the 3-stage explainer; `GET /learn/explanations/{id}`
fetches one stored version; `POST /learn/explanations/{id}/regenerate`
regenerates one step as a new version.

Test seams: ``chat_completion``, ``get_explanation``, ``generate_explanation``,
and ``regenerate_step`` are imported BY NAME so tests can
``monkeypatch.setattr("app.api.learn.<name>", stub)`` (mirrors the
query/ingest/retrieval router seams).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.grounding import STEP_KEYS
from app.core.meta_client import DEFAULT_META_MODEL, MetaAPIError, chat_completion
from app.db.explanations import get_explanation
from app.llm.explainer import (
    ExplainerValidationError,
    default_learner_context,
    generate_explanation,
    no_memory,
    regenerate_step,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["learn"])


class ExplainRequest(BaseModel):
    concept: str = Field(min_length=1)
    familiar_system_hint: str | None = None


class ExplainResponse(BaseModel):
    explanation_id: str
    reused_from: str | None
    steps: dict


class ExplanationOut(BaseModel):
    id: str
    concept: str
    version: int
    steps: dict
    mapping: list
    limitations: str
    reused_from: str | None
    created_at: str


class RegenerateRequest(BaseModel):
    step: str


RegenerateResponse = ExplainResponse


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


@router.post("/learn/explain", response_model=ExplainResponse)
async def post_explain(body: ExplainRequest) -> ExplainResponse:
    """Teach a concept: 3-stage generation persisted as a new version."""
    if not body.concept.strip():
        logger.warning("explain rejected: blank concept")
        raise HTTPException(status_code=422, detail="concept must not be blank")
    settings = get_settings()
    db_path = settings.database_path
    model_wanted = settings.meta_model or DEFAULT_META_MODEL
    try:
        result = await generate_explanation(
            concept=body.concept,
            hint=body.familiar_system_hint,
            db_path=db_path,
            chat_fn=_make_chat_fn(settings, model_wanted),
            profile_fn=default_learner_context,
            memory_fn=no_memory,
        )
    except ExplainerValidationError as exc:
        # BEFORE the generic ValueError branch: ExplainerValidationError subclasses it.
        logger.warning("explain failed: validation: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except MetaAPIError as exc:
        logger.warning("explain failed: meta: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    logger.info("explain served: concept=%s id=%s", body.concept, result.explanation_id)
    return ExplainResponse(
        explanation_id=result.explanation_id,
        reused_from=result.reused_from,
        steps=result.steps,
    )


@router.get("/learn/explanations/{explanation_id}", response_model=ExplanationOut)
def get_explanation_endpoint(explanation_id: str) -> ExplanationOut:
    """Fetch one stored explanation version."""
    detail = get_explanation(get_settings().database_path, explanation_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="explanation not found")
    return ExplanationOut(
        id=detail.id,
        concept=detail.concept,
        version=detail.version,
        steps=detail.steps,
        mapping=detail.mapping,
        limitations=detail.limitations,
        reused_from=detail.reused_from,
        created_at=detail.created_at,
    )


@router.post(
    "/learn/explanations/{explanation_id}/regenerate",
    response_model=RegenerateResponse,
)
async def post_regenerate(explanation_id: str, body: RegenerateRequest) -> ExplainResponse:
    """Regenerate one step of an explanation as a new version."""
    settings = get_settings()
    db_path = settings.database_path
    source = get_explanation(db_path, explanation_id)
    if source is None:
        logger.warning("regenerate rejected: unknown explanation %s", explanation_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="explanation not found")
    if body.step not in STEP_KEYS:
        logger.warning("regenerate rejected: invalid step %s", body.step)
        raise HTTPException(
            status_code=422,
            detail=f"invalid step {body.step!r}: must be one of {', '.join(STEP_KEYS)}",
        )
    model_wanted = settings.meta_model or DEFAULT_META_MODEL
    try:
        result = await regenerate_step(
            source=source,
            step=body.step,
            db_path=db_path,
            chat_fn=_make_chat_fn(settings, model_wanted),
        )
    except ExplainerValidationError as exc:
        # BEFORE the generic ValueError branch: ExplainerValidationError subclasses it.
        logger.warning("regenerate failed: validation: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except MetaAPIError as exc:
        logger.warning("regenerate failed: meta: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    logger.info(
        "regenerate served: source=%s step=%s id=%s",
        explanation_id,
        body.step,
        result.explanation_id,
    )
    return ExplainResponse(
        explanation_id=result.explanation_id,
        reused_from=result.reused_from,
        steps=result.steps,
    )
