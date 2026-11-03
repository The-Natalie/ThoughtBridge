import { apiGet, apiPost } from './client'
import type {
  ExplainRequest,
  ExplainResponse,
  ExplanationDetail,
  RegenerateRequest,
  RegenerateResponse,
} from './types'

/** Teach a concept: multi-stage generation persisted as a new version. */
export function postExplain(req: ExplainRequest): Promise<ExplainResponse> {
  return apiPost<ExplainResponse>('/api/v1/learn/explain', req)
}

/** Fetch one stored explanation version. */
export function getExplanation(id: string): Promise<ExplanationDetail> {
  return apiGet<ExplanationDetail>(`/api/v1/learn/explanations/${id}`)
}

/** Regenerate one step of an explanation as a new version. */
export function postRegenerate(
  id: string,
  req: RegenerateRequest,
): Promise<RegenerateResponse> {
  return apiPost<RegenerateResponse>(`/api/v1/learn/explanations/${id}/regenerate`, req)
}
