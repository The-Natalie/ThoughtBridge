import { useEffect, useState } from 'react'

import { listArtifacts } from '../api/artifacts'
import { getChunk } from '../api/query'
import { listAccomplishments, postExtract } from '../api/work'
import type { ArtifactSummary, ChunkDetail, ExtractFact, ExtractResponse } from '../api/types'
import FactCard from '../components/FactCard'
import CareerProfilePanel from './CareerProfilePanel'

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
  const [accomplishments, setAccomplishments] = useState<ExtractFact[] | null>(null)
  const [accFiltered, setAccFiltered] = useState(false)
  const [accLoading, setAccLoading] = useState(false)
  const [accQ, setAccQ] = useState('')
  const [accSkill, setAccSkill] = useState('')

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

  useEffect(() => {
    let cancelled = false
    async function load() {
      setAccLoading(true)
      try {
        const items = await listAccomplishments()
        if (!cancelled) {
          setAccomplishments(items)
          setAccFiltered(false)
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Request failed')
      } finally {
        if (!cancelled) setAccLoading(false)
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

  async function loadAccomplishments(q?: string, skill?: string, filtered = false) {
    setAccLoading(true)
    try {
      setAccomplishments(await listAccomplishments(q, skill))
      setAccFiltered(filtered)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setAccLoading(false)
    }
  }

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
      await loadAccomplishments()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  function searchAccomplishments() {
    const q = accQ.trim() === '' ? undefined : accQ
    const skill = accSkill.trim() === '' ? undefined : accSkill
    void loadAccomplishments(q, skill, q !== undefined || skill !== undefined)
  }

  async function openCitation(chunkId: number) {
    setError(null)
    try {
      setActiveCitation(await getChunk(chunkId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    }
  }

  function followLink(toFact: string, prefix = 'fact-') {
    setHighlightedFact(toFact)
    document.getElementById(`${prefix}${toFact}`)?.scrollIntoView?.()
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

      <CareerProfilePanel />

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
                  <FactCard
                    key={fact.fact_id}
                    fact={fact}
                    siblings={result?.facts ?? []}
                    highlighted={fact.fact_id === highlightedFact}
                    idPrefix="fact-"
                    onOpenCitation={(id) => void openCitation(id)}
                    onFollowLink={(to) => followLink(to, 'fact-')}
                  />
                ))}
              </div>
            )}
          </div>
        ))}

      <section aria-label="Saved accomplishments" className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold">Saved accomplishments</h2>
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-sm">
            Filter accomplishments by keyword
            <input
              type="text"
              aria-label="Filter accomplishments by keyword"
              value={accQ}
              onChange={(e) => setAccQ(e.target.value)}
              disabled={accLoading}
              className="rounded border px-3 py-1 text-sm"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Filter accomplishments by skill
            <input
              type="text"
              aria-label="Filter accomplishments by skill"
              value={accSkill}
              onChange={(e) => setAccSkill(e.target.value)}
              disabled={accLoading}
              className="rounded border px-3 py-1 text-sm"
            />
          </label>
          <button
            type="button"
            aria-label="Search accomplishments"
            onClick={searchAccomplishments}
            disabled={accLoading}
            className="rounded border px-3 py-1 text-sm"
          >
            Search
          </button>
        </div>

        {accomplishments === null ? (
          <p className="text-sm">Loading saved accomplishments…</p>
        ) : accomplishments.length === 0 ? (
          accFiltered ? (
            <p className="text-sm">No accomplishments match this filter.</p>
          ) : (
            <p className="text-sm">No saved accomplishments yet — run Extract first.</p>
          )
        ) : (
          <div className="flex flex-col gap-3">
            {accomplishments.map((fact) => (
              <FactCard
                key={fact.fact_id}
                fact={fact}
                siblings={accomplishments}
                highlighted={fact.fact_id === highlightedFact}
                idPrefix="acc-"
                onOpenCitation={(id) => void openCitation(id)}
                onFollowLink={(to) => followLink(to, 'acc-')}
              />
            ))}
          </div>
        )}
      </section>

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

      <p className="text-xs">Conversations are saved and retrievable.</p>
    </div>
  )
}

export default WorkView
