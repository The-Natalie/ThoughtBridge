import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import CareerProfilePanel from './CareerProfilePanel'

function profilePayload(overrides: Record<string, unknown> = {}) {
  return {
    current_role: '',
    past_roles: [],
    target_career: '',
    target_position: '',
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

describe('CareerProfilePanel', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('collapsed renders only the toggle and performs zero fetches', () => {
    const fetch = mockFetchSequence([])
    vi.stubGlobal('fetch', fetch)
    render(<CareerProfilePanel />)
    expect(screen.getByLabelText('Edit career profile')).toBeDefined()
    expect(screen.queryByLabelText('Current role')).toBeNull()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('expand fetches the profile and populates all four fields', async () => {
    const fetch = mockFetchSequence([
      profilePayload({
        current_role: 'Backend engineer',
        past_roles: ['QA analyst', 'Support engineer'],
        target_career: 'Management',
        target_position: 'Staff',
      }),
    ])
    vi.stubGlobal('fetch', fetch)
    render(<CareerProfilePanel />)
    fireEvent.click(screen.getByLabelText('Edit career profile'))
    await screen.findByLabelText('Current role')
    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch.mock.calls[0][0]).toBe('http://localhost:8000/api/v1/profile')
    expect((screen.getByLabelText('Current role') as HTMLInputElement).value).toBe(
      'Backend engineer',
    )
    expect((screen.getByLabelText('Past roles (one per line)') as HTMLTextAreaElement).value).toBe(
      'QA analyst\nSupport engineer',
    )
    expect((screen.getByLabelText('Target career') as HTMLInputElement).value).toBe('Management')
    expect((screen.getByLabelText('Target position') as HTMLInputElement).value).toBe('Staff')
  })

  it('edit plus save PUTs parsed roles and shows Saved', async () => {
    const fetch = mockFetchSequence([
      profilePayload(),
      profilePayload({
        current_role: 'Backend engineer',
        past_roles: ['QA analyst'],
        target_position: 'Staff',
      }),
    ])
    vi.stubGlobal('fetch', fetch)
    render(<CareerProfilePanel />)
    fireEvent.click(screen.getByLabelText('Edit career profile'))
    await screen.findByLabelText('Current role')
    fireEvent.change(screen.getByLabelText('Current role'), { target: { value: 'Backend engineer' } })
    fireEvent.change(screen.getByLabelText('Past roles (one per line)'), {
      target: { value: '  QA analyst  \n\n   \nSupport engineer\n' },
    })
    fireEvent.change(screen.getByLabelText('Target position'), { target: { value: 'Staff' } })
    fireEvent.click(screen.getByLabelText('Save career profile'))
    await screen.findByText('Saved ✓')
    expect(fetch).toHaveBeenCalledTimes(2)
    const [url, init] = fetch.mock.calls[1]
    expect(url).toBe('http://localhost:8000/api/v1/profile')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body)).toEqual({
      current_role: 'Backend engineer',
      past_roles: ['QA analyst', 'Support engineer'],
      target_career: '',
      target_position: 'Staff',
    })
  })

  it('saved tick clears on further edits', async () => {
    const fetch = mockFetchSequence([profilePayload(), profilePayload()])
    vi.stubGlobal('fetch', fetch)
    render(<CareerProfilePanel />)
    fireEvent.click(screen.getByLabelText('Edit career profile'))
    await screen.findByLabelText('Current role')
    fireEvent.click(screen.getByLabelText('Save career profile'))
    await screen.findByText('Saved ✓')
    fireEvent.change(screen.getByLabelText('Current role'), { target: { value: 'x' } })
    expect(screen.queryByText('Saved ✓')).toBeNull()
  })

  it('collapse hides the panel', async () => {
    const fetch = mockFetchSequence([profilePayload()])
    vi.stubGlobal('fetch', fetch)
    render(<CareerProfilePanel />)
    fireEvent.click(screen.getByLabelText('Edit career profile'))
    await screen.findByLabelText('Current role')
    fireEvent.click(screen.getByLabelText('Collapse career profile'))
    expect(screen.queryByLabelText('Current role')).toBeNull()
    expect(screen.getByLabelText('Edit career profile')).toBeDefined()
  })

  it('fetch error shows the alert and Dismiss clears it', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([new Error('boom')]))
    render(<CareerProfilePanel />)
    fireEvent.click(screen.getByLabelText('Edit career profile'))
    await screen.findByRole('alert')
    expect(screen.getByText('boom')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Dismiss error'))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('save error shows the alert', async () => {
    const fetch = mockFetchSequence([profilePayload(), new Error('save failed')])
    vi.stubGlobal('fetch', fetch)
    render(<CareerProfilePanel />)
    fireEvent.click(screen.getByLabelText('Edit career profile'))
    await screen.findByLabelText('Current role')
    fireEvent.click(screen.getByLabelText('Save career profile'))
    await screen.findByRole('alert')
    expect(screen.getByText('save failed')).toBeDefined()
    expect(screen.queryByText('Saved ✓')).toBeNull()
  })
})
