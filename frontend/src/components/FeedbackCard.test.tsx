import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

import type { GroundingLabel, PracticeFeedback } from '../api/types'
import FeedbackCard from './FeedbackCard'

const FEEDBACK: PracticeFeedback = {
  correct: ['retrieval first'],
  missing: ['chunking'],
  inaccurate: [],
  terminology: ['say embeddings'],
  next_step: 'Retry the full explanation.',
}

describe('FeedbackCard', () => {
  afterEach(() => {
    cleanup()
  })

  it('renders all five sections with items and empty markers', () => {
    render(<FeedbackCard feedback={FEEDBACK} grounding="both" />)
    expect(screen.getByText('Correct')).toBeDefined()
    expect(screen.getByText('retrieval first')).toBeDefined()
    expect(screen.getByText('Missing')).toBeDefined()
    expect(screen.getByText('chunking')).toBeDefined()
    expect(screen.getByText('Inaccurate')).toBeDefined()
    expect(screen.getByText('Terminology help')).toBeDefined()
    expect(screen.getByText('say embeddings')).toBeDefined()
    expect(screen.getByText('Next step')).toBeDefined()
    expect(screen.getByText('Retry the full explanation.')).toBeDefined()
    expect(screen.getAllByText('(none)')).toHaveLength(1)
  })

  it.each<GroundingLabel>(['from your notes', 'general explanation', 'both'])(
    'renders the grounding badge verbatim: %s',
    (grounding) => {
      render(<FeedbackCard feedback={FEEDBACK} grounding={grounding} />)
      expect(screen.getByLabelText('Grounding').textContent).toBe(grounding)
    },
  )
})
