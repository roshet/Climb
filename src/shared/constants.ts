// Shared renderer constants.

/** Fallback sidecar port when the Electron preload hasn't injected one. */
export const DEFAULT_SIDECAR_PORT = '8765'

/** Polling intervals (ms) for the windows that poll the sidecar. */
export const POLL_INTERVAL = {
  champSelect: 2000,
  live: 2000,
  status: 4000,
  /** How often the live overlay prunes expired alerts. */
  liveCleanup: 500,
} as const
