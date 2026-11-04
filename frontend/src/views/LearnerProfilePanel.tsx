import { useRef, useState } from 'react'

import { getLearnerProfile, updateLearnerProfile } from '../api/learn'
import type { LearnerEmphasis, LearnerProfile } from '../api/types'

const EMPHASIS_FIELDS: { key: keyof LearnerEmphasis; label: string }[] = [
  { key: 'familiar_systems', label: 'Familiar-system grounding' },
  { key: 'component_mapping', label: 'Explicit component mapping' },
  { key: 'process_placement', label: 'Larger-process placement' },
  { key: 'interactions', label: 'Interaction walkthroughs' },
  { key: 'terminology_bridge', label: 'Terminology bridging' },
]

function LearnerProfilePanel() {
  const [open, setOpen] = useState(false)
  const [profile, setProfile] = useState<LearnerProfile | null>(null)
  const [draftEmphasis, setDraftEmphasis] = useState<LearnerEmphasis | null>(null)
  const [draftText, setDraftText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedTick, setSavedTick] = useState(0)
  const inFlight = useRef(false)

  async function expand() {
    if (inFlight.current) return
    inFlight.current = true
    setOpen(true)
    setLoading(true)
    setError(null)
    setSavedTick(0)
    try {
      const fetched = await getLearnerProfile()
      setProfile(fetched)
      setDraftEmphasis({ ...fetched.emphasis })
      setDraftText(fetched.how_i_learn)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      inFlight.current = false
      setLoading(false)
    }
  }

  function collapse() {
    setOpen(false)
    setError(null)
    setSavedTick(0)
  }

  async function save() {
    if (inFlight.current || !draftEmphasis) return
    inFlight.current = true
    setLoading(true)
    setError(null)
    try {
      const updated = await updateLearnerProfile({
        emphasis: { ...draftEmphasis },
        how_i_learn: draftText,
      })
      setProfile(updated)
      setDraftEmphasis({ ...updated.emphasis })
      setDraftText(updated.how_i_learn)
      setSavedTick((t) => t + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      inFlight.current = false
      setLoading(false)
    }
  }

  if (!open) {
    return (
      <div className="flex flex-col gap-1">
        <button
          type="button"
          aria-label="Edit learning preferences"
          onClick={() => void expand()}
          disabled={loading}
          className="rounded border px-3 py-1 text-sm"
        >
          Learning preferences
        </button>
        <p className="text-xs">Shape how lessons are taught.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {error && (
        <div role="alert" className="rounded border border-red-500 px-3 py-2 text-sm">
          <span>{error}</span>{' '}
          <button type="button" aria-label="Dismiss error" onClick={() => setError(null)} className="underline">
            Dismiss
          </button>
        </div>
      )}

      {profile === null || draftEmphasis === null ? (
        <p className="text-sm">Loading…</p>
      ) : (
        <fieldset className="flex flex-col gap-1 rounded border px-3 py-2">
          <legend className="text-xs font-semibold">Emphasize in new lessons</legend>
          {EMPHASIS_FIELDS.map(({ key, label }) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                aria-label={`Emphasis: ${label}`}
                checked={draftEmphasis[key]}
                onChange={(e) => {
                  setDraftEmphasis({ ...draftEmphasis, [key]: e.target.checked })
                  setSavedTick(0)
                }}
                disabled={loading}
              />
              {label}
            </label>
          ))}
        </fieldset>
      )}

      <label className="flex flex-col gap-1 text-sm">
        How I learn best
        <textarea
          aria-label="How I learn best"
          value={draftText}
          onChange={(e) => {
            setDraftText(e.target.value)
            setSavedTick(0)
          }}
          placeholder="e.g. I learn best from worked examples"
          disabled={loading || profile === null}
          className="rounded border px-3 py-1 text-sm"
        />
      </label>

      <div className="flex items-center gap-2">
        <button
          type="button"
          aria-label="Save learning preferences"
          onClick={() => void save()}
          disabled={loading || profile === null}
          className="rounded border px-3 py-1 text-sm"
        >
          Save
        </button>
        <button
          type="button"
          aria-label="Collapse learning preferences"
          onClick={collapse}
          disabled={loading}
          className="rounded border px-3 py-1 text-sm"
        >
          Hide
        </button>
        {savedTick > 0 && (
          <span role="status" className="text-sm">
            Saved ✓
          </span>
        )}
      </div>
    </div>
  )
}

export default LearnerProfilePanel
