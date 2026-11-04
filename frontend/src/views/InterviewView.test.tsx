import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import type {
  PracticeAnswerResponse,
  PracticeAttempt,
  PracticeQuestionResponse,
} from '../api/types'
import InterviewView from './InterviewView'

function questionResponse(overrides: Partial<PracticeQuestionResponse> = {}): PracticeQuestionResponse {
  return {
    attempt_id: 'a1',
    question: 'Tell me about a difficult bug you solved.',
    question_kind: 'experience',
    reference_kind: 'facts',
    conversation_id: 'c1',
    ...overrides,
  }
}

function answerResponse(): PracticeAnswerResponse {
  return {
    feedback: {
      correct: ['described the fix'],
      missing: ['the tradeoff'],
      inaccurate: [],
      terminology: [],
      next_step: 'Name the tradeoff next time.',
    },
    grounding: 'from your notes',
  }
}

function attempt(overrides: Partial<PracticeAttempt> & { id: string }): PracticeAttempt {
  return {
    mode: 'interview',
    question_kind: 'experience',
    explanation_id: null,
    concept: null,
    question: 'Tell me about a bug?',
    answer: 'thin',
    feedback: null,
    grounding: 'from your notes',
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

describe('InterviewView', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('loads interview history on mount with experience default', async () => {
    const fetch = mockFetchSequence([[attempt({ id: 'h1' })]])
    vi.stubGlobal('fetch', fetch)
    render(<InterviewView />)
    expect(await screen.findByText('Practice history (1) · Retry queue (1)')).toBeDefined()
    expect(fetch.mock.calls[0][0]).toBe(
      'http://localhost:8000/api/v1/practice/attempts?mode=interview',
    )
    expect((screen.getByLabelText('Experience') as HTMLInputElement).checked).toBe(true)
  })

  it('runs the default-kind flow with empty focus omitted', async () => {
    const fetch = mockFetchSequence([
      [],
      questionResponse(),
      answerResponse(),
      [attempt({ id: 'a1' })],
    ])
    vi.stubGlobal('fetch', fetch)
    render(<InterviewView />)
    await screen.findByText('Practice history (0) · Retry queue (0)')
    fireEvent.click(screen.getByLabelText('Get question'))
    expect(await screen.findByText('Tell me about a difficult bug you solved.')).toBeDefined()
    expect(screen.getByLabelText('Question kind').textContent).toBe('experience')
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({
      mode: 'interview',
      question_kind: 'experience',
      context: {},
      conversation_id: null,
    })
    fireEvent.change(screen.getByLabelText('Your answer'), { target: { value: 'I fixed it.' } })
    fireEvent.click(screen.getByLabelText('Submit answer'))
    expect(await screen.findByText('Name the tradeoff next time.')).toBeDefined()
    expect(screen.getByLabelText('Grounding').textContent).toBe('from your notes')
  })

  it('kind switch changes the request body and clears stale questions', async () => {
    const fetch = mockFetchSequence([
      [],
      questionResponse(),
      questionResponse({
        attempt_id: 'a2',
        question: 'How do embeddings work?',
        question_kind: 'technical',
        reference_kind: 'general',
      }),
    ])
    vi.stubGlobal('fetch', fetch)
    render(<InterviewView />)
    await screen.findByText('Practice history (0) · Retry queue (0)')
    fireEvent.click(screen.getByLabelText('Get question'))
    await screen.findByText('Tell me about a difficult bug you solved.')
    fireEvent.click(screen.getByLabelText('Technical'))
    expect(screen.queryByLabelText('Question')).toBeNull()
    fireEvent.change(screen.getByLabelText('Focus (optional)'), { target: { value: 'APIs' } })
    fireEvent.click(screen.getByLabelText('Get question'))
    expect(await screen.findByText('How do embeddings work?')).toBeDefined()
    expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({
      mode: 'interview',
      question_kind: 'technical',
      context: { focus: 'APIs' },
      conversation_id: 'c1',
    })
  })

  it('retry loads the prior question and syncs the kind radio', async () => {
    const prior = attempt({
      id: 'old',
      question: 'Old technical Q?',
      question_kind: 'technical',
      answer: 'old answer',
    })
    vi.stubGlobal('fetch', mockFetchSequence([[prior]]))
    render(<InterviewView />)
    fireEvent.click(await screen.findByLabelText('Retry old'))
    expect(screen.getByLabelText('Question').textContent).toContain('Old technical Q?')
    expect((screen.getByLabelText('Technical') as HTMLInputElement).checked).toBe(true)
  })

  it('shows and dismisses errors', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([[], new Error('boom')]))
    render(<InterviewView />)
    await screen.findByText('Practice history (0) · Retry queue (0)')
    fireEvent.click(screen.getByLabelText('Get question'))
    expect(await screen.findByText('boom')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Dismiss error'))
    expect(screen.queryByText('boom')).toBeNull()
  })

  it('renders the disclosure line', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([[]]))
    render(<InterviewView />)
    expect(await screen.findByText('Conversations are saved and retrievable.')).toBeDefined()
  })
})
