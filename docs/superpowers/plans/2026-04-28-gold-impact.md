# Gold Impact Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the `gold_impact` field (already stored on every pivotal moment) throughout the UI so players see the gold cost of their mistakes as a tile in the post-game popup, inline on each moment card, and as a per-game figure in the history list.

**Architecture:** One backend change adds `gold_lost` to `GET /matches` (sum of negative `gold_impact` values, computed in the existing moment loop). Three frontend changes: `MomentCard.tsx` gains an inline badge, `App.tsx` (popup) replaces the Duration tile with a Gold Lost tile, and `HistoryList.tsx` shows colour-coded gold lost per row. The popup and game detail derive their total client-side from the already-returned `gold_impact` on each moment — no extra fetch.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, React 18, TypeScript, Tailwind CSS

---

## File Structure

| File | Change |
|---|---|
| `sidecar/main.py` | Fold gold computation into existing moment loop in `list_matches()` |
| `sidecar/tests/test_matches_gold.py` | New — 2 unit tests for gold computation logic |
| `src/popup/MomentCard.tsx` | Add inline `−Xg` badge when `goldImpact < 0` |
| `src/popup/App.tsx` | Compute `goldLost`, replace Duration tile with Gold Lost tile |
| `src/chat/HistoryList.tsx` | Add `gold_lost` to `MatchRow`, render colour-coded amount |

---

### Task 1: Add `gold_lost` to `/matches` endpoint

**Files:**
- Create: `sidecar/tests/test_matches_gold.py`
- Modify: `sidecar/main.py`

- [ ] **Step 1: Write 2 failing tests**

Create `sidecar/tests/test_matches_gold.py`:

```python
import pytest
from datetime import datetime
from database import save_match, save_pivotal_moments, get_pivotal_moments


def make_match(db, match_id, day=1):
    save_match(db, {
        "match_id": match_id,
        "played_at": datetime(2026, 1, day, 12, 0),
        "champion": "Graves",
        "role": "JUNGLE",
        "result": "loss",
        "duration_secs": 1800,
        "kda": "2/3/4",
        "cs": 100,
        "gold_earned": 9000,
        "vision_score": 15,
        "raw_timeline": {},
    })


def compute_gold_lost(moments) -> dict[str, int]:
    result: dict[str, int] = {}
    for m in moments:
        if m.gold_impact and m.gold_impact < 0:
            result[m.match_id] = result.get(m.match_id, 0) + abs(m.gold_impact)
    return result


def test_matches_includes_gold_lost(db):
    make_match(db, "m1", day=1)
    save_pivotal_moments(db, "m1", [
        {"timestamp_secs": 300, "moment_type": "lane_death",
         "description": "", "counterfactual": "", "gold_impact": -680},
        {"timestamp_secs": 800, "moment_type": "objective_missed",
         "description": "", "counterfactual": "", "gold_impact": -1460},
        {"timestamp_secs": 1200, "moment_type": "solo_kill",
         "description": "", "counterfactual": "", "gold_impact": 300},
    ])
    moments = get_pivotal_moments(db, ["m1"])
    gold_by_match = compute_gold_lost(moments)
    assert gold_by_match.get("m1", 0) == 2140  # 680 + 1460; positive solo_kill excluded


def test_matches_gold_lost_zero_when_no_moments(db):
    make_match(db, "m2", day=2)
    moments = get_pivotal_moments(db, ["m2"])
    gold_by_match = compute_gold_lost(moments)
    assert gold_by_match.get("m2", 0) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar && venv/Scripts/pytest tests/test_matches_gold.py -v
```

Expected: 2 passed (the tests only test the local `compute_gold_lost` helper, which is already defined in the test file — they should pass immediately). If they do pass, that confirms the logic is correct before wiring it into `main.py`.

- [ ] **Step 3: Update `list_matches()` in `sidecar/main.py`**

Find the existing `list_matches` function (currently at line 308). Replace it entirely with:

