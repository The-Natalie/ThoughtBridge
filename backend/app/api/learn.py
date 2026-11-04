"""Learning endpoints — thin router over llm/explainer + explanations.

`POST /learn/explain` runs the 3-stage explainer; `GET /learn/explanations/{id}`
fetches one stored version; `POST /learn/explanations/{id}/regenerate`
regenerates one step as a new version.

Test seams: ``chat_completion``, ``get_explanation``, ``generate_explanation``,
``regenerate_step``, ``build_memory_context``, ``list_explanations``,
``create_marker``, ``list_markers``, ``get_learner_profile``,
``update_learner_profile``, and ``read_learner_context`` are imported BY NAME
so tests can ``monkeypatch.setattr("app.api.learn.<name>", stub)`` (mirrors
the query/ingest/retrieval router seams).
"""

from __future__ import annotations

import functools
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.grounding import STEP_KEYS
from app.core.meta_client import DEFAULT_META_MODEL, MetaAPIError, chat_completion
from app.db.explanations import (
    create_marker,
    get_explanation,
    list_explanations,
    list_markers,
)
from app.db.learner_profile import (
    EMPHASIS_KEYS,
    get_learner_profile,
    update_learner_profile,
)
from app.llm.explainer import (
    ExplainerValidationError,
    generate_explanation,
    read_learner_context,
    regenerate_step,
)
from app.llm.memory import build_memory_context

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


class MarkerCreate(BaseModel):
    scope: Literal["explanation", "step"]
    step: str | None = None
    note: str = ""


class MarkerCreated(BaseModel):
    marker_id: str
    explanation_id: str
    scope: str
    step: str | None


class MarkerOut(BaseModel):
    id: str
    explanation_id: str
    scope: str
    step: str | None
    note: str
    created_at: str


class ExplanationSummaryOut(BaseModel):
    id: str
    concept: str
    version: int
    created_at: str
    reused_from: str | None
    reuse_count: int
    marked: bool
    marker_count: int
    attempt_count: int


class LearnerProfileOut(BaseModel):
    emphasis: dict[str, bool]
    how_i_learn: str


class LearnerProfileUpdate(BaseModel):
    emphasis: dict[str, bool] | None = None
    how_i_learn: str | None = None


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
            profile_fn=functools.partial(read_learner_context, db_path),
            memory_fn=functools.partial(build_memory_context, db_path),
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


@router.get("/learn/explanations", response_model=list[ExplanationSummaryOut])
def list_explanations_endpoint(
    concept: str | None = Query(default=None),
) -> list[ExplanationSummaryOut]:
    """List stored explanations with success signals, newest first."""
    if concept is not None and not concept.strip():
        logger.warning("explanations list rejected: blank concept filter")
        raise HTTPException(status_code=422, detail="concept filter must not be blank")
    return [
        ExplanationSummaryOut(
            id=s.id,
            concept=s.concept,
            version=s.version,
            created_at=s.created_at,
            reused_from=s.reused_from,
            reuse_count=s.reuse_count,
            marked=s.marked,
            marker_count=s.marker_count,
            attempt_count=s.attempt_count,
        )
        for s in list_explanations(get_settings().database_path, concept_filter=concept)
    ]


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
    "/learn/explanations/{explanation_id}/markers",
    response_model=MarkerCreated,
    status_code=status.HTTP_201_CREATED,
)
def post_marker(explanation_id: str, body: MarkerCreate) -> MarkerCreated:
    """Record a "clicked" marker on an explanation or one of its steps."""
    db_path = get_settings().database_path
    if get_explanation(db_path, explanation_id) is None:
        logger.warning("marker rejected: unknown explanation %s", explanation_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="explanation not found")
    if body.scope == "step" and (body.step is None or body.step not in STEP_KEYS):
        logger.warning("marker rejected: invalid step %s", body.step)
        raise HTTPException(
            status_code=422,
            detail=f"invalid step {body.step!r}: must be one of {', '.join(STEP_KEYS)}",
        )
    if body.scope == "explanation" and body.step is not None:
        logger.warning("marker rejected: step set for explanation scope")
        raise HTTPException(status_code=422, detail="step must be null when scope is 'explanation'")
    marker = create_marker(db_path, explanation_id, body.scope, body.step, body.note)
    logger.info(
        "marker created: explanation=%s scope=%s step=%s id=%s",
        explanation_id,
        body.scope,
        body.step,
        marker.id,
    )
    return MarkerCreated(
        marker_id=marker.id,
        explanation_id=marker.explanation_id,
        scope=marker.scope,
        step=marker.step,
    )


@router.get("/learn/explanations/{explanation_id}/markers", response_model=list[MarkerOut])
def list_markers_endpoint(explanation_id: str) -> list[MarkerOut]:
    """List "clicked" markers for one explanation, chronological."""
    db_path = get_settings().database_path
    if get_explanation(db_path, explanation_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="explanation not found")
    return [
        MarkerOut(
            id=m.id,
            explanation_id=m.explanation_id,
            scope=m.scope,
            step=m.step,
            note=m.note,
            created_at=m.created_at,
        )
        for m in list_markers(db_path, explanation_id)
    ]


@router.get("/learn/profile", response_model=LearnerProfileOut)
def get_learner_profile_endpoint() -> LearnerProfileOut:
    """Fetch the learner-preferences profile (defaults when never saved)."""
    profile = get_learner_profile(get_settings().database_path)
    return LearnerProfileOut(emphasis=profile.emphasis, how_i_learn=profile.how_i_learn)


@router.put("/learn/profile", response_model=LearnerProfileOut)
def put_learner_profile(body: LearnerProfileUpdate) -> LearnerProfileOut:
    """Merge-update the learner-preferences profile.

    Both fields are optional; missing and explicit null are identical
    (both merge-skipped), so `{}` is a valid no-op returning the current
    profile. Unknown emphasis keys are rejected; value types are enforced
    by Pydantic (non-bool/non-string → 422).
    """
    if body.emphasis is not None:
        unknown = sorted(set(body.emphasis) - set(EMPHASIS_KEYS))
        if unknown:
            logger.warning("profile update rejected: unknown emphasis keys %s", unknown)
            raise HTTPException(
                status_code=422,
                detail=(
                    f"invalid emphasis key(s) {unknown}: must be one of {', '.join(EMPHASIS_KEYS)}"
                ),
            )
    profile = update_learner_profile(get_settings().database_path, body.emphasis, body.how_i_learn)
    logger.info(
        "profile updated via API: how_i_learn_chars=%d",
        len(profile.how_i_learn),
    )
    return LearnerProfileOut(emphasis=profile.emphasis, how_i_learn=profile.how_i_learn)


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
