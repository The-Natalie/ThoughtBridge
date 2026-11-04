import { apiGet } from './client'
import type { ArtifactSummary } from './types'

/** List artifacts with provenance metadata and derived counts. */
export function listArtifacts(): Promise<ArtifactSummary[]> {
  return apiGet<ArtifactSummary[]>('/api/v1/artifacts')
}
