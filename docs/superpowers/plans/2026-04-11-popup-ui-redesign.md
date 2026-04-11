# Popup UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the post-game popup with 4 stat tiles, collapsible moment cards with type labels, and a filter bar (All / Good / Fix).

**Architecture:** All changes are frontend-only except one: expose `role` from the `/analysis/:matchId` endpoint. `MomentCard.tsx` gains local expand/collapse state. `App.tsx` gains stat tiles, filter bar, and removes the `Takeaway` component. `Takeaway.tsx` is deleted.

**Tech Stack:** React 18 + TypeScript, Tailwind CSS, FastAPI (Python)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `sidecar/main.py` | **MODIFY** | Add `role` to `/analysis/:matchId` response |
| `src/popup/MomentCard.tsx` | **MODIFY** | Collapsible cards with type label + timestamp row |
| `src/popup/App.tsx` | **MODIFY** | Stat tiles, filter bar, remove Takeaway import |
| `src/popup/Takeaway.tsx` | **DELETE** | Replaced by stat tiles in App.tsx |

---

## Task 1: Expose `role` from `/analysis/:matchId` endpoint

**Files:**
- Modify: `sidecar/main.py`

The `match` object already has a `role` field (saved by `save_match`). We just need to include it in the response.

- [ ] **Step 1: Add `role` to the return dict in `get_analysis`**

In `sidecar/main.py`, find the `get_analysis` function. The current return dict starts with `"match_id": match_id`. Add `"role"` after `"champion"`:

```python
    return {
        "match_id": match_id,
        "champion": match.champion,
        "role": match.role,
        "result": match.result,
        "duration_secs": match.duration_secs,
        "kda": match.kda,
        "moments": [
            {
                "timestamp_secs": m.timestamp_secs,
                "moment_type": m.moment_type,
                "description": m.description,
                "counterfactual": m.counterfactual,
                "gold_impact": m.gold_impact,
            }
            for m in moments
        ],
    }
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
cd sidecar && venv/Scripts/python -c "import main; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add sidecar/main.py
git commit -m "feat: expose role in /analysis/:matchId response"
```

---

## Task 2: Rewrite `MomentCard.tsx` with type label + collapsible coaching note

**Files:**
- Modify: `src/popup/MomentCard.tsx`

- [ ] **Step 1: Replace the entire contents of `src/popup/MomentCard.tsx`**

```tsx
import { useState } from 'react'

interface MomentCardProps {
  timestampSecs: number
  momentType: string
  description: string
  counterfactual: string
  goldImpact: number
}

const POSITIVE_TYPES = new Set([
  'solo_kill', 'objective_secured', 'gank_assist', 'baron_secured', 'dragon_stack'
])

function formatType(momentType: string): string {
  return momentType.replace(/_/g, ' ').toUpperCase()
}

export function MomentCard({ timestampSecs, momentType, description, counterfactual, goldImpact }: MomentCardProps) {
  const [expanded, setExpanded] = useState(false)
  const mins = Math.floor(timestampSecs / 60)
  const secs = timestampSecs % 60
  const time = `${mins}:${secs.toString().padStart(2, '0')}`
  const isPositive = POSITIVE_TYPES.has(momentType)

  const borderColor = isPositive ? 'border-green-500/30' : 'border-yellow-500/30'
  const bgColor = isPositive ? 'bg-green-500/5' : 'bg-yellow-500/5'
  const labelColor = isPositive ? 'text-green-400' : 'text-yellow-400'
  const arrowColor = isPositive ? 'text-green-400' : 'text-yellow-400'
  const dividerColor = isPositive ? 'border-green-500/20' : 'border-yellow-500/20'
  const impactColor = isPositive ? 'text-green-500/50' : 'text-yellow-500/50'

  return (
    <div
      className={`border ${borderColor} ${bgColor} rounded-lg p-3 mb-2 cursor-pointer`}
      onClick={() => setExpanded(prev => !prev)}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`${labelColor} text-[9px] font-semibold tracking-widest uppercase`}>
              {formatType(momentType)}
            </span>
            <span className={`${labelColor} text-[9px] opacity-60`}>{time}</span>
          </div>
          <p className="text-white text-xs leading-snug">{description}</p>
        </div>
        <span className={`${arrowColor} text-xs mt-0.5 shrink-0`}>
          {expanded ? '▲' : '▼'}
        </span>
      </div>

      {expanded && (
        <div className={`border-t ${dividerColor} mt-2 pt-2`}>
          <p className="text-gray-400 text-[11px] leading-relaxed">
            {counterfactual || 'No coaching note available.'}
          </p>
          <p className={`${impactColor} text-[10px] mt-1`}>~{goldImpact}g impact</p>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd c:/Users/rohan/OneDrive/Desktop/NewProject && npx tsc --noEmit 2>&1 | head -10
```

