import { afterEach, describe, expect, it, vi } from 'vitest'

import { listAttempts, postPracticeAnswer, postPracticeQuestion } from './practice'
import type { PracticeQuestionRequest } from './types'

function mockFetch(payload: unknown, ok = true, status = 200, statusText = 'OK') {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    statusText,
    json: async () => payload,
  })
}

describe('practice client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('postPracticeQuestion POSTs the body to /api/v1/practice/question', async () => {
    const fetch = mockFetch({ attempt_id: 'a' })
    vi.stubGlobal('fetch', fetch)
    const body: PracticeQuestionRequest = {
      mode: 'learning',
      context: { explanation_id: 'e1' },
      conversation_id: null,
    }
    await postPracticeQuestion(body)
    expect(fetch).toHaveBeenCalledOnce()
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/v1/practice/question')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual(body)
  })

  it('postPracticeAnswer POSTs the body to /api/v1/practice/answer', async () => {
    const fetch = mockFetch({ feedback: {}, grounding: 'both' })
    vi.stubGlobal('fetch', fetch)
    await postPracticeAnswer({ attempt_id: 'a1', answer: 'RAG fetches first.' })
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/v1/practice/answer')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ attempt_id: 'a1', answer: 'RAG fetches first.' })
  })

  it('listAttempts GETs the bare path without filters', async () => {
    const fetch = mockFetch([])
    vi.stubGlobal('fetch', fetch)
    await listAttempts()
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/practice/attempts')
    await listAttempts({ retry_only: false })
    expect(fetch.mock.calls[1][0]).toBe('http://localhost:8000/api/v1/practice/attempts')
  })

  it('listAttempts encodes filters as a query string', async () => {
    const fetch = mockFetch([])
    vi.stubGlobal('fetch', fetch)
    await listAttempts({ mode: 'interview', explanation_id: 'e 1', retry_only: true })
    expect(fetch.mock.calls[0][0]).toBe(
      'http://localhost:8000/api/v1/practice/attempts?mode=interview&explanation_id=e+1&retry_only=true',
    )
  })

  it('rejects with status detail on non-OK responses', async () => {
    vi.stubGlobal('fetch', mockFetch({ detail: 'x' }, false, 502, 'Bad Gateway'))
    await expect(
      postPracticeQuestion({ mode: 'interview', question_kind: 'technical' }),
    ).rejects.toThrow('API request failed: 502 Bad Gateway')
  })

  it('honors VITE_API_URL', async () => {
    vi.stubEnv('VITE_API_URL', 'https://demo.example.com')
    const fetch = mockFetch({})
    vi.stubGlobal('fetch', fetch)
    await postPracticeAnswer({ attempt_id: 'a', answer: 'b' })
    expect(fetch.mock.calls[0][0]).toBe('https://demo.example.com/api/v1/practice/answer')
  })
})
