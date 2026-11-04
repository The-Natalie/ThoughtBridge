import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'

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
    const streamed = (payload as { __stream?: unknown[] }).__stream
    if (streamed !== undefined) return Promise.resolve(streamResponse(streamed))
    return Promise.resolve({
      ok: !(payload as { __notOk?: boolean }).__notOk,
      status: (payload as { __status?: number }).__status ?? 200,
      statusText: (payload as { __statusText?: string }).__statusText ?? 'OK',
      json: async () => payload,
    })
  })
}

function streamResponse(events: unknown[]) {
  const text = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('') + 'data: [DONE]\n\n'
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    json: async () => ({}),
    body: new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(text))
        controller.close()
      },
    }),
  }
}

function streamEvents(
  overrides: { explanation_id?: string; reused_from?: string | null } = {},
) {
  return [
    { type: 'stage_started', stage: 'D' },
    { type: 'stage_validated', stage: 'D', steps: { definition: 'DEF' } },
    { type: 'stage_validated', stage: 'F', steps: { familiar_system: 'FAM' } },
    {
      type: 'stage_validated',
      stage: 'B',
      steps: { analogy: 'ANA', mapping: STEPS.mapping, walkthrough: 'WALK' },
    },
    {
      type: 'stage_validated',
      stage: 'C',
      steps: { placement: 'PLACE', interview_ready: 'READY' },
    },
    {
      type: 'lesson_complete',
      explanation_id: overrides.explanation_id ?? 'exp-1',
      reused_from: overrides.reused_from ?? null,
    },
  ]
}

function teachStream(overrides: { explanation_id?: string; reused_from?: string | null } = {}) {
  return { __stream: streamEvents(overrides) }
}

