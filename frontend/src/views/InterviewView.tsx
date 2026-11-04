import { useEffect, useState } from 'react'

import { listAttempts, postPracticeAnswer, postPracticeQuestion } from '../api/practice'
import type {
  GroundingLabel,
  PracticeAttempt,
  PracticeFeedback,
  QuestionKind,
} from '../api/types'
import AttemptHistory from '../components/AttemptHistory'
import FeedbackCard from '../components/FeedbackCard'

/** Interview-mode Practice Loop: experience or technical questions + feedback. */
function InterviewView() {
  const [kind, setKind] = useState<QuestionKind>('experience')
  const [focusInput, setFocusInput] = useState('')
  const [question, setQuestion] = useState<string | null>(null)
  const [questionKind, setQuestionKind] = useState<QuestionKind | null>(null)
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
        setAttempts(await listAttempts({ mode: 'interview' }))
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Request failed')
      }
    }
    void load()
  }, [])

  async function refreshAttempts() {
    setAttempts(await listAttempts({ mode: 'interview' }))
  }

  function clearQuestion() {
    setQuestion(null)
    setQuestionKind(null)
    setAttemptId(null)
    setFeedback(null)
    setGrounding(null)
    setAnswerInput('')
  }

  function changeKind(next: QuestionKind) {
    if (next === kind) return
    setKind(next)
    clearQuestion()
    setError(null)
  }

  async function getQuestion() {
    if (loading) return
    setLoading(true)
    setError(null)
    setFeedback(null)
    setGrounding(null)
    setAnswerInput('')
    try {
      const focus = focusInput.trim()
      const response = await postPracticeQuestion({
        mode: 'interview',
        question_kind: kind,
        context: focus ? { focus } : {},
        conversation_id: conversationId,
      })
      setConversationId(response.conversation_id)
      setAttemptId(response.attempt_id)
      setQuestion(response.question)
      setQuestionKind(response.question_kind)
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
    if (attempt.question_kind) setKind(attempt.question_kind)
    setAttemptId(attempt.id)
    setQuestion(attempt.question)
    setQuestionKind(attempt.question_kind)
    setFeedback(null)
    setGrounding(null)
    setAnswerInput(attempt.answer ?? '')
    setError(null)
  }

  function startNewSession() {
    setConversationId(null)
    clearQuestion()
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

      <fieldset>
        <legend className="text-xs font-semibold">Question kind</legend>
        <div className="mt-1 flex gap-4">
          <label className="text-sm">
            <input
              type="radio"
              name="question-kind"
              aria-label="Experience"
              checked={kind === 'experience'}
              onChange={() => changeKind('experience')}
              disabled={loading}
              className="mr-1"
            />
            Experience
          </label>
          <label className="text-sm">
            <input
              type="radio"
              name="question-kind"
              aria-label="Technical"
              checked={kind === 'technical'}
              onChange={() => changeKind('technical')}
              disabled={loading}
              className="mr-1"
            />
            Technical
          </label>
        </div>
      </fieldset>

      <div className="flex gap-2">
        <input
          aria-label="Focus (optional)"
          value={focusInput}
          onChange={(e) => setFocusInput(e.target.value)}
          placeholder="Topic or role hint…"
          disabled={loading}
          className="flex-1 rounded border px-3 py-1 text-sm"
        />
        <button
          type="button"
          aria-label="Get question"
          onClick={() => void getQuestion()}
          disabled={loading}
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

      {question && (
        <div aria-label="Question" className="rounded border px-3 py-2">
          {questionKind && (
            <p aria-label="Question kind" className="text-xs font-semibold">
              {questionKind}
            </p>
          )}
          <p className="mt-1 text-sm">{question}</p>
        </div>
      )}

      {question && attemptId && !feedback && (
        <div className="flex gap-2">
          <textarea
            aria-label="Your answer"
            value={answerInput}
            onChange={(e) => setAnswerInput(e.target.value)}
            placeholder="Answer as if in the interview…"
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
            disabled={loading}
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

export default InterviewView