Expected: zero errors

- [ ] **Step 3: Commit**

```bash
git add src/popup/MomentCard.tsx
git commit -m "feat: collapsible moment cards with type label and timestamp"
```

---

## Task 3: Rewrite `App.tsx` with stat tiles, filter bar, and remove Takeaway

**Files:**
- Modify: `src/popup/App.tsx`
- Delete: `src/popup/Takeaway.tsx`

- [ ] **Step 1: Replace the entire contents of `src/popup/App.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { MomentCard } from './MomentCard'
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

const POSITIVE_TYPES = new Set([
  'solo_kill', 'objective_secured', 'gank_assist', 'baron_secured', 'dragon_stack'
])

function getMatchId(): string | null {
  return new URLSearchParams(window.location.search).get('matchId')
}

function formatDuration(secs: number): string {
  return `${Math.floor(secs / 60)}m`
}

function PopupApp() {
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<Filter>('all')

  const port = window.sidecar?.port ?? '8765'
  const matchId = getMatchId()

  useEffect(() => {
    if (!matchId) { setLoading(false); return }
    fetch(`http://localhost:${port}/analysis/${matchId}`)
      .then(r => { if (!r.ok) throw new Error('not ok'); return r.json() })
      .then(data => { setAnalysis(data); setLoading(false) })
      .catch(() => setLoading(false))
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
          : filteredMoments.map((m, i) => (
              <MomentCard
                key={i}
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
```

- [ ] **Step 2: Delete `src/popup/Takeaway.tsx`**

```bash
rm src/popup/Takeaway.tsx
```

- [ ] **Step 3: TypeScript check**

```bash
cd c:/Users/rohan/OneDrive/Desktop/NewProject && npx tsc --noEmit 2>&1 | head -10
```

Expected: zero errors

- [ ] **Step 4: Commit**

```bash
git add src/popup/App.tsx && git rm src/popup/Takeaway.tsx
git commit -m "feat: popup redesign — stat tiles, filter bar, remove Takeaway"
```

---

## Task 4: Final verification

**Files:** None (verification only)

- [ ] **Step 1: Run TypeScript check**

```bash
cd c:/Users/rohan/OneDrive/Desktop/NewProject && npx tsc --noEmit
```

Expected: zero errors

- [ ] **Step 2: Build the app**

```bash
cd c:/Users/rohan/OneDrive/Desktop/NewProject && npm run build 2>&1 | tail -10
```

Expected: build succeeds with no errors

- [ ] **Step 3: Run trigger_analysis.py and check the popup**

```bash
cd sidecar && venv/Scripts/python trigger_analysis.py
```

Then start the app (`npm run dev`) and verify:
- 4 stat tiles show Champion, Result, KDA, Time
- Filter tabs show correct counts
- Clicking a card expands the coaching note inline
- Clicking the ✓ Good tab hides negative cards
- Clicking the ⚠ Fix tab hides positive cards
- "Ask about this game" button still works

- [ ] **Step 4: Git log check**

```bash
git log --oneline -6
```

Expected: clean trail with 3 new commits from this feature
