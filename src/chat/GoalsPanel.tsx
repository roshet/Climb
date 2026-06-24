import { useCallback, useEffect, useState } from 'react'
import { getJson, postJson, delJson } from '../shared/api'
import type { Goal, GoalMetricInfo, BenchmarkResponse, BenchmarkMetric } from '../shared/types'

const COMPARISON_WORDS: Record<Goal['comparison'], string> = {
  lte: 'at most',
  gte: 'at least',
}

const titleCase = (s: string) => s.charAt(0) + s.slice(1).toLowerCase()

/** Is the player's average on the good side of the tier benchmark? */
function meetsTier(m: BenchmarkMetric): boolean | null {
  if (m.your_avg === null || m.tier_avg === null) return null
  return m.comparison === 'lte' ? m.your_avg <= m.tier_avg : m.your_avg >= m.tier_avg
}

export function GoalsPanel() {
  const [goals, setGoals] = useState<Goal[]>([])
  const [metrics, setMetrics] = useState<GoalMetricInfo[]>([])
  const [metric, setMetric] = useState('')
  const [target, setTarget] = useState('')
  const [bench, setBench] = useState<BenchmarkResponse | null>(null)

  const refreshGoals = useCallback(async () => {
    const data = await getJson<Goal[]>('/goals')
    setGoals(Array.isArray(data) ? data : [])
  }, [])

  useEffect(() => {
    refreshGoals()
    getJson<GoalMetricInfo[]>('/goals/metrics').then(data => {
      const list = Array.isArray(data) ? data : []
      setMetrics(list)
      if (list.length > 0) setMetric(list[0].key)
    })
  }, [refreshGoals])

  useEffect(() => {
    getJson<BenchmarkResponse>('/benchmarks').then(d => setBench(d ?? null))
  }, [])

  const handleAdd = useCallback(async () => {
    const value = parseFloat(target)
    if (!metric || Number.isNaN(value) || value <= 0) return
    await postJson<Goal>('/goals', { metric, target: value })
    setTarget('')
    await refreshGoals()
  }, [metric, target, refreshGoals])

  const handleDelete = useCallback(async (id: number) => {
    await delJson(`/goals/${id}`)
    await refreshGoals()
  }, [refreshGoals])

  return (
    <div className="flex-1 overflow-y-auto px-4 py-3">
      <div className="text-[9px] font-bold tracking-wider text-indigo-400 mb-2">
        🎯 GOALS
      </div>

      {bench && bench.status !== 'none' && (
        <div className="mb-4 bg-[#1a1a3a] border border-indigo-500/40 rounded-lg px-3 py-2">
          <div className="text-[10px] font-bold text-indigo-300 mb-2">
            📊 Benchmarks vs {bench.target_tier ? titleCase(bench.target_tier) : ''}
          </div>
          {bench.status === 'harvesting' || bench.metrics.length === 0 ? (
            <div className="text-gray-500 text-xs">Building your benchmarks…</div>
          ) : (
            <div className="flex flex-col gap-1">
              {bench.metrics.map(m => {
                const good = meetsTier(m)
                return (
                  <div
                    key={m.metric_key}
                    data-testid={`bench-${m.metric_key}`}
                    className="flex items-center text-xs"
                  >
                    <span className="text-gray-300 w-24">{m.label}</span>
                    <span
                      className={
                        good === null ? 'text-gray-400'
                          : good ? 'text-green-400' : 'text-red-400'
                      }
                    >
                      {m.your_avg ?? '—'}
                    </span>
                    <span className="text-gray-600 mx-1">vs</span>
                    <span className="text-gray-300">
                      {m.tier_avg ?? 'not enough data'}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {goals.length === 0 ? (
        <div className="text-gray-500 text-xs mb-3">No goals yet — add one below.</div>
      ) : (
        <div className="flex flex-col gap-2 mb-4">
          {goals.map(g => (
            <div
              key={g.id}
              className="bg-[#1a1a3a] border border-indigo-500/40 rounded-lg px-3 py-2"
            >
              <div className="flex items-center">
                <span className="text-sm font-semibold text-white">
                  {g.label} {COMPARISON_WORDS[g.comparison]} {g.target}
                </span>
                <span
                  data-testid={`streak-${g.id}`}
                  className="ml-2 text-[10px] font-semibold text-green-400"
                  title="Current streak"
                >
                  🔥 {g.streak}
                </span>
                <button
                  onClick={() => handleDelete(g.id)}
                  aria-label="Delete goal"
                  className="ml-auto text-gray-500 hover:text-red-400 text-sm leading-none px-1"
                >
                  ✕
                </button>
              </div>
              {g.history.length > 0 && (
                <div className="flex items-center gap-1.5 mt-1.5">
                  <span className="text-gray-600 text-[9px]">last {g.history.length}</span>
                  <div className="flex gap-1">
                    {g.history.map((met, i) => (
                      <span
                        key={`dot-${g.id}-${i}`}
                        className={`w-2 h-2 rounded-full ${met ? 'bg-green-400' : 'bg-red-500'}`}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="bg-[#1a1a3a] border border-white/10 rounded-lg px-3 py-2 flex items-center gap-2">
        <select
          value={metric}
          onChange={e => setMetric(e.target.value)}
          className="bg-[#0f0f23] text-white text-xs rounded px-2 py-1 [color-scheme:dark]"
        >
          {metrics.map(m => (
            <option key={m.key} value={m.key}>{m.label}</option>
          ))}
        </select>
        <input
          type="number"
          value={target}
          onChange={e => setTarget(e.target.value)}
          aria-label="Target value"
          placeholder="target"
          className="bg-[#0f0f23] text-white text-xs rounded px-2 py-1 w-20"
        />
        <button
          onClick={handleAdd}
          className="ml-auto text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1 rounded transition-colors"
        >
          Add
        </button>
      </div>
    </div>
  )
}