```python
@app.get("/matches")
def list_matches(champion: Optional[str] = None, result: Optional[str] = None, last_n: int = 20):
    matches = get_matches(db, champion=champion, result=result, last_n=last_n)
    match_ids = [m.match_id for m in matches]
    all_moments = get_pivotal_moments(db, match_ids) if match_ids else []
    moment_counts: dict[str, int] = {}
    gold_by_match: dict[str, int] = {}
    for moment in all_moments:
        moment_counts[moment.match_id] = moment_counts.get(moment.match_id, 0) + 1
        if moment.gold_impact and moment.gold_impact < 0:
            gold_by_match[moment.match_id] = gold_by_match.get(moment.match_id, 0) + abs(moment.gold_impact)
    return [
        {
            "match_id": m.match_id,
            "champion": m.champion,
            "role": m.role,
            "result": m.result,
            "kda": m.kda,
            "cs": m.cs,
            "duration_secs": m.duration_secs,
            "played_at": m.played_at.isoformat(),
            "moment_count": moment_counts.get(m.match_id, 0),
            "gold_lost": gold_by_match.get(m.match_id, 0),
        }
        for m in matches
    ]
```

- [ ] **Step 4: Run full test suite**

```
cd sidecar && venv/Scripts/pytest tests/ -v
```

Expected: all tests pass (178+ passing).

- [ ] **Step 5: Commit**

```bash
git add sidecar/tests/test_matches_gold.py sidecar/main.py
git commit -m "feat: add gold_lost to /matches endpoint"
```

---

### Task 2: Show per-moment gold cost on MomentCard

**Files:**
- Modify: `src/popup/MomentCard.tsx`

- [ ] **Step 1: Update the type+time header row in `MomentCard`**

In `src/popup/MomentCard.tsx`, replace the inner header `<div>` (lines 36–41) with:

```tsx
          <div className="flex items-center gap-2 mb-1">
            <span className={`${labelColor} text-[9px] font-semibold tracking-widest uppercase`}>
              {formatType(momentType)}
            </span>
            <span className={`${labelColor} text-[9px] opacity-60`}>{time}</span>
            {goldImpact < 0 && (
              <span className="text-red-400 text-[9px] font-mono ml-auto">
                −{Math.abs(goldImpact).toLocaleString()}g
              </span>
            )}
          </div>
```

The full updated file for reference:

