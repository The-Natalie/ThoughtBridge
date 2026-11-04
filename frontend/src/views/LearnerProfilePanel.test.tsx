import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import LearnerProfilePanel from './LearnerProfilePanel'

const EMPHASIS_LABELS = [
  'Familiar-system grounding',
  'Explicit component mapping',
  'Larger-process placement',
  'Interaction walkthroughs',
  'Terminology bridging',
]

function profilePayload(overrides: Record<string, unknown> = {}) {
  return {
    emphasis: {
      familiar_systems: true,
      component_mapping: true,
      process_placement: true,
      interactions: true,
      terminology_bridge: true,
    },
    how_i_learn: '',
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

describe('LearnerProfilePanel', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('collapsed renders only the toggle and performs zero fetches', () => {
    const fetch = mockFetchSequence([])
    vi.stubGlobal('fetch', fetch)
    render(<LearnerProfilePanel />)
    expect(screen.getByLabelText('Edit learning preferences')).toBeDefined()
    expect(screen.queryByLabelText('How I learn best')).toBeNull()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('expand fetches the profile and renders five checked boxes plus textarea', async () => {
    const fetch = mockFetchSequence([profilePayload()])
    vi.stubGlobal('fetch', fetch)
    render(<LearnerProfilePanel />)
    fireEvent.click(screen.getByLabelText('Edit learning preferences'))
    await screen.findByLabelText('How I learn best')
    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/learn/profile')
    for (const label of EMPHASIS_LABELS) {
      const box = screen.getByLabelText(`Emphasis: ${label}`) as HTMLInputElement
      expect(box.checked).toBe(true)
    }
    expect((screen.getByLabelText('How I learn best') as HTMLTextAreaElement).value).toBe('')
  })

  it('uncheck plus text plus save PUTs the exact body and shows Saved', async () => {
    const fetch = mockFetchSequence([
      profilePayload(),
      profilePayload({
        emphasis: {
          familiar_systems: true,
          component_mapping: true,
          process_placement: true,
          interactions: false,
          terminology_bridge: true,
        },
        how_i_learn: 'typed',
      }),
    ])
    vi.stubGlobal('fetch', fetch)
    render(<LearnerProfilePanel />)
    fireEvent.click(screen.getByLabelText('Edit learning preferences'))
    await screen.findByLabelText('How I learn best')
    fireEvent.click(screen.getByLabelText('Emphasis: Interaction walkthroughs'))
    fireEvent.change(screen.getByLabelText('How I learn best'), { target: { value: 'typed' } })
    fireEvent.click(screen.getByLabelText('Save learning preferences'))
    await screen.findByText('Saved ✓')
    expect(fetch).toHaveBeenCalledTimes(2)
    const [url, init] = fetch.mock.calls[1]
    expect(url).toBe('http://localhost:8000/api/v1/learn/profile')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body)).toEqual({
      emphasis: {
        familiar_systems: true,
        component_mapping: true,
        process_placement: true,
        interactions: false,
        terminology_bridge: true,
      },
      how_i_learn: 'typed',
    })
  })

  it('GET failure shows an alert that dismisses', async () => {
    const fetch = mockFetchSequence([{ __notOk: true, __status: 500, __statusText: 'Boom' }])
    vi.stubGlobal('fetch', fetch)
    render(<LearnerProfilePanel />)
    fireEvent.click(screen.getByLabelText('Edit learning preferences'))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('API request failed: 500 Boom')
    fireEvent.click(screen.getByLabelText('Dismiss error'))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('save failure shows an alert and keeps the draft intact', async () => {
    const fetch = mockFetchSequence([
      profilePayload(),
      { __notOk: true, __status: 502, __statusText: 'Bad Gateway' },
    ])
    vi.stubGlobal('fetch', fetch)
    render(<LearnerProfilePanel />)
    fireEvent.click(screen.getByLabelText('Edit learning preferences'))
    await screen.findByLabelText('How I learn best')
    fireEvent.click(screen.getByLabelText('Emphasis: Interaction walkthroughs'))
    fireEvent.change(screen.getByLabelText('How I learn best'), { target: { value: 'kept' } })
    fireEvent.click(screen.getByLabelText('Save learning preferences'))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('API request failed: 502 Bad Gateway')
    expect(screen.queryByText('Saved ✓')).toBeNull()
    expect(
      (screen.getByLabelText('Emphasis: Interaction walkthroughs') as HTMLInputElement).checked,
    ).toBe(false)
    expect((screen.getByLabelText('How I learn best') as HTMLTextAreaElement).value).toBe('kept')
  })
})
