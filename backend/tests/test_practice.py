"""Practice orchestration tests: branches, references, grounding, staleness.

Stubbed chat/search/career — no network, no embedding model.
Repository-backed fixtures use tmp DBs via init_db.
"""

import asyncio
import inspect
import json
import uuid
from pathlib import Path

import pytest

from app.db.artifacts import store_artifact
from app.db.chunks import get_chunks_by_artifacts
from app.db.connection import connect, init_db
from app.db.explanations import create_explanation, create_marker
from app.db.facts import FactCreate, create_facts
from app.ingest.chunker import chunk_text
from app.llm.extraction import CareerContext, no_career
from app.llm.practice import (
    MAX_PRACTICE_FACTS,
    NoEvidenceError,
    PracticeInputError,
    PracticeValidationError,
    StaleReferenceError,
    UnknownReferenceError,
    evaluate_answer,
    generate_question,
)
from app.retrieval.search import SearchHit

STEPS = {"definition": "RAG retrieves then generates."}
FEEDBACK = {
    "correct": ["c"],
    "missing": ["m"],
    "inaccurate": [],
    "terminology": ["t"],
    "next_step": "n",
}


def _chat_for(payloads: list[str], record: list):
    queue = list(payloads)

    async def fake(messages: list[dict[str, str]], max_tokens: int) -> str:
        record.append((messages, max_tokens))
        assert queue, "chat called more times than payloads"
        return queue.pop(0)

    return fake


async def _boom_chat(messages: list[dict[str, str]], max_tokens: int) -> str:
    raise AssertionError("chat must not be called")


def _search_for(hits: list[SearchHit]):
    def fake(query: str, top_k: int) -> list[SearchHit]:
        return hits

    return fake


def _hit(chunk_id: int, artifact_id: str = "a") -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        artifact_id=artifact_id,
        span_start=0,
        span_end=5,
        excerpt="ex",
        rrf_score=1.0,
        bm25_rank=1,
        vector_rank=None,
    )


@pytest.fixture()
def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "practice.db")
    init_db(path)
    return path


def _store(db: str, title: str, content: str) -> tuple[str, list[int]]:
    used = chunk_text(content)
    aid = store_artifact(
        db_path=db,
        source_type="note",
        title=title,
        content=content,
        content_hash="h",
        origin_json="{}",
        created_at="2026-11-03T00:00:00+00:00",
        chunks=used,
        embeddings=[[0.0] * 384 for _ in used],
    )
    grouped = get_chunks_by_artifacts(db, [aid])
    return aid, [c.id for c in grouped[aid]]


def _accomplishment(db: str, chunk_ids: list[int], summary: str) -> str:
    (fact_id,) = create_facts(
        db_path=db,
        items=[
            (
                uuid.uuid4().hex,
                FactCreate(
                    kind="accomplishment",
                    status="completed",
                    summary=summary,
                    skills=["python"],
                    confidence=0.9,
                    chunk_ids=chunk_ids,
                ),
                [],
            )
        ],
        model="m",
        prompt_version="p",
    )
    return fact_id


def test_learning_question_uses_lesson(db_path: str) -> None:
    exp = create_explanation(db_path, "RAG", 1, dict(STEPS), [], "", None)
    record: list = []
    result = asyncio.run(
        generate_question(
            mode="learning",
            question_kind=None,
            explanation_id=exp.id,
            focus=None,
            db_path=db_path,
            chat_fn=_chat_for([json.dumps({"question": "Explain RAG?"})], record),
            search_fn=_search_for([]),
        )
    )
    assert result.question == "Explain RAG?"
    assert result.question_kind is None
    assert result.reference_kind == "explanation"
    assert result.reference_json == {}
    assert result.explanation_id == exp.id
    user_text = record[0][0][1]["content"]
    assert "RAG retrieves then generates" in user_text


def test_learning_requires_explanation_id(db_path: str) -> None:
    with pytest.raises(PracticeInputError):
        asyncio.run(
            generate_question(
                mode="learning",
                question_kind=None,
                explanation_id=None,
                focus=None,
                db_path=db_path,
                chat_fn=_boom_chat,
                search_fn=_search_for([]),
            )
        )


