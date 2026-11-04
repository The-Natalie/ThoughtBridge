import { afterEach, describe, expect, it, vi } from 'vitest'

import { getCareerProfile, listAccomplishments, postExtract, updateCareerProfile } from './work'

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

  it('getCareerProfile GETs /api/v1/profile', async () => {
    const fetch = mockFetch({ current_role: '', past_roles: [], target_career: '', target_position: '' })
    vi.stubGlobal('fetch', fetch)
    await getCareerProfile()
    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/profile')
  })

  it('updateCareerProfile PUTs the body to /api/v1/profile', async () => {
    const fetch = mockFetch({ current_role: 'r', past_roles: [], target_career: '', target_position: '' })
    vi.stubGlobal('fetch', fetch)
    await updateCareerProfile({ current_role: 'r' })
    expect(fetch).toHaveBeenCalledOnce()
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/v1/profile')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body)).toEqual({ current_role: 'r' })
  })

  it('listAccomplishments GETs the bare URL when params are undefined', async () => {
    const fetch = mockFetch([])
    vi.stubGlobal('fetch', fetch)
    await listAccomplishments()
    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/work/accomplishments')
  })

  it('listAccomplishments encodes q', async () => {
    const fetch = mockFetch([])
    vi.stubGlobal('fetch', fetch)
    await listAccomplishments('ci/cd pipelines')
    expect(fetch.mock.calls[0][0]).toBe(
      'http://localhost:8000/api/v1/work/accomplishments?q=ci%2Fcd%20pipelines',
    )
  })

  it('listAccomplishments combines q and skill', async () => {
    const fetch = mockFetch([])
    vi.stubGlobal('fetch', fetch)
    await listAccomplishments('docs', 'writing')
    expect(fetch.mock.calls[0][0]).toBe(
      'http://localhost:8000/api/v1/work/accomplishments?q=docs&skill=writing',
    )
  })

  it('listAccomplishments rejects on non-OK responses', async () => {
    vi.stubGlobal('fetch', mockFetch({ detail: 'x' }, false, 500, 'Server Error'))
    await expect(listAccomplishments()).rejects.toThrow('API request failed: 500 Server Error')
  })
})
