/// <reference types="vite/client" />

/** Base URL for the ThoughtBridge backend API. */
export function apiUrl(path: string): string {
  const base = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
  return `${base.replace(/\/$/, '')}/${path.replace(/^\//, '')}`
}

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`)
  }
  return (await response.json()) as T
}

/** Typed GET helper. All backend reads go through here. */
export async function apiGet<T>(path: string): Promise<T> {
  return parseJson<T>(await fetch(apiUrl(path)))
}

/** Typed POST helper. All backend writes go through here. */
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return parseJson<T>(
    await fetch(apiUrl(path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}
