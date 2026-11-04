"""Static checkpoint prompt endpoint (PRD F-9) — no DB, settings, or network."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

CHECKPOINT_PROMPT: str = (
    "Summarize this coding session for my work journal. Be specific and concrete.\n"
    "\n"
    "1. Work performed — what was built, changed, or fixed.\n"
    "2. Problems encountered — each problem, how it was resolved, or what is still open.\n"
    "3. Decisions and reasoning — choices made and why, including approaches considered and rejected and the reason each was rejected.\n"
    "4. Accomplishments and skills demonstrated — what got done and what it shows (for example debugging, design judgment, or failure-mode analysis).\n"
    "\n"
    "I will paste your response into ThoughtBridge as a raw note."
)

router = APIRouter(tags=["prompts"])


class CheckpointPromptResponse(BaseModel):
    prompt: str


@router.get("/prompts/checkpoint", response_model=CheckpointPromptResponse)
def get_checkpoint_prompt() -> CheckpointPromptResponse:
    """Return the static copyable checkpoint prompt (PRD F-9)."""
    return CheckpointPromptResponse(prompt=CHECKPOINT_PROMPT)
