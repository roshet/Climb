import { useState, useEffect } from 'react'

interface MatchRow {
  match_id: string
  gold_lost: number
  moment_count: number
}

type Metric = 'gold_lost' | 'moment_count'

function barColor(metric: Metric, value: number): string {
  if (metric === 'moment_count') return 'bg-indigo-500'
  if (value < 500) return 'bg-green-500'
  if (value <= 1500) return 'bg-yellow-500'
  return 'bg-red-500'
}

interface TrendChartProps {
  port: string
}

export function TrendChart({ port }: TrendChartProps) {
  const [matches, setMatches] = useState<MatchRow[]>([])
  const [metric, setMetric] = useState<Metric>('gold_lost')

  useEffect(() => {
    fetch(`http://localhost:${port}/matches?last_n=20`)
      .then(r => r.ok ? r.json() : [])
      .then((data: unknown) => {
        if (Array.isArray(data)) setMatches((data as MatchRow[]).slice().reverse())
      })
      .catch(() => {})
  }, [port])

  if (matches.length === 0) return null

  const values = matches.map(m => m[metric])
  const max = Math.max(...values)

  if (max === 0) return null

  return (
    <div className="bg-[#0d0d1f] border-b border-white/10 px-4 py-3 flex-shrink-0">
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
        {matches.map(m => (
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
