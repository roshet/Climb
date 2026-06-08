// Tiny typed client for the local sidecar. Centralizes port resolution, URL
// building, and the "degrade gracefully on error" pattern that every window
// previously hand-rolled with its own empty catch blocks.
import { DEFAULT_SIDECAR_PORT } from './constants'

declare global {
  interface Window {
    sidecar?: { port: string }
  }
}

export function sidecarPort(): string {
  return window.sidecar?.port ?? DEFAULT_SIDECAR_PORT
}

export function sidecarUrl(path: string): string {
  const p = path.startsWith('/') ? path : `/${path}`
  return `http://localhost:${sidecarPort()}${p}`
}

/**
 * GET JSON from the sidecar. Returns `null` on any network error or non-OK
 * status so callers can render a safe fallback instead of throwing. Use
 * `sidecarUrl` directly when a caller needs the raw Response (e.g. to branch
 * on a specific status code).
 */
export async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(sidecarUrl(path))
    if (!res.ok) return null
    return (await res.json()) as T
  } catch {
    return null
  }
}

/** POST JSON to the sidecar. Returns `null` on network error or non-OK status. */
export async function postJson<T>(path: string, body: unknown): Promise<T | null> {
  try {
    const res = await fetch(sidecarUrl(path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) return null
    return (await res.json()) as T
  } catch {
    return null
  }
}
