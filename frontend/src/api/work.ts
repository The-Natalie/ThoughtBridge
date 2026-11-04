import { apiPost } from './client'
import type { ExtractRequest, ExtractResponse } from './types'

/** Extract grounded facts with reasoning links over artifacts. */
export function postExtract(req: ExtractRequest): Promise<ExtractResponse> {
  return apiPost<ExtractResponse>('/api/v1/work/extract', req)
}
