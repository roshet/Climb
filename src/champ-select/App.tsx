import { useState, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import '../index.css'

declare global {
  interface Window { sidecar: { port: string } }
}

interface Pattern {
  label: 'recurring_issue' | 'win_condition'
  moment_type: string
  summary: string
}

interface Focus {
  moment_type: string
  label: string
  games_seen: number
  total_games: number
  avg_gold_lost: number
  champion_specific: boolean
}

interface ChampData {
  games: number
  wins: number
  win_rate: number
  no_history: boolean
  patterns: Pattern[]
  focus: Focus | null
}

interface ChampSelectState {
  in_champ_select: boolean
  locked_champion: string | null
  champ_data: ChampData | null
}

function PatternRow({ pattern }: { pattern: Pattern }) {
  const isIssue = pattern.label === 'recurring_issue'
  return (
    <div className={`border-l-2 rounded px-3 py-1.5 text-xs ${
      isIssue
        ? 'border-red-500 bg-red-950/80 text-red-200'
        : 'border-green-500 bg-green-950/80 text-green-200'
    }`}>
      <span className="mr-1">{isIssue ? '⚠' : '✓'}</span>
      {pattern.summary}
    </div>
  )
}

function FocusCard({ focus, champion }: { focus: Focus; champion: string }) {
  const scope = focus.champion_specific ? champion : 'All Champions'
  return (
    <div className="mx-2 mt-2 bg-[#1e1b4b] border border-indigo-500/60 rounded-lg px-3 py-2">
      <p className="text-indigo-300 text-[7px] font-bold uppercase tracking-widest mb-1">
        ⚡ Today's Focus · {scope}
      </p>
      <p className="text-white text-[11px] font-bold">{focus.label}</p>
      <p className="text-gray-400 text-[8px] mt-0.5">
        {focus.games_seen} of your last {focus.total_games} games
      </p>
      {focus.avg_gold_lost > 0 && (
        <p className="text-red-400 text-[8px] font-semibold mt-1">
          avg −{focus.avg_gold_lost.toLocaleString()}g per game
        </p>
      )}
    </div>
  )
}

function ChampSelectApp() {
  const [state, setState] = useState<ChampSelectState | null>(null)
  const port = window.sidecar?.port ?? '8765'

  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch(`http://localhost:${port}/champ-select`)
        if (!res.ok) return
        const data = await res.json() as ChampSelectState
        setState(data)
      } catch { /* sidecar not ready */ }
    }
    poll()
    const interval = setInterval(poll, 2000)
    return () => clearInterval(interval)
  }, [port])

  if (!state?.in_champ_select || !state.locked_champion) return null

  const { locked_champion, champ_data } = state

  return (
    <div className="fixed top-4 right-4 w-72 pointer-events-none select-none">
      <div className="bg-[#0d0d1f]/90 border border-indigo-900 rounded-xl shadow-2xl overflow-hidden">
        <div className="px-3 py-2 flex items-center gap-2 border-b border-white/10">
          <div className="w-7 h-7 rounded-full bg-purple-700 flex items-center justify-center text-white text-xs font-bold shrink-0">
            {locked_champion[0]}
          </div>
          <div className="flex-1 min-w-0">
            <span className="text-white text-sm font-semibold">{locked_champion}</span>
            {champ_data && !champ_data.no_history && (
              <span className="text-gray-400 text-xs ml-2">
                {champ_data.games} games · {Math.round(champ_data.win_rate * 100)}% WR
              </span>
            )}
          </div>
        </div>
        {champ_data?.focus && (
          <FocusCard focus={champ_data.focus} champion={locked_champion} />
        )}
        <div className="px-3 py-2 flex flex-col gap-1.5">
          {!champ_data || champ_data.no_history ? (
            <p className="text-gray-500 text-xs">No history yet for {locked_champion} — good luck!</p>
          ) : champ_data.patterns.length === 0 ? (
            <p className="text-gray-500 text-xs">No strong patterns found yet.</p>
          ) : (
            champ_data.patterns.map((p) => (
              <PatternRow key={p.moment_type} pattern={p} />
            ))
          )}
        </div>
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<ChampSelectApp />)