def test_learning_rejects_question_kind(db_path: str) -> None:
    with pytest.raises(PracticeInputError):
        asyncio.run(
            generate_question(
                mode="learning",
                question_kind="technical",
                explanation_id="e",
                focus=None,
                db_path=db_path,
                chat_fn=_boom_chat,
                search_fn=_search_for([]),
            )
        )


def test_learning_unknown_explanation_404(db_path: str) -> None:
    with pytest.raises(UnknownReferenceError):
        asyncio.run(
            generate_question(
                mode="learning",
                question_kind=None,
                explanation_id="missing",
                focus=None,
                db_path=db_path,
                chat_fn=_boom_chat,
                search_fn=_search_for([]),
            )
        )


def test_interview_requires_kind(db_path: str) -> None:
    with pytest.raises(PracticeInputError):
        asyncio.run(
            generate_question(
                mode="interview",
                question_kind=None,
                explanation_id=None,
                focus=None,
                db_path=db_path,
                chat_fn=_boom_chat,
                search_fn=_search_for([]),
            )
        )


def test_invalid_mode_rejected(db_path: str) -> None:
    with pytest.raises(PracticeInputError):
        asyncio.run(
            generate_question(
                mode="coaching",
                question_kind=None,
                explanation_id=None,
                focus=None,
                db_path=db_path,
                chat_fn=_boom_chat,
                search_fn=_search_for([]),
            )
        )


def test_experience_question_includes_facts_and_excerpts(db_path: str) -> None:
    _, cids = _store(db_path, "log", "Shipped the batched loader fix for checkout.")
    fid = _accomplishment(db_path, cids, "Shipped batched loader")
    record: list = []
    result = asyncio.run(
        generate_question(
            mode="interview",
            question_kind="experience",
            explanation_id=None,
            focus=None,
            db_path=db_path,
            chat_fn=_chat_for([json.dumps({"question": "Tell me about a fix."})], record),
            search_fn=_search_for([]),
        )
    )
    assert result.reference_kind == "facts"
    assert result.reference_json == {"fact_ids": [fid]}
    user_text = record[0][0][1]["content"]
    assert "Shipped batched loader" in user_text
    assert "batched loader fix" in user_text  # supporting source excerpt


def test_experience_zero_facts_422(db_path: str) -> None:
    with pytest.raises(NoEvidenceError, match="extract work first"):
        asyncio.run(
            generate_question(
                mode="interview",
                question_kind="experience",
                explanation_id=None,
                focus=None,
                db_path=db_path,
                chat_fn=_boom_chat,
                search_fn=_search_for([]),
            )
        )


def test_experience_focus_miss_names_focus_and_count(db_path: str) -> None:
    _, cids = _store(db_path, "log", "Shipped the loader.")
    _accomplishment(db_path, cids, "Shipped loader")
    with pytest.raises(NoEvidenceError) as excinfo:
        asyncio.run(
            generate_question(
                mode="interview",
                question_kind="experience",
                explanation_id=None,
                focus="kubernetes",
                db_path=db_path,
                chat_fn=_boom_chat,
                search_fn=_search_for([]),
            )
        )
    assert "kubernetes" in str(excinfo.value)
    assert "1 stored" in str(excinfo.value)


def test_experience_focus_hit_filters(db_path: str) -> None:
    _, cids = _store(db_path, "log", "Shipped loader. Tuned postgres index.")
    loader = _accomplishment(db_path, cids, "Shipped loader")
    _accomplishment(db_path, cids, "Tuned postgres")
    record: list = []
    result = asyncio.run(
        generate_question(
            mode="interview",
            question_kind="experience",
            explanation_id=None,
            focus="loader",
            db_path=db_path,
            chat_fn=_chat_for([json.dumps({"question": "Q?"})], record),
            search_fn=_search_for([]),
        )
    )
    assert result.reference_json == {"fact_ids": [loader]}


