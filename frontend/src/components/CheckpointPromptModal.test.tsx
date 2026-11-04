import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import { FALLBACK_CHECKPOINT_PROMPT } from '../api/prompts'
import CheckpointPromptModal from './CheckpointPromptModal'

const ORIGINAL_CLIPBOARD = Object.getOwnPropertyDescriptor(navigator, 'clipboard')
const ORIGINAL_EXEC_COMMAND = document.execCommand

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

function stubClipboard() {
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText },
    configurable: true,
  })
  return writeText
}

describe('CheckpointPromptModal', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    if (ORIGINAL_CLIPBOARD === undefined) {
      Reflect.deleteProperty(navigator, 'clipboard')
    } else {
      Object.defineProperty(navigator, 'clipboard', ORIGINAL_CLIPBOARD)
    }
    document.execCommand = ORIGINAL_EXEC_COMMAND
  })

  it('renders the fetched prompt text', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([{ prompt: 'PROMPT-TEXT' }]))
    render(<CheckpointPromptModal onClose={() => {}} />)
    expect(await screen.findByDisplayValue('PROMPT-TEXT')).toBeDefined()
    expect(screen.queryByText(/built-in copy/)).toBeNull()
  })

  it('copies via the clipboard and confirms', async () => {
    const writeText = stubClipboard()
    vi.stubGlobal('fetch', mockFetchSequence([{ prompt: 'PROMPT-TEXT' }]))
    render(<CheckpointPromptModal onClose={() => {}} />)
    expect(await screen.findByDisplayValue('PROMPT-TEXT')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Copy prompt'))
    expect(await screen.findByText('Copied ✓')).toBeDefined()
    expect(writeText).toHaveBeenCalledWith('PROMPT-TEXT')
  })

  it('falls back to built-in text when fetch fails, copy still works', async () => {
    const writeText = stubClipboard()
    vi.stubGlobal('fetch', mockFetchSequence([new Error('down')]))
    render(<CheckpointPromptModal onClose={() => {}} />)
    expect(
      await screen.findByText("Showing built-in copy (couldn't reach the server)."),
    ).toBeDefined()
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe(
      FALLBACK_CHECKPOINT_PROMPT,
    )
    fireEvent.click(screen.getByLabelText('Copy prompt'))
    expect(await screen.findByText('Copied ✓')).toBeDefined()
    expect(writeText).toHaveBeenCalledWith(FALLBACK_CHECKPOINT_PROMPT)
  })

  it('Close calls onClose', async () => {
    vi.stubGlobal('fetch', mockFetchSequence([{ prompt: 'PROMPT-TEXT' }]))
    const onClose = vi.fn()
    render(<CheckpointPromptModal onClose={onClose} />)
    expect(await screen.findByDisplayValue('PROMPT-TEXT')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Close'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('falls back to execCommand when the clipboard is unavailable', async () => {
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
    const execCommand = vi.fn().mockReturnValue(true)
    document.execCommand = execCommand as unknown as typeof document.execCommand
    vi.stubGlobal('fetch', mockFetchSequence([{ prompt: 'PROMPT-TEXT' }]))
    render(<CheckpointPromptModal onClose={() => {}} />)
    expect(await screen.findByDisplayValue('PROMPT-TEXT')).toBeDefined()
    fireEvent.click(screen.getByLabelText('Copy prompt'))
    expect(await screen.findByText('Copied ✓')).toBeDefined()
    expect(execCommand).toHaveBeenCalledWith('copy')
  })
})