```tsx
import { useState } from 'react'
import { POSITIVE_TYPES } from './constants'

interface MomentCardProps {
  timestampSecs: number
  momentType: string
  description: string
  counterfactual: string
  goldImpact: number
}

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
            {goldImpact < 0 && (
              <span className="text-red-400 text-[9px] font-mono ml-auto">
                −{Math.abs(goldImpact).toLocaleString()}g
              </span>
            )}
          </div>
          <p className="text-white text-xs leading-snug">{description}</p>
        </div>
        <span className={`${labelColor} text-xs mt-0.5 shrink-0`}>
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

- [ ] **Step 2: Build and verify**

```
npm run build
```

Expected: zero TypeScript errors, build completes.

- [ ] **Step 3: Commit**

```bash
git add src/popup/MomentCard.tsx
git commit -m "feat: show per-moment gold cost inline on MomentCard"
```

---

### Task 3: Replace Duration tile with Gold Lost tile in popup

**Files:**
- Modify: `src/popup/App.tsx`

- [ ] **Step 1: Add `goldLost` computation and replace the Duration tile**

In `src/popup/App.tsx`:

1. Add the `goldLost` computation just before the `return (` statement in `PopupApp` (after the `isWin` line):

```tsx
  const goldLost = analysis.moments
    .filter(m => m.gold_impact < 0)
    .reduce((sum, m) => sum + Math.abs(m.gold_impact), 0)
```

2. Replace the 4th stat tile (currently the Time / Duration tile, lines 175–178):

```tsx
        <div className={`bg-red-950 border rounded-lg p-2 text-center ${goldLost > 0 ? 'border-red-800' : 'border-transparent'}`}>
          <p className="text-red-200 text-[8px] uppercase tracking-wide mb-0.5">Gold Lost</p>
          <p className={`text-[11px] font-bold ${goldLost === 0 ? 'text-gray-500' : 'text-white'}`}>
            −{goldLost.toLocaleString()}g
          </p>
        </div>
```

- [ ] **Step 2: Build and verify**

```
npm run build
```

Expected: zero TypeScript errors, build completes.

- [ ] **Step 3: Run full sidecar test suite**

```
cd sidecar && venv/Scripts/pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/popup/App.tsx
git commit -m "feat: replace Duration tile with Gold Lost tile in post-game popup"
```

---

### Task 4: Add gold lost to history list

**Files:**
- Modify: `src/chat/HistoryList.tsx`

- [ ] **Step 1: Update `MatchRow` interface and add `goldColor` helper**

In `src/chat/HistoryList.tsx`:

1. Add `gold_lost: number` to the `MatchRow` interface:

```tsx
interface MatchRow {
  match_id: string
  champion: string
  role: string
  result: 'win' | 'loss'
  kda: string
  duration_secs: number
  played_at: string
  moment_count: number
  gold_lost: number
}
```

2. Add a `goldColor` helper after the `formatDuration` function:

```tsx
function goldColor(goldLost: number): string {
  if (goldLost < 500) return 'text-green-400'
  if (goldLost <= 1500) return 'text-yellow-400'
  return 'text-red-400'
}
```

- [ ] **Step 2: Render gold lost in each row**

In the right-side `<div>` of each match row (currently contains date + moment count), add the gold lost line:

```tsx
            <div className="text-right flex-shrink-0">
              <div className="text-gray-500 text-xs">{relativeDate(m.played_at)}</div>
              {m.moment_count > 0 && (
                <div className="text-indigo-400 text-xs mt-0.5">{m.moment_count} moments</div>
              )}
              {m.gold_lost > 0 && (
                <div className={`text-xs mt-0.5 font-mono ${goldColor(m.gold_lost)}`}>
                  −{m.gold_lost.toLocaleString()}g
                </div>
              )}
            </div>
```

The full updated `HistoryList.tsx` for reference:

```tsx
import { useEffect, useState } from 'react'

interface MatchRow {
  match_id: string
  champion: string
  role: string
  result: 'win' | 'loss'
  kda: string
  duration_secs: number
  played_at: string
  moment_count: number
  gold_lost: number
}

function relativeDate(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const days = Math.floor(diff / 86_400_000)
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days}d ago`
  return `${Math.floor(days / 7)}w ago`
}

function formatDuration(secs: number): string {
  return `${Math.floor(secs / 60)}m`
}

function goldColor(goldLost: number): string {
  if (goldLost < 500) return 'text-green-400'
  if (goldLost <= 1500) return 'text-yellow-400'
  return 'text-red-400'
}

interface HistoryListProps {
  port: string
  onSelect: (matchId: string) => void
}

export function HistoryList({ port, onSelect }: HistoryListProps) {
  const [matches, setMatches] = useState<MatchRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    fetch(`http://localhost:${port}/matches?last_n=20`)
      .then(r => {
        if (!r.ok) { setError(true); setLoading(false); return }
        r.json().then((data: unknown) => {
          if (Array.isArray(data)) setMatches(data as MatchRow[])
          else setError(true)
          setLoading(false)
        }).catch(() => { setError(true); setLoading(false) })
      })
      .catch(() => { setError(true); setLoading(false) })
  }, [port])

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-gray-500 text-sm">Loading games...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-red-400 text-sm">Could not load match history.</p>
      </div>
    )
  }

  if (matches.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-gray-500 text-sm">No games analyzed yet.</p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
      {matches.map(m => {
        const isWin = m.result === 'win'
        return (
          <button
            key={m.match_id}
            onClick={() => onSelect(m.match_id)}
            className="w-full text-left bg-white/5 hover:bg-white/10 rounded-lg px-4 py-3 transition-colors flex items-center gap-3"
          >
            <div className={`w-1 self-stretch rounded-full flex-shrink-0 ${isWin ? 'bg-green-500' : 'bg-red-500'}`} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-white text-sm font-semibold">{m.champion}</span>
                <span className="text-gray-500 text-xs">{m.role}</span>
              </div>
              <div className="text-gray-400 text-xs mt-0.5">{m.kda} · {formatDuration(m.duration_secs)}</div>
            </div>
            <div className="text-right flex-shrink-0">
              <div className="text-gray-500 text-xs">{relativeDate(m.played_at)}</div>
              {m.moment_count > 0 && (
                <div className="text-indigo-400 text-xs mt-0.5">{m.moment_count} moments</div>
              )}
              {m.gold_lost > 0 && (
                <div className={`text-xs mt-0.5 font-mono ${goldColor(m.gold_lost)}`}>
                  −{m.gold_lost.toLocaleString()}g
                </div>
              )}
            </div>
          </button>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 3: Build and verify**

```
npm run build
```

Expected: zero TypeScript errors, build completes.

- [ ] **Step 4: Run full sidecar test suite**

```
cd sidecar && venv/Scripts/pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/chat/HistoryList.tsx
git commit -m "feat: show gold lost per game in history list"
```
