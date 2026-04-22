import { useEffect, useState } from 'react'
import { MomentCard } from '../popup/MomentCard'
import { POSITIVE_TYPES } from '../popup/constants'

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

interface GameDetailProps {
  matchId: string
  port: string
  onBack: () => void
  onAskAboutGame: (matchId: string) => void
}

function formatDuration(secs: number): string {
  return `${Math.floor(secs / 60)}m`
}

export function GameDetail({ matchId, port, onBack, onAskAboutGame }: GameDetailProps) {
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<Filter>('all')

  useEffect(() => {
    setLoading(true)
    setFilter('all')
    fetch(`http://localhost:${port}/analysis/${matchId}`)
      .then(r => r.ok ? r.json() : null)
      .then((data: Analysis | null) => { setAnalysis(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [matchId, port])

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-gray-500 text-sm">Loading analysis...</p>
      </div>
    )
  }

  if (!analysis) {
    return (
      <div className="flex-1 flex items-center justify-center flex-col gap-2">
        <p className="text-red-400 text-sm">Could not load analysis.</p>
        <button onClick={onBack} className="text-indigo-400 text-xs hover:underline">← Back to History</button>
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
    <div className="flex-1 overflow-y-auto px-4 py-3">
      <button onClick={onBack} className="text-indigo-400 text-xs hover:underline mb-3 block">
        ← History
      </button>

      <div className="grid grid-cols-4 gap-1.5 mb-3">
        <div className="bg-[#1e1e3a] rounded-lg p-2 text-center">
          <p className="text-gray-500 text-[8px] uppercase tracking-wide mb-0.5">Champion</p>
          <p className="text-purple-400 text-[11px] font-bold truncate">{analysis.champion}</p>
          {analysis.role && <p className="text-gray-500 text-[8px] truncate">{analysis.role}</p>}
        </div>
        <div className={`${isWin ? 'bg-green-900/30' : 'bg-red-900/30'} rounded-lg p-2 text-center`}>
          <p className="text-gray-500 text-[8px] uppercase tracking-wide mb-0.5">Result</p>
          <p className={`${isWin ? 'text-green-400' : 'text-red-400'} text-[11px] font-bold uppercase`}>{analysis.result}</p>
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

      <div className="flex gap-2 mb-3">
        {(['all', 'positive', 'negative'] as Filter[]).map(f => {
          const label = f === 'all'
            ? `All · ${analysis.moments.length}`
            : f === 'positive'
            ? `✓ Good · ${positiveCount}`
            : `⚠ Fix · ${negativeCount}`
          return (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded-full px-3 py-1 text-[11px] font-semibold transition-colors ${
                filter === f ? 'bg-indigo-700 text-white' : 'bg-[#1e1e3a] text-gray-400 hover:text-white'
              }`}
            >
              {label}
            </button>
          )
        })}
      </div>

      <div className="mb-3">
        {filteredMoments.length === 0
          ? <p className="text-gray-400 text-sm">No moments in this category.</p>
          : filteredMoments.map(m => (
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

      <button
        onClick={() => onAskAboutGame(matchId)}
        className="w-full py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg transition-colors"
      >
        Ask about this game →
      </button>
    </div>
  )
}
