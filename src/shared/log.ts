// Renderer-side logging: forward uncaught errors to the Electron main process,
// which writes them to the central logfile (%APPDATA%/Climb/logs/main.log). The
// `window.electron` bridge is the single source of truth for the preload API and
// is declared here so every window shares one typed contract.

export interface SidecarConfig {
  riotApiKey: string
  geminiApiKey: string
  summonerName: string
  tagLine: string
  region: string
}

declare global {
  interface Window {
    electron: {
      setupComplete: (data: SidecarConfig) => void
      getConfig: () => Promise<SidecarConfig | null>
      onSetupError: (cb: (error: string) => void) => void
      log: (level: string, message: string) => void
    }
  }
}

/** Forward a message to the main-process logfile. Safe when the bridge is absent. */
export function logError(message: string): void {
  try {
    window.electron?.log?.('error', message)
  } catch { /* bridge unavailable */ }
}

let _installed = false

/**
 * Install global handlers that forward uncaught errors and unhandled promise
 * rejections to the main-process logfile. Call once per window. Idempotent.
 */
export function initRendererLogForwarding(): void {
  if (_installed) return
  _installed = true

  window.addEventListener('error', (e: ErrorEvent) => {
    logError(`uncaught: ${e.message} (${e.filename}:${e.lineno})`)
  })
  window.addEventListener('unhandledrejection', (e: PromiseRejectionEvent) => {
    logError(`unhandledrejection: ${String(e.reason)}`)
  })
}
