"""Work endpoints — thin router over llm/extraction (PRD §10).

`POST /work/extract` runs structured extraction over artifacts into grounded
facts with reasoning links. `GET`/`PUT /profile` manage the single-row career
profile. `GET /work/accomplishments` lists persisted accomplishment facts
with query-time-only filters.

Test seams: ``run_extraction``, ``chat_completion``,
``read_career_context``, ``get_career_profile``, ``update_career_profile``,
and ``list_accomplishments`` are imported BY NAME so tests can
``monkeypatch.setattr("app.api.work.<name>", stub)`` (mirrors the
learn/query/ingest router seams). ``no_career`` remains the unit-test
default inside ``app.llm.extraction``; the router wires the real read.
"""

from __future__ import annotations

import functools
import logging

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.meta_client import DEFAULT_META_MODEL, MetaAPIError, chat_completion
from app.db.career_profile import get_career_profile, update_career_profile
from app.db.facts import list_accomplishments
from app.llm.extraction import (
    MAX_EXTRACTION_ARTIFACTS,
    EmptyExtractionError,
    ExtractionTooLargeError,
    ExtractionValidationError,
    UnknownArtifactError,
    read_career_context,
    run_extraction,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["work"])


class ExtractRequest(BaseModel):
    artifact_ids: list[str]


class FactLinkOut(BaseModel):
    to_fact: str
    relation: str


class FactOut(BaseModel):
    fact_id: str
    kind: str
    status: str
    summary: str
    skills: list[str]
    confidence: float
    chunk_ids: list[int]
    links: list[FactLinkOut]


class ExtractResponse(BaseModel):
    facts: list[FactOut]


class CareerProfileOut(BaseModel):
    current_role: str
    past_roles: list[str]
    target_career: str
    target_position: str


class CareerProfileUpdate(BaseModel):
    """Merge-update body: missing ≡ null ≡ merge-skip, so `{}` is a no-op."""

    current_role: str | None = None
    past_roles: list[str] | None = None
    target_career: str | None = None
    target_position: str | None = None


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


@router.post("/work/extract", response_model=ExtractResponse)
async def post_extract(body: ExtractRequest) -> ExtractResponse:
    """Extract grounded facts with reasoning links over artifacts."""
    artifact_ids = [aid for aid in body.artifact_ids if aid.strip()]
    if not artifact_ids:
        logger.warning("extract rejected: empty artifact_ids")
        raise HTTPException(status_code=422, detail="artifact_ids must not be empty")
    if len(artifact_ids) > MAX_EXTRACTION_ARTIFACTS:
        logger.warning("extract rejected: %d ids over cap", len(artifact_ids))
        raise HTTPException(
            status_code=422,
            detail=f"artifact_ids exceeds MAX_EXTRACTION_ARTIFACTS={MAX_EXTRACTION_ARTIFACTS}",
        )
    settings = get_settings()
    db_path = settings.database_path
    model_wanted = settings.meta_model or DEFAULT_META_MODEL
    try:
        result = await run_extraction(
            artifact_ids=artifact_ids,
            db_path=db_path,
            chat_fn=_make_chat_fn(settings, model_wanted),
            career_fn=functools.partial(read_career_context, db_path),
            model=model_wanted,
        )
    except ExtractionValidationError as exc:
        # BEFORE the generic ValueError branch: ExtractionValidationError subclasses it.
        logger.warning("extract failed: validation: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ExtractionTooLargeError as exc:
        logger.warning("extract rejected: %s", exc)
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)) from exc
    except UnknownArtifactError as exc:
        logger.warning("extract rejected: %s", exc)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EmptyExtractionError as exc:
        logger.warning("extract rejected: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MetaAPIError as exc:
        logger.warning("extract failed: meta: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    logger.info("extract served: artifacts=%d facts=%d", len(artifact_ids), len(result.facts))
    return ExtractResponse(
        facts=[
            FactOut(
                fact_id=f.fact_id,
                kind=f.kind,
                status=f.status,
                summary=f.summary,
                skills=f.skills,
                confidence=f.confidence,
                chunk_ids=f.chunk_ids,
                links=[
                    FactLinkOut(to_fact=link.to_fact, relation=link.relation) for link in f.links
                ],
            )
            for f in result.facts
        ]
    )


@router.get("/profile", response_model=CareerProfileOut)
def get_profile_endpoint() -> CareerProfileOut:
    """Fetch the career profile (empty defaults when never saved)."""
    profile = get_career_profile(get_settings().database_path)
    return CareerProfileOut(
        current_role=profile.current_role,
        past_roles=profile.past_roles,
        target_career=profile.target_career,
        target_position=profile.target_position,
    )


@router.put("/profile", response_model=CareerProfileOut)
def put_profile(body: CareerProfileUpdate) -> CareerProfileOut:
    """Merge-update the career profile.

    Every field is optional; missing and explicit null are identical
    (both merge-skipped), so ``{}`` is a valid no-op returning the current
    profile. Value types are enforced by Pydantic (non-string → 422).
    Stripping + blank-role dropping live in the repository.
    """
    profile = update_career_profile(
        get_settings().database_path,
        body.current_role,
        body.past_roles,
        body.target_career,
        body.target_position,
    )
    logger.info(
        "profile updated via API: current_role_chars=%d past_roles=%d",
        len(profile.current_role),
        len(profile.past_roles),
    )
    return CareerProfileOut(
        current_role=profile.current_role,
        past_roles=profile.past_roles,
        target_career=profile.target_career,
        target_position=profile.target_position,
    )


@router.get("/work/accomplishments", response_model=list[FactOut])
def list_accomplishments_endpoint(
    q: str | None = Query(default=None),
    skill: str | None = Query(default=None),
) -> list[FactOut]:
    """List persisted accomplishment facts, newest first (query-time filters).

    ``q`` matches whitespace-separated keyword terms (AND, case-insensitive
    substring over summary + skills); ``skill`` matches one skill tag
    exactly (case-insensitive). Both are read-only: retention is
    independent of relevance.
    """
    if q is not None and not q.strip():
        logger.warning("accomplishments list rejected: blank q filter")
        raise HTTPException(status_code=422, detail="q filter must not be blank")
    if skill is not None and not skill.strip():
        logger.warning("accomplishments list rejected: blank skill filter")
        raise HTTPException(status_code=422, detail="skill filter must not be blank")
    return [
        FactOut(
            fact_id=f.fact_id,
            kind=f.kind,
            status=f.status,
            summary=f.summary,
            skills=f.skills,
            confidence=f.confidence,
            chunk_ids=f.chunk_ids,
            links=[FactLinkOut(to_fact=link.to_fact, relation=link.relation) for link in f.links],
        )
        for f in list_accomplishments(get_settings().database_path, q=q, skill=skill)
    ]
