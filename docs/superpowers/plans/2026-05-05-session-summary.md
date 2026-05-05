# Session Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Summarize today's session" button to the chat tab that fetches recent matches, filters to today's games, and fires a pre-built summary prompt to the analyst.

**Architecture:** All changes are in `src/chat/App.tsx`. A module-level `buildSessionMessage` helper constructs the message text. A `handleSummarize` callback fetches `/matches?last_n=20`, filters to today's games (falling back to last 5 if none), builds the message, and calls the existing `sendMessage`. A button between the pattern pills and the message list triggers the flow.

**Tech Stack:** React 18, TypeScript, Tailwind CSS

---

## File Structure

| File | Change |
|---|---|
| `src/chat/App.tsx` | Add `buildSessionMessage` helper, `summarizing` state, `handleSummarize` callback, button UI |

No new files. No backend changes.

---

### Task 1: Add session summary to App.tsx

All four changes are in `src/chat/App.tsx`. They must land together — the button references `handleSummarize`, which references `buildSessionMessage` and `summarizing`.

**Files:**
- Modify: `src/chat/App.tsx`

No unit tests — pure UI + fetch side-effect. Verified by build + visual check.

- [ ] **Step 1: Add `buildSessionMessage` module-level helper**

In `src/chat/App.tsx`, find the closing brace of the `MOMENT_LABELS` constant (line 53):

```tsx
}
```

Insert the following function immediately after it (before `function ChatApp()`):

```tsx
function buildSessionMessage(games: MatchRow[], isToday: boolean): string {
  const header = isToday
    ? `Summarize my session today (${games.length} game${games.length === 1 ? '' : 's'}):`
    : `I haven't played today. Here are my last ${games.length} games:`
  const lines = games.map((m, i) => {
    const mins = Math.round(m.duration_secs / 60)
    return `${i + 1}. ${m.champion} (${m.result === 'win' ? 'Win' : 'Loss'}, ${m.kda}, ${mins}min, ${m.gold_lost}g lost, ${m.moment_count} mistakes)`
  })
  return `${header}\n\n${lines.join('\n')}\n\nWhat patterns do you see? What went well and what should I focus on next session?`
}
```

- [ ] **Step 2: Add `summarizing` state**

In `src/chat/App.tsx`, find this line (line 65):

```tsx
  const [loading, setLoading] = useState(false)
```

Add the following line immediately after it:

```tsx
  const [summarizing, setSummarizing] = useState(false)
```

- [ ] **Step 3: Add `handleSummarize` callback**

In `src/chat/App.tsx`, find this line (line 139):

```tsx
  const handleBack = useCallback(() => setSelectedMatchId(null), [])
```

Add the following callback immediately after it:

```tsx
  const handleSummarize = useCallback(async () => {
    setSummarizing(true)
    try {
      const res = await fetch(`http://localhost:${port}/matches?last_n=20`)
      if (!res.ok) return
      const data = await res.json() as unknown
      if (!Array.isArray(data)) return
      const all = (data as MatchRow[]).slice().reverse()
      const today = new Date()
      today.setHours(0, 0, 0, 0)
      const todayGames = all.filter(m => new Date(m.played_at) >= today)
      const games = todayGames.length > 0 ? todayGames : all.slice(-5)
      sendMessage(buildSessionMessage(games, todayGames.length > 0))
    } catch {
      // silently swallow fetch/parse errors
    } finally {
      setSummarizing(false)
    }
  }, [port, sendMessage])
```

- [ ] **Step 4: Add the button UI in the chat tab**

In `src/chat/App.tsx`, find this line in the chat tab JSX (line 217):

```tsx
          <MessageList messages={messages} />
```

Replace with:

```tsx
          <div className="px-4 py-2 border-b border-white/10 flex-shrink-0">
            <button
              onClick={handleSummarize}
              disabled={summarizing || loading}
              className="w-full text-left text-xs text-indigo-300 hover:text-indigo-100 py-1 transition-colors disabled:opacity-50"
            >
              {summarizing ? 'Loading...' : '✦ Summarize today\'s session'}
            </button>
          </div>
          <MessageList messages={messages} />
```

- [ ] **Step 5: Build and verify**

```
npm run build
```

Expected: zero TypeScript errors, build completes.

- [ ] **Step 6: Commit**

```bash
git add src/chat/App.tsx
git commit -m "feat: add summarize session button to chat tab"
```
