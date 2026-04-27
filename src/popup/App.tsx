import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { MomentCard } from './MomentCard'
import { POSITIVE_TYPES } from './constants'
import '../index.css'

declare global {
  interface Window { sidecar: { port: string } }
}

interface Moment {
  timestamp_secs: number
  moment_type: string
  description: string
  counterfactual: string
  gold_impact: number
}

interface Analysis {
  match_id: string
  champion: string
  role: string
  result: 'win' | 'loss'
  duration_secs: number
  kda: string
  moments: Moment[]
}

type Filter = 'all' | 'positive' | 'negative'

interface ImprovementPattern {
  label: 'recurring_issue' | 'win_condition'
  moment_type: string
  display: string
  had_in_game: boolean
  streak: number
  recent_rate: number
}

interface ImprovementData {
  champion: string
  patterns: ImprovementPattern[]
  window: number
}

function getMatchId(): string | null {
  return new URLSearchParams(window.location.search).get('matchId')
}

function formatDuration(secs: number): string {
  return `${Math.floor(secs / 60)}m`
}

function ImprovementRow({ pattern, window }: { pattern: ImprovementPattern; window: number }) {
  const { label, display, had_in_game, streak, recent_rate } = pattern
  const isIssue = label === 'recurring_issue'
  const name = display.toLowerCase()

  let text: string
  if (isIssue) {
    if (!had_in_game) {
      text = streak >= 2 ? `No ${name} · ${streak} clean in a row` : `No ${name} this game`
    } else {
      text = `${display} again · ${recent_rate}/${window} recent games`
    }
  } else {
    text = had_in_game ? `${display} — keep it up` : `No ${name} — usually your win condition`
  }

  const isPositive = (isIssue && !had_in_game) || (!isIssue && had_in_game)
  return (
    <div className={`border-l-2 rounded px-3 py-1.5 text-xs ${
      isPositive
        ? 'border-green-500 bg-green-950/80 text-green-200'
        : 'border-red-500 bg-red-950/80 text-red-200'
    }`}>
      <span className="mr-1">{isPositive ? '✓' : '⚠'}</span>
      {text}
    </div>
  )
}

