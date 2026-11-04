import { apiGet, apiPost } from './client'
import type {
  PracticeAnswerRequest,
  PracticeAnswerResponse,
  PracticeAttempt,
  PracticeMode,
  PracticeQuestionRequest,
  PracticeQuestionResponse,
} from './types'

/** Ask for one practice question. Errors propagate as thrown Errors. */
export function postPracticeQuestion(
  req: PracticeQuestionRequest,
): Promise<PracticeQuestionResponse> {
  return apiPost<PracticeQuestionResponse>('/api/v1/practice/question', req)
}

/** Submit one answer for evaluation. Errors propagate as thrown Errors. */
export function postPracticeAnswer(
  req: PracticeAnswerRequest,
): Promise<PracticeAnswerResponse> {
  return apiPost<PracticeAnswerResponse>('/api/v1/practice/answer', req)
}

export interface AttemptFilters {
  mode?: PracticeMode
  explanation_id?: string
  retry_only?: boolean
}

/** List practice attempts, newest first, with optional filters. */
export function listAttempts(filters?: AttemptFilters): Promise<PracticeAttempt[]> {
  const params = new URLSearchParams()
  if (filters?.mode !== undefined) params.set('mode', filters.mode)
  if (filters?.explanation_id !== undefined) params.set('explanation_id', filters.explanation_id)
  if (filters?.retry_only === true) params.set('retry_only', 'true')
  const query = params.toString()
  const path = query ? `/api/v1/practice/attempts?${query}` : '/api/v1/practice/attempts'
  return apiGet<PracticeAttempt[]>(path)
}
