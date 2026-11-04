import type { GroundingLabel } from '../api/types'

const GROUNDING_STYLES: Record<GroundingLabel, string> = {
  'from your notes': 'border-green-600',
  'general explanation': 'border-neutral-400',
  both: 'border-blue-600',
}

/** Shared grounding badge: canonical label text plus its border color. */
function GroundingBadge({ grounding }: { grounding: GroundingLabel }) {
  return (
    <p aria-label="Grounding" className={`inline-block rounded border px-2 py-0.5 text-xs ${GROUNDING_STYLES[grounding]}`}>
      {grounding}
    </p>
  )
}

export default GroundingBadge
