import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'

import type {
  ArtifactSummary,
  ChunkDetail,
  ExtractFact,
  ExtractResponse,
} from '../api/types'
import WorkView from './WorkView'

function artifactSummary(overrides: Partial<ArtifactSummary> = {}): ArtifactSummary {
  return {
    id: 'art-1',
    title: 'Dev log',
    source_type: 'note',
    created_at: 't',
    chunk_count: 2,
    fact_count: 0,
    ...overrides,
  }
}

function extractFact(overrides: Partial<ExtractFact> = {}): ExtractFact {
  return {
    fact_id: 'f'.repeat(32),
    kind: 'accomplishment',
    status: 'completed',
    summary: 'Did the thing.',
    skills: ['python'],
    confidence: 0.9,
    chunk_ids: [7],
    links: [],
    ...overrides,
  }
}

function threeFacts(): ExtractFact[] {
  return [
    extractFact({ fact_id: 'a'.repeat(32), status: 'proposed', summary: 'Might do X.' }),
    extractFact({ fact_id: 'b'.repeat(32), status: 'rejected', summary: 'Rejected Y.' }),
    extractFact({
      fact_id: 'c'.repeat(32),
      status: 'completed',
      summary: 'Shipped Z.',
      links: [{ to_fact: 'b'.repeat(32), relation: 'decided' }],
    }),
  ]
}

function extractResponse(overrides: Partial<ExtractResponse> = {}): ExtractResponse {
  return { facts: threeFacts(), ...overrides }
}