async function teach(fetch: ReturnType<typeof mockFetchSequence>, concept = 'RAG') {
  render(<LearnView />)
  fireEvent.change(screen.getByLabelText('Concept'), { target: { value: concept } })
  fireEvent.click(screen.getByLabelText('Teach me'))
  // The ask box only renders once the completed explanation has loaded,
  // so this also waits out the mid-generation pager.
  await screen.findByLabelText('Ask about this step')
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

  it('teaches via stream-then-GET and shows the header from the GET payload', async () => {
    const fetch = mockFetchSequence([teachStream(), explanationDetail()])
    vi.stubGlobal('fetch', fetch)
    await teach(fetch)
    expect(screen.getByLabelText('Lesson steps')).toBeDefined()
    expect(screen.getByLabelText('Step: definition')).toBeDefined()
    expect(screen.getByLabelText('Step: interview_ready')).toBeDefined()
    expect(screen.queryByLabelText('Step: limitations')).toBeNull()
    expect(screen.getByRole('heading').textContent).toContain('RAG v1 explanation')
    expect(fetch.mock.calls.length).toBe(2)
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/learn/explain/stream')
    expect(fetch.mock.calls[0][1].method).toBe('POST')
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ concept: 'RAG' })
    expect(fetch.mock.calls[1][0]).toBe(
      'http://localhost:8000/api/v1/learn/explanations/exp-1',
    )
  })

  it('moves Next/Back without network calls', async () => {
    const fetch = mockFetchSequence([teachStream(), explanationDetail()])
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
      teachStream(),
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
      teachStream(),
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
    expect(screen.getByLabelText('Teach me')).toBeDefined()
    expect(screen.queryByLabelText('Lesson steps')).toBeNull()
  })

  it('renders mapping as conversational passages', async () => {
    const fetch = mockFetchSequence([teachStream(), explanationDetail()])
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
      teachStream(),
      explanationDetail({
        steps: { ...STEPS, mapping: [legacy] as unknown as string[] },
      }),
    ])
    vi.stubGlobal('fetch', fetch)
    await teach(fetch)
    fireEvent.click(screen.getByLabelText('Step: mapping'))
    expect(screen.getByText('librarian — retriever: finds things')).toBeDefined()
  })

  it('marks the whole explanation as clicked with an optional note', async () => {
    const fetch = mockFetchSequence([
      teachStream(),
      explanationDetail(),
      { marker_id: 'm-1', explanation_id: 'exp-1', scope: 'explanation', step: null },
    ])
    vi.stubGlobal('fetch', fetch)
    await teach(fetch)
    fireEvent.change(screen.getByLabelText('What clicked (optional note)'), {
      target: { value: 'librarian clicked' },
    })
    fireEvent.click(screen.getByLabelText('Mark whole explanation as clicked'))
    expect(await screen.findByText('Clicked ✓')).toBeDefined()
    const [url, init] = fetch.mock.calls[2]
    expect(url).toBe('http://localhost:8000/api/v1/learn/explanations/exp-1/markers')
    expect(JSON.parse(init.body)).toEqual({
      scope: 'explanation',
      step: null,
      note: 'librarian clicked',
    })
    expect(
      (screen.getByLabelText('Mark whole explanation as clicked') as HTMLButtonElement)
        .disabled,
    ).toBe(true)
  })

  it('marks the current step as clicked without a note key when empty', async () => {
    const fetch = mockFetchSequence([teachStream(), explanationDetail(), { marker_id: 'm-2' }])
    vi.stubGlobal('fetch', fetch)
    await teach(fetch)
    fireEvent.click(screen.getByLabelText('Step: mapping'))
    fireEvent.click(screen.getByLabelText('Mark this step as clicked'))
    expect(await screen.findByText('Clicked ✓')).toBeDefined()
    const [url, init] = fetch.mock.calls[2]
    expect(url).toBe('http://localhost:8000/api/v1/learn/explanations/exp-1/markers')
    expect(JSON.parse(init.body)).toEqual({ scope: 'step', step: 'mapping' })
    fireEvent.click(screen.getByLabelText('Step: definition'))
    expect(screen.getByLabelText('Mark this step as clicked').textContent).toBe(
      'This step clicked',
    )
  })

  it('shows a clicked-before notice with view-prior when reusing a marked explanation', async () => {
    const fetch = mockFetchSequence([
      teachStream({ explanation_id: 'exp-2', reused_from: 'exp-0' }),
      explanationDetail({ id: 'exp-2', version: 2 }),
      explanationDetail({ id: 'exp-0', version: 1 }),
      [
        {
          id: 'm-0',
          explanation_id: 'exp-0',
          scope: 'explanation',
          step: null,
          note: '',
          created_at: 't',
        },
      ],
      explanationDetail({
        id: 'exp-0',
        version: 1,
        steps: { ...STEPS, definition: 'PRIOR-DEF' },
      }),
    ])
    vi.stubGlobal('fetch', fetch)
    await teach(fetch)
    expect(await screen.findByLabelText('Reuse notice')).toBeDefined()
    expect(
      screen.getByText('This builds on an explanation that clicked for you before.'),
    ).toBeDefined()
    fireEvent.click(screen.getByLabelText('View prior explanation'))
    expect(fetch.mock.calls[4][0]).toBe(
      'http://localhost:8000/api/v1/learn/explanations/exp-0',
    )
    expect(await screen.findByText('PRIOR-DEF')).toBeDefined()
  })

  it('shows a plain reuse notice when the prior explanation is unmarked', async () => {
    const fetch = mockFetchSequence([
      teachStream({ explanation_id: 'exp-2', reused_from: 'exp-0' }),
      explanationDetail({ id: 'exp-2', version: 2 }),
      explanationDetail({ id: 'exp-0', version: 1 }),
      [],
    ])
    vi.stubGlobal('fetch', fetch)
    await teach(fetch)
    const notice = await screen.findByLabelText('Reuse notice')
    expect(notice.textContent).toContain('This builds on your earlier explanation.')
    expect(notice.textContent).not.toContain('clicked for you before')
  })

  it('toggles earlier versions with marked badges and loads on click', async () => {
    const history = [
      {
        id: 'exp-2',
        concept: 'RAG',
        version: 2,
        created_at: 't2',
        reused_from: 'exp-1',
        reuse_count: 0,
        marked: false,
        marker_count: 0,
        attempt_count: 0,
      },
      {
        id: 'exp-1',
        concept: 'RAG',
        version: 1,
        created_at: 't1',
        reused_from: null,
        reuse_count: 1,
        marked: true,
        marker_count: 1,
        attempt_count: 0,
      },
    ]
    const fetch = mockFetchSequence([
      teachStream({ explanation_id: 'exp-2' }),
      explanationDetail({ id: 'exp-2', version: 2 }),
      history,
      explanationDetail({ id: 'exp-1', version: 1, steps: { ...STEPS, definition: 'V1-DEF' } }),
    ])
    vi.stubGlobal('fetch', fetch)
    await teach(fetch)
    fireEvent.click(screen.getByLabelText('Show earlier versions'))
    expect(await screen.findByLabelText('Earlier versions')).toBeDefined()
    expect(fetch.mock.calls[2][0]).toBe(
      'http://localhost:8000/api/v1/learn/explanations?concept=RAG',
    )
    expect(screen.getByLabelText('Load version 1').textContent).toContain('✓')
    expect(screen.getByLabelText('Load version 2').textContent).not.toContain('✓')
    fireEvent.click(screen.getByLabelText('Load version 1'))
    expect(fetch.mock.calls[3][0]).toBe(
      'http://localhost:8000/api/v1/learn/explanations/exp-1',
    )
    expect(await screen.findByText('V1-DEF')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Hide earlier versions'))
    expect(screen.queryByLabelText('Earlier versions')).toBeNull()
  })

  it('renders a dismissible alert when marking fails', async () => {
    const fetch = mockFetchSequence([
      teachStream(),
      explanationDetail(),
      new Error('mark boom'),
    ])
    vi.stubGlobal('fetch', fetch)
    await teach(fetch)
    fireEvent.click(screen.getByLabelText('Mark whole explanation as clicked'))
    expect(await screen.findByRole('alert')).toBeDefined()
    expect(screen.getByText('mark boom')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Dismiss error'))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('shows the pager immediately and streams each tab as it validates', async () => {
    let controller!: ReadableStreamDefaultController<Uint8Array>
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        controller = c
      },
    })
    const send = (text: string) => controller.enqueue(new TextEncoder().encode(text))
    const event = (e: unknown) => `data: ${JSON.stringify(e)}\n\n`
    // Stream URL is intercepted below with the manually-driven body; the queue
    // holds only the follow-up GET payloads.
    const fetch = mockFetchSequence([explanationDetail()])
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (url.endsWith('/learn/explain/stream')) {
          return Promise.resolve({ ok: true, status: 200, statusText: 'OK', body })
        }
        return fetch(url)
      }),
    )
    render(<LearnView />)
    fireEvent.change(screen.getByLabelText('Concept'), { target: { value: 'RAG' } })
    fireEvent.click(screen.getByLabelText('Teach me'))
    // Pager appears immediately with Definition selected and loading.
    expect(await screen.findByLabelText('Lesson steps')).toBeDefined()
    expect(screen.getByLabelText('Step: definition').getAttribute('aria-current')).toBe('step')
    expect(screen.getByRole('heading').textContent).toContain('RAG (generating…)')
    expect(screen.getByRole('status').textContent).toBe('Loading…')
    // Unready tabs show the same loader; actions wait for completion.
    fireEvent.click(screen.getByLabelText('Step: familiar_system'))
    expect(screen.getByRole('status').textContent).toBe('Loading…')
    expect(screen.queryByLabelText('Ask about this step')).toBeNull()
    expect(screen.queryByLabelText('Show earlier versions')).toBeNull()
    fireEvent.click(screen.getByLabelText('Step: definition'))
    // Definition tokens stream into the Definition tab.
    send(event({ type: 'stage_started', stage: 'D' }))
    send(event({ type: 'token', stage: 'D', text: '{"definition": "PARTIAL' }))
    expect(await screen.findByText('PARTIAL')).toBeDefined()
    // Validated stages replace tokens and fill their own tabs.
    send(event({ type: 'stage_validated', stage: 'D', steps: { definition: 'FULL-DEF' } }))
    expect(await screen.findByText('FULL-DEF')).toBeDefined()
    expect(screen.queryByText('PARTIAL')).toBeNull()
    fireEvent.click(screen.getByLabelText('Step: familiar_system'))
    expect(screen.getByRole('status').textContent).toBe('Loading…')
    send(event({ type: 'stage_validated', stage: 'F', steps: { familiar_system: 'FAM' } }))
    expect(await screen.findByText('FAM')).toBeDefined()
    send(
      event({
        type: 'stage_validated',
        stage: 'B',
        steps: { analogy: 'ANA', mapping: STEPS.mapping, walkthrough: 'WALK' },
      }),
    )
    send(
      event({
        type: 'stage_validated',
        stage: 'C',
        steps: { placement: 'PLACE', interview_ready: 'READY' },
      }),
    )
    send(event({ type: 'lesson_complete', explanation_id: 'exp-1', reused_from: null }))
    send('data: [DONE]\n\n')
    controller.close()
    // Completion swaps in the persisted payload with actions, no loaders.
    expect(await screen.findByLabelText('Ask about this step')).toBeDefined()
    expect(screen.getByRole('heading').textContent).toContain('RAG v1 explanation')
    expect(screen.getByText('DEF')).toBeDefined()
    expect(screen.queryByText('Loading…')).toBeNull()
    expect(screen.queryByText('FULL-DEF')).toBeNull()
  })

  it('cancels a generation in flight when starting over', async () => {
    let controller!: ReadableStreamDefaultController<Uint8Array>
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        controller = c
      },
    })
    const send = (text: string) => controller.enqueue(new TextEncoder().encode(text))
    const event = (e: unknown) => `data: ${JSON.stringify(e)}\n\n`
    const fetch = mockFetchSequence([explanationDetail()])
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (url.endsWith('/learn/explain/stream')) {
          return Promise.resolve({ ok: true, status: 200, statusText: 'OK', body })
        }
        return fetch(url)
      }),
    )
    render(<LearnView />)
    fireEvent.change(screen.getByLabelText('Concept'), { target: { value: 'RAG' } })
    fireEvent.click(screen.getByLabelText('Teach me'))
    expect(await screen.findByLabelText('Lesson steps')).toBeDefined()
    send(event({ type: 'token', stage: 'D', text: '{"definition": "PARTIAL' }))
    expect(await screen.findByText('PARTIAL')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Start over'))
    expect(screen.getByLabelText('Teach me')).toBeDefined()
    expect(screen.queryByLabelText('Lesson steps')).toBeNull()
    // Late stream events from the abandoned generation are ignored.
    send(event({ type: 'lesson_complete', explanation_id: 'exp-1', reused_from: null }))
    send('data: [DONE]\n\n')
    controller.close()
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0))
    })
    expect(screen.queryByLabelText('Lesson steps')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('shows a dismissible alert when the stream emits an error event', async () => {
    const fetch = mockFetchSequence([
      {
        __stream: [
          { type: 'stage_started', stage: 'D' },
          { type: 'error', stage: 'D', message: 'stream boom' },
        ],
      },
      explanationDetail(),
    ])
    vi.stubGlobal('fetch', fetch)
    render(<LearnView />)
    fireEvent.change(screen.getByLabelText('Concept'), { target: { value: 'RAG' } })
    fireEvent.click(screen.getByLabelText('Teach me'))
    expect(await screen.findByRole('alert')).toBeDefined()
    expect(screen.getByText('stream boom')).toBeDefined()
    expect(screen.getByLabelText('Teach me')).toBeDefined()
    expect(screen.queryByLabelText('Lesson steps')).toBeNull()
  })

  it('discloses that conversations are saved and retrievable', () => {
    vi.stubGlobal('fetch', mockFetchSequence([]))
    render(<LearnView />)
    expect(screen.getByText('Conversations are saved and retrievable.')).toBeDefined()
  })

  it('shows a grounding badge on uncited interrupt answers', async () => {
    const fetch = mockFetchSequence([teachStream(), explanationDetail(), queryResponse()])
    vi.stubGlobal('fetch', fetch)
    await teach(fetch)
    fireEvent.change(screen.getByLabelText('Ask about this step'), { target: { value: 'why?' } })
    fireEvent.click(screen.getByLabelText('Ask'))
    expect(await screen.findByText('Because librarians retrieve.')).toBeDefined()
    expect(screen.getByLabelText('Grounding').textContent).toBe('general explanation')
    expect(screen.queryByLabelText(/Citation /)).toBeNull()
  })

  it('opens the chunk panel from an interrupt citation chip', async () => {
    const fetch = mockFetchSequence([
      teachStream(),
      explanationDetail(),
      queryResponse({
        citations: [
          { chunk_id: 3, artifact_id: 'a1', span: [0, 10], excerpt: 'Librarians retrieve things.', source_type: 'note' },
        ],
      }),
      { id: 3, artifact_id: 'a1', chunk_idx: 0, span: [0, 10], text: 'FULL interrupt chunk text', source_type: 'note' },
    ])
    vi.stubGlobal('fetch', fetch)
    await teach(fetch)
    fireEvent.change(screen.getByLabelText('Ask about this step'), { target: { value: 'why?' } })
    fireEvent.click(screen.getByLabelText('Ask'))
    expect(await screen.findByText('Because librarians retrieve.')).toBeDefined()
    expect(screen.getByLabelText('Grounding').textContent).toBe('both')
    fireEvent.click(screen.getByLabelText('Citation 3'))
    expect(await screen.findByText('FULL interrupt chunk text')).toBeDefined()
    expect(fetch.mock.calls[3][0]).toBe('http://localhost:8000/api/v1/chunks/3')
  })
})