def test_experience_fact_cap_newest_first(db_path: str) -> None:
    _, cids = _store(db_path, "log", "Work happened.")
    ids = [_accomplishment(db_path, cids, f"Accomplishment number {i:02d}") for i in range(12)]
    # Deterministic recency: force distinct ordered timestamps (newest last).
    conn = connect(db_path)
    try:
        with conn:
            for n, fid in enumerate(ids):
                conn.execute(
                    "UPDATE facts SET created_at = ? WHERE id = ?",
                    (f"2026-11-03T00:00:{n:02d}+00:00", fid),
                )
    finally:
        conn.close()
    record: list = []
    result = asyncio.run(
        generate_question(
            mode="interview",
            question_kind="experience",
            explanation_id=None,
            focus=None,
            db_path=db_path,
            chat_fn=_chat_for([json.dumps({"question": "Q?"})], record),
            search_fn=_search_for([]),
        )
    )
    assert result.reference_json == {"fact_ids": ids[-1 : -(MAX_PRACTICE_FACTS + 1) : -1]}
    assert len(result.reference_json["fact_ids"]) == MAX_PRACTICE_FACTS


def test_experience_oversize_reference_refused(db_path: str) -> None:
    _, cids = _store(db_path, "log", "Work.")
    _accomplishment(db_path, cids, "X" * 13000)
    with pytest.raises(NoEvidenceError, match="reference budget"):
        asyncio.run(
            generate_question(
                mode="interview",
                question_kind="experience",
                explanation_id=None,
                focus=None,
                db_path=db_path,
                chat_fn=_boom_chat,
                search_fn=_search_for([]),
            )
        )


def test_technical_question_weaves_passages(db_path: str) -> None:
    _, cids = _store(db_path, "log", "Studied vector indexes deeply.")
    record: list = []
    result = asyncio.run(
        generate_question(
            mode="interview",
            question_kind="technical",
            explanation_id=None,
            focus="indexes",
            db_path=db_path,
            chat_fn=_chat_for([json.dumps({"question": "How do indexes work?"})], record),
            search_fn=_search_for([_hit(cids[0])]),
        )
    )
    assert result.reference_kind == "general"
    assert result.reference_json == {"chunk_ids": [cids[0]]}
    assert "vector indexes" in record[0][0][1]["content"]


def test_technical_empty_hits_legal(db_path: str) -> None:
    record: list = []
    result = asyncio.run(
        generate_question(
            mode="interview",
            question_kind="technical",
            explanation_id=None,
            focus=None,
            db_path=db_path,
            chat_fn=_chat_for([json.dumps({"question": "Q?"})], record),
            search_fn=_search_for([]),
        )
    )
    assert result.reference_json == {"chunk_ids": []}


def test_technical_missing_chunk_dropped(db_path: str) -> None:
    record: list = []
    result = asyncio.run(
        generate_question(
            mode="interview",
            question_kind="technical",
            explanation_id=None,
            focus=None,
            db_path=db_path,
            chat_fn=_chat_for([json.dumps({"question": "Q?"})], record),
            search_fn=_search_for([_hit(424242)]),
        )
    )
    assert result.reference_json == {"chunk_ids": []}


def test_career_block_injected_when_present(db_path: str) -> None:
    exp = create_explanation(db_path, "RAG", 1, dict(STEPS), [], "", None)
    record: list = []

    def career():
        return CareerContext(
            current_role="Backend dev", past_roles=[], target_career="", target_position="Staff"
        )

    asyncio.run(
        generate_question(
            mode="learning",
            question_kind=None,
            explanation_id=exp.id,
            focus=None,
            db_path=db_path,
            chat_fn=_chat_for([json.dumps({"question": "Q?"})], record),
            search_fn=_search_for([]),
            career_fn=career,
        )
    )
    roles = [m["role"] for m in record[0][0]]
    assert roles == ["system", "system", "user"]
    assert "Backend dev" in record[0][0][1]["content"]


def test_career_block_absent_by_default(db_path: str) -> None:
    exp = create_explanation(db_path, "RAG", 1, dict(STEPS), [], "", None)
    record: list = []
    asyncio.run(
        generate_question(
            mode="learning",
            question_kind=None,
            explanation_id=exp.id,
            focus=None,
            db_path=db_path,
            chat_fn=_chat_for([json.dumps({"question": "Q?"})], record),
            search_fn=_search_for([]),
            career_fn=no_career,
        )
    )
    assert [m["role"] for m in record[0][0]] == ["system", "user"]


