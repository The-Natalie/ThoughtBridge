import { useEffect, useState } from 'react'

import {
  deleteArtifact,
  getArtifact,
  listArtifacts,
  postArtifact,
  uploadArtifact,
} from '../api/artifacts'
import type {
  ArtifactDetail,
  ArtifactSourceType,
  ArtifactSummary,
} from '../api/types'

const SOURCE_TYPES: ArtifactSourceType[] = ['note', 'paste', 'summary']

function rowLabel(a: ArtifactSummary): string {
  return `${a.title || '(untitled)'} · ${a.source_type} · ${a.chunk_count} chunks · ${a.fact_count} facts`
}

/** Capture view: typed/pasted notes plus .txt/.md/.pdf/.docx uploads. */
function CaptureView() {
  const [artifacts, setArtifacts] = useState<ArtifactSummary[] | null>(null)
  const [sourceType, setSourceType] = useState<ArtifactSourceType>('note')
  const [titleInput, setTitleInput] = useState('')
  const [contentInput, setContentInput] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [fileKey, setFileKey] = useState(0)
  const [detail, setDetail] = useState<ArtifactDetail | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const items = await listArtifacts()
        if (!cancelled) setArtifacts(items)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Request failed')
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  async function refresh() {
    setArtifacts(await listArtifacts())
  }

  async function capture() {
    if (!contentInput.trim() || loading) return
    setLoading(true)
    setError(null)
    setNotice(null)
    try {
      const created = await postArtifact({
        source_type: sourceType,
        title: titleInput.trim(),
        content: contentInput,
      })
      setNotice(`Captured ${created.artifact_id.slice(0, 8)}… (${created.chunks} chunks)`)
      setTitleInput('')
      setContentInput('')
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  async function upload() {
    if (!file || loading) return
    setLoading(true)
    setError(null)
    setNotice(null)
    try {
      const created = await uploadArtifact(file)
      const pages = created.pages === null ? '' : `, ${created.pages} pages`
      setNotice(
        `Uploaded ${file.name}: ${created.extracted_chars} chars, ${created.chunks} chunks${pages}`,
      )
      setFile(null)
      setFileKey((k) => k + 1)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  async function openDetail(id: string) {
    if (loading) return
    setLoading(true)
    setError(null)
    try {
      setDetail(await getArtifact(id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  async function remove(id: string, label: string) {
    if (loading) return
    setLoading(true)
    setError(null)
    setNotice(null)
    try {
      const result = await deleteArtifact(id)
      setNotice(
        `Deleted ${label}: ${result.deleted.chunks ?? 0} chunks, ${result.deleted.facts ?? 0} facts removed, ${result.unlinked.facts ?? 0} facts unlinked.`,
      )
      setDetail((prev) => (prev !== null && prev.id === id ? null : prev))
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <div role="alert" className="rounded border border-red-500 px-3 py-2 text-sm">
          <span>{error}</span>{' '}
          <button type="button" aria-label="Dismiss error" onClick={() => setError(null)} className="underline">
            Dismiss
          </button>
        </div>
      )}

      {notice && (
        <p role="status" className="rounded border px-3 py-2 text-sm">
          {notice}
        </p>
      )}

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-semibold">Capture text</legend>
        <label className="flex flex-col gap-1 text-sm">
          Source type
          <select
            aria-label="Source type"
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value as ArtifactSourceType)}
            disabled={loading}
            className="rounded border px-3 py-1 text-sm"
          >
            {SOURCE_TYPES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <input
          aria-label="Title (optional)"
          value={titleInput}
          onChange={(e) => setTitleInput(e.target.value)}
          placeholder="Title (optional)"
          disabled={loading}
          className="rounded border px-3 py-1 text-sm"
        />
        <textarea
          aria-label="Content"
          value={contentInput}
          onChange={(e) => setContentInput(e.target.value)}
          placeholder="Type or paste a note…"
          disabled={loading}
          rows={6}
          className="rounded border px-3 py-1 text-sm"
        />
        <button
          type="button"
          aria-label="Capture"
          onClick={() => void capture()}
          disabled={loading || !contentInput.trim()}
          className="self-start rounded border px-3 py-1 text-sm"
        >
          Capture
        </button>
      </fieldset>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-semibold">Upload file</legend>
        <input
          key={fileKey}
          type="file"
          aria-label="Upload file"
          accept=".txt,.md,.pdf,.docx"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          disabled={loading}
          className="text-sm"
        />
        <button
          type="button"
          aria-label="Upload"
          onClick={() => void upload()}
          disabled={loading || file === null}
          className="self-start rounded border px-3 py-1 text-sm"
        >
          Upload
        </button>
      </fieldset>

      <p className="text-xs">Pasted content is stored verbatim — don&apos;t paste secrets or credentials.</p>

      <section aria-label="Captured artifacts" className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold">Captured artifacts</h2>
        {artifacts === null ? (
          <p className="text-sm">Loading artifacts…</p>
        ) : artifacts.length === 0 ? (
          <p className="text-sm">No captures yet — write a note or upload a file above.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {artifacts.map((a) => (
              <div key={a.id} className="rounded border px-3 py-2">
                <p className="text-sm">{rowLabel(a)}</p>
                <div className="mt-1 flex gap-2">
                  <button
                    type="button"
                    aria-label={`View ${a.title || a.id.slice(0, 8)}`}
                    onClick={() => void openDetail(a.id)}
                    disabled={loading}
                    className="rounded border px-2 py-0.5 text-xs underline"
                  >
                    View
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete ${a.title || a.id.slice(0, 8)}`}
                    onClick={() => void remove(a.id, a.title || a.id.slice(0, 8))}
                    disabled={loading}
                    className="rounded border px-2 py-0.5 text-xs underline"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {detail && (
        <div className="rounded border px-3 py-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold">
              {detail.title || '(untitled)'} · {detail.source_type} · {detail.chunks.length} chunks ·{' '}
              {detail.fact_ids.length} facts · {detail.interpretation_ids.length} interpretations
            </p>
            <button
              type="button"
              aria-label="Close details"
              onClick={() => setDetail(null)}
              className="text-xs underline"
            >
              Close
            </button>
          </div>
          <p className="mt-1 whitespace-pre-wrap text-sm">{detail.content}</p>
        </div>
      )}
    </div>
  )
}

export default CaptureView
