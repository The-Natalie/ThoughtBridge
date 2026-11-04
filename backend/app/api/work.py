"""Work endpoints — thin router over llm/extraction (PRD §10).

`POST /work/extract` runs structured extraction over artifacts into grounded
facts with reasoning links.

Test seams: ``run_extraction``, ``chat_completion``, and ``no_career`` are
imported BY NAME so tests can ``monkeypatch.setattr("app.api.work.<name>",
stub)`` (mirrors the learn/query/ingest router seams).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.meta_client import DEFAULT_META_MODEL, MetaAPIError, chat_completion
from app.llm.extraction import (
    MAX_EXTRACTION_ARTIFACTS,
    EmptyExtractionError,
    ExtractionTooLargeError,
    ExtractionValidationError,
    UnknownArtifactError,
    no_career,
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
            # D5 handoff: deliverable 5 replaces no_career with the
            # read_career_context(db_path) filler.
            career_fn=no_career,
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
