# Champ Select Coaching Sentence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Gemini-generated coaching sentence from `/focus` to the existing focus card in the champ-select overlay.

**Architecture:** Single file change to `src/champ-select/App.tsx`. Fetch `/focus` once on mount, pass `coaching_sentence` as an optional prop to the existing `FocusCard` component, render it as italic text at the bottom of the card. No backend changes.

**Tech Stack:** React 18, TypeScript, Tailwind CSS. No frontend test framework — verification is manual via the Electron app.

---

### Task 1: Add coaching sentence to champ-select FocusCard

**Files:**
- Modify: `src/champ-select/App.tsx`

This is the only file that changes. The entire feature lives here.

**Current state of `src/champ-select/App.tsx` for reference:**

```tsx
// Lines 15-22: existing Focus interface (champion-specific)
interface Focus {
  moment_type: string
  label: string
  games_seen: number
  total_games: number
  avg_gold_lost: number
  champion_specific: boolean
}

// Lines 53-71: existing FocusCard component
function FocusCard({ focus, champion }: { focus: Focus; champion: string }) {
  const scope = focus.champion_specific ? champion : 'All Champions'
  return (
    <div className="mx-2 mt-2 bg-[#1e1b4b] border border-indigo-500/60 rounded-lg px-3 py-2">
      <p className="text-indigo-300 text-[7px] font-bold uppercase tracking-widest mb-1">
        ⚡ Today's Focus · {scope}
      </p>
      <p className="text-white text-[11px] font-bold">{focus.label}</p>
      <p className="text-gray-400 text-[8px] mt-0.5">
        {focus.games_seen} of your last {focus.total_games} games
      </p>
      {focus.avg_gold_lost > 0 && (
        <p className="text-red-400 text-[8px] font-semibold mt-1">
          avg −{focus.avg_gold_lost.toLocaleString()}g per game
        </p>
      )}
    </div>
  )
}

// Lines 73-89: ChampSelectApp component with state and poll loop
function ChampSelectApp() {
  const [state, setState] = useState<ChampSelectState | null>(null)
  const port = window.sidecar?.port ?? '8765'

  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch(`http://localhost:${port}/champ-select`)
        if (!res.ok) return
        const data = await res.json() as ChampSelectState
        setState(data)
      } catch { /* sidecar not ready */ }
    }
    poll()
    const interval = setInterval(poll, 2000)
    return () => clearInterval(interval)
  }, [port])
  // ...
}

// Line 111-113: existing FocusCard render call
{champ_data?.focus && !champ_data.no_history && (
  <FocusCard focus={champ_data.focus} champion={locked_champion} />
)}
```

---

- [ ] **Step 1: Add `coachingSentence` state and fetch to `ChampSelectApp`**

Inside `ChampSelectApp`, add the new state variable and a one-time fetch useEffect. Place both after the existing `const port` line and before the existing poll `useEffect`:

```tsx
function ChampSelectApp() {
  const [state, setState] = useState<ChampSelectState | null>(null)
  const [coachingSentence, setCoachingSentence] = useState<string | null>(null)
  const port = window.sidecar?.port ?? '8765'

  useEffect(() => {
    fetch(`http://localhost:${port}/focus`)
      .then(r => r.ok ? r.json() : null)
      .then((data: { coaching_sentence?: string } | null) => {
        setCoachingSentence(data?.coaching_sentence ?? null)
      })
      .catch(() => {})
  }, [port])

  useEffect(() => {
    // existing poll loop — unchanged
    const poll = async () => {
      try {
        const res = await fetch(`http://localhost:${port}/champ-select`)
        if (!res.ok) return
        const data = await res.json() as ChampSelectState
        setState(data)
      } catch { /* sidecar not ready */ }
    }
    poll()
    const interval = setInterval(poll, 2000)
    return () => clearInterval(interval)
  }, [port])
```

---

- [ ] **Step 2: Update `FocusCard` to accept and render `coachingSentence`**

Replace the existing `FocusCard` function with this updated version that adds the optional prop and renders it:

```tsx
function FocusCard({ focus, champion, coachingSentence }: {
  focus: Focus
  champion: string
  coachingSentence?: string | null
}) {
  const scope = focus.champion_specific ? champion : 'All Champions'
  return (
    <div className="mx-2 mt-2 bg-[#1e1b4b] border border-indigo-500/60 rounded-lg px-3 py-2">
      <p className="text-indigo-300 text-[7px] font-bold uppercase tracking-widest mb-1">
        ⚡ Today's Focus · {scope}
      </p>
      <p className="text-white text-[11px] font-bold">{focus.label}</p>
      <p className="text-gray-400 text-[8px] mt-0.5">
        {focus.games_seen} of your last {focus.total_games} games
      </p>
      {focus.avg_gold_lost > 0 && (
        <p className="text-red-400 text-[8px] font-semibold mt-1">
          avg −{focus.avg_gold_lost.toLocaleString()}g per game
        </p>
      )}
      {coachingSentence && (
        <p className="text-gray-400 text-[8px] italic mt-1.5 leading-relaxed">
          "{coachingSentence}"
        </p>
      )}
    </div>
  )
}
```

---

- [ ] **Step 3: Pass `coachingSentence` to the `FocusCard` render call**

Find the existing `FocusCard` render call (around line 111) and add the new prop:

```tsx
{champ_data?.focus && !champ_data.no_history && (
  <FocusCard
    focus={champ_data.focus}
    champion={locked_champion}
    coachingSentence={coachingSentence}
  />
)}
```

---

- [ ] **Step 4: Build and verify**

```bash
npm run build
```

Expected: build completes with no TypeScript errors.

Then launch the Electron app and enter champ select (or wait for it to be detected). Verify:

1. **Focus card with coaching sentence:** When a focus card exists in the DB, the existing champion-specific focus card now shows a small italic coaching sentence at the bottom.
2. **No focus card:** When `/focus` returns null (fresh install or not enough games), the focus card renders exactly as before — no coaching sentence, no visible change.
3. **Sidecar offline:** `/focus` fetch fails, `coachingSentence` stays null, card renders unchanged.

---

- [ ] **Step 5: Commit**

```bash
git add src/champ-select/App.tsx
git commit -m "feat: show coaching sentence in champ select focus card"
```
