import { useEffect, useState } from 'react'

import { FALLBACK_CHECKPOINT_PROMPT, getCheckpointPrompt } from '../api/prompts'

/** One-click checkpoint prompt: fetch the static text (fallback built in), copy it. */
function CheckpointPromptModal({ onClose }: { onClose: () => void }) {
  const [text, setText] = useState<string | null>(null)
  const [fallbackUsed, setFallbackUsed] = useState(false)
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle')

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const response = await getCheckpointPrompt()
        if (!cancelled) setText(response.prompt)
      } catch {
        if (!cancelled) {
          setText(FALLBACK_CHECKPOINT_PROMPT)
          setFallbackUsed(true)
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  function legacyCopy(value: string): boolean {
    const area = document.createElement('textarea')
    area.value = value
    area.setAttribute('readonly', '')
    area.style.position = 'absolute'
    area.style.left = '-9999px'
    document.body.appendChild(area)
    area.select()
    let ok = false
    try {
      ok = document.execCommand('copy')
    } catch {
      ok = false
    }
    document.body.removeChild(area)
    return ok
  }

  async function copy() {
    if (text === null) return
    const clipboard = navigator.clipboard
    if (clipboard) {
      try {
        await clipboard.writeText(text)
        setCopyState('copied')
        return
      } catch {
        // fall through to the legacy path
      }
    }
    setCopyState(legacyCopy(text) ? 'copied' : 'failed')
  }

  return (
    <div role="dialog" aria-label="Checkpoint prompt" className="rounded border px-3 py-2">
      {text === null ? (
        <p role="status" className="text-sm">
          Loading…
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          <textarea
            aria-label="Checkpoint prompt"
            readOnly
            value={text}
            rows={12}
            className="rounded border px-3 py-1 text-sm"
          />
          {fallbackUsed && (
            <p className="text-xs italic">Showing built-in copy (couldn't reach the server).</p>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              aria-label="Copy prompt"
              onClick={() => void copy()}
              className="rounded border px-3 py-1 text-sm"
            >
              Copy prompt
            </button>
            <button
              type="button"
              aria-label="Close"
              onClick={onClose}
              className="rounded border px-3 py-1 text-sm"
            >
              Close
            </button>
          </div>
          {copyState === 'copied' && <p className="text-sm">Copied ✓</p>}
          {copyState === 'failed' && (
            <p className="text-sm">Copy failed — select and copy manually.</p>
          )}
        </div>
      )}
    </div>
  )
}

export default CheckpointPromptModal
