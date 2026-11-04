import type { ChunkDetail } from '../api/types'

interface CitationPanelProps {
  chunk: ChunkDetail
  onClose: () => void
}

/** Shared chunk-detail panel: header meta + conversation badge + full text. */
function CitationPanel({ chunk, onClose }: CitationPanelProps) {
  return (
    <div className="rounded border px-3 py-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold">
          Chunk {chunk.id} · artifact {chunk.artifact_id} · span {chunk.span[0]}–{chunk.span[1]}
        </p>
        <button
          type="button"
          aria-label="Close citation"
          onClick={onClose}
          className="text-xs underline"
        >
          Close
        </button>
      </div>
      {chunk.source_type === 'tb_conversation' && (
        <p aria-label="Conversation source" className="text-xs italic">
          from a ThoughtBridge conversation
        </p>
      )}
      <p className="mt-1 text-sm">{chunk.text}</p>
    </div>
  )
}

export default CitationPanel
