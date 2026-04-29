# Trend Chart Design Spec

## Goal

Show the player whether they're improving over their last 20 games. A bar chart at the top of the History tab visualises gold lost or mistake count per game, so the player can see at a glance whether those numbers are trending down.

## Problem

The app tracks patterns and post-game costs, but nothing tells the player whether their play is actually getting better over time. The History tab shows individual games but no aggregate trend. Adding a chart above the list answers "am I actually improving?" without requiring extra navigation.

## Decisions

- **Surface:** Top of History tab only, above the game list. Right where the player is already reviewing past performance.
- **Metrics:** Gold lost and mistake count, toggled — one chart at a time. Different scales and units make overlaying them confusing; a toggle keeps each metric readable.
- **Games:** Last 20 (same window as the existing history list).
- **Implementation:** Pure CSS bars — no chart library dependency. The chart is a single metric over 20 games; flex `<div>` bars are sufficient and match the existing UI style.
- **Data:** No backend changes. `GET /matches?last_n=20` already returns `gold_lost: int` and `moment_count: int` per game.

## Architecture

Two files change:

| File | Change |
|---|---|
| `src/chat/TrendChart.tsx` | New — self-contained component, fetches `/matches?last_n=20`, renders bar chart + toggle |
| `src/chat/App.tsx` | Render `<TrendChart port={port} />` above `<HistoryList>` when history tab is open and no game is selected |

`TrendChart` fetches independently rather than sharing `HistoryList`'s data. Keeps both components self-contained; `HistoryList` is untouched.

## Data Flow

1. Player opens History tab → `TrendChart` mounts, fetches `/matches?last_n=20`
2. Response is an array of `MatchRow` objects (same shape `HistoryList` already uses), newest-first
3. Component reverses the array so oldest game is on the left, most recent on the right
4. `max` value computed across all 20 games for the active metric
5. Each bar height = `(value / max) * 100%`
6. Player clicks "Gold Lost" or "Mistakes" toggle → `metric` state updates, bars recompute

## API Contract

No new endpoints. Existing `GET /matches?last_n=20` response fields used:

```json
[
  {
    "match_id": "...",
    "gold_lost": 2400,
    "moment_count": 5,
    ...
  }
]
```

## Component API

```tsx
// src/chat/TrendChart.tsx
interface TrendChartProps {
  port: string
}
export function TrendChart({ port }: TrendChartProps)
```

## UI Spec

```
[ Gold Lost ]  Mistakes          ← toggle buttons, "Gold Lost" active by default
┌──────────────────────────────┐
│ ▓▓                           │
│ ▓▓ ▓▓                        │
│ ▓▓ ▓▓ ▓▓                     │
│ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓               │
│ ▓▓ ▓▓ ▓▓ ▓▓ ▓▓ ░░ ░░ ░░ ░░  │
└──────────────────────────────┘
  ← older                recent →
```

Styling:
- Container: `bg-[#0d0d1f] border-b border-white/10 px-4 py-3`
- Toggle row: two `<button>` elements, active = `text-white font-semibold border-b-2 border-indigo-500`, inactive = `text-gray-500`
- Chart area: `flex items-end gap-[2px] h-16` — bars fill horizontally via `flex: 1`
- Bar colors (gold_lost): `< 500g` → `bg-green-500`, `500–1500g` → `bg-yellow-500`, `> 1500g` → `bg-red-500`
- Bar colors (moment_count): `bg-indigo-500` fixed
- "← older / recent →" axis labels: `text-gray-600 text-[9px]`

## Error Handling

- **Loading:** Component renders nothing until fetch resolves — no spinner, no skeleton. Chart appears once data is ready.
- **Fetch error:** Component renders nothing silently. The game list below is unaffected.
- **Empty (0 games):** Component renders nothing.
- **All-zero metric** (e.g. all games have `gold_lost = 0`): All bars render at 0 height (max = 0 edge case — skip rendering bars, show empty chart area).

## Testing

No unit tests for `TrendChart` — it's a pure rendering component with no logic beyond linear normalisation. Verified by building and visually inspecting in the app.

`src/chat/App.tsx` change is trivial (one JSX line) — no test required.
