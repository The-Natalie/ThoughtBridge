import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import type { ChunkDetail } from '../api/types'
import CitationPanel from './CitationPanel'

function chunkDetail(overrides: Partial<ChunkDetail> = {}): ChunkDetail {
  return {
    id: 7,
    artifact_id: 'art-1',
    chunk_idx: 0,
    span: [0, 10],
    text: 'full chunk text here',
    source_type: 'note',
    ...overrides,
  }
}

describe('CitationPanel', () => {
  afterEach(() => {
    cleanup()
  })

  it('renders header meta, full text, and Close', () => {
    render(<CitationPanel chunk={chunkDetail()} onClose={() => {}} />)
    expect(screen.getByText(/Chunk 7/)).toBeDefined()
    expect(screen.getByText(/artifact art-1/)).toBeDefined()
    expect(screen.getByText('full chunk text here')).toBeDefined()
    expect(screen.getByLabelText('Close citation')).toBeDefined()
  })

  it('badges conversation chunks and not note chunks', () => {
    const { unmount } = render(
      <CitationPanel chunk={chunkDetail({ source_type: 'tb_conversation' })} onClose={() => {}} />,
    )
    expect(screen.getByLabelText('Conversation source').textContent).toBe(
      'from a ThoughtBridge conversation',
    )
    unmount()
    render(<CitationPanel chunk={chunkDetail()} onClose={() => {}} />)
    expect(screen.queryByLabelText('Conversation source')).toBeNull()
  })

  it('Close button calls onClose', () => {
    const onClose = vi.fn()
    render(<CitationPanel chunk={chunkDetail()} onClose={onClose} />)
    fireEvent.click(screen.getByLabelText('Close citation'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
