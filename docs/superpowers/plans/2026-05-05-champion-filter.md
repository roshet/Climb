# Champion Filter for Trend Chart — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add champion pills to the trend chart so the player can filter to their last 20 games on a specific champion.

**Architecture:** `TrendChart` gains a `port: string` prop and two new state vars (`selectedChampion`, `filteredMatches`). When a champion pill is tapped, it fetches `/matches?last_n=20&champion=X` and renders that data; "All" resets to the `matches` prop passed from `App.tsx`. `App.tsx` adds `port={port}` to the existing `<TrendChart>` call — one line change. No backend changes needed.

**Tech Stack:** React 18, TypeScript, Tailwind CSS

---

## File Structure

| File | Change |
|---|---|
| `src/chat/TrendChart.tsx` | Add `port` prop, champion filter state + fetch, pills UI |
| `src/chat/App.tsx` | Add `port={port}` to `<TrendChart>` call |

---

### Task 1: Add champion filter to TrendChart and wire port prop in App.tsx

Both files change together — `TrendChart` now requires `port` and `App.tsx` must supply it. Splitting them would produce a TypeScript error between commits.

**Files:**
- Modify: `src/chat/TrendChart.tsx`
- Modify: `src/chat/App.tsx`

No unit tests — pure rendering component with fetch side-effect. Verified by build + visual check.

- [ ] **Step 1: Replace `src/chat/TrendChart.tsx` entirely**

Current file is 66 lines. Replace with:

```tsx
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
    if (selectedChampion === null) {
      setFilteredMatches(null)
      return
    }
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
```

- [ ] **Step 2: Add `port={port}` to `<TrendChart>` in `src/chat/App.tsx`**

Find this line in `src/chat/App.tsx` (inside the history tab JSX, around line 178):

```tsx
          <TrendChart matches={matches} />
```

Replace with:

```tsx
          <TrendChart port={port} matches={matches} />
```

No other changes to `App.tsx`.

- [ ] **Step 3: Build and verify**

```
npm run build
```

Expected: zero TypeScript errors, build completes.

- [ ] **Step 4: Commit**

```bash
git add src/chat/TrendChart.tsx src/chat/App.tsx
git commit -m "feat: add champion filter pills to trend chart"
```
