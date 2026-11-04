import { afterEach, describe, expect, it, vi } from 'vitest'

import { deleteArtifact, getArtifact, listArtifacts, postArtifact, uploadArtifact } from './artifacts'

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

  it('postArtifact POSTs JSON and returns the created shape', async () => {
    const fetch = mockFetch({ artifact_id: 'a1', chunks: 3 })
    vi.stubGlobal('fetch', fetch)
    await expect(
      postArtifact({ source_type: 'note', title: 'T', content: 'body' }),
    ).resolves.toEqual({ artifact_id: 'a1', chunks: 3 })
    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/artifacts')
    const init = fetch.mock.calls[0][1] as { method: string; body: string }
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ source_type: 'note', title: 'T', content: 'body' })
  })

  it('postArtifact rejects on blank-content 422', async () => {
    vi.stubGlobal('fetch', mockFetch({ detail: 'x' }, false, 422, 'Unprocessable Entity'))
    await expect(postArtifact({ source_type: 'note', content: ' ' })).rejects.toThrow(
      'API request failed: 422 Unprocessable Entity',
    )
  })

  it('uploadArtifact POSTs multipart form data with the file', async () => {
    const payload = { artifact_id: 'a2', chunks: 1, extracted_chars: 11, pages: null }
    const fetch = mockFetch(payload)
    vi.stubGlobal('fetch', fetch)
    const file = new File(['hello world'], 'notes.txt', { type: 'text/plain' })
    await expect(uploadArtifact(file)).resolves.toEqual(payload)
    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/artifacts/upload')
    const init = fetch.mock.calls[0][1] as { method: string; body: unknown }
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    expect((init.body as FormData).get('file')).toBe(file)
  })

  it('uploadArtifact rejects on bad-file 400', async () => {
    vi.stubGlobal('fetch', mockFetch({ detail: 'x' }, false, 400, 'Bad Request'))
    const file = new File(['x'], 'bad.exe', { type: 'application/octet-stream' })
    await expect(uploadArtifact(file)).rejects.toThrow('API request failed: 400 Bad Request')
  })

  it('getArtifact GETs the detail path', async () => {
    const payload = {
      id: 'a1',
      title: 'T',
      source_type: 'note',
      content: 'body',
      content_hash: 'h',
      origin: {},
      created_at: 't',
      chunks: [],
      fact_ids: [],
      interpretation_ids: [],
    }
    const fetch = mockFetch(payload)
    vi.stubGlobal('fetch', fetch)
    await expect(getArtifact('a1')).resolves.toEqual(payload)
    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/artifacts/a1')
  })
})
