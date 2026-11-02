import { useState } from 'react'

import { getChunk, postQuery } from '../api/query'
import type { ChunkDetail, Citation, ModeUsed } from '../api/types'

interface Message {
  role: 'user' | 'assistant'
  content: string
  citations: Citation[]
  modeUsed: ModeUsed | null
}

function groundingLabel(modeUsed: ModeUsed, citations: Citation[]): string {
  if (modeUsed === 'evidence') return 'from your notes'
  return citations.length > 0 ? 'general explanation + your notes' : 'general explanation'
}

function ChatView() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeCitation, setActiveCitation] = useState<ChunkDetail | null>(null)

  async function send() {
    const question = input.trim()
    if (!question || loading) return
    setLoading(true)
    setError(null)
    setMessages((prev) => [...prev, { role: 'user', content: question, citations: [], modeUsed: null }])
    try {
      const response = await postQuery({ question, mode: 'auto', conversation_id: conversationId })
      setConversationId(response.conversation_id)
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: response.answer,
          citations: response.citations,
          modeUsed: response.mode_used,
        },
      ])
      setInput('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  async function openCitation(chunkId: number) {
    setError(null)
    try {
      setActiveCitation(await getChunk(chunkId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <div role="alert" className="rounded border border-red-500 px-3 py-2 text-sm">
          <span>{error}</span>{' '}
          <button type="button" aria-label="Dismiss error" onClick={() => setError(null)} className="underline">
            Dismiss
          </button>
        </div>
      )}

      <div aria-label="Messages" className="flex flex-col gap-3">
        {messages.map((m, i) =>
          m.role === 'user' ? (
            <div key={i} className="self-end rounded border px-3 py-2">
              <p className="text-xs font-semibold">You</p>
              <p className="text-sm">{m.content}</p>
            </div>
          ) : (
            <div key={i} className="self-start rounded border px-3 py-2">
              <p className="text-xs font-semibold">ThoughtBridge</p>
              {m.modeUsed && (
                <p className="text-xs italic">{groundingLabel(m.modeUsed, m.citations)}</p>
              )}
              {m.content.split('\n\n').map((para, j) => (
                <p key={j} className="mt-1 text-sm">
                  {para}
                </p>
              ))}
              {m.citations.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {m.citations.map((c) => (
                    <button
                      key={c.chunk_id}
                      type="button"
                      aria-label={`Citation ${c.chunk_id}`}
                      onClick={() => void openCitation(c.chunk_id)}
                      className="rounded border px-2 py-0.5 text-xs underline"
                    >
                      [{c.chunk_id}] {c.excerpt.slice(0, 40)}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ),
        )}
      </div>

      {activeCitation && (
        <div className="rounded border px-3 py-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold">
              Chunk {activeCitation.id} · artifact {activeCitation.artifact_id} · span{' '}
              {activeCitation.span[0]}–{activeCitation.span[1]}
            </p>
            <button
              type="button"
              aria-label="Close citation"
              onClick={() => setActiveCitation(null)}
              className="text-xs underline"
            >
              Close
            </button>
          </div>
          <p className="mt-1 text-sm">{activeCitation.text}</p>
        </div>
      )}

      <div className="flex gap-2">
        <input
          aria-label="Ask a question"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void send()
          }}
          placeholder="Ask about your notes…"
          disabled={loading}
          className="flex-1 rounded border px-3 py-1 text-sm"
        />
        <button
          type="button"
          aria-label="Send"
          onClick={() => void send()}
          disabled={loading}
          className="rounded border px-3 py-1 text-sm"
        >
          Send
        </button>
      </div>

      <p className="text-xs">Conversations are saved and retrievable.</p>
    </div>
  )
}

export default ChatView
