# Post-Game Focus Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a "Your Focus" section in the post-game popup telling the player whether they hit or missed their pre-game focus goal.

**Architecture:** Single frontend file change. The popup fetches `/focus` (already exists) alongside its two existing fetches, derives `had_in_game` and `count` from the already-fetched analysis moments, and renders a `FocusResultBlock` component above the "vs your patterns" section. No backend changes.

**Tech Stack:** React 18, TypeScript, Tailwind CSS. No test framework for frontend — verification is manual via the Electron app.

---

### Task 1: Add FocusResultBlock component and wire it into the popup

**Files:**
- Modify: `src/popup/App.tsx`

This is the only task. The entire feature lives in one file.

**Current state of `src/popup/App.tsx` for reference:**
- Lines 1-5: imports
- Lines 11-44: interfaces (`Moment`, `Analysis`, `Filter`, `ImprovementPattern`, `ImprovementData`)
- Lines 79-83: `PopupApp` state (`analysis`, `improvement`, `loading`, `filter`)
- Lines 88-105: `useEffect` with `Promise.all` fetching `/analysis/{matchId}` and `/improvement/{matchId}`
- Lines 183-195: renders the "vs your patterns" section

---

- [ ] **Step 1: Add the `FocusResult` interface**

In `src/popup/App.tsx`, add this interface after the `ImprovementData` interface (after line 44):

```tsx
interface FocusResult {
  moment_type: string
  display: string
  streak_clean: number
}
```

---

- [ ] **Step 2: Add the `FocusResultBlock` component**

Add this component after the `ImprovementRow` function (after line 77), before `function PopupApp()`:

```tsx
function FocusResultBlock({ focus, moments }: { focus: FocusResult; moments: Moment[] }) {
  const count = moments.filter(m => m.moment_type === focus.moment_type).length
  const isClean = focus.streak_clean > 0

  let text: string
  if (isClean) {
    text = focus.streak_clean >= 2
      ? `${focus.display} — clean game! ${focus.streak_clean} in a row`
      : `${focus.display} — clean game!`
  } else {
    text = `${focus.display} — ${count} time${count === 1 ? '' : 's'} this game`
  }

  return (
    <div className="mb-3">
      <p className="text-gray-500 text-[9px] uppercase tracking-wide mb-1.5">🎯 Your Focus</p>
      <div className={`border-l-2 rounded px-3 py-1.5 text-xs ${
        isClean
          ? 'border-indigo-500 bg-indigo-950/50 text-indigo-200'
          : 'border-red-500 bg-red-950/80 text-red-200'
      }`}>
        <span className="mr-1">{isClean ? '✓' : '⚠'}</span>
        {text}
      </div>
    </div>
  )
}
```

---

- [ ] **Step 3: Add `focusResult` state to `PopupApp`**

In `PopupApp`, add the new state variable alongside the existing ones (after line 83):

```tsx
const [analysis, setAnalysis] = useState<Analysis | null>(null)
const [improvement, setImprovement] = useState<ImprovementData | null>(null)
const [focusResult, setFocusResult] = useState<FocusResult | null>(null)
const [loading, setLoading] = useState(true)
const [filter, setFilter] = useState<Filter>('all')
```

---

- [ ] **Step 4: Add `/focus` fetch to the `Promise.all`**

Replace the existing `Promise.all` block (lines 90-105) with:

```tsx
Promise.all([
  fetch(`http://localhost:${port}/analysis/${matchId}`)
    .then(r => { if (!r.ok) throw new Error('not ok'); return r.json() as Promise<Analysis> }),
  fetch(`http://localhost:${port}/improvement/${matchId}`)
    .then(r => r.ok ? r.json() as Promise<ImprovementData> : null)
    .catch(() => null),
  fetch(`http://localhost:${port}/focus`)
    .then(r => r.ok ? r.json() as Promise<FocusResult | null> : null)
    .catch(() => null),
]).then(([analysisData, improvementData, focusData]) => {
  setAnalysis(analysisData)
  setImprovement(improvementData)
  setFocusResult(focusData ?? null)
  setLoading(false)
}).catch(() => {
  setAnalysis(null)
  setImprovement(null)
  setFocusResult(null)
  setLoading(false)
})
```

---

- [ ] **Step 5: Render `FocusResultBlock` above "vs your patterns"**

Find the "vs your patterns" section (currently around line 183):

```tsx
{/* Improvement: vs your patterns */}
{improvement && improvement.patterns.length > 0 && (
  <div className="mb-3">
    <p className="text-gray-500 text-[9px] uppercase tracking-wide mb-1.5">
      vs your patterns ({improvement.champion})
    </p>
```

Add `FocusResultBlock` immediately before it:

```tsx
{/* Focus feedback */}
{focusResult && analysis && (
  <FocusResultBlock focus={focusResult} moments={analysis.moments} />
)}

{/* Improvement: vs your patterns */}
{improvement && improvement.patterns.length > 0 && (
  <div className="mb-3">
    <p className="text-gray-500 text-[9px] uppercase tracking-wide mb-1.5">
      vs your patterns ({improvement.champion})
    </p>
```

---

- [ ] **Step 6: Build and verify**

Run the dev build:
```bash
npm run build
```
Expected: build completes with no TypeScript errors.

Then launch the Electron app and open the post-game popup for any game. Verify:

1. **Focus card exists and player avoided the issue:** "🎯 Your Focus" section appears above "vs your patterns". Shows `✓ [display] — clean game! N in a row` with indigo styling.
2. **Focus card exists and player had the issue:** Shows `⚠ [display] — N times this game` with red styling.
3. **No focus card** (e.g., fresh install with few games): "Your Focus" section is hidden. Popup looks unchanged.
4. **Sidecar offline:** `/focus` fetch fails gracefully, section hidden.

If you don't have a focus card in your DB yet, you can temporarily test by opening the browser devtools on the popup and checking the network tab to see what `/focus` returns.

---

- [ ] **Step 7: Commit**

```bash
git add src/popup/App.tsx
git commit -m "feat: show focus feedback in post-game popup"
```