function chunkDetail(overrides: Partial<ChunkDetail> = {}): ChunkDetail {
  return {
    id: 7,
    artifact_id: 'art-1',
    chunk_idx: 0,
    span: [0, 10],
    text: 'full chunk text here',
    source_type: 'note',
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

async function extractWith(factsPayloads: unknown[], artifactsPayload: unknown = [artifactSummary()]) {
  // Mount fires two GETs (artifacts, then accomplishments); callers append [] after each extract POST.
  const fetch = mockFetchSequence([artifactsPayload, [], ...factsPayloads])
  vi.stubGlobal('fetch', fetch)
  render(<WorkView />)
  expect(await screen.findByLabelText('Select artifact Dev log')).toBeDefined()
  fireEvent.click(screen.getByLabelText('Select artifact Dev log'))
  fireEvent.click(screen.getByLabelText('Extract'))
  return fetch
}

describe('WorkView', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('mount lists artifacts with checkboxes', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetchSequence([[artifactSummary(), artifactSummary({ id: 'art-2', title: 'Log 2' })], []]),
    )
    render(<WorkView />)
    expect(await screen.findByLabelText('Select artifact Dev log')).toBeDefined()
    expect(screen.getByLabelText('Select artifact Log 2')).toBeDefined()
    expect(screen.getByText(/Dev log/)).toBeDefined()
  })

  it('extract is disabled with none selected', () => {
    vi.stubGlobal('fetch', mockFetchSequence([[artifactSummary()], []]))
    render(<WorkView />)
    expect((screen.getByLabelText('Extract') as HTMLButtonElement).disabled).toBe(true)
  })

  it('select two and Extract POSTs sorted ids and renders fact cards', async () => {
    const fetch = mockFetchSequence([
      [artifactSummary({ id: 'b-id', title: 'Log B' }), artifactSummary({ id: 'a-id', title: 'Log A' })],
      [],
      extractResponse(),
      [],
    ])
    vi.stubGlobal('fetch', fetch)
    render(<WorkView />)
    expect(await screen.findByLabelText('Select artifact Log B')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Select artifact Log B'))
    fireEvent.click(screen.getByLabelText('Select artifact Log A'))
    fireEvent.click(screen.getByLabelText('Extract'))
    expect(await screen.findByText('Might do X.')).toBeDefined()
    expect(screen.getByText('Rejected Y.')).toBeDefined()
    expect(screen.getByText('Shipped Z.')).toBeDefined()
    expect(fetch.mock.calls[2][0]).toBe('http://localhost:8000/api/v1/work/extract')
    expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({ artifact_ids: ['a-id', 'b-id'] })
  })

  it('status filter chips narrow the cards without refetching', async () => {
    const fetch = await extractWith([extractResponse(), []])
    expect(await screen.findByText('Might do X.')).toBeDefined()
    expect(fetch.mock.calls.length).toBe(4)
    fireEvent.click(screen.getByLabelText('Filter: completed'))
    expect(screen.queryByText('Might do X.')).toBeNull()
    expect(screen.getByText('Shipped Z.')).toBeDefined()
    expect(screen.getAllByLabelText(/^Fact /).length).toBe(1)
    fireEvent.click(screen.getByLabelText('Filter: all'))
    expect(screen.getAllByLabelText(/^Fact /).length).toBe(3)
    expect(fetch.mock.calls.length).toBe(4)
  })

  it('evidence chip opens the chunk panel and Close dismisses it', async () => {
    await extractWith([extractResponse(), [], chunkDetail()])
    expect(await screen.findByText('Might do X.')).toBeDefined()
    fireEvent.click(screen.getAllByLabelText('Evidence chunk 7')[0])
    expect(await screen.findByText('full chunk text here')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Close citation'))
    expect(screen.queryByText('full chunk text here')).toBeNull()
  })

  it('reasoning-link click highlights the target card', async () => {
    await extractWith([extractResponse(), []])
    expect(await screen.findByText('Shipped Z.')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Reasoning link decided to bbbbbbbb'))
    const target = screen.getByLabelText('Fact bbbbbbbb')
    expect(target.className).toContain('ring-2')
  })

  it('empty facts result shows the status line and no error', async () => {
    await extractWith([extractResponse({ facts: [] }), []])
    expect(
      await screen.findByText('Nothing extractable found in the selected artifacts.'),
    ).toBeDefined()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('failed extract shows a dismissible alert', async () => {
    await extractWith([new Error('boom')])
    expect(await screen.findByRole('alert')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Dismiss error'))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('empty artifact list shows the capture-first hint', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([[], []]))
    render(<WorkView />)
    expect(await screen.findByText('No artifacts yet — capture notes first.')).toBeDefined()
  })

  it('zero-match filter shows the status line with no cards and no error', async () => {
    const completedOnly = extractResponse({
      facts: [extractFact({ fact_id: 'c'.repeat(32), status: 'completed', summary: 'Done.' })],
    })
    await extractWith([completedOnly, []])
    expect(await screen.findByText('Done.')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Filter: proposed'))
    expect(screen.getByText('No facts with this status.')).toBeDefined()
    expect(screen.queryAllByLabelText(/^Fact /).length).toBe(0)
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('mount fetches accomplishments bare and renders browser cards', async () => {
    const saved = [
      extractFact({ fact_id: 'd'.repeat(32), summary: 'Browser fact one.' }),
      extractFact({ fact_id: 'e'.repeat(32), summary: 'Browser fact two.' }),
    ]
    const fetch = mockFetchSequence([[artifactSummary()], saved])
    vi.stubGlobal('fetch', fetch)
    render(<WorkView />)
    expect(await screen.findByText('Browser fact one.')).toBeDefined()
    const browser = screen.getByLabelText('Saved accomplishments')
    expect(within(browser).getByText('Browser fact two.')).toBeDefined()
    expect(fetch.mock.calls[1][0]).toBe('http://localhost:8000/api/v1/work/accomplishments')
  })

  it('keyword search GETs encoded q and re-renders', async () => {
    const fetch = mockFetchSequence([
      [artifactSummary()],
      [extractFact({ fact_id: 'd'.repeat(32), summary: 'Browser fact one.' })],
      [extractFact({ fact_id: 'e'.repeat(32), summary: 'Filtered fact.' })],
    ])
    vi.stubGlobal('fetch', fetch)
    render(<WorkView />)
    expect(await screen.findByText('Browser fact one.')).toBeDefined()
    fireEvent.change(screen.getByLabelText('Filter accomplishments by keyword'), {
      target: { value: 'ci/cd' },
    })
    fireEvent.click(screen.getByLabelText('Search accomplishments'))
    expect(await screen.findByText('Filtered fact.')).toBeDefined()
    expect(screen.queryByText('Browser fact one.')).toBeNull()
    expect(fetch.mock.calls[2][0]).toBe(
      'http://localhost:8000/api/v1/work/accomplishments?q=ci%2Fcd',
    )
  })

  it('skill search GETs the skill param', async () => {
    const fetch = mockFetchSequence([
      [artifactSummary()],
      [extractFact({ fact_id: 'd'.repeat(32), summary: 'Browser fact one.' })],
      [extractFact({ fact_id: 'e'.repeat(32), summary: 'Skilled fact.' })],
    ])
    vi.stubGlobal('fetch', fetch)
    render(<WorkView />)
    expect(await screen.findByText('Browser fact one.')).toBeDefined()
    fireEvent.change(screen.getByLabelText('Filter accomplishments by skill'), {
      target: { value: 'writing' },
    })
    fireEvent.click(screen.getByLabelText('Search accomplishments'))
    expect(await screen.findByText('Skilled fact.')).toBeDefined()
    expect(fetch.mock.calls[2][0]).toBe(
      'http://localhost:8000/api/v1/work/accomplishments?skill=writing',
    )
  })

  it('unfiltered empty browser shows the run-extract hint', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([[artifactSummary()], []]))
    render(<WorkView />)
    expect(
      await screen.findByText('No saved accomplishments yet — run Extract first.'),
    ).toBeDefined()
  })

  it('filtered empty browser shows the no-match line', async () => {
    const fetch = mockFetchSequence([
      [artifactSummary()],
      [extractFact({ fact_id: 'd'.repeat(32), summary: 'Browser fact one.' })],
      [],
    ])
    vi.stubGlobal('fetch', fetch)
    render(<WorkView />)
    expect(await screen.findByText('Browser fact one.')).toBeDefined()
    fireEvent.change(screen.getByLabelText('Filter accomplishments by keyword'), {
      target: { value: 'nonsense-zzz' },
    })
    fireEvent.click(screen.getByLabelText('Search accomplishments'))
    expect(await screen.findByText('No accomplishments match this filter.')).toBeDefined()
    expect(fetch.mock.calls[2][0]).toBe(
      'http://localhost:8000/api/v1/work/accomplishments?q=nonsense-zzz',
    )
  })

  it('successful extract refetches accomplishments bare', async () => {
    const bare = 'http://localhost:8000/api/v1/work/accomplishments'
    const fetch = await extractWith([extractResponse(), []])
    expect(await screen.findByText('Might do X.')).toBeDefined()
    const bareCalls = fetch.mock.calls.filter((call) => call[0] === bare)
    expect(bareCalls.length).toBe(2)
  })

  it('browser reasoning-link click highlights the acc-prefixed target', async () => {
    const target = extractFact({ fact_id: 'b'.repeat(32), summary: 'Browser target.' })
    const source = extractFact({
      fact_id: 'a'.repeat(32),
      summary: 'Browser source.',
      links: [{ to_fact: 'b'.repeat(32), relation: 'decided' }],
    })
    vi.stubGlobal('fetch', mockFetchSequence([[artifactSummary()], [source, target]]))
    render(<WorkView />)
    expect(await screen.findByText('Browser source.')).toBeDefined()
    const browser = screen.getByLabelText('Saved accomplishments')
    fireEvent.click(within(browser).getByLabelText('Reasoning link decided to bbbbbbbb'))
    const card = within(browser).getByLabelText('Fact bbbbbbbb')
    expect(card.className).toContain('ring-2')
    expect(card.id).toBe(`acc-${'b'.repeat(32)}`)
  })

  it('browser fetch failure surfaces the alert', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([[artifactSummary()], new Error('acc down')]))
    render(<WorkView />)
    expect(await screen.findByRole('alert')).toBeDefined()
    expect(screen.getByText('acc down')).toBeDefined()
  })

  it('discloses that conversations are saved and retrievable', () => {
    vi.stubGlobal('fetch', mockFetchSequence([[artifactSummary()], []]))
    render(<WorkView />)
    expect(screen.getByText('Conversations are saved and retrievable.')).toBeDefined()
  })

  it('citation panel badges conversation chunks', async () => {
    await extractWith([
      extractResponse(),
      [],
      chunkDetail({ source_type: 'tb_conversation', text: 'User: we decided quokka' }),
    ])
    expect(await screen.findByText('Might do X.')).toBeDefined()
    fireEvent.click(screen.getAllByLabelText('Evidence chunk 7')[0])
    expect(await screen.findByText('User: we decided quokka')).toBeDefined()
    expect(screen.getByLabelText('Conversation source').textContent).toBe(
      'from a ThoughtBridge conversation',
    )
  })
})
