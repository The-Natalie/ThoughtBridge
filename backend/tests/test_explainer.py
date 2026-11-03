"""Explainer orchestration tests: chaining, validation, versioning, seams.

Stubbed chat/profile/memory/persist — no network, no embedding model.
Repository-backed subset uses tmp DBs via init_db.
"""

import asyncio
import json
from pathlib import Path

import pytest

from app.core.grounding import STEP_KEYS
from app.db.connection import connect, init_db
from app.db.explanations import ExplanationDetail, create_explanation, get_explanation
from app.llm.explainer import (
    ExplainerValidationError,
    LearnerContext,
    MemoryContext,
    default_learner_context,
    generate_explanation,
    no_memory,
    regenerate_step,
)

STAGE_A = {"definition": "RAG defined.", "familiar_system": "A library with a librarian."}
STAGE_B = {
    "analogy": "Full analogy text.",
    "mapping": [
        "The librarian finds passages just as the retriever finds chunks.",
        "Shelves organize books just as the vector index organizes embeddings.",
    ],
    "walkthrough": "Walkthrough text.",
}
STAGE_C = {
    "placement": "Placement text.",
    "interview_ready": "Interview-ready text.",
    "limitations": "Limitations text.",
}


def _chat_for(payloads: list[str], record: list):
    queue = list(payloads)

    async def fake(messages: list[dict[str, str]], max_tokens: int) -> str:
        record.append((messages, max_tokens))
        assert queue, "chat called more times than payloads"
        return queue.pop(0)

    return fake


def _source() -> ExplanationDetail:
    steps = {
        "definition": "d",
        "familiar_system": "f",
        "analogy": "a",
        "mapping": ["X maps to Y because Z."],
        "walkthrough": "w",
        "placement": "p",
        "interview_ready": "i",
        "limitations": "l",
    }
    return ExplanationDetail(
        id="src-1",
        concept="RAG",
        version=1,
        steps=steps,
        mapping=steps["mapping"],
        limitations="l",
        reused_from=None,
        created_at="t",
    )


def test_generate_happy_path_chains_three_calls() -> None:
    record: list = []
    result = asyncio.run(
        generate_explanation(
            concept="RAG",
            hint="library",
            db_path=":memory:",
            chat_fn=_chat_for(
                [json.dumps(STAGE_A), json.dumps(STAGE_B), json.dumps(STAGE_C)], record
            ),
            profile_fn=default_learner_context,
            memory_fn=no_memory,
            persist_fn=lambda steps, reused: ("exp-1", 1),
        )
    )
    assert len(record) == 3
    assert [budget for _, budget in record] == [8192, 16384, 8192]
    assert sorted(result.steps.keys()) == sorted(STEP_KEYS)
    assert result.explanation_id == "exp-1"
    assert result.reused_from is None
    assert result.steps["definition"] == "RAG defined."
    assert result.steps["mapping"][0].startswith("The librarian")
    stage_b_user = record[1][0][-1]["content"]
    assert "RAG defined." in stage_b_user
    stage_c_user = record[2][0][-1]["content"]
    assert "Full analogy text." in stage_c_user
    assert "library" in record[0][0][-1]["content"]


def test_stage_b_malformed_raises_and_skips_persist() -> None:
    def boom(steps: dict, reused: str | None) -> tuple[str, int]:
        raise AssertionError("persist must not be called")

    with pytest.raises(ExplainerValidationError, match="stage B"):
        asyncio.run(
            generate_explanation(
                concept="RAG",
                hint=None,
                db_path=":memory:",
                chat_fn=_chat_for([json.dumps(STAGE_A), "not json", json.dumps(STAGE_C)], []),
                profile_fn=default_learner_context,
                memory_fn=no_memory,
                persist_fn=boom,
            )
        )


def test_memory_context_flows_into_result_and_prompt() -> None:
    memory = MemoryContext(
        reused_from="exp-0",
        prior_steps={"definition": "old"},
        framing_note="THIS-WORKED-BEFORE",
    )
    record: list = []
    result = asyncio.run(
        generate_explanation(
            concept="RAG",
            hint=None,
            db_path=":memory:",
            chat_fn=_chat_for(
                [json.dumps(STAGE_A), json.dumps(STAGE_B), json.dumps(STAGE_C)], record
            ),
            profile_fn=default_learner_context,
            memory_fn=lambda concept: memory,
            persist_fn=lambda steps, reused: ("exp-1", 1),
        )
    )
    assert result.reused_from == "exp-0"
    assert "THIS-WORKED-BEFORE" in record[0][0][-1]["content"]


def test_profile_how_i_learn_reaches_stage_a() -> None:
    profile = LearnerContext(emphasis={"familiar_systems": False}, how_i_learn="LEARN-BY-DOING")
    record: list = []
    asyncio.run(
        generate_explanation(
            concept="RAG",
            hint=None,
            db_path=":memory:",
            chat_fn=_chat_for(
                [json.dumps(STAGE_A), json.dumps(STAGE_B), json.dumps(STAGE_C)], record
            ),
            profile_fn=lambda: profile,
            memory_fn=no_memory,
            persist_fn=lambda steps, reused: ("exp-1", 1),
        )
    )
    content = record[0][0][-1]["content"]
    assert "LEARN-BY-DOING" in content
    assert "familiar-system grounding: de-emphasized" in content


