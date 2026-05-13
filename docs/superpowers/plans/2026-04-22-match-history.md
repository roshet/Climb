# Match History + Game Detail View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a History tab to the main chat window so users can browse recent games and drill into any game's pivotal moments without waiting for the post-game popup.

**Architecture:** Add `tab` and `selectedMatchId` state to `App.tsx` to switch between a scrollable `HistoryList` and an inline `GameDetail` view; `GameDetail` reuses `MomentCard` and `POSITIVE_TYPES` from the existing popup. The `/matches` API endpoint gains `role`, `duration_secs`, and `moment_count` fields.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, FastAPI, SQLAlchemy

---

## File Map

| File | Change |
|------|--------|
| `sidecar/main.py` | Add `role`, `duration_secs`, `moment_count` to `/matches` response |
| `src/chat/HistoryList.tsx` | New — scrollable list of game rows |
| `src/chat/GameDetail.tsx` | New — inline game analysis view with back button |
| `src/chat/App.tsx` | Add tab state, selectedMatchId, chatMatchId; wire new components |

---

### Task 1: Extend `/matches` endpoint with role, duration_secs, moment_count

**Files:**
- Modify: `sidecar/main.py` (the `list_matches` function, around line 282)

Context: `get_pivotal_moments` is already imported at the top of `main.py`. The `Match` model already has `role` and `duration_secs` fields — they just aren't being serialised.

- [ ] **Step 1: Open `sidecar/main.py` and find the `list_matches` function**

It currently looks like this (around line 281):

```python
@app.get("/matches")
def list_matches(champion: Optional[str] = None, result: Optional[str] = None, last_n: int = 20):
    matches = get_matches(db, champion=champion, result=result, last_n=last_n)
    return [
        {
            "match_id": m.match_id,
            "champion": m.champion,
            "result": m.result,
            "kda": m.kda,
            "cs": m.cs,
            "played_at": m.played_at.isoformat(),
        }
        for m in matches
    ]
```

- [ ] **Step 2: Replace it with the updated version**

```python
@app.get("/matches")
def list_matches(champion: Optional[str] = None, result: Optional[str] = None, last_n: int = 20):
    matches = get_matches(db, champion=champion, result=result, last_n=last_n)
    match_ids = [m.match_id for m in matches]
    all_moments = get_pivotal_moments(db, match_ids) if match_ids else []
    moment_counts: dict[str, int] = {}
    for moment in all_moments:
        moment_counts[moment.match_id] = moment_counts.get(moment.match_id, 0) + 1
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
        }
        for m in matches
    ]
```

- [ ] **Step 3: Start the sidecar and verify the response**

```bash
cd sidecar
uvicorn main:app --port 8765 --reload
```

In a second terminal:
```bash
curl -s http://localhost:8765/matches | python -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d[0], indent=2)) if d else print('no matches')"
```

Expected: response object includes `role`, `duration_secs`, and `moment_count` fields. Example:
```json
{
  "match_id": "NA1_...",
  "champion": "Caitlyn",
  "role": "BOTTOM",
  "result": "win",
  "kda": "12/2/7",
  "cs": 241,
  "duration_secs": 1680,
  "played_at": "2026-04-20T18:32:00",
  "moment_count": 6
}
```

- [ ] **Step 4: Commit**

```bash
git add sidecar/main.py
git commit -m "feat: add role, duration_secs, moment_count to /matches endpoint"
```

---

### Task 2: Create HistoryList component

**Files:**
- Create: `src/chat/HistoryList.tsx`

This component fetches `/matches`, renders a scrollable list of game rows, and calls `onSelect(matchId)` when a row is clicked.

- [ ] **Step 1: Create `src/chat/HistoryList.tsx`**

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

interface HistoryListProps {
  port: string
  onSelect: (matchId: string) => void
}

