# Session Summary — Design Spec

## Goal

Let the player tap one button to get a plain-English summary of their session — what they played, what went wrong, what went well, and what to focus on next.

## Problem

After a few games the player has to manually ask "how did I do today?" with no context pre-loaded. The analyst has to be prompted explicitly and doesn't know what games were just played. A one-tap session summary removes that friction and makes the tool feel proactive.

## Decisions

- **Trigger:** Dedicated "Summarize today's session" button in the chat tab (not a slash command, not auto-fire on tab switch).
- **Session definition:** Today's games (local date, filter by `played_at`). Fallback to last 5 if no games today.
- **Context delivery:** Game stats embedded inline in the message text — no backend changes needed.
- **Backend:** No changes. Reuses existing POST /chat endpoint with `sendMessage()`.

## Architecture

One file changes:

| File | Change |
|---|---|
| `src/chat/App.tsx` | Add `handleSummarize` fetch handler + button UI in chat tab |

No new files. No new components. No backend changes.

## Data Flow

```
User taps "Summarize today's session"
  → fetch /matches?last_n=20
  → filter: new Date(m.played_at) >= today (midnight local)
  → if 0 today → fallback: matches.slice(-5) (most recent 5, matches is oldest-first)
  → build message string with per-game stats
  → sendMessage(builtText)   ← reuses existing chat flow
```

The built message format:
```
Summarize my session today (3 games):

1. Graves (Win, 6/2/4, 24min, 320g lost, 3 mistakes)
2. Jinx (Loss, 3/8/1, 31min, 1450g lost, 8 mistakes)
3. Graves (Win, 8/1/6, 28min, 180g lost, 2 mistakes)

What patterns do you see? What went well and what should I focus on next session?
```

Fallback message header:
```
I haven't played today. Here are my last 5 games:
```

## Component API

No new props or components. `handleSummarize` is a local async function in `ChatApp` that reads `port` from closure and calls `sendMessage`.

## UI Spec

```
[ Lane Deaths x5 ] [ Gold Deficit x3 ]    ← pattern pills row (existing)
─────────────────────────────────────────
[ ✦ Summarize today's session ]            ← new button
─────────────────────────────────────────
  messages...
```

Button placement: between pattern pills and message list, inside a `flex-shrink-0` container with `border-b border-white/10`.

Button styling:
- Container: `px-4 py-2 border-b border-white/10 flex-shrink-0`
- Button: `w-full text-left text-xs text-indigo-300 hover:text-indigo-100 py-1 transition-colors disabled:opacity-50`
- Label: "✦ Summarize today's session"
- Loading state: "Loading..." + `disabled`

Hide condition: `matches.length === 0` when tab === 'history' is known... actually the button is in the chat tab and fires its own fetch, so hide when: button is loading OR chat is loading. Never hidden based on match count (we don't know match count from chat tab without fetching).

## Message Construction

```ts
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

## Error Handling

- Fetch fails → silently swallow, re-enable button
- 0 games returned total → build message with empty games list; sendMessage handles it gracefully (AI will say there's no data)
- Button disabled while `loading` (chat in flight) — prevents double-fire
- No `match_id` passed to POST /chat — this is a multi-game summary, not a specific game context

## Testing

No unit tests — pure UI + fetch side-effect. Verified by building (zero TypeScript errors) and visually confirming:
- Button appears in chat tab
- Tap fires fetch, shows loading state
- Message appears in chat with correct game list
- AI responds with session summary
