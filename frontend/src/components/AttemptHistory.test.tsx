import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import type { PracticeAttempt } from '../api/types'
import AttemptHistory from './AttemptHistory'

function attempt(overrides: Partial<PracticeAttempt> & { id: string }): PracticeAttempt {
  return {
    mode: 'learning',
    question_kind: null,
    explanation_id: 'e1',
    concept: 'RAG',
    question: 'Explain RAG?',
    answer: 'thin',
    feedback: null,
    grounding: 'general explanation',
    needs_retry: false,
    created_at: 't',
    ...overrides,
  }
}

describe('AttemptHistory', () => {
  afterEach(() => {
    cleanup()
  })

  it('renders empty state with zero counts', () => {
    render(<AttemptHistory attempts={[]} onRetry={() => {}} />)
    expect(screen.getByText('No attempts yet.')).toBeDefined()
    expect(screen.getByText('Practice history (0) · Retry queue (0)')).toBeDefined()
  })

  it('shows retry queue oldest-first above the newest-first list', () => {
    const newer = attempt({ id: 'new', question: 'New Q?', needs_retry: true })
    const older = attempt({ id: 'old', question: 'Old Q?', needs_retry: true })
    const clean = attempt({ id: 'clean', question: 'Clean Q?', needs_retry: false })
    render(<AttemptHistory attempts={[newer, older, clean]} onRetry={() => {}} />)
    expect(screen.getByText('Practice history (3) · Retry queue (2)')).toBeDefined()
    const queue = screen.getByLabelText('Retry queue')
    const queued = Array.from(queue.querySelectorAll('p.mt-1')).map((p) => p.textContent)
    expect(queued).toEqual(['Old Q?', 'New Q?'])
    expect(screen.getByLabelText('Retry old')).toBeDefined()
    expect(screen.getByLabelText('Retry new')).toBeDefined()
    expect(screen.queryByLabelText('Retry clean')).toBeNull()
  })

  it('fires onRetry with the whole attempt', () => {
    const target = attempt({ id: 'r1', question: 'Retry me?', needs_retry: true })
    const onRetry = vi.fn()
    render(<AttemptHistory attempts={[target]} onRetry={onRetry} />)
    fireEvent.click(screen.getByLabelText('Retry r1'))
    expect(onRetry).toHaveBeenCalledOnce()
    expect(onRetry).toHaveBeenCalledWith(target)
  })
})
