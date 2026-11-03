"""Eight-step explainer orchestration: chained teaching-mode stages → validate → persist.

Pure orchestration over injected seams: unit tests stub ``chat_fn`` /
``profile_fn`` / ``memory_fn`` / ``persist_fn``, the router passes the real
Meta adapter, seam defaults, and ``None`` for the repository path. Any stage
failure raises ``ExplainerValidationError`` BEFORE persisting — no partial
lessons, no orphan rows.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from app.core.grounding import (
    STEP_KEYS,
    StageName,
    build_regenerate_messages,
    build_stage_messages,
)
from app.db.explanations import (
    ExplanationDetail,
    create_explanation,
    max_version_for_concept,
)
from app.llm.qa import strip_fences

logger = logging.getLogger(__name__)

STAGE_A_MAX_TOKENS = 8192
STAGE_B_MAX_TOKENS = 16384
STAGE_C_MAX_TOKENS = 8192
REGEN_MAX_TOKENS = 8192

# (messages, max_tokens) — different arity from qa.ChatFn on purpose: stage
# budgets differ, so the budget travels with the call and the router adapts.
ExplainerChatFn = Callable[[list[dict[str, str]], int], Awaitable[str]]


@dataclass
class LearnerContext:
    emphasis: dict[str, bool]
    how_i_learn: str


@dataclass
class MemoryContext:
    reused_from: str
    prior_steps: dict
    framing_note: str


ProfileFn = Callable[[], LearnerContext]
MemoryFn = Callable[[str], MemoryContext | None]
PersistFn = Callable[[dict, str | None], tuple[str, int]]


class ExplainerValidationError(ValueError):
    """A stage or regen model output failed schema validation (→ HTTP 502)."""


class StageAOut(BaseModel):
    definition: str
    familiar_system: str


class StageBOut(BaseModel):
    analogy: str
    mapping: list[str]
    walkthrough: str


class StageCOut(BaseModel):
    placement: str
    interview_ready: str
    limitations: str


class RegenOut(BaseModel):
    step: str
    content: str | list[str]


@dataclass
class ExplainedResult:
    explanation_id: str
    reused_from: str | None
    steps: dict


EMPHASIS_LABELS = {
    "familiar_systems": "familiar-system grounding",
    "component_mapping": "explicit component mapping",
    "process_placement": "larger-process placement",
    "interactions": "interaction walkthroughs",
    "terminology_bridge": "terminology bridging",
}


def default_learner_context() -> LearnerContext:
    """Seam default: all emphasis on, no free text (PRD F-13 defaults)."""
    return LearnerContext(emphasis={key: True for key in EMPHASIS_LABELS}, how_i_learn="")


def no_memory(concept: str) -> None:
    """Seam default: no stored explanations yet (deliverable 2 fills this)."""


def render_profile_block(profile: LearnerContext) -> str:
    """Render learner emphasis + free text as lesson-shaping instructions."""
    lines = ["Learner profile (shape the lesson to these preferences):"]
    for key, label in EMPHASIS_LABELS.items():
        state = "emphasized" if profile.emphasis.get(key, True) else "de-emphasized"
        lines.append(f"- {label}: {state}")
    if profile.how_i_learn.strip():
        lines.append(f"How this learner learns best: {profile.how_i_learn.strip()}")
    return "\n".join(lines)


def render_memory_block(memory: MemoryContext | None) -> str:
    """Render prior-explanation context, or "" when there is none."""
    if memory is None:
        return ""
    return "\n".join(
        [
            memory.framing_note,
            "Prior explanation that worked (JSON — reuse its analogy family):",
            json.dumps(memory.prior_steps, default=str),
        ]
    )


def _parse_stage[StageT: BaseModel](stage: StageName, raw: str, model: type[StageT]) -> StageT:
    try:
        return model.model_validate_json(strip_fences(raw))
    except (ValueError, ValidationError) as exc:
        logger.warning("explainer validation failed: stage=%s detail=%s", stage, exc)
        raise ExplainerValidationError(f"stage {stage} returned malformed JSON: {exc}") from exc


async def generate_explanation(
    *,
    concept: str,
    hint: str | None,
    db_path: str,
    chat_fn: ExplainerChatFn,
    profile_fn: ProfileFn,
    memory_fn: MemoryFn,
    persist_fn: PersistFn | None = None,
) -> ExplainedResult:
    """Run the A→B→C chain and persist the versioned lesson (atomic)."""
    profile_block = render_profile_block(profile_fn())
    memory = memory_fn(concept)
    memory_block = render_memory_block(memory)
    reused_from = memory.reused_from if memory is not None else None

    raw_a = await chat_fn(
        build_stage_messages("A", concept, hint, profile_block, memory_block, ""),
        STAGE_A_MAX_TOKENS,
    )
    stage_a = _parse_stage("A", raw_a, StageAOut)

    raw_b = await chat_fn(
        build_stage_messages(
            "B", concept, hint, profile_block, memory_block, stage_a.model_dump_json()
        ),
        STAGE_B_MAX_TOKENS,
    )
    stage_b = _parse_stage("B", raw_b, StageBOut)

    prior_ab = json.dumps({"stage_a": stage_a.model_dump(), "stage_b": stage_b.model_dump()})
    raw_c = await chat_fn(
        build_stage_messages("C", concept, hint, profile_block, memory_block, prior_ab),
        STAGE_C_MAX_TOKENS,
    )
    stage_c = _parse_stage("C", raw_c, StageCOut)

    mapping_items = list(stage_b.mapping)
    steps: dict[str, object] = {
        "definition": stage_a.definition,
        "familiar_system": stage_a.familiar_system,
        "analogy": stage_b.analogy,
        "mapping": mapping_items,
        "walkthrough": stage_b.walkthrough,
        "placement": stage_c.placement,
        "interview_ready": stage_c.interview_ready,
        "limitations": stage_c.limitations,
    }

    if persist_fn is not None:
        explanation_id, _version = persist_fn(steps, reused_from)
    else:
        version = max_version_for_concept(db_path, concept) + 1
        detail = create_explanation(
            db_path,
            concept,
            version,
            steps,
            mapping_items,
            stage_c.limitations,
            reused_from,
        )
        explanation_id = detail.id
    logger.info(
        "explainer generated: concept=%s id=%s reused_from=%s", concept, explanation_id, reused_from
    )
    return ExplainedResult(explanation_id=explanation_id, reused_from=reused_from, steps=steps)


async def regenerate_step(
    *,
    source: ExplanationDetail,
    step: str,
    db_path: str,
    chat_fn: ExplainerChatFn,
    persist_fn: PersistFn | None = None,
) -> ExplainedResult:
    """Regenerate one step of an explanation as a new version (D4/D8)."""
    if step not in STEP_KEYS:
        raise ValueError(f"invalid step {step!r}: must be one of {', '.join(STEP_KEYS)}")
    raw = await chat_fn(build_regenerate_messages(source.steps, step), REGEN_MAX_TOKENS)
    try:
        parsed = RegenOut.model_validate_json(strip_fences(raw))
    except (ValueError, ValidationError) as exc:
        logger.warning("explainer regen validation failed: step=%s detail=%s", step, exc)
        raise ExplainerValidationError(
            f"regen for {step!r} returned malformed JSON: {exc}"
        ) from exc
    if step == "mapping":
        if not isinstance(parsed.content, list):
            raise ExplainerValidationError("regen for 'mapping' must return an array")
        new_content: object = list(parsed.content)
    else:
        if not isinstance(parsed.content, str):
            raise ExplainerValidationError(f"regen for {step!r} must return a string")
        new_content = parsed.content

    merged: dict[str, object] = dict(source.steps)
    merged[step] = new_content
    mapping = merged["mapping"]
    limitations = merged["limitations"]
    if not isinstance(mapping, list) or not isinstance(limitations, str):
        raise TypeError(f"source explanation {source.id} has malformed stored steps")

    if persist_fn is not None:
        explanation_id, _version = persist_fn(merged, None)
    else:
        version = max_version_for_concept(db_path, source.concept) + 1
        detail = create_explanation(
            db_path, source.concept, version, merged, mapping, limitations, None
        )
        explanation_id = detail.id
    logger.info("explainer regenerated: source=%s step=%s id=%s", source.id, step, explanation_id)
    return ExplainedResult(explanation_id=explanation_id, reused_from=None, steps=merged)
