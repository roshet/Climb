# Per-Champion Stats in History Tab — Design Spec

## Goal

When the player selects a champion pill in the trend chart, show a concise stat line summarising their performance on that champion across the filtered games: games played, win rate, average gold lost, average mistakes per game.

## Problem

The champion filter pill already filters the trend chart to a specific champion, but the chart alone doesn't answer "am I actually winning more on Graves?" or "is my gold loss better?" The player has to mentally count wins from the game list. A stat line surfaced at selection time answers that question instantly.

## Decisions

- **Placement:** Inline in the TrendChart area, between the champion pills row and the metric toggle — visible only when a champion is selected, hidden on "All".
- **Stats:** Games played, win rate (%), avg gold lost, avg mistakes/game. No KDA — it's a noisy signal and doesn't align with the app's coaching focus.
- **Computation:** Client-side from `displayMatches` (the same array the bars use). No fetch, no new state.
- **Loading state:** While the filtered fetch is in flight (`filteredMatches` is null), compute from `matches` filtered client-side — consistent with how `displayMatches` already handles that case.

## Architecture

One file changes:

| File | Change |
|---|---|
| `src/chat/TrendChart.tsx` | Add stat line computation + JSX between pills and metric toggle |

No new files. No new state. No backend changes.

## Data Flow

```
selectedChampion selected
  → displayMatches = filteredMatches ?? matches   (already computed)
  → games = displayMatches.length
  → wins = displayMatches.filter(m => m.result === 'win').length
  → winRate = Math.round(wins / games * 100)
  → avgGold = Math.round(sum(gold_lost) / games)
  → avgMistakes = (sum(moment_count) / games).toFixed(1)
  → render stat line between pills and metric toggle
```

## UI Spec

```
[ All ]  [ Graves ]  [ Jinx ]                    ← champion pills (existing)
8 games · 62% WR · −820g avg · 4.2 mistakes/game  ← new stat line
[ Gold Lost ]  Mistakes                           ← metric toggle (existing)
┌──────────────────────────────────────────────┐
│ bars...                                      │
└──────────────────────────────────────────────┘
  ← older                              recent →
```

Stat line hidden when `selectedChampion === null`.

Stat line styling:
- Container: `flex gap-3 mb-2 text-[10px]`
- Games: `text-gray-400`
- Win rate: `text-green-400` if ≥ 50%, `text-red-400` if below
- Avg gold: `text-green-400` if < 500g, `text-yellow-400` if ≤ 1500g, `text-red-400` if above
- Avg mistakes: `text-gray-400`
- Separator: `·` in `text-gray-600`

## Error Handling

- `displayMatches.length === 0`: the existing `if (max === 0) return null` guard in TrendChart causes the whole component to return null — the stat line never renders, so no division-by-zero risk
- `selectedChampion` set but `filteredMatches` still null (fetch in flight): stats computed from `matches` as placeholder — acceptable approximation, replaced once fetch resolves

## Testing

No unit tests — pure derived rendering. Verified by build (zero TypeScript errors) and visual check: select a champion pill, confirm stat line appears with correct numbers; click "All", confirm stat line disappears.
