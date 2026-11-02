"""Grounded Q&A endpoints — thin router over retrieval + llm/qa + conversations.

`POST /query` answers one question (PRD §10); `GET /conversations` and
`GET /conversations/{id}` read the persisted turn log. `context` is
accepted but ignored in Phase 1 (forward-compat for Phase 2
interrupt/resume); deletion stays Phase 3 work.

Test seams: ``hybrid_search`` and ``chat_completion`` are imported BY NAME
so tests can ``monkeypatch.setattr("app.api.query.hybrid_search", stub)``
and ``...chat_completion`` (mirrors the ingest/retrieval router seams).
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.grounding import HistoryTurn, ModeUsed, QueryMode, select_history
from app.core.meta_client import DEFAULT_META_MODEL, MetaAPIError, chat_completion
from app.db.connection import EmbeddingDimMismatchError
from app.db.conversations import (
    append_turns,
    create_conversation_with_turns,
    get_conversation,
    list_conversations,
)
from app.llm.qa import QaValidationError, answer_question
from app.retrieval.search import TOP_K_DEFAULT, TOP_K_MAX, hybrid_search

logger = logging.getLogger(__name__)

router = APIRouter(tags=["query"])


class QueryContext(BaseModel):
    explanation_id: str | None = None


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    mode: QueryMode = "auto"
    top_k: int = Field(default=TOP_K_DEFAULT, ge=1, le=TOP_K_MAX)
    context: QueryContext | None = None
    conversation_id: str | None = None


class CitationOut(BaseModel):
    chunk_id: int
    artifact_id: str
    span: list[int]
    excerpt: str


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    mode_used: ModeUsed
    conversation_id: str


class TurnOut(BaseModel):
    id: str
    idx: int
    role: str
    content: str
    mode: str | None
    citations: list
    created_at: str


class ConversationOut(BaseModel):
    id: str
    kind: str
    created_at: str
    turns: list[TurnOut]


class ConversationSummaryOut(BaseModel):
    id: str
    kind: str
    created_at: str
    turn_count: int


@router.post("/query", response_model=QueryResponse)
async def post_query(body: QueryRequest) -> QueryResponse:
    """Answer one grounded question, persisting both turns."""
    if not body.question.strip():
        logger.warning("query rejected: blank question")
        raise HTTPException(status_code=422, detail="question must not be blank")
    settings = get_settings()
    db_path = settings.database_path
    embedding_model = settings.embedding_model
    model_wanted = settings.meta_model or DEFAULT_META_MODEL

    existing = None
    if body.conversation_id is not None:
        existing = get_conversation(db_path, body.conversation_id)
        if existing is None:
            logger.warning("query rejected: unknown conversation %s", body.conversation_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found"
            )
    prior: list[HistoryTurn] = []
    if existing is not None:
        for turn in existing.turns:
            if turn.role == "user":
                prior.append(HistoryTurn(role="user", content=turn.content))
            elif turn.role == "assistant":
                prior.append(HistoryTurn(role="assistant", content=turn.content))
    history = select_history(prior)

    def search_fn(query: str, top_k: int):  # stub seam: hybrid_search by name
        return hybrid_search(
            db_path=db_path,
            query=query,
            top_k=top_k,
            embedding_model=embedding_model,
            embed_fn=None,
        )

    async def chat_fn(messages: list[dict[str, str]]) -> str:  # stub seam: by name
        key = settings.model_api_key.get_secret_value()
        if not key:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="MODEL_API_KEY not configured",
            )
        return await chat_completion(api_key=key, model=model_wanted, messages=messages)

    try:
        result = await answer_question(
            question=body.question,
            mode=body.mode,
            top_k=body.top_k,
            db_path=db_path,
            search_fn=search_fn,
            chat_fn=chat_fn,
            history=tuple(history),
        )
    except QaValidationError as exc:
        # BEFORE the generic ValueError branch: QaValidationError subclasses it.
        logger.warning("query failed: teaching validation: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except MetaAPIError as exc:
        logger.warning("query failed: meta: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except (EmbeddingDimMismatchError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    citations = [
        CitationOut(
            chunk_id=c.chunk_id,
            artifact_id=c.artifact_id,
            span=[c.span_start, c.span_end],
            excerpt=c.excerpt,
        )
        for c in result.citations
    ]
    turns: list[tuple[str, str, str | None, str]] = [
        ("user", body.question, result.mode_used, "[]"),
        (
            "assistant",
            result.answer,
            result.mode_used,
            json.dumps([c.model_dump() for c in citations]),
        ),
    ]
    if existing is None:
        conversation_id, _ = create_conversation_with_turns(db_path, "qa", turns)
    else:
        append_turns(db_path, existing.id, turns)
        conversation_id = existing.id
    logger.info(
        "query answered: mode=%s citations=%d conversation=%s",
        result.mode_used,
        len(citations),
        conversation_id,
    )
    return QueryResponse(
        answer=result.answer,
        citations=citations,
        mode_used=result.mode_used,
        conversation_id=conversation_id,
    )


@router.get("/conversations", response_model=list[ConversationSummaryOut])
def list_conversations_endpoint() -> list[ConversationSummaryOut]:
    """List auto-saved conversations with turn counts."""
    return [
        ConversationSummaryOut(
            id=c.id, kind=c.kind, created_at=c.created_at, turn_count=c.turn_count
        )
        for c in list_conversations(get_settings().database_path)
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def get_conversation_endpoint(conversation_id: str) -> ConversationOut:
    """One conversation with its ordered, role-labeled turns."""
    detail = get_conversation(get_settings().database_path, conversation_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    return ConversationOut(
        id=detail.id,
        kind=detail.kind,
        created_at=detail.created_at,
        turns=[
            TurnOut(
                id=t.id,
                idx=t.idx,
                role=t.role,
                content=t.content,
                mode=t.mode,
                citations=json.loads(t.citations_json),
                created_at=t.created_at,
            )
            for t in detail.turns
        ],
    )
