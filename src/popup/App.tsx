import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { MomentCard } from './MomentCard'
import { Takeaway } from './Takeaway'
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
  result: 'win' | 'loss'
  duration_secs: number
  kda: string
  moments: Moment[]
}

function getMatchId(): string | null {
  return new URLSearchParams(window.location.search).get('matchId')
}

function PopupApp() {
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [loading, setLoading] = useState(true)

  const port = window.sidecar?.port ?? '8765'
  const matchId = getMatchId()

  useEffect(() => {
    if (!matchId) { setLoading(false); return }
    fetch(`http://localhost:${port}/analysis/${matchId}`)
      .then(r => r.json())
      .then(data => { setAnalysis(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [matchId, port])

  const openChat = () => {
    fetch(`http://localhost:${port}/open-chat`, { method: 'POST' })
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

  return (
    <div className="bg-[#1a1a2e] min-h-screen p-4 text-white font-sans">
      <div className="flex justify-between items-center mb-3">
        <h1 className="text-white font-bold text-base">Game Analysis</h1>
        <button
          onClick={() => window.close()}
          className="text-gray-500 hover:text-white text-lg leading-none"
        >✕</button>
      </div>

      <div className="mb-3">
        <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Pivotal Moments</p>
        {analysis.moments.length === 0
          ? <p className="text-gray-400 text-sm">No pivotal moments detected.</p>
          : analysis.moments.map((m, i) => (
              <MomentCard key={i}
                timestampSecs={m.timestamp_secs}
                momentType={m.moment_type}
                description={m.description}
                counterfactual={m.counterfactual}
                goldImpact={m.gold_impact}
              />
            ))
        }
      </div>

      <Takeaway
        champion={analysis.champion}
        result={analysis.result}
        durationSecs={analysis.duration_secs}
        kda={analysis.kda}
      />

      <button
        onClick={openChat}
        className="w-full mt-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg transition-colors"
      >
        Ask about this game →
      </button>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<PopupApp />)
