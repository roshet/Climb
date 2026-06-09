import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { sidecarPort, sidecarUrl, getJson, postJson } from './api'

describe('sidecar api client', () => {
  beforeEach(() => {
    window.sidecar = { port: '9999' }
  })
  afterEach(() => {
    vi.restoreAllMocks()
    delete window.sidecar
  })

  it('uses the injected sidecar port', () => {
    expect(sidecarPort()).toBe('9999')
  })

  it('falls back to the default port when none is injected', () => {
    delete window.sidecar
    expect(sidecarPort()).toBe('8765')
  })

  it('builds absolute URLs, tolerating a missing leading slash', () => {
    expect(sidecarUrl('/focus')).toBe('http://localhost:9999/focus')
    expect(sidecarUrl('focus')).toBe('http://localhost:9999/focus')
  })

  it('getJson returns parsed JSON on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ hello: 'world' }),
    }))
    await expect(getJson<{ hello: string }>('/x')).resolves.toEqual({ hello: 'world' })
  })

  it('getJson returns null on a non-OK status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: () => Promise.resolve({}) }))
    await expect(getJson('/x')).resolves.toBeNull()
  })

  it('getJson returns null on a network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    await expect(getJson('/x')).resolves.toBeNull()
  })

  it('postJson sends a JSON body and returns parsed JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ ok: 1 }) })
    vi.stubGlobal('fetch', fetchMock)
    const res = await postJson<{ ok: number }>('/chat', { message: 'hi' })
    expect(res).toEqual({ ok: 1 })
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:9999/chat',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: 'hi' }),
      }),
    )
  })

  it('postJson returns null on a network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    await expect(postJson('/chat', {})).resolves.toBeNull()
  })
})
