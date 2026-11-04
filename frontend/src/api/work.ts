import { apiGet, apiPost, apiPut } from './client'
import type {
  CareerProfile,
  CareerProfileUpdate,
  ExtractFact,
  ExtractRequest,
  ExtractResponse,
} from './types'

/** Extract grounded facts with reasoning links over artifacts. */
export function postExtract(req: ExtractRequest): Promise<ExtractResponse> {
  return apiPost<ExtractResponse>('/api/v1/work/extract', req)
}

/** Fetch the career profile (empty defaults when never saved). */
export function getCareerProfile(): Promise<CareerProfile> {
  return apiGet<CareerProfile>('/api/v1/profile')
}

/** Merge-update the career profile. */
export function updateCareerProfile(body: CareerProfileUpdate): Promise<CareerProfile> {
  return apiPut<CareerProfile>('/api/v1/profile', body)
}

/** List persisted accomplishment facts, newest first, with optional filters. */
export function listAccomplishments(q?: string, skill?: string): Promise<ExtractFact[]> {
  const params: string[] = []
  if (q !== undefined) params.push(`q=${encodeURIComponent(q)}`)
  if (skill !== undefined) params.push(`skill=${encodeURIComponent(skill)}`)
  const query = params.length > 0 ? `?${params.join('&')}` : ''
  return apiGet<ExtractFact[]>(`/api/v1/work/accomplishments${query}`)
}
