import { useRef, useState } from 'react'

import {
  createMarker,
  extractPartialDefinition,
  getExplanation,
  listExplanations,
  listMarkers,
  postExplainStream,
  postRegenerate,
} from '../api/learn'
import { postQuery } from '../api/query'
import LearnerProfilePanel from './LearnerProfilePanel'
import type {
  ExplainRequest,
  ExplanationDetail,
  ExplanationSteps,
  ExplanationSummary,
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
]

const STEP_DISPLAY_NAMES: Record<keyof ExplanationSteps, string> = {
  definition: 'Definition',
  familiar_system: 'Familiar system',
  analogy: 'Analogy',
  mapping: 'Mapping',
  walkthrough: 'Walkthrough',
  placement: 'Placement',
  interview_ready: 'Interview-ready',
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
  const [noteInput, setNoteInput] = useState('')
  const [wholeMarked, setWholeMarked] = useState(false)
  const [stepMarked, setStepMarked] = useState<Record<string, boolean>>({})
  const [notice, setNotice] = useState<{ text: string; priorId: string } | null>(null)
  const [history, setHistory] = useState<ExplanationSummary[] | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [streamingDef, setStreamingDef] = useState<string | null>(null)
  const [streamedSteps, setStreamedSteps] = useState<Partial<ExplanationSteps>>({})
  const [activeConcept, setActiveConcept] = useState<string | null>(null)
  const genRef = useRef(0)

  async function teach() {
    const concept = conceptInput.trim()
    if (!concept || loading) return
    genRef.current += 1
    const gen = genRef.current
    setLoading(true)
    setError(null)
    setStreamingDef(null)
    setStreamedSteps({})
    setActiveConcept(concept)
    setStepIndex(0)
    try {
      const req: ExplainRequest = hintInput.trim()
        ? { concept, familiar_system_hint: hintInput.trim() }
        : { concept }
      let rawDef = ''
      let completed: { explanation_id: string; reused_from: string | null } | null = null
      await postExplainStream(req, (event) => {
        if (gen !== genRef.current) return
        if (event.type === 'token' && event.stage === 'D' && event.text) {
          rawDef += event.text
          const text = extractPartialDefinition(rawDef)
          if (text) setStreamingDef(text)
        } else if (event.type === 'stage_validated' && event.steps) {
          const steps = event.steps as Partial<ExplanationSteps>
          if (event.stage === 'D' && typeof steps.definition === 'string') {
            setStreamingDef(steps.definition)
          }
          setStreamedSteps((prev) => ({ ...prev, ...steps }))
        } else if (event.type === 'lesson_complete' && event.explanation_id) {
          completed = { explanation_id: event.explanation_id, reused_from: event.reused_from ?? null }
        } else if (event.type === 'error') {
          throw new Error(event.message || 'Generation failed')
        }
      })
      if (gen !== genRef.current) return
      if (!completed) throw new Error('Generation ended without completing')
      const done: { explanation_id: string; reused_from: string | null } = completed
      const detail = await getExplanation(done.explanation_id)
      setExplanation(detail)
      setStepIndex(0)
      setThreads({})
      setConversationId(null)
      setNoteInput('')
      setWholeMarked(false)
      setStepMarked({})
      setNotice(null)
      setHistory(null)
      setHistoryOpen(false)
      setStreamingDef(null)
      setStreamedSteps({})
      setActiveConcept(null)
      if (done.reused_from) {
        const [, markers] = await Promise.all([
          getExplanation(done.reused_from),
          listMarkers(done.reused_from),
        ])
        setNotice({
          text: markers.some((m) => m.scope === 'explanation')
            ? 'This builds on an explanation that clicked for you before.'
            : 'This builds on your earlier explanation.',
          priorId: done.reused_from,
        })
      }
    } catch (err) {
      if (gen !== genRef.current) return
      setError(err instanceof Error ? err.message : 'Request failed')
      setStreamingDef(null)
      setStreamedSteps({})
      setActiveConcept(null)
    } finally {
      if (gen === genRef.current) setLoading(false)
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
      setNoteInput('')
      setWholeMarked(false)
      setStepMarked({})
      setNotice(null)
      setHistory(null)
      setHistoryOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  async function markWhole() {
    if (loading || !explanation) return
    setLoading(true)
    setError(null)
    try {
      await createMarker(explanation.id, {
        scope: 'explanation',
        step: null,
        ...(noteInput.trim() ? { note: noteInput.trim() } : {}),
      })
      setWholeMarked(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  async function markStep() {
    if (loading || !explanation) return
    const current = STEP_KEYS[stepIndex]
    setLoading(true)
    setError(null)
    try {
      await createMarker(explanation.id, {
        scope: 'step',
        step: current,
        ...(noteInput.trim() ? { note: noteInput.trim() } : {}),
      })
      setStepMarked((prev) => ({ ...prev, [current]: true }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  async function toggleHistory() {
    if (historyOpen) {
      setHistoryOpen(false)
      setHistory(null)
      return
    }
    if (loading || !explanation) return
    setLoading(true)
    setError(null)
    try {
      const items = await listExplanations(explanation.concept)
      setHistory(items)
      setHistoryOpen(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  async function loadVersion(id: string) {
    if (loading) return
    setLoading(true)
    setError(null)
    try {
      const detail = await getExplanation(id)
      setExplanation(detail)
      setStepIndex(0)
      setThreads({})
      setConversationId(null)
      setNoteInput('')
      setWholeMarked(false)
      setStepMarked({})
      setNotice(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  function viewPrior() {
    if (notice) void loadVersion(notice.priorId)
  }

  function startOver() {
    genRef.current += 1
    setLoading(false)
    setActiveConcept(null)
    setStreamingDef(null)
    setStreamedSteps({})
    setExplanation(null)
    setStepIndex(0)
    setThreads({})
    setConversationId(null)
    setConceptInput('')
    setHintInput('')
    setAskInput('')
    setError(null)
    setNoteInput('')
    setWholeMarked(false)
    setStepMarked({})
    setNotice(null)
    setHistory(null)
    setHistoryOpen(false)
  }

  const step = STEP_KEYS[stepIndex]
  const generating = activeConcept !== null && explanation === null
  const viewSteps: Partial<ExplanationSteps> = explanation
    ? explanation.steps
    : { ...streamedSteps, ...(streamingDef ? { definition: streamingDef } : {}) }

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

      {!(explanation || activeConcept) ? (
        <div className="flex flex-col gap-2">
          <LearnerProfilePanel />
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
              {explanation ? (
                <>
                  {explanation.concept} v{explanation.version} explanation{' '}
                  {explanation.id.slice(0, 8)}…
                </>
              ) : (
                <>{activeConcept} (generating…)</>
              )}
            </h2>
            <button
              type="button"
              aria-label="Start over"
              onClick={startOver}
              disabled={loading && !generating}
              className="rounded border px-3 py-1 text-sm"
            >
              Start over
            </button>
          </div>

          {notice && (
            <div
              role="status"
              aria-label="Reuse notice"
              className="rounded border px-3 py-2 text-sm"
            >
              <span>{notice.text}</span>{' '}
              <button
                type="button"
                aria-label="View prior explanation"
                onClick={() => viewPrior()}
                disabled={loading}
                className="underline"
              >
                View prior
              </button>
            </div>
          )}

          <nav aria-label="Lesson steps" className="flex flex-wrap gap-1">
            {STEP_KEYS.map((key, i) => (
              <button
                key={key}
                type="button"
                aria-label={`Step: ${key}`}
                aria-current={i === stepIndex ? 'step' : undefined}
                onClick={() => setStepIndex(i)}
                disabled={loading && !generating}
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
              Array.isArray(viewSteps.mapping) ? (
                <div className="flex flex-col gap-2">
                  {viewSteps.mapping.map((m, i) => (
                    <p key={i} className="mt-1 text-sm">
                      {mappingText(m)}
                    </p>
                  ))}
                </div>
              ) : (
                <p role="status" className="mt-1 text-sm">
                  Loading…
                </p>
              )
            ) : typeof viewSteps[step] === 'string' ? (
              (viewSteps[step] as string).split('\n\n').map((para, j) => (
                <p key={j} className="mt-1 text-sm">
                  {para}
                </p>
              ))
            ) : (
              <p role="status" className="mt-1 text-sm">
                Loading…
              </p>
            )}
          </div>

          {explanation && (
          <div className="flex gap-2">
            <input
              aria-label="What clicked (optional note)"
              value={noteInput}
              onChange={(e) => setNoteInput(e.target.value)}
              placeholder="What clicked? (optional)"
              disabled={loading}
              className="flex-1 rounded border px-3 py-1 text-sm"
            />
            <button
              type="button"
              aria-label="Mark whole explanation as clicked"
              onClick={() => void markWhole()}
              disabled={loading || wholeMarked}
              className="rounded border px-3 py-1 text-sm"
            >
              {wholeMarked ? 'Clicked ✓' : 'This clicked'}
            </button>
            <button
              type="button"
              aria-label="Mark this step as clicked"
              onClick={() => void markStep()}
              disabled={loading || (stepMarked[step] ?? false)}
              className="rounded border px-3 py-1 text-sm"
            >
              {stepMarked[step] ? 'Clicked ✓' : 'This step clicked'}
            </button>
          </div>
          )}

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

          {explanation && (
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
          )}

          <div className="flex gap-2">
            <button
              type="button"
              aria-label="Previous step"
              onClick={() => setStepIndex((i) => Math.max(0, i - 1))}
              disabled={(loading && !generating) || stepIndex === 0}
              className="rounded border px-3 py-1 text-sm"
            >
              Back
            </button>
            <button
              type="button"
              aria-label="Next step"
              onClick={() => setStepIndex((i) => Math.min(STEP_KEYS.length - 1, i + 1))}
              disabled={(loading && !generating) || stepIndex === STEP_KEYS.length - 1}
              className="rounded border px-3 py-1 text-sm"
            >
              Next
            </button>
          </div>

          {explanation && (
          <div className="flex flex-col gap-2">
            <button
              type="button"
              aria-label={historyOpen ? 'Hide earlier versions' : 'Show earlier versions'}
              onClick={() => void toggleHistory()}
              disabled={loading}
              className="rounded border px-3 py-1 text-sm"
            >
              {historyOpen ? 'Hide earlier versions' : 'Show earlier versions'}
            </button>
            {historyOpen && history && (
              <div aria-label="Earlier versions" className="flex flex-wrap gap-1">
                {history.map((h) => (
                  <button
                    key={h.id}
                    type="button"
                    aria-label={`Load version ${h.version}`}
                    aria-current={h.id === explanation.id ? 'true' : undefined}
                    onClick={() => void loadVersion(h.id)}
                    disabled={loading}
                    className="rounded border px-2 py-0.5 text-xs"
                  >
                    v{h.version}
                    {h.marked ? ' ✓' : ''}
                  </button>
                ))}
              </div>
            )}
          </div>
          )}
        </div>
      )}

      <p className="text-xs">Lessons are saved and reusable.</p>
    </div>
  )
}

export default LearnView
