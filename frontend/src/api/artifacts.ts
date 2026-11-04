import { apiDelete, apiGet, apiPost, apiUrl } from './client'
import type {
  ArtifactCreate,
  ArtifactCreated,
  ArtifactDeleteResponse,
  ArtifactDetail,
  ArtifactSummary,
  UploadCreated,
} from './types'

/** List artifacts with provenance metadata and derived counts. */
export function listArtifacts(): Promise<ArtifactSummary[]> {
  return apiGet<ArtifactSummary[]>('/api/v1/artifacts')
}

/** Ingest typed/pasted text as a new artifact. */
export function postArtifact(req: ArtifactCreate): Promise<ArtifactCreated> {
  return apiPost<ArtifactCreated>('/api/v1/artifacts', req)
}

/** Upload a .txt/.md/.pdf/.docx file as a new artifact. */
export async function uploadArtifact(file: File): Promise<UploadCreated> {
  const form = new FormData()
  form.append('file', file)
  const response = await fetch(apiUrl('/api/v1/artifacts/upload'), {
    method: 'POST',
    body: form,
  })
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`)
  }
  return (await response.json()) as UploadCreated
}

/** Fetch one artifact with full content and derived summary. */
export function getArtifact(id: string): Promise<ArtifactDetail> {
  return apiGet<ArtifactDetail>(`/api/v1/artifacts/${id}`)
}

/** Delete one artifact with full derived cascade. */
export function deleteArtifact(id: string): Promise<ArtifactDeleteResponse> {
  return apiDelete<ArtifactDeleteResponse>(`/api/v1/artifacts/${id}`)
}
