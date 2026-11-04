import type { ExtractFact } from '../api/types'

interface FactCardProps {
  fact: ExtractFact
  /** Sibling facts for resolving reasoning-link labels. */
  siblings: ExtractFact[]
  highlighted: boolean
  /** Element-id prefix (`fact-` in results, `acc-` in the browser). */
  idPrefix: string
  onOpenCitation: (chunkId: number) => void
  onFollowLink: (toFact: string) => void
}

function FactCard({ fact, siblings, highlighted, idPrefix, onOpenCitation, onFollowLink }: FactCardProps) {
  function factSummary(factId: string): string {
    return siblings.find((f) => f.fact_id === factId)?.summary ?? factId.slice(0, 8)
  }

  return (
    <div
      id={`${idPrefix}${fact.fact_id}`}
      aria-label={`Fact ${fact.fact_id.slice(0, 8)}`}
      className={`rounded border px-3 py-2 ${highlighted ? 'ring-2 font-semibold' : ''}`}
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
              onClick={() => onOpenCitation(id)}
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
              onClick={() => onFollowLink(link.to_fact)}
              className="text-left text-xs underline"
            >
              {link.relation} → {factSummary(link.to_fact).slice(0, 80)}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default FactCard
