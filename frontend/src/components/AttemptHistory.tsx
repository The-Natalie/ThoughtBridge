import type { PracticeAttempt } from '../api/types'

interface AttemptHistoryProps {
  attempts: PracticeAttempt[]
  onRetry: (attempt: PracticeAttempt) => void
}

function attemptLabel(a: PracticeAttempt): string {
  const kind = a.question_kind ? `/${a.question_kind}` : ''
  const concept = a.concept ? ` · ${a.concept}` : ''
  return `${a.mode}${kind}${concept}`
}

/** Shared attempt history: retry queue first (oldest first), then full list. */
function AttemptHistory({ attempts, onRetry }: AttemptHistoryProps) {
  const retries = attempts.filter((a) => a.needs_retry).reverse()

  return (
    <div aria-label="Practice history" className="flex flex-col gap-2">
      <p className="text-sm font-semibold">
        Practice history ({attempts.length}) · Retry queue ({retries.length})
      </p>
      {attempts.length === 0 && <p className="text-sm italic">No attempts yet.</p>}
      {retries.length > 0 && (
        <div aria-label="Retry queue" className="flex flex-col gap-2">
          {retries.map((a) => (
            <div key={a.id} className="rounded border px-3 py-2">
              <p className="text-xs font-semibold">
                Retry · {attemptLabel(a)}
              </p>
              <p className="mt-1 text-sm">{a.question}</p>
              <button
                type="button"
                aria-label={`Retry ${a.id}`}
                onClick={() => onRetry(a)}
                className="mt-1 rounded border px-2 py-0.5 text-xs underline"
              >
                Retry this question
              </button>
            </div>
          ))}
        </div>
      )}
      {attempts.map((a) => (
        <div key={a.id} className="rounded border px-3 py-2">
          <p className="text-xs font-semibold">
            {attemptLabel(a)}
            {a.needs_retry && ' · Retry'}
            {a.grounding ? ` · ${a.grounding}` : ''}
          </p>
          <p className="mt-1 text-sm">{a.question}</p>
        </div>
      ))}
    </div>
  )
}

export default AttemptHistory
