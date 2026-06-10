import { useState, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { initRendererLogForwarding } from '../shared/log'
import {
  ChampSelectPattern as Pattern,
  ChampSelectFocus as Focus,
  ChampSelectState,
} from '../shared/types'
import { getJson } from '../shared/api'
import { POLL_INTERVAL } from '../shared/constants'
import '../index.css'

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

function FocusCard({ focus, champion, coachingSentence }: {
  focus: Focus
  champion: string
  coachingSentence?: string | null
}) {
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
      {coachingSentence && (
        <p className="text-gray-400 text-[8px] italic mt-1.5 leading-relaxed">
          "{coachingSentence}"
        </p>
      )}
    </div>
  )
}

function ChampSelectApp() {
  const [state, setState] = useState<ChampSelectState | null>(null)
  const [coachingSentence, setCoachingSentence] = useState<string | null>(null)
  const lockedChampion = state?.locked_champion

  useEffect(() => {
    if (!lockedChampion) return
    setCoachingSentence(null)
    getJson<{ coaching_sentence?: string }>('/focus').then((data) => {
      setCoachingSentence(data?.coaching_sentence ?? null)
    })
  }, [lockedChampion])

  useEffect(() => {
    const poll = async () => {
      const data = await getJson<ChampSelectState>('/champ-select')
      if (data) setState(data)
    }
    poll()
    const interval = setInterval(poll, POLL_INTERVAL.champSelect)
    return () => clearInterval(interval)
  }, [])

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
        {champ_data?.focus && !champ_data.no_history && (
          <FocusCard
            focus={champ_data.focus}
            champion={locked_champion}
            coachingSentence={coachingSentence}
          />
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
        {champ_data?.matchups && champ_data.matchups.length > 0 && (
          <div className="px-3 py-2 border-t border-white/10">
            <div className="text-[8px] uppercase tracking-widest text-gray-500 mb-1.5">your tough matchups</div>
            {champ_data.matchups.map((m) => (
              <div key={m.opponent} className="flex justify-between items-center mb-1">
                <div>
                  <span className="text-[10px] text-gray-200">{m.opponent}</span>
                  {m.dominant_moment && (
                    <span className="text-[8px] text-gray-500 ml-1">
                      {m.dominant_moment.replace(/_/g, ' ')}
                    </span>
                  )}
                </div>
                <span className={`text-[10px] font-bold ${
                  m.win_rate < 0.4 ? 'text-red-400' : 'text-yellow-400'
                }`}>
                  {m.wins}W {m.losses}L
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

initRendererLogForwarding()
createRoot(document.getElementById('root')!).render(<ChampSelectApp />)
