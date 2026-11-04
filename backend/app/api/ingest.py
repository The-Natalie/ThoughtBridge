"""Ingest endpoints — thin router over adapters + pipeline (PRD §10).

Upload handling order: byte-cap FIRST, then suffix, then UTF-8 decode,
then blank check. Blank content is 422 on the JSON path (schema problem)
and 400 on the upload path (file problem).

Test seam: ``ingest_source`` is imported BY NAME so tests can
``monkeypatch.setattr("app.api.ingest.ingest_source", stub)`` (mirrors the
health-router probe seam). The stub wraps the real pipeline with a fake
``embed_fn``; the default suite never downloads the fastembed model.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.db.artifacts import get_artifact_detail, list_artifacts
from app.db.connection import EmbeddingDimMismatchError
from app.ingest.adapters import (
    UndecodableUploadError,
    UnparseableUploadError,
    UnsupportedSuffixError,
    adapt_text,
    adapt_upload,
)
from app.ingest.pipeline import ArtifactTooLargeError, ingest_source

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest"])


class ArtifactCreate(BaseModel):
    source_type: Literal["note", "paste", "summary"]
    title: str = ""
    content: str = Field(min_length=1)


class ArtifactCreated(BaseModel):
    artifact_id: str
    chunks: int


class UploadCreated(BaseModel):
    artifact_id: str
    chunks: int
    extracted_chars: int
    pages: int | None = None


class ArtifactListItem(BaseModel):
    id: str
    title: str
    source_type: str
    created_at: str
    chunk_count: int
    fact_count: int


class ArtifactChunkOut(BaseModel):
    id: int
    chunk_idx: int
    span: list[int]
    text: str


class ArtifactDetailOut(BaseModel):
    id: str
    title: str
    source_type: str
    content: str
    content_hash: str
    origin: dict[str, str]
    created_at: str
    chunks: list[ArtifactChunkOut]
    fact_ids: list[str]
    interpretation_ids: list[str]


@router.post("/artifacts", response_model=ArtifactCreated, status_code=status.HTTP_201_CREATED)
def create_artifact(body: ArtifactCreate) -> ArtifactCreated:
    """Ingest typed/pasted text as a new artifact."""
    if not body.content.strip():
        logger.warning("ingest rejected: blank JSON content")
        raise HTTPException(status_code=422, detail="content must not be blank")
    settings = get_settings()
    adapted = adapt_text(body.source_type, body.title, body.content)
    try:
        result = ingest_source(
            db_path=settings.database_path,
            source_type=adapted.source_type,
            title=adapted.title,
            content=adapted.content,
            origin=adapted.origin,
            max_artifact_chars=settings.max_artifact_chars,
            embedding_model=settings.embedding_model,
            embed_fn=None,
        )
    except ArtifactTooLargeError as exc:
        logger.warning("ingest rejected: %s", exc)
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)) from exc
    except EmbeddingDimMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    return ArtifactCreated(artifact_id=result.artifact_id, chunks=result.chunk_count)


@router.post("/artifacts/upload", response_model=UploadCreated, status_code=status.HTTP_201_CREATED)
def upload_artifact(file: UploadFile = File(...)) -> UploadCreated:  # noqa: B008
    """Ingest a `.txt`/`.md`/`.pdf`/`.docx` file upload as a new artifact."""
    settings = get_settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    raw = file.file.read(max_bytes + 1)
    if len(raw) > max_bytes:
        logger.warning("upload rejected: %d bytes over %dMB cap", len(raw), settings.max_upload_mb)
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"upload exceeds MAX_UPLOAD_MB={settings.max_upload_mb}",
        )
    try:
        adapted = adapt_upload(file.filename or "", file.content_type, raw)
    except (UnsupportedSuffixError, UndecodableUploadError, UnparseableUploadError) as exc:
        logger.warning("upload rejected: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not adapted.content.strip():
        logger.warning("upload rejected: blank file content")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file content blank")
    try:
        result = ingest_source(
            db_path=settings.database_path,
            source_type=adapted.source_type,
            title=adapted.title,
            content=adapted.content,
            origin=adapted.origin,
            max_artifact_chars=settings.max_artifact_chars,
            embedding_model=settings.embedding_model,
            embed_fn=None,
        )
    except ArtifactTooLargeError as exc:
        logger.warning("upload rejected: %s", exc)
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)) from exc
    except EmbeddingDimMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    return UploadCreated(
        artifact_id=result.artifact_id,
        chunks=result.chunk_count,
        extracted_chars=len(adapted.content),
        pages=int(adapted.origin["pages"]) if "pages" in adapted.origin else None,
    )


@router.get("/artifacts", response_model=list[ArtifactListItem])
def list_artifacts_endpoint() -> list[ArtifactListItem]:
    """List artifacts with provenance metadata and derived counts."""
    return [
        ArtifactListItem(
            id=a.id,
            title=a.title,
            source_type=a.source_type,
            created_at=a.created_at,
            chunk_count=a.chunk_count,
            fact_count=a.fact_count,
        )
        for a in list_artifacts(get_settings().database_path)
    ]


@router.get("/artifacts/{artifact_id}", response_model=ArtifactDetailOut)
def get_artifact_endpoint(artifact_id: str) -> ArtifactDetailOut:
    """Full original content plus derived summary (chunks, linked ids)."""
    detail = get_artifact_detail(get_settings().database_path, artifact_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found")
    return ArtifactDetailOut(
        id=detail.id,
        title=detail.title,
        source_type=detail.source_type,
        content=detail.content,
        content_hash=detail.content_hash,
        origin=json.loads(detail.origin),
        created_at=detail.created_at,
        chunks=[
            ArtifactChunkOut(
                id=c.id, chunk_idx=c.chunk_idx, span=[c.span_start, c.span_end], text=c.text
            )
            for c in detail.chunks
        ],
        fact_ids=detail.fact_ids,
        interpretation_ids=detail.interpretation_ids,
    )
