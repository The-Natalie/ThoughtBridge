import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import type {
  ExplanationSummary,
  PracticeAnswerResponse,
  PracticeAttempt,
  PracticeQuestionResponse,
} from '../api/types'
import PracticeView from './PracticeView'

function explanations(): ExplanationSummary[] {
  return [
    {
      id: 'e1',
      concept: 'RAG',
      version: 2,
      created_at: 't',
      reused_from: null,
      reuse_count: 0,
      marked: false,
      marker_count: 0,
      attempt_count: 0,
    },
  ]
}

function questionResponse(overrides: Partial<PracticeQuestionResponse> = {}): PracticeQuestionResponse {
  return {
    attempt_id: 'a1',
    question: 'Explain RAG as if to an interviewer.',
    question_kind: null,
    reference_kind: 'explanation',
    conversation_id: 'c1',
    ...overrides,
  }
}

function answerResponse(): PracticeAnswerResponse {
  return {
    feedback: {
      correct: ['retrieval first'],
      missing: ['chunking'],
      inaccurate: [],
      terminology: ['say embeddings'],
      next_step: 'Retry the full explanation.',
    },
    grounding: 'general explanation',
  }
}

function attempt(overrides: Partial<PracticeAttempt> & { id: string }): PracticeAttempt {
  return {
    mode: 'learning',
    question_kind: null,
    explanation_id: 'e1',
    concept: 'RAG',
    question: 'Explain RAG?',
    answer: 'thin',
    feedback: null,
    grounding: 'general explanation',
    needs_retry: true,
    created_at: 't',
    ...overrides,
  }
}

function mockFetchSequence(payloads: unknown[]) {
  const queue = [...payloads]
  return vi.fn().mockImplementation(() => {
    const payload = queue.shift()
    if (payload instanceof Error) return Promise.reject(payload)
    return Promise.resolve({
      ok: !(payload as { __notOk?: boolean }).__notOk,
      status: (payload as { __status?: number }).__status ?? 200,
      statusText: (payload as { __statusText?: string }).__statusText ?? 'OK',
      json: async () => payload,
    })
  })
}

describe('PracticeView', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('loads lessons and history on mount', async () => {
    const fetch = mockFetchSequence([explanations(), [attempt({ id: 'h1' })]])
    vi.stubGlobal('fetch', fetch)
    render(<PracticeView />)
    expect(await screen.findByText('RAG (v2)')).toBeDefined()
    expect(screen.getByText('Practice history (1) · Retry queue (1)')).toBeDefined()
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/learn/explanations')
    expect(fetch.mock.calls[1][0]).toBe(
      'http://localhost:8000/api/v1/practice/attempts?mode=learning',
    )
  })

  it('runs question, answer, feedback, and history refresh', async () => {
    const fetch = mockFetchSequence([
      explanations(),
      [],
      questionResponse(),
      answerResponse(),
      [attempt({ id: 'a1', needs_retry: true })],
    ])
    vi.stubGlobal('fetch', fetch)
    render(<PracticeView />)
    fireEvent.change(await screen.findByLabelText('Lesson'), { target: { value: 'e1' } })
    fireEvent.click(screen.getByLabelText('Get question'))
    expect(await screen.findByText('Explain RAG as if to an interviewer.')).toBeDefined()
    const [, questionInit] = fetch.mock.calls[2]
    expect(JSON.parse(questionInit.body)).toEqual({
      mode: 'learning',
      context: { explanation_id: 'e1' },
      conversation_id: null,
    })
    fireEvent.change(screen.getByLabelText('Your answer'), { target: { value: 'RAG fetches.' } })
    fireEvent.click(screen.getByLabelText('Submit answer'))
    expect(await screen.findByText('Retry the full explanation.')).toBeDefined()
    expect(screen.getByLabelText('Grounding').textContent).toBe('general explanation')
    expect(await screen.findByText('Practice history (1) · Retry queue (1)')).toBeDefined()
  })

  it('passes the conversation back on the next question', async () => {
    const fetch = mockFetchSequence([
      explanations(),
      [],
      questionResponse({ conversation_id: 'c9' }),
      answerResponse(),
      [],
      questionResponse({ attempt_id: 'a2', conversation_id: 'c9' }),
    ])
    vi.stubGlobal('fetch', fetch)
    render(<PracticeView />)
    fireEvent.change(await screen.findByLabelText('Lesson'), { target: { value: 'e1' } })
    fireEvent.click(screen.getByLabelText('Get question'))
    fireEvent.change(await screen.findByLabelText('Your answer'), { target: { value: 'x' } })
    fireEvent.click(screen.getByLabelText('Submit answer'))
    fireEvent.click(await screen.findByLabelText('Next question'))
    await screen.findByLabelText('Your answer')
    const lastBody = JSON.parse(fetch.mock.calls[fetch.mock.calls.length - 1][1].body)
    expect(lastBody.conversation_id).toBe('c9')
  })

  it('retry loads the prior question for re-answer', async () => {
    const prior = attempt({ id: 'old', question: 'Old question?', answer: 'old answer' })
    const fetch = mockFetchSequence([explanations(), [prior]])
    vi.stubGlobal('fetch', fetch)
    render(<PracticeView />)
    fireEvent.click(await screen.findByLabelText('Retry old'))
    expect(screen.getByLabelText('Question').textContent).toContain('Old question?')
    expect((screen.getByLabelText('Your answer') as HTMLTextAreaElement).value).toBe('old answer')
  })

  it('new session clears the loop but keeps history', async () => {
    const fetch = mockFetchSequence([explanations(), [attempt({ id: 'h1' })], questionResponse()])
    vi.stubGlobal('fetch', fetch)
    render(<PracticeView />)
    fireEvent.change(await screen.findByLabelText('Lesson'), { target: { value: 'e1' } })
    fireEvent.click(screen.getByLabelText('Get question'))
    await screen.findByLabelText('Question')
    fireEvent.click(screen.getByLabelText('Start new session'))
    expect(screen.queryByLabelText('Question')).toBeNull()
    expect(screen.getByText('Practice history (1) · Retry queue (1)')).toBeDefined()
  })

  it('disables Get question with an empty-lessons hint', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([[], []]))
    render(<PracticeView />)
    expect(await screen.findByText(/No lessons yet/)).toBeDefined()
    expect((screen.getByLabelText('Get question') as HTMLButtonElement).disabled).toBe(true)
  })

  it('shows and dismisses errors', async () => {
    const fetch = mockFetchSequence([explanations(), [], new Error('boom')])
    vi.stubGlobal('fetch', fetch)
    render(<PracticeView />)
    expect(await screen.findByText('RAG (v2)')).toBeDefined()
    fireEvent.change(screen.getByLabelText('Lesson'), { target: { value: 'e1' } })
    fireEvent.click(screen.getByLabelText('Get question'))
    expect(await screen.findByText('boom')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Dismiss error'))
    expect(screen.queryByText('boom')).toBeNull()
  })

  it('renders the disclosure line', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([[], []]))
    render(<PracticeView />)
    expect(await screen.findByText('Conversations are saved and retrievable.')).toBeDefined()
  })
})
