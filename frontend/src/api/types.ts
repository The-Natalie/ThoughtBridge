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

export interface ExplainRequest {
  concept: string
  familiar_system_hint?: string | null
}

/** Pre-prose mapping rows (stored before mapping became passages). Render-only. */
export interface LegacyMappingItem {
  familiar: string
  technical: string
  note: string
}

export interface ExplanationSteps {
  definition: string
  familiar_system: string
  analogy: string
  mapping: string[]
  walkthrough: string
  placement: string
  interview_ready: string
}

export interface ExplainResponse {
  explanation_id: string
  reused_from: string | null
  steps: ExplanationSteps
}

export interface ExplanationDetail {
  id: string
  concept: string
  version: number
  steps: ExplanationSteps
  mapping: string[]
  limitations: string
  reused_from: string | null
  created_at: string
}

export interface RegenerateRequest {
  step: string
}

export type RegenerateResponse = ExplainResponse

export type MarkerScope = 'explanation' | 'step'

export interface MarkerCreate {
  scope: MarkerScope
  step?: string | null
  note?: string
}

export interface MarkerOut {
  id: string
  explanation_id: string
  scope: MarkerScope
  step: string | null
  note: string
  created_at: string
}

export interface ExplanationSummary {
  id: string
  concept: string
  version: number
  created_at: string
  reused_from: string | null
  reuse_count: number
  marked: boolean
  marker_count: number
  attempt_count: number
}

export interface LearnerEmphasis {
  familiar_systems: boolean
  component_mapping: boolean
  process_placement: boolean
  interactions: boolean
  terminology_bridge: boolean
}

export interface LearnerProfile {
  emphasis: LearnerEmphasis
  how_i_learn: string
}

export interface LearnerProfileUpdate {
  emphasis?: Partial<LearnerEmphasis>
  how_i_learn?: string
}

export interface ArtifactSummary {
  id: string
  title: string
  source_type: string
  created_at: string
  chunk_count: number
  fact_count: number
}

export interface ExtractRequest {
  artifact_ids: string[]
}

export interface ExtractLink {
  to_fact: string
  relation: string
}

export interface ExtractFact {
  fact_id: string
  kind: string
  status: string
  summary: string
  skills: string[]
  confidence: number
  chunk_ids: number[]
  links: ExtractLink[]
}

export interface ExtractResponse {
  facts: ExtractFact[]
}

export interface ExplainStreamEvent {
  type: string
  stage?: string
  text?: string
  steps?: Record<string, unknown>
  explanation_id?: string
  reused_from?: string | null
  message?: string
}
