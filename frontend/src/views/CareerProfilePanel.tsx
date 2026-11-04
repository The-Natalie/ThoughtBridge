import { useRef, useState } from 'react'

import { getCareerProfile, updateCareerProfile } from '../api/work'
import type { CareerProfile } from '../api/types'

function CareerProfilePanel() {
  const [open, setOpen] = useState(false)
  const [profile, setProfile] = useState<CareerProfile | null>(null)
  const [draftRole, setDraftRole] = useState('')
  const [draftPastRoles, setDraftPastRoles] = useState('')
  const [draftCareer, setDraftCareer] = useState('')
  const [draftPosition, setDraftPosition] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedTick, setSavedTick] = useState(0)
  const inFlight = useRef(false)

  function applyDraft(fetched: CareerProfile) {
    setProfile(fetched)
    setDraftRole(fetched.current_role)
    setDraftPastRoles(fetched.past_roles.join('\n'))
    setDraftCareer(fetched.target_career)
    setDraftPosition(fetched.target_position)
  }

  async function expand() {
    if (inFlight.current) return
    inFlight.current = true
    setOpen(true)
    setLoading(true)
    setError(null)
    setSavedTick(0)
    try {
      applyDraft(await getCareerProfile())
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

  function touch() {
    setSavedTick(0)
  }

  async function save() {
    if (inFlight.current || profile === null) return
    inFlight.current = true
    setLoading(true)
    setError(null)
    try {
      const updated = await updateCareerProfile({
        current_role: draftRole,
        past_roles: draftPastRoles
          .split('\n')
          .map((line) => line.trim())
          .filter((line) => line !== ''),
        target_career: draftCareer,
        target_position: draftPosition,
      })
      applyDraft(updated)
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
          aria-label="Edit career profile"
          onClick={() => void expand()}
          disabled={loading}
          className="rounded border px-3 py-1 text-sm"
        >
          Career profile
        </button>
        <p className="text-xs">Shape extraction toward your trajectory.</p>
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

      {profile === null ? (
        <p className="text-sm">Loading…</p>
      ) : (
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1 text-sm">
            Current role
            <input
              type="text"
              aria-label="Current role"
              value={draftRole}
              onChange={(e) => {
                setDraftRole(e.target.value)
                touch()
              }}
              placeholder="e.g. Backend engineer"
              disabled={loading}
              className="rounded border px-3 py-1 text-sm"
            />
          </label>

          <label className="flex flex-col gap-1 text-sm">
            Past roles (one per line)
            <textarea
              aria-label="Past roles (one per line)"
              value={draftPastRoles}
              onChange={(e) => {
                setDraftPastRoles(e.target.value)
                touch()
              }}
              placeholder={'e.g. QA analyst\nSupport engineer'}
              disabled={loading}
              className="rounded border px-3 py-1 text-sm"
            />
          </label>

          <label className="flex flex-col gap-1 text-sm">
            Target career
            <input
              type="text"
              aria-label="Target career"
              value={draftCareer}
              onChange={(e) => {
                setDraftCareer(e.target.value)
                touch()
              }}
              placeholder="e.g. Engineering management"
              disabled={loading}
              className="rounded border px-3 py-1 text-sm"
            />
          </label>

          <label className="flex flex-col gap-1 text-sm">
            Target position
            <input
              type="text"
              aria-label="Target position"
              value={draftPosition}
              onChange={(e) => {
                setDraftPosition(e.target.value)
                touch()
              }}
              placeholder="e.g. Staff backend engineer"
              disabled={loading}
              className="rounded border px-3 py-1 text-sm"
            />
          </label>
        </div>
      )}

      <div className="flex items-center gap-2">
        <button
          type="button"
          aria-label="Save career profile"
          onClick={() => void save()}
          disabled={loading || profile === null}
          className="rounded border px-3 py-1 text-sm"
        >
          Save
        </button>
        <button
          type="button"
          aria-label="Collapse career profile"
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

export default CareerProfilePanel
