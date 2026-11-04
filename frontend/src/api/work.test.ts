import { afterEach, describe, expect, it, vi } from 'vitest'

import { postExtract } from './work'

function mockFetch(payload: unknown, ok = true, status = 200, statusText = 'OK') {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    statusText,
    json: async () => payload,
  })
}

describe('work client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('postExtract POSTs the artifact ids to /api/v1/work/extract', async () => {
    const fetch = mockFetch({ facts: [] })
    vi.stubGlobal('fetch', fetch)
    await postExtract({ artifact_ids: ['a1', 'a2'] })
    expect(fetch).toHaveBeenCalledOnce()
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/v1/work/extract')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ artifact_ids: ['a1', 'a2'] })
  })

  it('rejects with status detail on non-OK responses', async () => {
    vi.stubGlobal('fetch', mockFetch({ detail: 'x' }, false, 502, 'Bad Gateway'))
    await expect(postExtract({ artifact_ids: ['a1'] })).rejects.toThrow(
      'API request failed: 502 Bad Gateway',
    )
  })
})
