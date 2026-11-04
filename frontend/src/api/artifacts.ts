import { apiDelete, apiGet } from './client'
import type { ArtifactDeleteResponse, ArtifactSummary } from './types'

/** List artifacts with provenance metadata and derived counts. */
export function listArtifacts(): Promise<ArtifactSummary[]> {
  return apiGet<ArtifactSummary[]>('/api/v1/artifacts')
}

/** Delete one artifact with full derived cascade. */
export function deleteArtifact(id: string): Promise<ArtifactDeleteResponse> {
  return apiDelete<ArtifactDeleteResponse>(`/api/v1/artifacts/${id}`)
}
