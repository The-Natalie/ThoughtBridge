import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import type { ExtractFact } from '../api/types'
import FactCard from './FactCard'

function fact(overrides: Partial<ExtractFact> = {}): ExtractFact {
  return {
    fact_id: 'f'.repeat(32),
    kind: 'accomplishment',
    status: 'completed',
    summary: 'Did the thing.',
    skills: ['python'],
    confidence: 0.9,
    chunk_ids: [7],
    links: [],
    ...overrides,
  }
}

describe('FactCard', () => {
  afterEach(() => {
    cleanup()
  })

  it('renders badges, summary, skills, chunks, and links', () => {
    const target = fact({ fact_id: 'b'.repeat(32), summary: 'Target summary here.' })
    const source = fact({
      fact_id: 'a'.repeat(32),
      links: [{ to_fact: 'b'.repeat(32), relation: 'decided' }],
    })
    render(
      <FactCard
        fact={source}
        siblings={[source, target]}
        highlighted={false}
        idPrefix="fact-"
        onOpenCitation={() => {}}
        onFollowLink={() => {}}
      />,
    )
    expect(screen.getByText(/accomplishment · completed · 90%/)).toBeDefined()
    expect(screen.getByText('Did the thing.')).toBeDefined()
    expect(screen.getByText('python')).toBeDefined()
    expect(screen.getByLabelText('Evidence chunk 7')).toBeDefined()
    expect(screen.getByLabelText(`Reasoning link decided to ${'b'.repeat(8)}`)).toBeDefined()
    expect(screen.getByText(/decided → Target summary here\./)).toBeDefined()
  })

  it('omits empty skills, chunks, and links sections', () => {
    render(
      <FactCard
        fact={fact({ skills: [], chunk_ids: [], links: [] })}
        siblings={[]}
        highlighted={false}
        idPrefix="fact-"
        onOpenCitation={() => {}}
        onFollowLink={() => {}}
      />,
    )
    expect(screen.queryByLabelText(/Evidence chunk/)).toBeNull()
    expect(screen.queryByLabelText(/Reasoning link/)).toBeNull()
  })

  it('chunk click calls onOpenCitation with the id', () => {
    const onOpenCitation = vi.fn()
    render(
      <FactCard
        fact={fact()}
        siblings={[]}
        highlighted={false}
        idPrefix="fact-"
        onOpenCitation={onOpenCitation}
        onFollowLink={() => {}}
      />,
    )
    fireEvent.click(screen.getByLabelText('Evidence chunk 7'))
    expect(onOpenCitation).toHaveBeenCalledWith(7)
  })

  it('link click calls onFollowLink and truncates long labels at 80 chars', () => {
    const onFollowLink = vi.fn()
    const long = 'x'.repeat(120)
    const target = fact({ fact_id: 'b'.repeat(32), summary: long })
    const source = fact({
      fact_id: 'a'.repeat(32),
      links: [{ to_fact: 'b'.repeat(32), relation: 'decided' }],
    })
    render(
      <FactCard
        fact={source}
        siblings={[source, target]}
        highlighted={false}
        idPrefix="fact-"
        onOpenCitation={() => {}}
        onFollowLink={onFollowLink}
      />,
    )
    const button = screen.getByLabelText(`Reasoning link decided to ${'b'.repeat(8)}`)
    expect(button.textContent).toBe(`decided → ${'x'.repeat(80)}`)
    fireEvent.click(button)
    expect(onFollowLink).toHaveBeenCalledWith('b'.repeat(32))
  })

  it('applies ring classes when highlighted', () => {
    render(
      <FactCard
        fact={fact({ fact_id: 'a'.repeat(32) })}
        siblings={[]}
        highlighted={true}
        idPrefix="fact-"
        onOpenCitation={() => {}}
        onFollowLink={() => {}}
      />,
    )
    const card = screen.getByLabelText(`Fact ${'a'.repeat(8)}`)
    expect(card.className).toContain('ring-2')
    expect(card.className).toContain('font-semibold')
  })

  it('honors idPrefix for the element id', () => {
    render(
      <FactCard
        fact={fact({ fact_id: 'a'.repeat(32) })}
        siblings={[]}
        highlighted={false}
        idPrefix="acc-"
        onOpenCitation={() => {}}
        onFollowLink={() => {}}
      />,
    )
    expect(screen.getByLabelText(`Fact ${'a'.repeat(8)}`).id).toBe(`acc-${'a'.repeat(32)}`)
  })
})
