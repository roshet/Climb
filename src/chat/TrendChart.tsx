import { useState, useEffect } from 'react'
import { MatchRow } from './types'

type Metric = 'gold_lost' | 'moment_count'

function barColor(metric: Metric, value: number): string {
  if (metric === 'moment_count') return 'bg-indigo-500'
  if (value < 500) return 'bg-green-500'
  if (value <= 1500) return 'bg-yellow-500'
  return 'bg-red-500'
}

interface TrendChartProps {
  port: string
  matches: MatchRow[]
}

export function TrendChart({ port, matches }: TrendChartProps) {
  const [metric, setMetric] = useState<Metric>('gold_lost')
  const [selectedChampion, setSelectedChampion] = useState<string | null>(null)
  const [filteredMatches, setFilteredMatches] = useState<MatchRow[] | null>(null)

  useEffect(() => {
    setFilteredMatches(null)
    if (selectedChampion === null) return
    fetch(`http://localhost:${port}/matches?last_n=20&champion=${encodeURIComponent(selectedChampion)}`)
      .then(r => r.ok ? r.json() : null)
      .then((data: unknown) => {
        if (Array.isArray(data)) setFilteredMatches((data as MatchRow[]).slice().reverse())
      })
      .catch(() => {})
  }, [port, selectedChampion])

  if (matches.length === 0) return null

  const champions: string[] = []
  for (let i = matches.length - 1; i >= 0; i--) {
    if (!champions.includes(matches[i].champion)) champions.push(matches[i].champion)
  }

  const displayMatches = selectedChampion ? (filteredMatches ?? matches) : matches
  const champGames = displayMatches.length
  const champWins = displayMatches.filter(m => m.result === 'win').length
  const champWinRate = champGames > 0 ? Math.round(champWins / champGames * 100) : 0
  const champAvgGold = champGames > 0 ? Math.round(displayMatches.reduce((s, m) => s + m.gold_lost, 0) / champGames) : 0
  const champAvgMistakes = champGames > 0 ? (displayMatches.reduce((s, m) => s + m.moment_count, 0) / champGames).toFixed(1) : '0.0'
  const values = displayMatches.map(m => m[metric])
  const max = Math.max(...values)

  if (max === 0) return null

  return (
    <div className="bg-[#0d0d1f] border-b border-white/10 px-4 py-3 flex-shrink-0">
      <div className="flex flex-wrap gap-1.5 mb-2">
        <button
          onClick={() => setSelectedChampion(null)}
          className={`text-[10px] px-2 py-0.5 rounded-full transition-colors ${
            selectedChampion === null
              ? 'bg-indigo-600 text-white font-semibold'
              : 'bg-transparent text-gray-500 border border-gray-700 hover:text-gray-300'
          }`}
        >
          All
        </button>
        {champions.map(champ => (
          <button
            key={champ}
            onClick={() => setSelectedChampion(champ)}
            className={`text-[10px] px-2 py-0.5 rounded-full transition-colors ${
              selectedChampion === champ
                ? 'bg-indigo-600 text-white font-semibold'
                : 'bg-transparent text-gray-500 border border-gray-700 hover:text-gray-300'
            }`}
          >
            {champ}
          </button>
        ))}
      </div>
      {selectedChampion !== null && (
        <div className="flex gap-3 mb-2 text-[10px]">
          <span className="text-gray-400">{champGames} game{champGames === 1 ? '' : 's'}</span>
          <span className="text-gray-600">·</span>
          <span className={champWinRate >= 50 ? 'text-green-400' : 'text-red-400'}>{champWinRate}% WR</span>
          <span className="text-gray-600">·</span>
          <span className={champAvgGold < 500 ? 'text-green-400' : champAvgGold <= 1500 ? 'text-yellow-400' : 'text-red-400'}>−{champAvgGold.toLocaleString()}g avg</span>
          <span className="text-gray-600">·</span>
          <span className="text-gray-400">{champAvgMistakes} mistakes/game</span>
        </div>
      )}
      <div className="flex gap-4 mb-2">
        <button
          onClick={() => setMetric('gold_lost')}
          className={`text-xs pb-0.5 transition-colors ${
            metric === 'gold_lost'
              ? 'text-white font-semibold border-b-2 border-indigo-500'
              : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          Gold Lost
        </button>
        <button
          onClick={() => setMetric('moment_count')}
          className={`text-xs pb-0.5 transition-colors ${
            metric === 'moment_count'
              ? 'text-white font-semibold border-b-2 border-indigo-500'
              : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          Mistakes
        </button>
      </div>
      <div className="flex items-end gap-[2px] h-16">
        {displayMatches.map(m => (
          <div
            key={m.match_id}
            className={`flex-1 rounded-t-sm ${barColor(metric, m[metric])}`}
            style={{ height: `${(m[metric] / max) * 100}%` }}
          />
        ))}
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-[9px] text-gray-600">← older</span>
        <span className="text-[9px] text-gray-600">recent →</span>
      </div>
    </div>
  )
}
