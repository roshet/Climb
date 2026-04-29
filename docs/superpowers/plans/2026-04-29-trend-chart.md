# Trend Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bar chart to the top of the History tab showing gold lost or mistake count per game over the last 20 games, with a toggle between the two metrics.

**Architecture:** One new self-contained component `TrendChart` fetches `/matches?last_n=20` (no backend changes needed — both fields already exist), renders pure CSS flex bars, and exposes a metric toggle. One line change in `App.tsx` renders it above `HistoryList` when the history tab is open and no game is selected.

**Tech Stack:** React 18, TypeScript, Tailwind CSS

---

## File Structure

| File | Change |
|---|---|
| `src/chat/TrendChart.tsx` | Create — fetches matches, renders bar chart + toggle |
| `src/chat/App.tsx` | Modify — import and render `<TrendChart port={port} />` above `<HistoryList>` |

---

### Task 1: Create TrendChart component

**Files:**
- Create: `src/chat/TrendChart.tsx`

No unit tests — pure rendering component with no logic beyond linear normalisation (per spec).

- [ ] **Step 1: Create `src/chat/TrendChart.tsx`**

```tsx
import { useState, useEffect } from 'react'

interface MatchRow {
  gold_lost: number
  moment_count: number
}

type Metric = 'gold_lost' | 'moment_count'

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

  function barColor(value: number): string {
    if (metric === 'moment_count') return 'bg-indigo-500'
    if (value < 500) return 'bg-green-500'
    if (value <= 1500) return 'bg-yellow-500'
    return 'bg-red-500'
  }

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
        {values.map((v, i) => (
          <div
            key={i}
            className={`flex-1 rounded-t-sm ${barColor(v)}`}
            style={{ height: `${(v / max) * 100}%` }}
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

- [ ] **Step 2: Build and verify**

```
npm run build
```

Expected: zero TypeScript errors, build completes.

- [ ] **Step 3: Commit**

```bash
git add src/chat/TrendChart.tsx
git commit -m "feat: add TrendChart component for gold lost / mistake count trend"
```

---

### Task 2: Render TrendChart in the history tab

**Files:**
- Modify: `src/chat/App.tsx`

Context: `App.tsx` currently renders `<HistoryList port={port} onSelect={setSelectedMatchId} />` when `tab === 'history' && selectedMatchId === null` (line 154–156). The chart goes above it, wrapped in a fragment.

- [ ] **Step 1: Add the import and update the history tab JSX in `src/chat/App.tsx`**

Add this import at the top of the file alongside the existing component imports:

```tsx
import { TrendChart } from './TrendChart'
```

Replace the existing history tab block (currently at lines 154–156):

```tsx
      {tab === 'history' && selectedMatchId === null && (
        <HistoryList port={port} onSelect={setSelectedMatchId} />
      )}
```

With:

```tsx
      {tab === 'history' && selectedMatchId === null && (
        <>
          <TrendChart port={port} />
          <HistoryList port={port} onSelect={setSelectedMatchId} />
        </>
      )}
```

- [ ] **Step 2: Build and verify**

```
npm run build
```

Expected: zero TypeScript errors, build completes.

- [ ] **Step 3: Commit**

```bash
git add src/chat/App.tsx
git commit -m "feat: show trend chart at top of history tab"
```
