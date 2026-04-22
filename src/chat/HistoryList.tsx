import { useEffect, useState } from 'react'

interface MatchRow {
  match_id: string
  champion: string
  role: string
  result: 'win' | 'loss'
  kda: string
  duration_secs: number
  played_at: string
  moment_count: number
}

function relativeDate(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const days = Math.floor(diff / 86_400_000)
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days}d ago`
  return `${Math.floor(days / 7)}w ago`
}

function formatDuration(secs: number): string {
  return `${Math.floor(secs / 60)}m`
}

interface HistoryListProps {
  port: string
  onSelect: (matchId: string) => void
}

export function HistoryList({ port, onSelect }: HistoryListProps) {
  const [matches, setMatches] = useState<MatchRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`http://localhost:${port}/matches?last_n=20`)
      .then(r => r.ok ? r.json() : [])
      .then((data: MatchRow[]) => { setMatches(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [port])

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-gray-500 text-sm">Loading games...</p>
      </div>
    )
  }

  if (matches.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-gray-500 text-sm">No games analyzed yet.</p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
      {matches.map(m => {
        const isWin = m.result === 'win'
        return (
          <button
            key={m.match_id}
            onClick={() => onSelect(m.match_id)}
            className="w-full text-left bg-white/5 hover:bg-white/10 rounded-lg px-4 py-3 transition-colors flex items-center gap-3"
          >
            <div className={`w-1 self-stretch rounded-full flex-shrink-0 ${isWin ? 'bg-green-500' : 'bg-red-500'}`} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-white text-sm font-semibold">{m.champion}</span>
                <span className="text-gray-500 text-xs">{m.role}</span>
              </div>
              <div className="text-gray-400 text-xs mt-0.5">{m.kda} · {formatDuration(m.duration_secs)}</div>
            </div>
            <div className="text-right flex-shrink-0">
              <div className="text-gray-500 text-xs">{relativeDate(m.played_at)}</div>
              {m.moment_count > 0 && (
                <div className="text-indigo-400 text-xs mt-0.5">{m.moment_count} moments</div>
              )}
            </div>
          </button>
        )
      })}
    </div>
  )
}
