import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import type { ExplainResponse, ExplanationDetail, QueryResponse } from '../api/types'
import LearnView from './LearnView'

const STEPS = {
  definition: 'DEF',
  familiar_system: 'FAM',
  analogy: 'ANA',
  mapping: [
    'The librarian finds things just as the retriever finds passages.',
    'Shelves store things just as the index stores embeddings.',
  ],
  walkthrough: 'WALK',
  placement: 'PLACE',
  interview_ready: 'READY',
  limitations: 'LIMITS',
}

function explainResponse(overrides: Partial<ExplainResponse> = {}): ExplainResponse {
  return {
    explanation_id: 'exp-1',
    reused_from: null,
    steps: STEPS,
    ...overrides,
  }
}

function explanationDetail(overrides: Partial<ExplanationDetail> = {}): ExplanationDetail {
  return {
    id: 'exp-1',
    concept: 'RAG',
    version: 1,
    steps: STEPS,
    mapping: STEPS.mapping,
    limitations: 'LIMITS',
    reused_from: null,
    created_at: 't',
    ...overrides,
  }
}

function queryResponse(overrides: Partial<QueryResponse> = {}): QueryResponse {
  return {
    answer: 'Because librarians retrieve.',
    citations: [],
    mode_used: 'teaching',
    conversation_id: 'conv-1',
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

async function teach(fetch: ReturnType<typeof mockFetchSequence>, concept = 'RAG') {
  render(<LearnView />)
  fireEvent.change(screen.getByLabelText('Concept'), { target: { value: concept } })
  fireEvent.click(screen.getByLabelText('Teach me'))
  await screen.findByText('DEF')
  return fetch
}

describe('LearnView', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('renders the concept form with no stepper initially', () => {
    vi.stubGlobal('fetch', mockFetchSequence([]))
    render(<LearnView />)
    expect(screen.getByLabelText('Concept')).toBeDefined()
    expect(screen.getByLabelText('Familiar system hint (optional)')).toBeDefined()
    expect(screen.getByLabelText('Teach me')).toBeDefined()
    expect(screen.queryByLabelText('Lesson steps')).toBeNull()
    expect(screen.getByText('Lessons are saved and reusable.')).toBeDefined()
  })

  it('teaches via POST-then-GET and shows the header from the GET payload', async () => {
    const fetch = mockFetchSequence([explainResponse(), explanationDetail()])
    vi.stubGlobal('fetch', fetch)
    await teach(fetch)
    expect(screen.getByLabelText('Lesson steps')).toBeDefined()
    expect(screen.getByLabelText('Step: definition')).toBeDefined()
    expect(screen.getByLabelText('Step: limitations')).toBeDefined()
    expect(screen.getByRole('heading').textContent).toContain('RAG v1 explanation')
    expect(fetch.mock.calls.length).toBe(2)
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/learn/explain')
    expect(fetch.mock.calls[1][0]).toBe(
      'http://localhost:8000/api/v1/learn/explanations/exp-1',
    )
  })

  it('moves Next/Back without network calls', async () => {
    const fetch = mockFetchSequence([explainResponse(), explanationDetail()])
    vi.stubGlobal('fetch', fetch)
    await teach(fetch)
    expect(fetch.mock.calls.length).toBe(2)
    fireEvent.click(screen.getByLabelText('Next step'))
    fireEvent.click(screen.getByLabelText('Next step'))
    expect(screen.getByText('ANA')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Previous step'))
    expect(screen.getByText('FAM')).toBeDefined()
    expect(fetch.mock.calls.length).toBe(2)
  })

  it('asks via teaching /query with context and threads the conversation', async () => {
    const fetch = mockFetchSequence([
      explainResponse(),
      explanationDetail(),
      queryResponse(),
      queryResponse({ answer: 'second answer' }),
    ])
    vi.stubGlobal('fetch', fetch)
    await teach(fetch)
    fireEvent.change(screen.getByLabelText('Ask about this step'), {
      target: { value: 'why?' },
    })
    fireEvent.click(screen.getByLabelText('Ask'))
    expect(await screen.findByText('Because librarians retrieve.')).toBeDefined()
    expect(fetch.mock.calls[2][0]).toBe('http://localhost:8000/api/v1/query')
    expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({
      question: 'why?',
      mode: 'teaching',
      context: { explanation_id: 'exp-1' },
      conversation_id: null,
    })
    fireEvent.change(screen.getByLabelText('Ask about this step'), {
      target: { value: 'why again?' },
    })
    fireEvent.click(screen.getByLabelText('Ask'))
    expect(await screen.findByText('second answer')).toBeDefined()
    expect(JSON.parse(fetch.mock.calls[3][1].body).conversation_id).toBe('conv-1')
  })

  it('regenerates via POST-then-GET, keeping position', async () => {
    const v2Steps = { ...STEPS, analogy: 'ANA2' }
    const fetch = mockFetchSequence([
      explainResponse(),
      explanationDetail(),
      explainResponse({ explanation_id: 'exp-2' }),
      explanationDetail({ id: 'exp-2', version: 2, steps: v2Steps }),
    ])
    vi.stubGlobal('fetch', fetch)
    await teach(fetch)
    fireEvent.click(screen.getByLabelText('Step: analogy'))
    expect(screen.getByText('ANA')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Regenerate this step'))
    expect(await screen.findByText('ANA2')).toBeDefined()
    expect(screen.getByRole('heading').textContent).toContain('RAG v2 explanation')
    expect(screen.getByLabelText('Step: analogy').getAttribute('aria-current')).toBe('step')
    expect(fetch.mock.calls[2][0]).toBe(
      'http://localhost:8000/api/v1/learn/explanations/exp-1/regenerate',
    )
    expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({ step: 'analogy' })
    expect(fetch.mock.calls[3][0]).toBe(
      'http://localhost:8000/api/v1/learn/explanations/exp-2',
    )
  })

  it('renders a dismissible alert when teaching fails', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([new Error('boom')]))
    render(<LearnView />)
    fireEvent.change(screen.getByLabelText('Concept'), { target: { value: 'RAG' } })
    fireEvent.click(screen.getByLabelText('Teach me'))
    expect(await screen.findByRole('alert')).toBeDefined()
    expect(screen.getByText('boom')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Dismiss error'))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('renders mapping as conversational passages', async () => {
    const fetch = mockFetchSequence([explainResponse(), explanationDetail()])
    vi.stubGlobal('fetch', fetch)
    await teach(fetch)
    fireEvent.click(screen.getByLabelText('Step: mapping'))
    expect(
      screen.getByText('The librarian finds things just as the retriever finds passages.'),
    ).toBeDefined()
    expect(
      screen.getByText('Shelves store things just as the index stores embeddings.'),
    ).toBeDefined()
  })

  it('renders pre-prose mapping rows best-effort', async () => {
    const legacy = { familiar: 'librarian', technical: 'retriever', note: 'finds things' }
    const fetch = mockFetchSequence([
      explainResponse(),
      explanationDetail({
        steps: { ...STEPS, mapping: [legacy] as unknown as string[] },
      }),
    ])
    vi.stubGlobal('fetch', fetch)
    await teach(fetch)
    fireEvent.click(screen.getByLabelText('Step: mapping'))
    expect(screen.getByText('librarian — retriever: finds things')).toBeDefined()
  })
})
