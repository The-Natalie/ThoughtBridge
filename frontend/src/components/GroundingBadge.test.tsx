import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

import type { GroundingLabel } from '../api/types'
import GroundingBadge from './GroundingBadge'

describe('GroundingBadge', () => {
  afterEach(() => {
    cleanup()
  })

  it.each<GroundingLabel>(['from your notes', 'general explanation', 'both'])(
    'renders the grounding label verbatim: %s',
    (grounding) => {
      render(<GroundingBadge grounding={grounding} />)
      expect(screen.getByLabelText('Grounding').textContent).toBe(grounding)
    },
  )

  it('gives each label a distinct border class', () => {
    const classes = (
      ['from your notes', 'general explanation', 'both'] as GroundingLabel[]
    ).map((grounding) => {
      const { unmount } = render(<GroundingBadge grounding={grounding} />)
      const cls = screen.getByLabelText('Grounding').className
      unmount()
      return cls
    })
    expect(new Set(classes).size).toBe(3)
  })
})
