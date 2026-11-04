import { afterEach, describe, expect, it, vi } from 'vitest'

import { deleteArtifact, listArtifacts } from './artifacts'

function mockFetch(payload: unknown, ok = true, status = 200, statusText = 'OK') {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    statusText,
    json: async () => payload,
  })
}

describe('artifacts client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('listArtifacts GETs the artifacts list path', async () => {
    const fetch = mockFetch([])
    vi.stubGlobal('fetch', fetch)
    await listArtifacts()
    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/artifacts')
  })

  it('rejects with status detail on non-OK responses', async () => {
    vi.stubGlobal('fetch', mockFetch({ detail: 'x' }, false, 500, 'Internal Server Error'))
    await expect(listArtifacts()).rejects.toThrow(
      'API request failed: 500 Internal Server Error',
    )
  })

  it('deleteArtifact DELETEs the artifact path', async () => {
    const payload = { deleted: { artifacts: 1, chunks: 2, facts: 0 }, unlinked: { facts: 0 } }
    const fetch = mockFetch(payload)
    vi.stubGlobal('fetch', fetch)
    await expect(deleteArtifact('abc')).resolves.toEqual(payload)
    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/artifacts/abc')
    const init = fetch.mock.calls[0][1] as { method: string }
    expect(init.method).toBe('DELETE')
  })

  it('deleteArtifact rejects on non-OK responses', async () => {
    vi.stubGlobal('fetch', mockFetch({ detail: 'x' }, false, 404, 'Not Found'))
    await expect(deleteArtifact('abc')).rejects.toThrow('API request failed: 404 Not Found')
  })
})
