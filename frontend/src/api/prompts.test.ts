import { afterEach, describe, expect, it, vi } from 'vitest'

import { FALLBACK_CHECKPOINT_PROMPT, getCheckpointPrompt } from './prompts'

function mockFetchSequence(payloads: unknown[]) {
  const queue = [...payloads]
  return vi.fn().mockImplementation(() => {
    const payload = queue.shift()
    if (payload instanceof Error) return Promise.reject(payload)
    return Promise.resolve({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => payload,
    })
  })
}

describe('prompts client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('GETs the checkpoint endpoint and returns the prompt verbatim', async () => {
    const fetch = mockFetchSequence([{ prompt: 'PROMPT-TEXT' }])
    vi.stubGlobal('fetch', fetch)
    await expect(getCheckpointPrompt()).resolves.toEqual({ prompt: 'PROMPT-TEXT' })
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/prompts/checkpoint')
  })

  it('fallback covers all four F-9 sections', () => {
    for (const marker of [
      'Work performed',
      'Problems encountered',
      'Decisions and reasoning',
      'Accomplishments and skills demonstrated',
    ]) {
      expect(FALLBACK_CHECKPOINT_PROMPT).toContain(marker)
    }
  })
})