export function HistoryList({ port, onSelect }: HistoryListProps) {
  const [matches, setMatches] = useState<MatchRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`http://localhost:${port}/matches?last_n=20`)
      .then(r => r.ok ? r.json() : [])
      .then((data: MatchRow[]) => { setMatches(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [port])

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-gray-500 text-sm">Loading games...</p>
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
            </div>
          </button>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: no errors related to `HistoryList.tsx`. (The file is not yet imported anywhere so it won't be exercised until Task 4.)

- [ ] **Step 3: Commit**

```bash
git add src/chat/HistoryList.tsx
git commit -m "feat: add HistoryList component"
```

---

### Task 3: Create GameDetail component

**Files:**
- Create: `src/chat/GameDetail.tsx`
- Read (for reference, do not modify): `src/popup/MomentCard.tsx`, `src/popup/constants.ts`

This component fetches `/analysis/{matchId}`, renders the stat tiles + filter bar + MomentCards, and exposes `onBack` and `onAskAboutGame` callbacks. It imports `MomentCard` and `POSITIVE_TYPES` directly from the popup directory.

- [ ] **Step 1: Create `src/chat/GameDetail.tsx`**

```tsx
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
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/chat/GameDetail.tsx
git commit -m "feat: add GameDetail component"
```

---

### Task 4: Wire App.tsx — tabs, selectedMatchId, chatMatchId

**Files:**
- Modify: `src/chat/App.tsx`

This is a full replacement of `App.tsx`. Key changes from the current version:
- Import `HistoryList` and `GameDetail`
- `matchId` (URL-only, frozen) → `chatMatchId` (mutable state, starts from URL param)
- Add `tab: 'chat' | 'history'` state
- Add `selectedMatchId: string | null` state
- Header gains Chat / History tab buttons
- Body conditionally renders chat view, `HistoryList`, or `GameDetail`

- [ ] **Step 1: Replace `src/chat/App.tsx` with the updated version**

```tsx
import { useState, useEffect, useCallback } from 'react'
import { createRoot } from 'react-dom/client'
import { MessageList } from './MessageList'
import { InputBar } from './InputBar'
import { Setup } from './Setup'
import { HistoryList } from './HistoryList'
import { GameDetail } from './GameDetail'
import '../index.css'

declare global {
  interface Window { sidecar: { port: string } }
}

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface Pattern {
  moment_type: string
  label: 'recurring_issue' | 'win_condition'
  games_seen: number
  total_games: number
  win_rate_with: number
  overall_win_rate: number
  summary: string
}

type Tab = 'chat' | 'history'

const SESSION_ID = `session-${Date.now()}`

const MOMENT_LABELS: Record<string, string> = {
  lane_death: 'Lane Deaths',
  cs_differential: 'CS Deficit',
  gold_differential: 'Gold Deficit',
  turret_plates_lost: 'Plates Lost',
  split_push_death: 'Split Push Deaths',
  enemy_roam_kill: 'Enemy Roams',
  low_vision: 'Low Vision',
  objective_missed: 'Missed Objectives',
  tower_lost: 'Towers Lost',
  death: 'Deaths',
  solo_kill: 'Solo Kills',
  objective_secured: 'Objectives Secured',
  roam_kill: 'Roam Kills',
  roam_assist: 'Roam Assists',
  ward_kill: 'Vision Control',
  bad_back_objective: 'Bad Backs (Objective)',
  bad_back_gold: 'Bad Backs (Low Gold)',
}

function ChatApp() {
  const [isSetup, setIsSetup] = useState<boolean | null>(null)
  const [tab, setTab] = useState<Tab>('chat')
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null)
  const [chatMatchId, setChatMatchId] = useState<string | null>(
    new URLSearchParams(window.location.search).get('matchId')
  )
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: "Hi! I'm your personal LoL analyst. Ask me anything about your games — patterns, mistakes, champion performance, or what to focus on to climb." }
  ])
  const [loading, setLoading] = useState(false)
  const [patterns, setPatterns] = useState<Pattern[]>([])

  const port = window.sidecar?.port ?? '8765'

  useEffect(() => {
    fetch(`http://localhost:${port}/player`)
      .then(r => {
        if (r.status === 404) { setIsSetup(false); return }
        if (r.ok)             { setIsSetup(true);  return }
        setIsSetup(null)
      })
      .catch(() => setIsSetup(null))
  }, [port])

  useEffect(() => {
    if (!isSetup) return
    fetch(`http://localhost:${port}/patterns`)
      .then(r => r.ok ? r.json() : { patterns: [] })
      .then((data: { patterns: Pattern[] }) => setPatterns(data.patterns))
      .catch(() => {})
  }, [port, isSetup])

  const sendMessage = useCallback(async (text: string) => {
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setLoading(true)
    try {
      const res = await fetch(`http://localhost:${port}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: SESSION_ID, message: text, match_id: chatMatchId }),
      })
      if (!res.ok) throw new Error('sidecar error')
      const data = await res.json() as { response: string }
      setMessages(prev => [...prev, { role: 'assistant', content: data.response }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error connecting to analyst. Is the sidecar running?' }])
    } finally {
      setLoading(false)
    }
  }, [port, chatMatchId])

  const handleAskAboutGame = useCallback((matchId: string) => {
    setChatMatchId(matchId)
    setSelectedMatchId(null)
    setTab('chat')
  }, [])

  const handleTabChange = useCallback((newTab: Tab) => {
    setTab(newTab)
    if (newTab === 'history') setSelectedMatchId(null)
  }, [])

  if (isSetup === null) {
    return (
      <div className="bg-[#1a1a2e] h-screen flex items-center justify-center">
        <p className="text-gray-500 text-sm">Starting...</p>
      </div>
    )
  }

  if (!isSetup) {
    return <Setup port={port} onComplete={() => setIsSetup(true)} />
  }

  return (
    <div className="bg-[#1a1a2e] h-screen flex flex-col text-white font-sans">
      {/* Header with tabs */}
      <div className="border-b border-white/10 px-4 py-3 flex items-center gap-4 flex-shrink-0">
        <h1 className="font-bold text-base">Climb</h1>
        <div className="flex gap-1">
          {(['chat', 'history'] as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => handleTabChange(t)}
              className={`px-3 py-1 rounded-md text-xs font-semibold transition-colors capitalize ${
                tab === t ? 'bg-indigo-700 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
        {tab === 'chat' && chatMatchId && (
          <span className="text-xs text-blue-400 ml-auto">Viewing specific game</span>
        )}
      </div>

      {/* History tab */}
      {tab === 'history' && selectedMatchId === null && (
        <HistoryList port={port} onSelect={setSelectedMatchId} />
      )}
      {tab === 'history' && selectedMatchId !== null && (
        <GameDetail
          matchId={selectedMatchId}
          port={port}
          onBack={() => setSelectedMatchId(null)}
          onAskAboutGame={handleAskAboutGame}
        />
      )}

      {/* Chat tab */}
      {tab === 'chat' && (
        <>
          {patterns.length > 0 && (
            <div className="px-4 py-2 border-b border-white/10 flex gap-2 overflow-x-auto flex-shrink-0">
              {patterns.map((p) => (
                <button
                  key={p.moment_type}
                  onClick={() => sendMessage(
                    `Tell me about my ${(MOMENT_LABELS[p.moment_type] ?? p.moment_type.replace(/_/g, ' ')).toLowerCase()} pattern`
                  )}
                  className={`flex-shrink-0 text-left px-3 py-2 rounded-lg border-l-4 bg-white/5 hover:bg-white/10 transition-colors ${
                    p.label === 'recurring_issue' ? 'border-red-400' : 'border-green-400'
                  }`}
                >
                  <div className="text-xs font-semibold whitespace-nowrap">
                    {MOMENT_LABELS[p.moment_type] ?? p.moment_type}
                  </div>
                  <div className="text-xs text-gray-400 whitespace-nowrap">
                    {p.games_seen} of {p.total_games} · {Math.round(p.win_rate_with * 100)}% WR
                  </div>
                </button>
              ))}
            </div>
          )}
          <MessageList messages={messages} />
          {loading && (
            <div className="px-4 pb-1 flex-shrink-0">
              <span className="text-gray-500 text-xs">Analyzing...</span>
            </div>
          )}
          <InputBar onSend={sendMessage} disabled={loading} />
        </>
      )}
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<ChatApp />)
```

- [ ] **Step 2: Verify TypeScript compiles with no errors**

```bash
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Run the app and verify the full flow**

```bash
npm run dev
```

Open the Climb chat window. Check:
1. Header shows "Chat" and "History" tab buttons
2. Clicking "History" shows a scrollable list of recent games (champion, result bar, KDA, date, moment count)
3. Clicking a game row shows the detail view (stat tiles, filter bar, MomentCards, "Ask about this game →" button)
4. Clicking "← History" returns to the game list
5. Clicking "Ask about this game →" switches to the Chat tab with "Viewing specific game" shown in the header
6. Clicking a pattern chip in Chat tab still works and sends a message

- [ ] **Step 4: Commit**

```bash
git add src/chat/App.tsx
git commit -m "feat: add Chat/History tabs with inline game detail view"
```
