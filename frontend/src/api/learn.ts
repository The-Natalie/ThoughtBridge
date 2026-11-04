import { apiGet, apiPost, apiPut } from './client'
import type {
  ExplainRequest,
  ExplainResponse,
  ExplanationDetail,
  ExplanationSummary,
  LearnerProfile,
  LearnerProfileUpdate,
  MarkerCreate,
  MarkerOut,
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

/** List stored explanations with success signals, newest first. */
export function listExplanations(concept?: string): Promise<ExplanationSummary[]> {
  if (concept === undefined) {
    return apiGet<ExplanationSummary[]>('/api/v1/learn/explanations')
  }
  return apiGet<ExplanationSummary[]>(
    `/api/v1/learn/explanations?concept=${encodeURIComponent(concept)}`,
  )
}

/** Set a "clicked" marker on an explanation or one of its steps. */
export function createMarker(id: string, body: MarkerCreate): Promise<MarkerOut> {
  return apiPost<MarkerOut>(`/api/v1/learn/explanations/${id}/markers`, body)
}

/** List "clicked" markers for one explanation, chronological. */
export function listMarkers(id: string): Promise<MarkerOut[]> {
  return apiGet<MarkerOut[]>(`/api/v1/learn/explanations/${id}/markers`)
}

/** Fetch the learner-preferences profile (defaults when never saved). */
export function getLearnerProfile(): Promise<LearnerProfile> {
  return apiGet<LearnerProfile>('/api/v1/learn/profile')
}

/** Merge-update the learner-preferences profile. */
export function updateLearnerProfile(body: LearnerProfileUpdate): Promise<LearnerProfile> {
  return apiPut<LearnerProfile>('/api/v1/learn/profile', body)
}