def test_regenerate_happy_path_copies_verbatim() -> None:
    record: list = []
    captured: dict = {}

    def persist(steps: dict, reused: str | None) -> tuple[str, int]:
        captured["steps"] = steps
        captured["reused"] = reused
        return ("exp-2", 2)

    result = asyncio.run(
        regenerate_step(
            source=_source(),
            step="analogy",
            db_path=":memory:",
            chat_fn=_chat_for([json.dumps({"step": "analogy", "content": "NEW-ANALOGY"})], record),
            persist_fn=persist,
        )
    )
    assert len(record) == 1
    assert result.explanation_id == "exp-2"
    assert result.reused_from is None
    assert captured["reused"] is None
    assert result.steps["analogy"] == "NEW-ANALOGY"
    for key in [k for k in STEP_KEYS if k != "analogy"]:
        assert result.steps[key] == _source().steps[key]


def test_regenerate_invalid_step_raises_without_call() -> None:
    async def boom(messages: list[dict[str, str]], max_tokens: int) -> str:
        raise AssertionError("chat must not be called")

    def boom_persist(steps: dict, reused: str | None) -> tuple[str, int]:
        raise AssertionError("persist must not be called")

    with pytest.raises(ValueError) as excinfo:
        asyncio.run(
            regenerate_step(
                source=_source(),
                step="bogus",
                db_path=":memory:",
                chat_fn=boom,
                persist_fn=boom_persist,
            )
        )
    assert "bogus" in str(excinfo.value)
    for key in STEP_KEYS:
        assert key in str(excinfo.value)


def test_regenerate_mapping_validates_array_and_rejects_mismatch() -> None:
    def run(step: str, content: object):
        return regenerate_step(
            source=_source(),
            step=step,
            db_path=":memory:",
            chat_fn=_chat_for([json.dumps({"step": step, "content": content})], []),
            persist_fn=lambda steps, reused: ("x", 1),
        )

    result = asyncio.run(run("mapping", ["A maps to B because C."]))
    assert result.steps["mapping"] == ["A maps to B because C."]

    with pytest.raises(ExplainerValidationError):
        asyncio.run(run("analogy", ["not a string"]))

    with pytest.raises(ExplainerValidationError):
        asyncio.run(run("mapping", "nope"))

    with pytest.raises(ExplainerValidationError):
        asyncio.run(run("mapping", [{"familiar": "a", "technical": "b", "note": "c"}]))


def test_real_repository_versions_and_atomic_failure(tmp_path: Path) -> None:
    db = str(tmp_path / "explainer.db")
    init_db(db)

    async def run(payloads: list[str]):
        return await generate_explanation(
            concept="RAG",
            hint=None,
            db_path=db,
            chat_fn=_chat_for(payloads, []),
            profile_fn=default_learner_context,
            memory_fn=no_memory,
        )

    good = [json.dumps(STAGE_A), json.dumps(STAGE_B), json.dumps(STAGE_C)]
    r1 = asyncio.run(run(list(good)))
    r2 = asyncio.run(run(list(good)))
    assert r1.explanation_id != r2.explanation_id
    assert get_explanation(db, r1.explanation_id).version == 1  # type: ignore[union-attr]
    assert get_explanation(db, r2.explanation_id).version == 2  # type: ignore[union-attr]

    with pytest.raises(ExplainerValidationError):
        asyncio.run(run([json.dumps(STAGE_A), "junk", json.dumps(STAGE_C)]))

    conn = connect(db)
    try:
        n = conn.execute("SELECT COUNT(*) AS n FROM explanations").fetchone()["n"]
    finally:
        conn.close()
    assert n == 2


def test_regen_column_sync_mapping_and_limitations(tmp_path: Path) -> None:
    db = str(tmp_path / "explainer_sync.db")
    init_db(db)
    steps = {
        "definition": "d",
        "familiar_system": "f",
        "analogy": "a",
        "mapping": ["X maps to Y because Z."],
        "walkthrough": "w",
        "placement": "p",
        "interview_ready": "i",
        "limitations": "old-limits",
    }
    src = create_explanation(db, "RAG", 1, steps, steps["mapping"], "old-limits", None)

    r = asyncio.run(
        regenerate_step(
            source=src,
            step="mapping",
            db_path=db,
            chat_fn=_chat_for(
                [json.dumps({"step": "mapping", "content": ["N maps to M because O."]})],
                [],
            ),
        )
    )
    got = get_explanation(db, r.explanation_id)
    assert got is not None
    assert got.mapping == ["N maps to M because O."]
    assert got.mapping == got.steps["mapping"]
    assert got.version == 2

    r2 = asyncio.run(
        regenerate_step(
            source=got,
            step="limitations",
            db_path=db,
            chat_fn=_chat_for([json.dumps({"step": "limitations", "content": "NEW-LIMITS"})], []),
        )
    )
    got2 = get_explanation(db, r2.explanation_id)
    assert got2 is not None
    assert got2.limitations == "NEW-LIMITS"
    assert got2.limitations == got2.steps["limitations"]
    assert got2.version == 3
