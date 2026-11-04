import { apiGet } from './client'
import type { CheckpointPromptResponse } from './types'

/**
 * Hardcoded fallback for the static checkpoint prompt (PRD §10: the
 * frontend hardcodes the prompt text as fallback). Must stay byte-identical
 * to backend `CHECKPOINT_PROMPT` — the L4-0 validation step diffs them.
 */
export const FALLBACK_CHECKPOINT_PROMPT: string = `Summarize this coding session for my work journal. Be specific and concrete.

1. Work performed — what was built, changed, or fixed.
2. Problems encountered — each problem, how it was resolved, or what is still open.
3. Decisions and reasoning — choices made and why, including approaches considered and rejected and the reason each was rejected.
4. Accomplishments and skills demonstrated — what got done and what it shows (for example debugging, design judgment, or failure-mode analysis).

I will paste your response into ThoughtBridge as a raw note.`;

/** Fetch the static checkpoint prompt text. Errors propagate as thrown Errors. */
export function getCheckpointPrompt(): Promise<CheckpointPromptResponse> {
  return apiGet<CheckpointPromptResponse>('/api/v1/prompts/checkpoint')
}
