# Trend Chart Tooltip & Color Legend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add hover tooltips to each bar in the TrendChart (showing champion, W/L, and the actual metric value) and a color legend so users know what bar colors mean.

**Architecture:** All changes in `src/chat/TrendChart.tsx`. Add `hoveredIndex` state, wrap each bar in a relative-positioned container that shows a tooltip on mouseenter, and render a color legend row below the metric toggle when the active metric is gold_lost.

**Tech Stack:** React 18, TypeScript, Tailwind CSS

---

## File Structure

| File | Change |
|---|---|
| `src/chat/TrendChart.tsx` | Add hoveredIndex state, tooltipValue helper, bar wrapper + tooltip JSX, color legend JSX |

---

### Task 1: Add hover tooltip and color legend to TrendChart

No unit tests — pure derived rendering. Verified by build + visual check.

- [ ] **Step 1: Add `hoveredIndex` state and `tooltipValue` helper**

In `src/chat/TrendChart.tsx`, find this block (lines 19–21):

```tsx
  const [metric, setMetric] = useState<Metric>('gold_lost')
  const [selectedChampion, setSelectedChampion] = useState<string | null>(null)
  const [filteredMatches, setFilteredMatches] = useState<MatchRow[] | null>(null)
```

Replace with:

```tsx
  const [metric, setMetric] = useState<Metric>('gold_lost')
  const [selectedChampion, setSelectedChampion] = useState<string | null>(null)
  const [filteredMatches, setFilteredMatches] = useState<MatchRow[] | null>(null)
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)
```

Then find this block (lines 49–51, just before the `return`):

```tsx
  const fallbackMetric: Metric = 'moment_count'
  const displayValues = max === 0 ? displayMatches.map(m => m[fallbackMetric]) : values
  const displayMax = max === 0 ? Math.max(...displayValues) : max
```

Replace with:

```tsx
  const fallbackMetric: Metric = 'moment_count'
  const displayValues = max === 0 ? displayMatches.map(m => m[fallbackMetric]) : values
  const displayMax = max === 0 ? Math.max(...displayValues) : max
  const activeMetric = max === 0 ? fallbackMetric : metric
  const tooltipValue = (m: MatchRow) =>
    activeMetric === 'gold_lost'
      ? `−${m.gold_lost.toLocaleString()}g`
      : `${m.moment_count} mistake${m.moment_count === 1 ? '' : 's'}`
```

- [ ] **Step 2: Replace bar rendering with hover-aware wrapper**

In `src/chat/TrendChart.tsx`, find this block (lines 115–123):

```tsx
      <div className="flex items-end gap-[2px] h-16">
        {displayMatches.map((m, i) => (
          <div
            key={m.match_id}
            className={`flex-1 rounded-t-sm ${barColor(max === 0 ? fallbackMetric : metric, displayValues[i])}`}
            style={{ height: `${(displayValues[i] / displayMax) * 100}%` }}
          />
        ))}
      </div>
```

Replace with:

```tsx
      <div className="flex items-end gap-[2px] h-16">
        {displayMatches.map((m, i) => (
          <div
            key={m.match_id}
            className="flex-1 relative flex items-end h-full"
            onMouseEnter={() => setHoveredIndex(i)}
            onMouseLeave={() => setHoveredIndex(null)}
          >
            {hoveredIndex === i && (
              <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 z-10 bg-[#1a1a2e] border border-white/20 rounded px-2 py-1 text-[9px] whitespace-nowrap pointer-events-none">
                <span className="text-gray-300">{m.champion}</span>
                <span className="text-gray-600 mx-1">·</span>
                <span className={m.result === 'win' ? 'text-green-400' : 'text-red-400'}>
                  {m.result === 'win' ? 'W' : 'L'}
                </span>
                <span className="text-gray-600 mx-1">·</span>
                <span className="text-gray-300">{tooltipValue(m)}</span>
              </div>
            )}
            <div
              className={`w-full rounded-t-sm ${barColor(max === 0 ? fallbackMetric : metric, displayValues[i])}`}
              style={{ height: `${(displayValues[i] / displayMax) * 100}%` }}
            />
          </div>
        ))}
      </div>
```

- [ ] **Step 3: Add color legend below metric toggle**

In `src/chat/TrendChart.tsx`, find this block (lines 93–113, the metric toggle + chart):

```tsx
      <div className="flex gap-4 mb-2">
        <button
          onClick={() => setMetric('gold_lost')}
```

Replace with:

```tsx
      <div className="flex gap-4 mb-2">
        <button
          onClick={() => setMetric('gold_lost')}
```

Wait — just insert the legend between the metric toggle closing `</div>` and the bars `<div className="flex items-end ...">`. Find this exact block:

```tsx
      </div>
      <div className="flex items-end gap-[2px] h-16">
```

(This is the closing tag of the metric toggle row followed by the bar container.) Replace with:

```tsx
      </div>
      {activeMetric === 'gold_lost' && (
        <div className="flex gap-3 mb-2 text-[9px] text-gray-500">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-green-500 inline-block" />
            &lt;500g
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-yellow-500 inline-block" />
            500–1500g
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-red-500 inline-block" />
            &gt;1500g
          </span>
        </div>
      )}
      <div className="flex items-end gap-[2px] h-16">
```

- [ ] **Step 4: Build and verify**

```
npm run build
```

Expected: zero TypeScript errors, build completes.

Then start the app and verify:
- Hovering a bar shows a tooltip: e.g. `Caitlyn · L · −8,916g`
- W shows in green, L shows in red
- Color legend appears below metric toggle when Gold Lost is selected
- Color legend disappears when Mistakes is selected
- Hovering works on champion-filtered bars too

- [ ] **Step 5: Commit**

```bash
git add src/chat/TrendChart.tsx
git commit -m "feat: add hover tooltips and color legend to trend chart"
```
