import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import type { ArtifactDetail, ArtifactSummary } from '../api/types'
import CaptureView from './CaptureView'

function artifactSummary(overrides: Partial<ArtifactSummary> = {}): ArtifactSummary {
  return {
    id: 'art-1-uuid',
    title: 'Dev log',
    source_type: 'note',
    created_at: 't',
    chunk_count: 2,
    fact_count: 1,
    ...overrides,
  }
}

function artifactDetail(overrides: Partial<ArtifactDetail> = {}): ArtifactDetail {
  return {
    id: 'art-1-uuid',
    title: 'Dev log',
    source_type: 'note',
    content: 'FULL ORIGINAL NOTE TEXT',
    content_hash: 'h',
    origin: { adapter: 'text' },
    created_at: 't',
    chunks: [],
    fact_ids: ['f1'],
    interpretation_ids: [],
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

describe('CaptureView', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('mount lists captured artifacts with view and delete buttons', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([[artifactSummary()]]))
    render(<CaptureView />)
    expect(await screen.findByText(/Dev log · note · 2 chunks · 1 facts/)).toBeDefined()
    expect(screen.getByLabelText('View Dev log')).toBeDefined()
    expect(screen.getByLabelText('Delete Dev log')).toBeDefined()
  })

  it('empty list shows the capture-first hint', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([[]]))
    render(<CaptureView />)
    expect(
      await screen.findByText('No captures yet — write a note or upload a file above.'),
    ).toBeDefined()
  })

  it('capture posts JSON, shows the notice, and refreshes the list', async () => {
    const fetch = mockFetchSequence([[], { artifact_id: 'abcdef123456', chunks: 3 }, [artifactSummary()]])
    vi.stubGlobal('fetch', fetch)
    render(<CaptureView />)
    expect(await screen.findByText(/No captures yet/)).toBeDefined()
    fireEvent.change(screen.getByLabelText('Title (optional)'), { target: { value: 'T' } })
    fireEvent.change(screen.getByLabelText('Content'), { target: { value: 'note body' } })
    fireEvent.click(screen.getByLabelText('Capture'))
    expect(await screen.findByText('Captured abcdef12… (3 chunks)')).toBeDefined()
    expect(fetch.mock.calls[1][0]).toBe('http://localhost:8000/api/v1/artifacts')
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({
      source_type: 'note',
      title: 'T',
      content: 'note body',
    })
    expect(await screen.findByText(/Dev log · note/)).toBeDefined()
    expect((screen.getByLabelText('Content') as HTMLTextAreaElement).value).toBe('')
  })

  it('capture is disabled with blank content', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([[]]))
    render(<CaptureView />)
    expect(await screen.findByText(/No captures yet/)).toBeDefined()
    expect((screen.getByLabelText('Capture') as HTMLButtonElement).disabled).toBe(true)
  })

  it('source type select changes the posted source_type', async () => {
    const fetch = mockFetchSequence([[], { artifact_id: 'p1', chunks: 1 }, []])
    vi.stubGlobal('fetch', fetch)
    render(<CaptureView />)
    expect(await screen.findByText(/No captures yet/)).toBeDefined()
    fireEvent.change(screen.getByLabelText('Source type'), { target: { value: 'paste' } })
    fireEvent.change(screen.getByLabelText('Content'), { target: { value: 'pasted log' } })
    fireEvent.click(screen.getByLabelText('Capture'))
    expect(await screen.findByText(/Captured p1/)).toBeDefined()
    expect(JSON.parse(fetch.mock.calls[1][1].body).source_type).toBe('paste')
  })

  it('upload posts the file and shows extracted counts', async () => {
    const fetch = mockFetchSequence([
      [],
      { artifact_id: 'u1', chunks: 2, extracted_chars: 11, pages: null },
      [artifactSummary({ title: 'notes.txt' })],
    ])
    vi.stubGlobal('fetch', fetch)
    render(<CaptureView />)
    expect(await screen.findByText(/No captures yet/)).toBeDefined()
    const file = new File(['hello world'], 'notes.txt', { type: 'text/plain' })
    fireEvent.change(screen.getByLabelText('Upload file'), { target: { files: [file] } })
    fireEvent.click(screen.getByLabelText('Upload'))
    expect(await screen.findByText('Uploaded notes.txt: 11 chars, 2 chunks')).toBeDefined()
    expect(fetch.mock.calls[1][0]).toBe('http://localhost:8000/api/v1/artifacts/upload')
    const body = fetch.mock.calls[1][1].body as FormData
    expect(body.get('file')).toBe(file)
  })

  it('upload is disabled without a file', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([[]]))
    render(<CaptureView />)
    expect(await screen.findByText(/No captures yet/)).toBeDefined()
    expect((screen.getByLabelText('Upload') as HTMLButtonElement).disabled).toBe(true)
  })

  it('view opens the detail panel with full content and Close dismisses it', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([[artifactSummary()], artifactDetail()]))
    render(<CaptureView />)
    expect(await screen.findByText(/Dev log · note/)).toBeDefined()
    fireEvent.click(screen.getByLabelText('View Dev log'))
    expect(await screen.findByText('FULL ORIGINAL NOTE TEXT')).toBeDefined()
    expect(screen.getByText(/0 chunks · 1 facts · 0 interpretations/)).toBeDefined()
    fireEvent.click(screen.getByLabelText('Close details'))
    expect(screen.queryByText('FULL ORIGINAL NOTE TEXT')).toBeNull()
  })

  it('delete shows cascade counts and removes the row', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetchSequence([
        [artifactSummary()],
        { deleted: { artifacts: 1, chunks: 2, facts: 1 }, unlinked: { facts: 0 } },
        [],
      ]),
    )
    render(<CaptureView />)
    expect(await screen.findByText(/Dev log · note/)).toBeDefined()
    fireEvent.click(screen.getByLabelText('Delete Dev log'))
    expect(
      await screen.findByText('Deleted Dev log: 2 chunks, 1 facts removed, 0 facts unlinked.'),
    ).toBeDefined()
    expect(await screen.findByText(/No captures yet/)).toBeDefined()
  })

  it('failed capture shows a dismissible alert', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([[], new Error('capture boom')]))
    render(<CaptureView />)
    expect(await screen.findByText(/No captures yet/)).toBeDefined()
    fireEvent.change(screen.getByLabelText('Content'), { target: { value: 'x' } })
    fireEvent.click(screen.getByLabelText('Capture'))
    expect(await screen.findByRole('alert')).toBeDefined()
    expect(screen.getByText('capture boom')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Dismiss error'))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('shows the verbatim-storage caution', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([[]]))
    render(<CaptureView />)
    expect(
      await screen.findByText("Pasted content is stored verbatim — don't paste secrets or credentials."),
    ).toBeDefined()
  })
})