def test_malformed_question_json_502(db_path: str) -> None:
    exp = create_explanation(db_path, "RAG", 1, dict(STEPS), [], "", None)
    with pytest.raises(PracticeValidationError):
        asyncio.run(
            generate_question(
                mode="learning",
                question_kind=None,
                explanation_id=exp.id,
                focus=None,
                db_path=db_path,
                chat_fn=_chat_for(["junk{{{"], []),
                search_fn=_search_for([]),
            )
        )


def test_blank_question_502(db_path: str) -> None:
    exp = create_explanation(db_path, "RAG", 1, dict(STEPS), [], "", None)
    with pytest.raises(PracticeValidationError, match="blank"):
        asyncio.run(
            generate_question(
                mode="learning",
                question_kind=None,
                explanation_id=exp.id,
                focus=None,
                db_path=db_path,
                chat_fn=_chat_for([json.dumps({"question": "   "})], []),
                search_fn=_search_for([]),
            )
        )


def test_evaluate_takes_no_search_fn_by_design() -> None:
    # Structural lock: the evaluator CANNOT re-derive references — it only
    # rehydrates the stored reference passed in. If this fails, the
    # evaluator-constraint design has regressed.
    assert "search_fn" not in inspect.signature(evaluate_answer).parameters


def test_evaluate_learning_against_lesson(db_path: str) -> None:
    exp = create_explanation(db_path, "RAG", 1, dict(STEPS), [], "", None)
    record: list = []
    result = asyncio.run(
        evaluate_answer(
            mode="learning",
            question_kind=None,
            explanation_id=exp.id,
            reference_json={},
            answer="RAG fetches passages first.",
            db_path=db_path,
            chat_fn=_chat_for([json.dumps({"feedback": FEEDBACK})], record),
        )
    )
    assert result.feedback == FEEDBACK
    assert result.grounding == "general explanation"
    user_text = record[0][0][1]["content"]
    assert "RAG retrieves then generates" in user_text
    assert "RAG fetches passages first" in user_text


def test_evaluate_learning_reused_lesson_is_both(db_path: str) -> None:
    v1 = create_explanation(db_path, "RAG", 1, dict(STEPS), [], "", None)
    v2 = create_explanation(db_path, "RAG", 2, dict(STEPS), [], "", v1.id)
    result = asyncio.run(
        evaluate_answer(
            mode="learning",
            question_kind=None,
            explanation_id=v2.id,
            reference_json={},
            answer="a",
            db_path=db_path,
            chat_fn=_chat_for([json.dumps({"feedback": FEEDBACK})], []),
        )
    )
    assert result.grounding == "both"


def test_evaluate_learning_memory_shaped_is_both(db_path: str) -> None:
    v1 = create_explanation(db_path, "RAG", 1, dict(STEPS), [], "", None)
    v2 = create_explanation(db_path, "RAG", 2, dict(STEPS), [], "", None)
    create_marker(db_path, v2.id, "explanation", None, "")  # v2 wins memory deterministically
    result = asyncio.run(
        evaluate_answer(
            mode="learning",
            question_kind=None,
            explanation_id=v1.id,
            reference_json={},
            answer="a",
            db_path=db_path,
            chat_fn=_chat_for([json.dumps({"feedback": FEEDBACK})], []),
        )
    )
    assert result.grounding == "both"


def test_evaluate_learning_missing_explanation_404(db_path: str) -> None:
    with pytest.raises(UnknownReferenceError):
        asyncio.run(
            evaluate_answer(
                mode="learning",
                question_kind=None,
                explanation_id="missing",
                reference_json={},
                answer="a",
                db_path=db_path,
                chat_fn=_boom_chat,
            )
        )


