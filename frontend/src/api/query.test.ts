import { afterEach, describe, expect, it, vi } from 'vitest'

import { getChunk, getConversation, listConversations, postQuery } from './query'

function mockFetch(payload: unknown, ok = true, status = 200, statusText = 'OK') {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    statusText,
    json: async () => payload,
  })
}

describe('query client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('postQuery POSTs the question body to /api/v1/query', async () => {
    const fetch = mockFetch({ answer: 'a', citations: [], mode_used: 'evidence', conversation_id: 'c' })
    vi.stubGlobal('fetch', fetch)
    await postQuery({ question: 'hi?', mode: 'auto', conversation_id: null })
    expect(fetch).toHaveBeenCalledOnce()
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/v1/query')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ question: 'hi?', mode: 'auto', conversation_id: null })
  })

  it('getChunk GETs the chunk path', async () => {
    const fetch = mockFetch({ id: 7 })
    vi.stubGlobal('fetch', fetch)
    await getChunk(7)
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/chunks/7')
  })

  it('listConversations and getConversation hit the conversation paths', async () => {
    const fetch = mockFetch([])
    vi.stubGlobal('fetch', fetch)
    await listConversations()
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/conversations')
    await getConversation('abc')
    expect(fetch.mock.calls[1][0]).toBe('http://localhost:8000/api/v1/conversations/abc')
  })

  it('rejects with status detail on non-OK responses', async () => {
    vi.stubGlobal('fetch', mockFetch({ detail: 'x' }, false, 502, 'Bad Gateway'))
    await expect(postQuery({ question: 'hi?' })).rejects.toThrow('API request failed: 502 Bad Gateway')
  })

  it('honors VITE_API_URL', async () => {
    vi.stubEnv('VITE_API_URL', 'https://demo.example.com')
    const fetch = mockFetch({})
    vi.stubGlobal('fetch', fetch)
    await postQuery({ question: 'hi?' })
    expect(fetch.mock.calls[0][0]).toBe('https://demo.example.com/api/v1/query')
  })
})
