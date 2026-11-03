import { afterEach, describe, expect, it, vi } from 'vitest'

import { getExplanation, postExplain, postRegenerate } from './learn'

function mockFetch(payload: unknown, ok = true, status = 200, statusText = 'OK') {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    statusText,
    json: async () => payload,
  })
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
})