def test_evaluate_experience_from_notes_with_excerpt(db_path: str) -> None:
    _, cids = _store(db_path, "log", "Shipped the batched loader fix for checkout.")
    fid = _accomplishment(db_path, cids, "Shipped batched loader")
    record: list = []
    result = asyncio.run(
        evaluate_answer(
            mode="interview",
            question_kind="experience",
            explanation_id=None,
            reference_json={"fact_ids": [fid]},
            answer="I fixed checkout loading.",
            db_path=db_path,
            chat_fn=_chat_for([json.dumps({"feedback": FEEDBACK})], record),
        )
    )
    assert result.grounding == "from your notes"
    user_text = record[0][0][1]["content"]
    assert "Shipped batched loader" in user_text
    assert "batched loader fix" in user_text


def test_evaluate_experience_stale_fact_409(db_path: str) -> None:
    with pytest.raises(StaleReferenceError):
        asyncio.run(
            evaluate_answer(
                mode="interview",
                question_kind="experience",
                explanation_id=None,
                reference_json={"fact_ids": ["gone"]},
                answer="a",
                db_path=db_path,
                chat_fn=_boom_chat,
            )
        )


def test_evaluate_experience_missing_chunk_keeps_summary(db_path: str) -> None:
    _, cids = _store(db_path, "log", "Shipped the loader.")
    fid = _accomplishment(db_path, cids, "Shipped loader")
    conn = connect(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM chunks WHERE id = ?", (cids[0],))
    finally:
        conn.close()
    record: list = []
    result = asyncio.run(
        evaluate_answer(
            mode="interview",
            question_kind="experience",
            explanation_id=None,
            reference_json={"fact_ids": [fid]},
            answer="a",
            db_path=db_path,
            chat_fn=_chat_for([json.dumps({"feedback": FEEDBACK})], record),
        )
    )
    assert result.grounding == "from your notes"
    assert "Shipped loader" in record[0][0][1]["content"]


def test_evaluate_technical_with_passages_is_both(db_path: str) -> None:
    _, cids = _store(db_path, "log", "Studied vector indexes.")
    result = asyncio.run(
        evaluate_answer(
            mode="interview",
            question_kind="technical",
            explanation_id=None,
            reference_json={"chunk_ids": [cids[0]]},
            answer="a",
            db_path=db_path,
            chat_fn=_chat_for([json.dumps({"feedback": FEEDBACK})], []),
        )
    )
    assert result.grounding == "both"


def test_evaluate_technical_no_passages_is_general(db_path: str) -> None:
    result = asyncio.run(
        evaluate_answer(
            mode="interview",
            question_kind="technical",
            explanation_id=None,
            reference_json={"chunk_ids": []},
            answer="a",
            db_path=db_path,
            chat_fn=_chat_for([json.dumps({"feedback": FEEDBACK})], []),
        )
    )
    assert result.grounding == "general explanation"


def test_evaluate_technical_deleted_chunks_degrade(db_path: str) -> None:
    record: list = []
    result = asyncio.run(
        evaluate_answer(
            mode="interview",
            question_kind="technical",
            explanation_id=None,
            reference_json={"chunk_ids": [999001]},
            answer="a",
            db_path=db_path,
            chat_fn=_chat_for([json.dumps({"feedback": FEEDBACK})], record),
        )
    )
    assert result.grounding == "general explanation"
    assert "Passage" not in record[0][0][1]["content"]


def test_evaluate_invalid_branch_rejected(db_path: str) -> None:
    with pytest.raises(PracticeInputError):
        asyncio.run(
            evaluate_answer(
                mode="interview",
                question_kind=None,
                explanation_id=None,
                reference_json={},
                answer="a",
                db_path=db_path,
                chat_fn=_boom_chat,
            )
        )


def test_malformed_feedback_json_502(db_path: str) -> None:
    exp = create_explanation(db_path, "RAG", 1, dict(STEPS), [], "", None)
    with pytest.raises(PracticeValidationError):
        asyncio.run(
            evaluate_answer(
                mode="learning",
                question_kind=None,
                explanation_id=exp.id,
                reference_json={},
                answer="a",
                db_path=db_path,
                chat_fn=_chat_for(["junk{{{"], []),
            )
        )
