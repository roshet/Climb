# Champion Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a per-champion stat line (games, win rate, avg gold lost, avg mistakes/game) inside the TrendChart when a champion pill is selected.

**Architecture:** All changes are in `src/chat/TrendChart.tsx`. After computing `displayMatches`, derive five stat variables. Render a stat line div conditionally between the champion pills row and the metric toggle row when `selectedChampion !== null`. No new files, no new state, no backend changes.

**Tech Stack:** React 18, TypeScript, Tailwind CSS

---

## File Structure

| File | Change |
|---|---|
| `src/chat/TrendChart.tsx` | Add stat computation variables + conditional stat line JSX |

---

### Task 1: Add champion stat line to TrendChart

Both changes land in the same file and must be made together — the JSX references the variables defined in the computation block.

**Files:**
- Modify: `src/chat/TrendChart.tsx`

No unit tests — pure derived rendering. Verified by build + visual check.

- [ ] **Step 1: Insert stat computation variables**

In `src/chat/TrendChart.tsx`, find this block (lines 41–42):

```tsx
  const displayMatches = selectedChampion ? (filteredMatches ?? matches) : matches
  const values = displayMatches.map(m => m[metric])
```

Replace with:

```tsx
  const displayMatches = selectedChampion ? (filteredMatches ?? matches) : matches
  const champGames = displayMatches.length
  const champWins = displayMatches.filter(m => m.result === 'win').length
  const champWinRate = champGames > 0 ? Math.round(champWins / champGames * 100) : 0
  const champAvgGold = champGames > 0 ? Math.round(displayMatches.reduce((s, m) => s + m.gold_lost, 0) / champGames) : 0
  const champAvgMistakes = champGames > 0 ? (displayMatches.reduce((s, m) => s + m.moment_count, 0) / champGames).toFixed(1) : '0.0'
  const values = displayMatches.map(m => m[metric])
```

- [ ] **Step 2: Insert the stat line JSX**

In `src/chat/TrendChart.tsx`, find this block (lines 72–74):

```tsx
        ))}
      </div>
      <div className="flex gap-4 mb-2">
```

Replace with:

```tsx
        ))}
      </div>
      {selectedChampion !== null && (
        <div className="flex gap-3 mb-2 text-[10px]">
          <span className="text-gray-400">{champGames} game{champGames === 1 ? '' : 's'}</span>
          <span className="text-gray-600">·</span>
          <span className={champWinRate >= 50 ? 'text-green-400' : 'text-red-400'}>{champWinRate}% WR</span>
          <span className="text-gray-600">·</span>
          <span className={champAvgGold < 500 ? 'text-green-400' : champAvgGold <= 1500 ? 'text-yellow-400' : 'text-red-400'}>−{champAvgGold.toLocaleString()}g avg</span>
          <span className="text-gray-600">·</span>
          <span className="text-gray-400">{champAvgMistakes} mistakes/game</span>
        </div>
      )}
      <div className="flex gap-4 mb-2">
```

- [ ] **Step 3: Build and verify**

```
npm run build
```

Expected: zero TypeScript errors, build completes.

- [ ] **Step 4: Commit**

```bash
git add src/chat/TrendChart.tsx
git commit -m "feat: show per-champion stats when champion pill is selected"
```
