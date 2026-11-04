import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'

import App from './App'

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

describe('App checkpoint button', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('renders the Checkpoint prompt button outside the primary nav', () => {
    vi.stubGlobal('fetch', mockFetchSequence([]))
    render(<App />)
    expect(screen.getByLabelText('Checkpoint prompt')).toBeDefined()
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).queryByLabelText('Checkpoint prompt')).toBeNull()
  })

  it('opens the checkpoint dialog on click', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([{ prompt: 'PROMPT-TEXT' }]))
    render(<App />)
    fireEvent.click(screen.getByLabelText('Checkpoint prompt'))
    expect(await screen.findByRole('dialog')).toBeDefined()
    expect(screen.getByDisplayValue('PROMPT-TEXT')).toBeDefined()
  })

  it('Close dismisses the dialog', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([{ prompt: 'PROMPT-TEXT' }]))
    render(<App />)
    fireEvent.click(screen.getByLabelText('Checkpoint prompt'))
    expect(await screen.findByRole('dialog')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Close'))
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
