import { useEffect, useState } from 'react'

import { listExplanations } from '../api/learn'
import { listAttempts, postPracticeAnswer, postPracticeQuestion } from '../api/practice'
import type {
  ExplanationSummary,
  GroundingLabel,
  PracticeAttempt,
  PracticeFeedback,
} from '../api/types'
import AttemptHistory from '../components/AttemptHistory'
import FeedbackCard from '../components/FeedbackCard'

/** Learning-mode Practice Loop: explain back a stored lesson, get feedback. */
function PracticeView() {
  const [explanations, setExplanations] = useState<ExplanationSummary[] | null>(null)
  const [explanationId, setExplanationId] = useState('')
  const [question, setQuestion] = useState<string | null>(null)
  const [attemptId, setAttemptId] = useState<string | null>(null)
  const [answerInput, setAnswerInput] = useState('')
  const [feedback, setFeedback] = useState<PracticeFeedback | null>(null)
  const [grounding, setGrounding] = useState<GroundingLabel | null>(null)
  const [attempts, setAttempts] = useState<PracticeAttempt[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        setExplanations(await listExplanations())
        setAttempts(await listAttempts({ mode: 'learning' }))
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Request failed')
      }
    }
    void load()
  }, [])

  async function refreshAttempts() {
    setAttempts(await listAttempts({ mode: 'learning' }))
  }

  async function getQuestion() {
    if (!explanationId || loading) return
    setLoading(true)
    setError(null)
    setFeedback(null)
    setGrounding(null)
    setAnswerInput('')
    try {
      const response = await postPracticeQuestion({
        mode: 'learning',
        context: { explanation_id: explanationId },
        conversation_id: conversationId,
      })
      setConversationId(response.conversation_id)
      setAttemptId(response.attempt_id)
      setQuestion(response.question)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  async function submitAnswer() {
    const answer = answerInput.trim()
    if (!attemptId || !answer || loading) return
    setLoading(true)
    setError(null)
    try {
      const response = await postPracticeAnswer({ attempt_id: attemptId, answer })
      setFeedback(response.feedback)
      setGrounding(response.grounding)
      setAnswerInput('')
      await refreshAttempts()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  function retryAttempt(attempt: PracticeAttempt) {
    setAttemptId(attempt.id)
    setQuestion(attempt.question)
    setFeedback(null)
    setGrounding(null)
    setAnswerInput(attempt.answer ?? '')
    setError(null)
  }

  function startNewSession() {
    setConversationId(null)
    setQuestion(null)
    setAttemptId(null)
    setFeedback(null)
    setGrounding(null)
    setAnswerInput('')
    setError(null)
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

      <div className="flex gap-2">
        <select
          aria-label="Lesson"
          value={explanationId}
          onChange={(e) => setExplanationId(e.target.value)}
          disabled={loading}
          className="flex-1 rounded border px-3 py-1 text-sm"
        >
          <option value="">Choose a lesson…</option>
          {(explanations ?? []).map((e) => (
            <option key={e.id} value={e.id}>
              {e.concept} (v{e.version})
            </option>
          ))}
        </select>
        <button
          type="button"
          aria-label="Get question"
          onClick={() => void getQuestion()}
          disabled={loading || !explanationId}
          className="rounded border px-3 py-1 text-sm"
        >
          Get question
        </button>
        <button
          type="button"
          aria-label="Start new session"
          onClick={startNewSession}
          disabled={loading}
          className="rounded border px-3 py-1 text-sm"
        >
          New session
        </button>
      </div>
      {explanations !== null && explanations.length === 0 && (
        <p className="text-sm italic">No lessons yet — teach a concept in the Learn tab first.</p>
      )}

      {question && (
        <div aria-label="Question" className="rounded border px-3 py-2">
          <p className="text-xs font-semibold">Explain back</p>
          <p className="mt-1 text-sm">{question}</p>
        </div>
      )}

      {question && attemptId && !feedback && (
        <div className="flex gap-2">
          <textarea
            aria-label="Your answer"
            value={answerInput}
            onChange={(e) => setAnswerInput(e.target.value)}
            placeholder="Explain in your own words…"
            disabled={loading}
            className="flex-1 rounded border px-3 py-1 text-sm"
          />
          <button
            type="button"
            aria-label="Submit answer"
            onClick={() => void submitAnswer()}
            disabled={loading || !answerInput.trim()}
            className="rounded border px-3 py-1 text-sm"
          >
            Submit answer
          </button>
        </div>
      )}

      {feedback && grounding && (
        <div className="flex flex-col gap-2">
          <FeedbackCard feedback={feedback} grounding={grounding} />
          <button
            type="button"
            aria-label="Next question"
            onClick={() => void getQuestion()}
            disabled={loading || !explanationId}
            className="self-start rounded border px-3 py-1 text-sm"
          >
            Next question
          </button>
        </div>
      )}

      <AttemptHistory attempts={attempts} onRetry={retryAttempt} />

      <p className="text-xs">Conversations are saved and retrievable.</p>
    </div>
  )
}

export default PracticeView
