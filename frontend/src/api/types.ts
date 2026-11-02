/** Shared API types. Field names mirror backend Pydantic JSON exactly. */

export type QueryMode = 'evidence' | 'teaching' | 'auto'
export type ModeUsed = 'evidence' | 'teaching'

export interface Citation {
  chunk_id: number
  artifact_id: string
  span: [number, number]
  excerpt: string
}

export interface QueryRequest {
  question: string
  mode?: QueryMode
  top_k?: number
  context?: { explanation_id: string | null }
  conversation_id?: string | null
}

export interface QueryResponse {
  answer: string
  citations: Citation[]
  mode_used: ModeUsed
  conversation_id: string
}

export interface ChunkDetail {
  id: number
  artifact_id: string
  chunk_idx: number
  span: [number, number]
  text: string
}

export interface Turn {
  id: string
  idx: number
  role: 'user' | 'assistant'
  content: string
  mode: string | null
  citations: Citation[]
  created_at: string
}

export interface ConversationDetail {
  id: string
  kind: string
  created_at: string
  turns: Turn[]
}

export interface ConversationSummary {
  id: string
  kind: string
  created_at: string
  turn_count: number
}
