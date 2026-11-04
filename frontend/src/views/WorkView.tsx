import { useEffect, useState } from 'react'

import { listArtifacts } from '../api/artifacts'
import { getChunk } from '../api/query'
import { postExtract } from '../api/work'
import type { ArtifactSummary, ChunkDetail, ExtractFact, ExtractResponse } from '../api/types'

type StatusFilter = 'all' | 'proposed' | 'rejected' | 'completed'

const FILTERS: StatusFilter[] = ['all', 'proposed', 'rejected', 'completed']

function WorkView() {
  const [artifacts, setArtifacts] = useState<ArtifactSummary[] | null>(null)
  const [selected, setSelected] = useState<Record<string, boolean>>({})
  const [result, setResult] = useState<ExtractResponse | null>(null)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [activeCitation, setActiveCitation] = useState<ChunkDetail | null>(null)
  const [highlightedFact, setHighlightedFact] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const items = await listArtifacts()
        if (!cancelled) setArtifacts(items)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Request failed')
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  const selectedIds = Object.keys(selected)
    .filter((id) => selected[id])
    .sort()

  async function extract() {
    if (selectedIds.length === 0 || loading) return
    setLoading(true)
    setError(null)
    try {
      const response = await postExtract({ artifact_ids: selectedIds })
      setResult(response)
      setStatusFilter('all')
      setActiveCitation(null)
      setHighlightedFact(null)
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

  function followLink(toFact: string) {
    setHighlightedFact(toFact)
    document.getElementById(`fact-${toFact}`)?.scrollIntoView?.()
  }

  function toggle(id: string) {
    setSelected((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  const visibleFacts: ExtractFact[] =
    result == null
      ? []
      : statusFilter === 'all'
        ? result.facts
        : result.facts.filter((f) => f.status === statusFilter)

  function factSummary(factId: string): string {
    return result?.facts.find((f) => f.fact_id === factId)?.summary ?? factId.slice(0, 8)
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

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-semibold">Artifacts to extract</legend>
        {artifacts == null ? (
          <p className="text-sm">Loading artifacts…</p>
        ) : artifacts.length === 0 ? (
          <p className="text-sm">No artifacts yet — capture notes first.</p>
        ) : (
          artifacts.map((a) => (
            <label key={a.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                aria-label={`Select artifact ${a.title || a.id.slice(0, 8)}`}
                checked={selected[a.id] ?? false}
                onChange={() => toggle(a.id)}
                disabled={loading}
              />
              <span>
                {a.title || '(untitled)'} · {a.source_type} · {a.chunk_count} chunks ·{' '}
                {a.fact_count} facts
              </span>
            </label>
          ))
        )}
      </fieldset>

      <button
        type="button"
        aria-label="Extract"
        onClick={() => void extract()}
        disabled={loading || selectedIds.length === 0}
        className="rounded border px-3 py-1 text-sm"
      >
        Extract
      </button>

      {result != null &&
        (result.facts.length === 0 ? (
          <p role="status" className="text-sm">
            Nothing extractable found in the selected artifacts.
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            <div aria-label="Status filter" className="flex flex-wrap gap-1">
              {FILTERS.map((f) => (
                <button
                  key={f}
                  type="button"
                  aria-label={`Filter: ${f}`}
                  aria-pressed={f === statusFilter}
                  onClick={() => setStatusFilter(f)}
                  className={`rounded border px-2 py-0.5 text-xs ${
                    f === statusFilter ? 'font-semibold underline' : ''
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>

            {visibleFacts.length === 0 ? (
              <p className="text-sm">No facts with this status.</p>
            ) : (
              <div aria-label="Extracted facts" className="flex flex-col gap-3">
                {visibleFacts.map((fact) => (
                  <div
                    key={fact.fact_id}
                    id={`fact-${fact.fact_id}`}
                    aria-label={`Fact ${fact.fact_id.slice(0, 8)}`}
                    className={`rounded border px-3 py-2 ${
                      fact.fact_id === highlightedFact ? 'ring-2 font-semibold' : ''
                    }`}
                  >
                    <p className="text-xs font-semibold">
                      {fact.kind} · {fact.status} · {Math.round(fact.confidence * 100)}%
                    </p>
                    <p className="mt-1 text-sm">{fact.summary}</p>
                    {fact.skills.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {fact.skills.map((s) => (
                          <span key={s} className="rounded border px-2 py-0.5 text-xs">
                            {s}
                          </span>
                        ))}
                      </div>
                    )}
                    {fact.chunk_ids.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {fact.chunk_ids.map((id) => (
                          <button
                            key={id}
                            type="button"
                            aria-label={`Evidence chunk ${id}`}
                            onClick={() => void openCitation(id)}
                            className="rounded border px-2 py-0.5 text-xs underline"
                          >
                            [{id}]
                          </button>
                        ))}
                      </div>
                    )}
                    {fact.links.length > 0 && (
                      <div className="mt-2 flex flex-col gap-1">
                        {fact.links.map((link) => (
                          <button
                            key={`${link.to_fact}-${link.relation}`}
                            type="button"
                            aria-label={`Reasoning link ${link.relation} to ${link.to_fact.slice(0, 8)}`}
                            onClick={() => followLink(link.to_fact)}
                            className="text-left text-xs underline"
                          >
                            {link.relation} → {factSummary(link.to_fact).slice(0, 80)}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}

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
    </div>
  )
}

export default WorkView
