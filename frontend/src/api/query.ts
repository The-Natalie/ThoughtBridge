import { apiDelete, apiGet, apiPost } from './client'
import type {
  ChunkDetail,
  ConversationDeleteResponse,
  ConversationDetail,
  ConversationSummary,
  QueryRequest,
  QueryResponse,
} from './types'

/** Send one grounded question. Errors propagate as thrown Errors. */
export function postQuery(req: QueryRequest): Promise<QueryResponse> {
  return apiPost<QueryResponse>('/api/v1/query', req)
}

/** Fetch one chunk with full text (citation target). */
export function getChunk(id: number): Promise<ChunkDetail> {
  return apiGet<ChunkDetail>(`/api/v1/chunks/${id}`)
}

/** List auto-saved conversations. */
export function listConversations(): Promise<ConversationSummary[]> {
  return apiGet<ConversationSummary[]>('/api/v1/conversations')
}

/** Fetch one conversation with its turns. */
export function getConversation(id: string): Promise<ConversationDetail> {
  return apiGet<ConversationDetail>(`/api/v1/conversations/${id}`)
}

/** Delete one conversation with full derived cascade. */
export function deleteConversation(id: string): Promise<ConversationDeleteResponse> {
  return apiDelete<ConversationDeleteResponse>(`/api/v1/conversations/${id}`)
}
