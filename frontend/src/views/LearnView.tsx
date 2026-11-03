import { useState } from 'react'

import { getExplanation, postExplain, postRegenerate } from '../api/learn'
import { postQuery } from '../api/query'
import type {
  ExplainRequest,
  ExplanationDetail,
  ExplanationSteps,
  LegacyMappingItem,
} from '../api/types'

const STEP_KEYS: (keyof ExplanationSteps)[] = [
  'definition',
  'familiar_system',
  'analogy',
  'mapping',
  'walkthrough',
  'placement',
  'interview_ready',
  'limitations',
]

const STEP_DISPLAY_NAMES: Record<keyof ExplanationSteps, string> = {
  definition: 'Definition',
  familiar_system: 'Familiar system',
  analogy: 'Analogy',
  mapping: 'Mapping',
  walkthrough: 'Walkthrough',
  placement: 'Placement',
  interview_ready: 'Interview-ready',
  limitations: 'Limitations',
}

interface ThreadEntry {
  question: string
  answer: string
}

/** Render one mapping passage; pre-prose rows fall back to their note text. */
function mappingText(m: unknown): string {
  if (typeof m === 'string') return m
  const legacy = m as LegacyMappingItem
  return `${legacy.familiar} — ${legacy.technical}: ${legacy.note}`
}

function LearnView() {
  const [explanation, setExplanation] = useState<ExplanationDetail | null>(null)
  const [stepIndex, setStepIndex] = useState(0)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [threads, setThreads] = useState<Record<string, ThreadEntry[]>>({})
  const [conceptInput, setConceptInput] = useState('')
  const [hintInput, setHintInput] = useState('')
  const [askInput, setAskInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function teach() {
    const concept = conceptInput.trim()
    if (!concept || loading) return
    setLoading(true)
    setError(null)
    try {
      const req: ExplainRequest = hintInput.trim()
        ? { concept, familiar_system_hint: hintInput.trim() }
        : { concept }
      const response = await postExplain(req)
      const detail = await getExplanation(response.explanation_id)
      setExplanation(detail)
      setStepIndex(0)
      setThreads({})
      setConversationId(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  async function ask() {
    const question = askInput.trim()
    if (!question || loading || !explanation) return
    const step = STEP_KEYS[stepIndex]
    setLoading(true)
    setError(null)
    try {
      const response = await postQuery({
        question,
        mode: 'teaching',
        context: { explanation_id: explanation.id },
        conversation_id: conversationId,
      })
      setConversationId(response.conversation_id)
      setThreads((prev) => ({
        ...prev,
        [step]: [...(prev[step] ?? []), { question, answer: response.answer }],
      }))
      setAskInput('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  async function regenerate() {
    if (loading || !explanation) return
    setLoading(true)
    setError(null)
    try {
      const response = await postRegenerate(explanation.id, {
        step: STEP_KEYS[stepIndex],
      })
      const detail = await getExplanation(response.explanation_id)
      setExplanation(detail)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  function startOver() {
    setExplanation(null)
    setStepIndex(0)
    setThreads({})
    setConversationId(null)
    setConceptInput('')
    setHintInput('')
    setAskInput('')
    setError(null)
  }

  const step = STEP_KEYS[stepIndex]

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

      {!explanation ? (
        <div className="flex flex-col gap-2">
          <input
            aria-label="Concept"
            value={conceptInput}
            onChange={(e) => setConceptInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void teach()
            }}
            placeholder="What do you want to learn?"
            disabled={loading}
            className="rounded border px-3 py-1 text-sm"
          />
          <input
            aria-label="Familiar system hint (optional)"
            value={hintInput}
            onChange={(e) => setHintInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void teach()
            }}
            placeholder="A system you already understand (optional)"
            disabled={loading}
            className="rounded border px-3 py-1 text-sm"
          />
          <button
            type="button"
            aria-label="Teach me"
            onClick={() => void teach()}
            disabled={loading}
            className="rounded border px-3 py-1 text-sm"
          >
            Teach me
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">
              {explanation.concept} v{explanation.version} explanation{' '}
              {explanation.id.slice(0, 8)}…
            </h2>
            <button
              type="button"
              aria-label="Start over"
              onClick={startOver}
              disabled={loading}
              className="rounded border px-3 py-1 text-sm"
            >
              Start over
            </button>
          </div>

          <nav aria-label="Lesson steps" className="flex flex-wrap gap-1">
            {STEP_KEYS.map((key, i) => (
              <button
                key={key}
                type="button"
                aria-label={`Step: ${key}`}
                aria-current={i === stepIndex ? 'step' : undefined}
                onClick={() => setStepIndex(i)}
                disabled={loading}
                className={`rounded border px-2 py-0.5 text-xs ${
                  i === stepIndex ? 'font-semibold underline' : ''
                }`}
              >
                {STEP_DISPLAY_NAMES[key]}
              </button>
            ))}
          </nav>

          <div className="rounded border px-3 py-2">
            <p className="text-xs font-semibold">{STEP_DISPLAY_NAMES[step]}</p>
            {step === 'mapping' ? (
              <div className="flex flex-col gap-2">
                {explanation.steps.mapping.map((m, i) => (
                  <p key={i} className="mt-1 text-sm">
                    {mappingText(m)}
                  </p>
                ))}
              </div>
            ) : (
              (explanation.steps[step] as string).split('\n\n').map((para, j) => (
                <p key={j} className="mt-1 text-sm">
                  {para}
                </p>
              ))
            )}
          </div>

          {(threads[step] ?? []).length > 0 && (
            <div aria-label={`Questions about ${step}`} className="flex flex-col gap-2">
              {(threads[step] ?? []).map((t, i) => (
                <div key={i} className="rounded border px-3 py-2">
                  <p className="text-xs font-semibold">You asked: {t.question}</p>
                  <p className="mt-1 text-sm">{t.answer}</p>
                </div>
              ))}
            </div>
          )}

          <div className="flex gap-2">
            <input
              aria-label="Ask about this step"
              value={askInput}
              onChange={(e) => setAskInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void ask()
              }}
              placeholder="Ask about this step…"
              disabled={loading}
              className="flex-1 rounded border px-3 py-1 text-sm"
            />
            <button
              type="button"
              aria-label="Ask"
              onClick={() => void ask()}
              disabled={loading}
              className="rounded border px-3 py-1 text-sm"
            >
              Ask
            </button>
            <button
              type="button"
              aria-label="Regenerate this step"
              onClick={() => void regenerate()}
              disabled={loading}
              className="rounded border px-3 py-1 text-sm"
            >
              Regenerate this step
            </button>
          </div>

          <div className="flex gap-2">
            <button
              type="button"
              aria-label="Previous step"
              onClick={() => setStepIndex((i) => Math.max(0, i - 1))}
              disabled={loading || stepIndex === 0}
              className="rounded border px-3 py-1 text-sm"
            >
              Back
            </button>
            <button
              type="button"
              aria-label="Next step"
              onClick={() => setStepIndex((i) => Math.min(STEP_KEYS.length - 1, i + 1))}
              disabled={loading || stepIndex === STEP_KEYS.length - 1}
              className="rounded border px-3 py-1 text-sm"
            >
              Next
            </button>
          </div>
        </div>
      )}

      <p className="text-xs">Lessons are saved and reusable.</p>
    </div>
  )
}

export default LearnView
