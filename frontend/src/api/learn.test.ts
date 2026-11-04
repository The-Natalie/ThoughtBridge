import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  createMarker,
  extractPartialDefinition,
  getExplanation,
  getLearnerProfile,
  listExplanations,
  listMarkers,
  postExplain,
  postExplainStream,
  postRegenerate,
  updateLearnerProfile,
} from './learn'

function mockFetch(payload: unknown, ok = true, status = 200, statusText = 'OK') {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    statusText,
    json: async () => payload,
  })
}

function mockStreamFetch(frames: string[], ok = true, status = 200, statusText = 'OK') {
  const body =
    frames.length === 0
      ? null
      : new ReadableStream({
          start(controller) {
            for (const frame of frames) {
              controller.enqueue(new TextEncoder().encode(frame))
            }
            controller.close()
          },
        })
  return vi.fn().mockResolvedValue({ ok, status, statusText, body })
}

function sseEvent(event: unknown): string {
  return `data: ${JSON.stringify(event)}\n\n`
}

describe('learn client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('postExplain POSTs the concept body to /api/v1/learn/explain', async () => {
    const fetch = mockFetch({ explanation_id: 'e', reused_from: null, steps: {} })
    vi.stubGlobal('fetch', fetch)
    await postExplain({ concept: 'RAG', familiar_system_hint: 'library' })
    expect(fetch).toHaveBeenCalledOnce()
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/v1/learn/explain')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ concept: 'RAG', familiar_system_hint: 'library' })
  })

  it('getExplanation GETs the explanation path', async () => {
    const fetch = mockFetch({ id: 'exp-1' })
    vi.stubGlobal('fetch', fetch)
    await getExplanation('exp-1')
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/learn/explanations/exp-1')
  })

  it('postRegenerate POSTs the step to the regenerate path', async () => {
    const fetch = mockFetch({ explanation_id: 'exp-2' })
    vi.stubGlobal('fetch', fetch)
    await postRegenerate('exp-1', { step: 'analogy' })
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/v1/learn/explanations/exp-1/regenerate')
    expect(JSON.parse(init.body)).toEqual({ step: 'analogy' })
  })

  it('rejects with status detail on non-OK responses', async () => {
    vi.stubGlobal('fetch', mockFetch({ detail: 'x' }, false, 502, 'Bad Gateway'))
    await expect(postExplain({ concept: 'RAG' })).rejects.toThrow(
      'API request failed: 502 Bad Gateway',
    )
  })

  it('listExplanations GETs the bare list path without a concept', async () => {
    const fetch = mockFetch([])
    vi.stubGlobal('fetch', fetch)
    await listExplanations()
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/learn/explanations')
  })

  it('listExplanations encodes the concept filter', async () => {
    const fetch = mockFetch([])
    vi.stubGlobal('fetch', fetch)
    await listExplanations('RAG retrieval')
    expect(fetch.mock.calls[0][0]).toBe(
      'http://localhost:8000/api/v1/learn/explanations?concept=RAG%20retrieval',
    )
  })

  it('createMarker POSTs the marker body to the markers path', async () => {
    const fetch = mockFetch({ marker_id: 'm-1' })
    vi.stubGlobal('fetch', fetch)
    await createMarker('exp-1', { scope: 'step', step: 'mapping' })
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/v1/learn/explanations/exp-1/markers')
    expect(JSON.parse(init.body)).toEqual({ scope: 'step', step: 'mapping' })
  })

  it('listMarkers GETs the markers path', async () => {
    const fetch = mockFetch([])
    vi.stubGlobal('fetch', fetch)
    await listMarkers('exp-1')
    expect(fetch.mock.calls[0][0]).toBe(
      'http://localhost:8000/api/v1/learn/explanations/exp-1/markers',
    )
  })

  it('getLearnerProfile GETs the profile path', async () => {
    const fetch = mockFetch({ emphasis: {}, how_i_learn: '' })
    vi.stubGlobal('fetch', fetch)
    await getLearnerProfile()
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/learn/profile')
  })

  it('updateLearnerProfile PUTs the partial body to the profile path', async () => {
    const fetch = mockFetch({ emphasis: {}, how_i_learn: '' })
    vi.stubGlobal('fetch', fetch)
    await updateLearnerProfile({ emphasis: { interactions: false }, how_i_learn: 'x' })
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/v1/learn/profile')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body)).toEqual({
      emphasis: { interactions: false },
      how_i_learn: 'x',
    })
  })

  it('postExplainStream POSTs to the stream endpoint and dispatches events in order', async () => {
    const events = [
      { type: 'stage_started', stage: 'D' },
      { type: 'token', stage: 'D', text: 'hi' },
      { type: 'lesson_complete', explanation_id: 'e', reused_from: null },
    ]
    const fetch = mockStreamFetch([...events.map(sseEvent), 'data: [DONE]\n\n'])
    vi.stubGlobal('fetch', fetch)
    const seen: unknown[] = []
    await postExplainStream({ concept: 'RAG' }, (e) => seen.push(e))
    expect(fetch).toHaveBeenCalledOnce()
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/v1/learn/explain/stream')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ concept: 'RAG' })
    expect(seen).toEqual(events)
  })

  it('postExplainStream reassembles events split across chunks', async () => {
    const full = sseEvent({ type: 'token', stage: 'D', text: 'split-me' })
    const fetch = mockStreamFetch([full.slice(0, 10), full.slice(10), 'data: [DONE]\n\n'])
    vi.stubGlobal('fetch', fetch)
    const seen: unknown[] = []
    await postExplainStream({ concept: 'RAG' }, (e) => seen.push(e))
    expect(seen).toEqual([{ type: 'token', stage: 'D', text: 'split-me' }])
  })

  it('postExplainStream rejects on non-OK responses', async () => {
    vi.stubGlobal('fetch', mockStreamFetch(['data: [DONE]\n\n'], false, 502, 'Bad Gateway'))
    await expect(postExplainStream({ concept: 'RAG' }, () => {})).rejects.toThrow(
      'API request failed: 502 Bad Gateway',
    )
  })

  it('extractPartialDefinition returns null until the value starts', () => {
    expect(extractPartialDefinition('')).toBeNull()
    expect(extractPartialDefinition('{"def')).toBeNull()
    expect(extractPartialDefinition('{"definition": ')).toBeNull()
    expect(extractPartialDefinition('{"definition": "')).toBeNull()
  })

  it('extractPartialDefinition reads partial and closed strings with escapes', () => {
    expect(extractPartialDefinition('{"definition": "Hello')).toBe('Hello')
    expect(extractPartialDefinition('{"definition": "Hello"}')).toBe('Hello')
    expect(extractPartialDefinition('{"definition": "a\\"b')).toBe('a"b')
    expect(extractPartialDefinition('{"definition": "line\\nbreak')).toBe('line\nbreak')
    expect(extractPartialDefinition('{"definition": "trail\\')).toBe('trail')
    expect(extractPartialDefinition('{"other": 1, "definition": "late')).toBe('late')
  })
})
