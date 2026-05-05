# Champion Filter for Trend Chart — Design Spec

## Goal

Let the player filter the trend chart to a specific champion so they can see whether they're improving on their main, not just across all champions mixed together.

## Problem

The trend chart currently shows all 20 recent games regardless of champion. A player who plays 3 champions in 20 games gets a noisy signal — a bad Jinx game inflates the Graves trend. Filtering to a specific champion gives a clean, meaningful trend line.

## Decisions

- **Filter style:** Champion pills — one pill per champion played in the last 20 games, plus an "All" pill that resets. Scannable, one tap to switch.
- **Game window when filtered:** Last 20 games of that champion (not last 20 overall filtered down). Maximises the data shown per champion.
- **Default:** "All" — no filter applied on load.
- **Backend:** No changes needed. `GET /matches?last_n=20&champion=Graves` already works.

## Architecture

Two file changes:

| File | Change |
|---|---|
| `src/chat/TrendChart.tsx` | Add `port: string` prop, `selectedChampion` + `filteredMatches` state, champion pills UI, filtered fetch on champion select |
| `src/chat/App.tsx` | Add `port={port}` to the `<TrendChart>` call |

No backend changes. No new files.

## Data Flow

1. App.tsx fetches `/matches?last_n=20` once → passes `matches` (all 20, oldest-first) and `port` to `TrendChart`
2. TrendChart derives champion list: `[...new Set(allMatches.map(m => m.champion))]` — unique champions in order of first appearance
3. "All" selected (default): display data = `allMatches` — zero extra fetches
4. Champion pill tapped → TrendChart fetches `/matches?last_n=20&champion=Graves`, reverses result (oldest-first), stores in `filteredMatches`
5. Display data = `selectedChampion ? (filteredMatches ?? allMatches) : allMatches`
   - `filteredMatches ?? allMatches`: while filtered fetch is in flight, keep showing previous data — no loading flash

## Component API

```tsx
interface TrendChartProps {
  port: string        // added — used for filtered champion fetch
  matches: MatchRow[] // existing — all 20 games, oldest-first
}
```

## UI Spec

```
[ All ]  [ Graves ]  [ Jinx ]  [ Thresh ]   ← champion pills
[ Gold Lost ]  Mistakes                      ← metric toggle (unchanged)
┌──────────────────────────────────────────┐
│ bars...                                  │
└──────────────────────────────────────────┘
  ← older                          recent →
```

Champion pills styling:
- Row: `flex flex-wrap gap-1.5 mb-2`
- Active pill: `bg-indigo-600 text-white text-[10px] font-semibold px-2 py-0.5 rounded-full`
- Inactive pill: `bg-transparent text-gray-500 text-[10px] px-2 py-0.5 rounded-full border border-gray-700 hover:text-gray-300`

Champion list order: iterate `allMatches` from the end (most recent game first) to collect unique champions — so the most recently played champion appears first in the pill row after "All".

## Error Handling

- Filtered fetch fails: silently keep displaying previous data (`filteredMatches ?? allMatches`)
- Champion with 0 games in the filtered result: chart renders nothing (existing `matches.length === 0` guard returns null) — pill stays selected
- `allMatches` empty: no pills rendered, chart hidden (existing guard)
- Champion list has only one champion: still show pills ("All" + that one champion) — useful to know you're filtered

## Testing

No unit tests — pure rendering component. Verified by building (zero TypeScript errors) and visually confirming pills render, filter switches data, "All" resets.
