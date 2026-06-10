// Shown when the sidecar (the local analyst process) is unreachable for a couple
// of consecutive /status polls. It clears automatically once the sidecar — which
// the Electron main process auto-restarts — answers again.
export function OfflineBanner({ offline }: { offline: boolean }) {
  if (!offline) return null
  return (
    <div
      role="alert"
      className="mx-3 mt-2 px-3 py-2 bg-amber-950/60 border border-amber-500/40 rounded-lg flex items-center gap-2 flex-shrink-0"
    >
      <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse shrink-0" />
      <p className="text-amber-300 text-[11px]">Analyst offline — reconnecting…</p>
    </div>
  )
}
