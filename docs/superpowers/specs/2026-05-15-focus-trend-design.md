# Focus Trend Dot Trail Design

## Goal

Add a per-game history trail to the chat tab's focus card so the player can see at a glance whether they're improving on their top focus issue.

## Context

The focus card in `src/chat/FocusCard.tsx` already shows the player's top recurring issue, streak count, and coaching sentence. What it lacks is a historical view — the player can see their current streak but not whether they're trending better or worse across the last 10 games.

## Architecture

Two file changes. No schema changes.

- **Backend:** `sidecar/main.py` — add `history` and `trend` fields to the `/focus` response
- **Frontend:** `src/chat/FocusCard.tsx` — render the dot trail below the coaching sentence

The data is already available in the `/focus` endpoint: `moments_by_match` and `recent_ids` are computed there. The new fields are derived from those.

The dot trail renders in the **chat tab focus card only** — not in the champ select overlay. The champ select card is time-pressured and already compact; the dot trail is a reflection tool suited to the chat tab.

## Backend Changes

### New fields on `/focus` response

```python
history_ids = list(reversed(recent_ids[:10]))
history = [
    top_issue.moment_type not in moments_by_match.get(mid, set())
    for mid in history_ids
]
first_half = sum(history[:len(history) // 2])
second_half = sum(history[len(history) // 2:])
trend = (
    "improving" if second_half > first_half
    else "regressing" if second_half < first_half
    else None
) if len(history) >= 6 else None
```

Add to the return dict:
```python
"history": history,
"trend": trend,
```

### Field definitions

| Field | Type | Description |
|-------|------|-------------|
| `history` | `list[bool]` | Last ≤10 games, oldest→newest. `True` = clean (focus issue absent), `False` = had the issue |
| `trend` | `"improving" \| "regressing" \| null` | Compares clean-game count in first half vs second half. `null` if fewer than 6 games in history |

## Frontend Changes

### `FocusCardData` interface

Add two optional fields:

```tsx
interface FocusCardData {
  // ...existing fields...
  history?: boolean[]
  trend?: string | null
}
```

### Dot trail render

Add below the coaching sentence inside `FocusCard`, only when `card.history` has at least one entry:

```tsx
{card.history && card.history.length > 0 && (
  <div className="flex items-center gap-1.5 mt-2">
    <span className="text-gray-500 text-[9px]">last {card.history.length}</span>
    <div className="flex gap-1">
      {card.history.map((clean, i) => (
        <span
          key={i}
          className={`w-2 h-2 rounded-full ${clean ? 'bg-green-400' : 'bg-red-500'}`}
        />
      ))}
    </div>
    {card.trend && (
      <span className={`text-[9px] font-semibold ml-0.5 ${
        card.trend === 'improving' ? 'text-green-400' : 'text-red-400'
      }`}>
        {card.trend === 'improving' ? '↑ improving' : '↓ regressing'}
      </span>
    )}
  </div>
)}
```

Visual: green dot = clean game, red dot = had the issue. Left = oldest, right = most recent. Trend label appears to the right when ≥6 games exist.

## Edge Cases

| Scenario | Behaviour |
|----------|-----------|
| Fewer than 10 games in history | Show however many exist (minimum 1 dot) |
| Fewer than 6 games | Dot trail shows, trend label hidden (`trend = null`) |
| No `history` field (stale cached focus card) | Dot trail section simply doesn't render |
| All games clean | All green dots, trend = null or "improving" |
| All games with issue | All red dots, trend = null or "regressing" |
