import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import type { QueryResponse } from '../api/types'
import ChatView from './ChatView'

function queryResponse(overrides: Partial<QueryResponse> = {}): QueryResponse {
  return {
    answer: 'The pipeline uses Modal.',
    citations: [
      { chunk_id: 1, artifact_id: 'a1', span: [0, 24], excerpt: 'The pipeline uses Modal.', source_type: 'note' },
      { chunk_id: 2, artifact_id: 'a1', span: [25, 50], excerpt: 'Volume persists the file.', source_type: 'note' },
    ],
    mode_used: 'evidence',
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

describe('ChatView', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('renders input and disclosure text with no mode select', () => {
    vi.stubGlobal('fetch', mockFetchSequence([]))
    render(<ChatView />)
    expect(screen.getByLabelText('Ask a question')).toBeDefined()
    expect(screen.getByLabelText('Send')).toBeDefined()
    expect(screen.queryByLabelText('Answer mode')).toBeNull()
    expect(screen.getByText('Conversations are saved and retrievable.')).toBeDefined()
  })

  it('sends on submit and renders answer with citation chips', async () => {
    const fetch = mockFetchSequence([queryResponse()])
    vi.stubGlobal('fetch', fetch)
    render(<ChatView />)
    fireEvent.change(screen.getByLabelText('Ask a question'), { target: { value: 'Where?' } })
    fireEvent.click(screen.getByLabelText('Send'))
    expect(await screen.findByText('The pipeline uses Modal.')).toBeDefined()
    expect(screen.getByLabelText('Citation 1')).toBeDefined()
    expect(screen.getByLabelText('Citation 2')).toBeDefined()
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/v1/query')
    expect(JSON.parse(init.body)).toEqual({ question: 'Where?', mode: 'auto', conversation_id: null })
  })

  it('passes the stored conversation_id on the second send', async () => {
    const fetch = mockFetchSequence([queryResponse(), queryResponse({ answer: 'second' })])
    vi.stubGlobal('fetch', fetch)
    render(<ChatView />)
    const input = screen.getByLabelText('Ask a question') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'first?' } })
    fireEvent.click(screen.getByLabelText('Send'))
    await screen.findByText('The pipeline uses Modal.')
    fireEvent.change(input, { target: { value: 'second?' } })
    fireEvent.click(screen.getByLabelText('Send'))
    await screen.findByText('second')
    expect(JSON.parse(fetch.mock.calls[1][1].body).conversation_id).toBe('conv-1')
  })

  it('opens the citation panel with full chunk text on chip click', async () => {
    const fetch = mockFetchSequence([
      queryResponse(),
      { id: 1, artifact_id: 'a1', chunk_idx: 0, span: [0, 24], text: 'FULL chunk body text', source_type: 'note' },
    ])
    vi.stubGlobal('fetch', fetch)
    render(<ChatView />)
    fireEvent.change(screen.getByLabelText('Ask a question'), { target: { value: 'Where?' } })
    fireEvent.click(screen.getByLabelText('Send'))
    await screen.findByText('The pipeline uses Modal.')
    fireEvent.click(screen.getByLabelText('Citation 1'))
    expect(await screen.findByText('FULL chunk body text')).toBeDefined()
    expect(fetch.mock.calls[1][0]).toBe('http://localhost:8000/api/v1/chunks/1')
    fireEvent.click(screen.getByLabelText('Close citation'))
    expect(screen.queryByText('FULL chunk body text')).toBeNull()
  })

  it('shows the error banner and keeps input content on 502', async () => {
    const fetch = mockFetchSequence([{ __notOk: true, __status: 502, __statusText: 'Bad Gateway' }])
    vi.stubGlobal('fetch', fetch)
    render(<ChatView />)
    const input = screen.getByLabelText('Ask a question') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'kept?' } })
    fireEvent.click(screen.getByLabelText('Send'))
    expect(await screen.findByRole('alert')).toBeDefined()
    expect(screen.getByText('API request failed: 502 Bad Gateway')).toBeDefined()
    expect(input.value).toBe('kept?')
  })

  it('badges evidence answers as from your notes', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([queryResponse({ mode_used: 'evidence' })]))
    render(<ChatView />)
    fireEvent.change(screen.getByLabelText('Ask a question'), { target: { value: 'q?' } })
    fireEvent.click(screen.getByLabelText('Send'))
    expect(await screen.findByText('from your notes')).toBeDefined()
  })

  it('badges uncited teaching answers as general explanation', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetchSequence([queryResponse({ mode_used: 'teaching', citations: [] })]),
    )
    render(<ChatView />)
    fireEvent.change(screen.getByLabelText('Ask a question'), { target: { value: 'q?' } })
    fireEvent.click(screen.getByLabelText('Send'))
    expect(await screen.findByText('general explanation')).toBeDefined()
  })

  it('badges cited teaching answers as blended', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([queryResponse({ mode_used: 'teaching' })]))
    render(<ChatView />)
    fireEvent.change(screen.getByLabelText('Ask a question'), { target: { value: 'q?' } })
    fireEvent.click(screen.getByLabelText('Send'))
    expect(await screen.findByText('general explanation + your notes')).toBeDefined()
  })

  it('shows no conversation badge for note citations', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([queryResponse()]))
    render(<ChatView />)
    fireEvent.change(screen.getByLabelText('Ask a question'), { target: { value: 'Where?' } })
    fireEvent.click(screen.getByLabelText('Send'))
    await screen.findByText('The pipeline uses Modal.')
    expect(screen.queryByLabelText('Conversation source')).toBeNull()
  })

  it('badges conversation citations on the chip', async () => {
    const resp = queryResponse({
      citations: [
        { chunk_id: 9, artifact_id: 'conv-art', span: [0, 30], excerpt: 'User: we decided quokka', source_type: 'tb_conversation' },
      ],
    })
    vi.stubGlobal('fetch', mockFetchSequence([resp]))
    render(<ChatView />)
    fireEvent.change(screen.getByLabelText('Ask a question'), { target: { value: 'What?' } })
    fireEvent.click(screen.getByLabelText('Send'))
    await screen.findByText('The pipeline uses Modal.')
    expect(screen.getByLabelText('Conversation source')).toBeDefined()
    expect(screen.getByLabelText('Conversation source').textContent).toContain(
      'from a ThoughtBridge conversation',
    )
  })

  it('badges the citation panel for conversation chunks', async () => {
    const resp = queryResponse({
      citations: [
        { chunk_id: 9, artifact_id: 'conv-art', span: [0, 30], excerpt: 'User: we decided quokka', source_type: 'tb_conversation' },
      ],
    })
    vi.stubGlobal(
      'fetch',
      mockFetchSequence([
        resp,
        { id: 9, artifact_id: 'conv-art', chunk_idx: 0, span: [0, 30], text: 'User: we decided quokka', source_type: 'tb_conversation' },
      ]),
    )
    render(<ChatView />)
    fireEvent.change(screen.getByLabelText('Ask a question'), { target: { value: 'What?' } })
    fireEvent.click(screen.getByLabelText('Send'))
    await screen.findByText('The pipeline uses Modal.')
    fireEvent.click(screen.getByLabelText('Citation 9'))
    expect(await screen.findByText('User: we decided quokka')).toBeDefined()
    const badges = screen.getAllByLabelText('Conversation source')
    expect(badges.length).toBe(2)
    expect(badges[1].textContent).toBe('from a ThoughtBridge conversation')
  })
})