function PopupApp() {
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [improvement, setImprovement] = useState<ImprovementData | null>(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<Filter>('all')

  const port = window.sidecar?.port ?? '8765'
  const matchId = getMatchId()

  useEffect(() => {
    if (!matchId) { setLoading(false); return }
    Promise.all([
      fetch(`http://localhost:${port}/analysis/${matchId}`)
        .then(r => { if (!r.ok) throw new Error('not ok'); return r.json() as Promise<Analysis> }),
      fetch(`http://localhost:${port}/improvement/${matchId}`)
        .then(r => r.ok ? r.json() as Promise<ImprovementData> : null)
        .catch(() => null),
    ]).then(([analysisData, improvementData]) => {
      setAnalysis(analysisData)
      setImprovement(improvementData)
      setLoading(false)
    }).catch(() => {
      setAnalysis(null)
      setImprovement(null)
      setLoading(false)
    })
  }, [matchId, port])

  const openChat = () => {
    fetch(`http://localhost:${port}/open-chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ match_id: matchId }),
    })
  }

  if (loading) {
    return (
      <div className="bg-[#1a1a2e] min-h-screen flex items-center justify-center">
        <p className="text-gray-400 text-sm">Analyzing game...</p>
      </div>
    )
  }

  if (!analysis) {
    return (
      <div className="bg-[#1a1a2e] min-h-screen flex items-center justify-center">
        <p className="text-red-400 text-sm">Could not load analysis.</p>
      </div>
    )
  }

  const positiveCount = analysis.moments.filter(m => POSITIVE_TYPES.has(m.moment_type)).length
  const negativeCount = analysis.moments.length - positiveCount

  const filteredMoments = analysis.moments.filter(m => {
    if (filter === 'positive') return POSITIVE_TYPES.has(m.moment_type)
    if (filter === 'negative') return !POSITIVE_TYPES.has(m.moment_type)
    return true
  })

  const isWin = analysis.result === 'win'

  return (
    <div className="bg-[#1a1a2e] min-h-screen p-4 text-white font-sans">

      {/* Header */}
      <div className="flex justify-between items-center mb-3">
        <h1 className="text-white font-bold text-base">Game Analysis</h1>
        <button
          onClick={() => window.close()}
          className="text-gray-500 hover:text-white text-lg leading-none"
        >✕</button>
      </div>

      {/* Stat tiles */}
      <div className="grid grid-cols-4 gap-1.5 mb-3">
        <div className="bg-[#1e1e3a] rounded-lg p-2 text-center">
          <p className="text-gray-500 text-[8px] uppercase tracking-wide mb-0.5">Champion</p>
          <p className="text-purple-400 text-[11px] font-bold truncate">{analysis.champion}</p>
          {analysis.role && <p className="text-gray-500 text-[8px] truncate">{analysis.role}</p>}
        </div>
        <div className={`${isWin ? 'bg-green-900/30' : 'bg-red-900/30'} rounded-lg p-2 text-center`}>
          <p className="text-gray-500 text-[8px] uppercase tracking-wide mb-0.5">Result</p>
          <p className={`${isWin ? 'text-green-400' : 'text-red-400'} text-[11px] font-bold uppercase`}>
            {analysis.result}
          </p>
        </div>
        <div className="bg-[#1e1e3a] rounded-lg p-2 text-center">
          <p className="text-gray-500 text-[8px] uppercase tracking-wide mb-0.5">KDA</p>
          <p className="text-white text-[11px] font-bold">{analysis.kda}</p>
        </div>
        <div className="bg-[#1e1e3a] rounded-lg p-2 text-center">
          <p className="text-gray-500 text-[8px] uppercase tracking-wide mb-0.5">Time</p>
          <p className="text-white text-[11px] font-bold">{formatDuration(analysis.duration_secs)}</p>
        </div>
      </div>

      {/* Improvement: vs your patterns */}
      {improvement && improvement.patterns.length > 0 && (
        <div className="mb-3">
          <p className="text-gray-500 text-[9px] uppercase tracking-wide mb-1.5">
            vs your patterns ({improvement.champion})
          </p>
          <div className="flex flex-col gap-1.5">
            {improvement.patterns.map(p => (
              <ImprovementRow key={p.moment_type} pattern={p} window={improvement.window} />
            ))}
          </div>
        </div>
      )}

      {/* Filter bar */}
      <div className="flex gap-2 mb-3">
        <button
          onClick={() => setFilter('all')}
          className={`rounded-full px-3 py-1 text-[11px] font-semibold transition-colors ${
            filter === 'all' ? 'bg-indigo-700 text-white' : 'bg-[#1e1e3a] text-gray-400 hover:text-white'
          }`}
        >
          All · {analysis.moments.length}
        </button>
        <button
          onClick={() => setFilter('positive')}
          className={`rounded-full px-3 py-1 text-[11px] font-semibold transition-colors ${
            filter === 'positive' ? 'bg-indigo-700 text-white' : 'bg-[#1e1e3a] text-gray-400 hover:text-white'
          }`}
        >
          ✓ Good · {positiveCount}
        </button>
        <button
          onClick={() => setFilter('negative')}
          className={`rounded-full px-3 py-1 text-[11px] font-semibold transition-colors ${
            filter === 'negative' ? 'bg-indigo-700 text-white' : 'bg-[#1e1e3a] text-gray-400 hover:text-white'
          }`}
        >
          ⚠ Fix · {negativeCount}
        </button>
      </div>

      {/* Moment cards */}
      <div className="mb-3">
        {filteredMoments.length === 0
          ? <p className="text-gray-400 text-sm">No moments in this category.</p>
          : filteredMoments.map((m) => (
              <MomentCard
                key={`${m.timestamp_secs}-${m.moment_type}`}
                timestampSecs={m.timestamp_secs}
                momentType={m.moment_type}
                description={m.description}
                counterfactual={m.counterfactual}
                goldImpact={m.gold_impact}
              />
            ))
        }
      </div>

      {/* Ask about game */}
      <button
        onClick={openChat}
        className="w-full py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg transition-colors"
      >
        Ask about this game →
      </button>

    </div>
  )
}

createRoot(document.getElementById('root')!).render(<PopupApp />)
