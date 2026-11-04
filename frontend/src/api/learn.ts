import { apiGet, apiPost, apiPut, apiUrl } from './client'
import type {
  ExplainRequest,
  ExplainResponse,
  ExplainStreamEvent,
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

/** Teach a concept, receiving stage events as SSE (same generation as explain). */
export async function postExplainStream(
  req: ExplainRequest,
  onEvent: (event: ExplainStreamEvent) => void,
): Promise<void> {
  const response = await fetch(apiUrl('/api/v1/learn/explain/stream'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!response.ok || !response.body) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) return
    buffer += decoder.decode(value, { stream: true })
    let cut: number
    while ((cut = buffer.indexOf('\n\n')) >= 0) {
      const frame = buffer.slice(0, cut)
      buffer = buffer.slice(cut + 2)
      for (const line of frame.split('\n')) {
        const text = line.trim()
        if (!text.startsWith('data:')) continue
        const payload = text.slice(5).trim()
        if (payload === '[DONE]') return
        onEvent(JSON.parse(payload) as ExplainStreamEvent)
      }
    }
  }
}

const DEF_KEY = '"definition"'

/**
 * Best-effort Definition text from a partial stage-D JSON buffer.
 * Returns null until a parseable prefix exists; the validated render
 * always supersedes this. Never throws on truncated input.
 */
export function extractPartialDefinition(buffer: string): string | null {
  const keyAt = buffer.indexOf(DEF_KEY)
  if (keyAt < 0) return null
  const colonAt = buffer.indexOf(':', keyAt + DEF_KEY.length)
  if (colonAt < 0) return null
  const openAt = buffer.indexOf('"', colonAt + 1)
  if (openAt < 0) return null
  let raw = ''
  let i = openAt + 1
  let closed = false
  while (i < buffer.length) {
    const ch = buffer[i]
    if (ch === '\\') {
      raw += buffer.slice(i, i + 2)
      i += 2
      continue
    }
    if (ch === '"') {
      closed = true
      break
    }
    raw += ch
    i += 1
  }
  if (!raw) return null
  try {
    return JSON.parse(`"${raw}"`) as string
  } catch {
    if (!closed && raw.endsWith('\\')) {
      try {
        return JSON.parse(`"${raw.slice(0, -1)}"`) as string
      } catch {
        return null
      }
    }
    return null
  }
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
