# Setup UI Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the duplicated region dropdown and Riot-ID inputs from the two setup UIs into shared components so the region list lives in exactly one place, with no behavior change to either save flow.

**Architecture:** Two new presentational components in `src/shared/components/` — `RegionSelect` (owns the region list + dark-mode styling) and `RiotIdInput` (the `GameName # TAG` pair). Both `src/setup/App.tsx` (Electron window, IPC save) and `src/chat/Setup.tsx` (in-chat 404-recovery form, direct POST) consume them. Parents keep their own change side-effects, so both save paths are preserved exactly.

**Tech Stack:** React 18 + TypeScript, Tailwind (utility classes inline), Vitest + @testing-library/react (no `user-event` — use `fireEvent`), jest-dom matchers.

---

## File Structure

- **Create** `src/shared/components/RegionSelect.tsx` — styled `<select>` + the `REGIONS` list (single source of truth, comment-pinned to `riot_client.py:REGIONAL_ROUTING`).
- **Create** `src/shared/components/RegionSelect.test.tsx` — RTL tests.
- **Create** `src/shared/components/RiotIdInput.tsx` — the two-input Riot ID row.
- **Create** `src/shared/components/RiotIdInput.test.tsx` — RTL tests.
- **Modify** `src/setup/App.tsx` — drop local `REGIONS`, use both shared components.
- **Modify** `src/chat/Setup.tsx` — drop inline region array, use both shared components.

Note: `RegionSelect` deliberately has **no** `className` prop — both consumers use the identical class string, so it's hardcoded (YAGNI). Both selects currently use the exact same classes.

---

## Task 1: RegionSelect component

**Files:**
- Create: `src/shared/components/RegionSelect.tsx`
- Test: `src/shared/components/RegionSelect.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `src/shared/components/RegionSelect.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { RegionSelect } from './RegionSelect'

describe('RegionSelect', () => {
  const ALL = ['NA1', 'EUW1', 'EUNE1', 'KR', 'BR1', 'LAN', 'LAS', 'OC1', 'TR1', 'RU', 'JP1']

  it('renders all 11 region options matching the routing map keys', () => {
    render(<RegionSelect value="NA1" onChange={() => {}} />)
    for (const r of ALL) {
      expect(screen.getByRole('option', { name: r })).toBeInTheDocument()
    }
  })

  it('reflects the value prop as the selected option', () => {
    render(<RegionSelect value="KR" onChange={() => {}} />)
    expect(screen.getByRole('combobox')).toHaveValue('KR')
  })

  it('fires onChange with the selected region', () => {
    const onChange = vi.fn()
    render(<RegionSelect value="NA1" onChange={onChange} />)
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'EUNE1' } })
    expect(onChange).toHaveBeenCalledWith('EUNE1')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- RegionSelect`
Expected: FAIL — cannot resolve `'./RegionSelect'` (module not found).

- [ ] **Step 3: Write minimal implementation**

Create `src/shared/components/RegionSelect.tsx`:

```tsx
// Values must match REGIONAL_ROUTING keys in sidecar/riot_client.py — any value not
// in that map silently falls through to the "americas" routing cluster.
const REGIONS = ['NA1', 'EUW1', 'EUNE1', 'KR', 'BR1', 'LAN', 'LAS', 'OC1', 'TR1', 'RU', 'JP1']

interface RegionSelectProps {
  value: string
  onChange: (region: string) => void
}

export function RegionSelect({ value, onChange }: RegionSelectProps) {
  return (
    <select
      className="w-full bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none [color-scheme:dark]"
      value={value}
      onChange={e => onChange(e.target.value)}
    >
      {REGIONS.map(r => (
        <option key={r} value={r} className="bg-[#1a1a2e] text-white">{r}</option>
      ))}
    </select>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- RegionSelect`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/shared/components/RegionSelect.tsx src/shared/components/RegionSelect.test.tsx
git commit -m "feat: add shared RegionSelect component"
```

---

## Task 2: RiotIdInput component

**Files:**
- Create: `src/shared/components/RiotIdInput.tsx`
- Test: `src/shared/components/RiotIdInput.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `src/shared/components/RiotIdInput.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { RiotIdInput } from './RiotIdInput'

describe('RiotIdInput', () => {
  it('renders both fields with the passed values', () => {
    render(
      <RiotIdInput
        gameName="RoShet"
        tagLine="NA1"
        onGameNameChange={() => {}}
        onTagLineChange={() => {}}
      />,
    )
    expect(screen.getByPlaceholderText('Game Name')).toHaveValue('RoShet')
    expect(screen.getByPlaceholderText('TAG')).toHaveValue('NA1')
  })

  it('fires onGameNameChange when the game name changes', () => {
    const onGameNameChange = vi.fn()
    render(
      <RiotIdInput gameName="" tagLine="" onGameNameChange={onGameNameChange} onTagLineChange={() => {}} />,
    )
    fireEvent.change(screen.getByPlaceholderText('Game Name'), { target: { value: 'Faker' } })
    expect(onGameNameChange).toHaveBeenCalledWith('Faker')
  })

  it('fires onTagLineChange when the tag changes', () => {
    const onTagLineChange = vi.fn()
    render(
      <RiotIdInput gameName="" tagLine="" onGameNameChange={() => {}} onTagLineChange={onTagLineChange} />,
    )
    fireEvent.change(screen.getByPlaceholderText('TAG'), { target: { value: 'KR1' } })
    expect(onTagLineChange).toHaveBeenCalledWith('KR1')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- RiotIdInput`
Expected: FAIL — cannot resolve `'./RiotIdInput'` (module not found).

- [ ] **Step 3: Write minimal implementation**

Create `src/shared/components/RiotIdInput.tsx`:

```tsx
interface RiotIdInputProps {
  gameName: string
  tagLine: string
  onGameNameChange: (value: string) => void
  onTagLineChange: (value: string) => void
}

export function RiotIdInput({ gameName, tagLine, onGameNameChange, onTagLineChange }: RiotIdInputProps) {
  return (
    <div className="flex gap-2">
      <input
        className="flex-1 bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
        placeholder="Game Name"
        value={gameName}
        onChange={e => onGameNameChange(e.target.value)}
      />
      <span className="text-gray-500 self-center">#</span>
      <input
        className="w-20 bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
        placeholder="TAG"
        value={tagLine}
        onChange={e => onTagLineChange(e.target.value)}
      />
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- RiotIdInput`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/shared/components/RiotIdInput.tsx src/shared/components/RiotIdInput.test.tsx
git commit -m "feat: add shared RiotIdInput component"
```

---

## Task 3: Use shared components in the Electron setup window

**Files:**
- Modify: `src/setup/App.tsx`

The current file declares `REGIONS` at the top (lines ~6-8), renders the Riot-ID block inside a labelled `<div>` (the inner `<div className="flex gap-2">…</div>` at ~109-123), and renders the `<select>` at ~126-132. Keep the outer "Riot ID" label `<div>`; replace only its inner flex row and the select. Region/Riot-ID change handlers must keep calling `dirty()`.

- [ ] **Step 1: Add the imports**

In `src/setup/App.tsx`, after the existing import block (after the `initRendererLogForwarding` import on line 4), add:

```tsx
import { RegionSelect } from '../shared/components/RegionSelect'
import { RiotIdInput } from '../shared/components/RiotIdInput'
```

- [ ] **Step 2: Delete the local REGIONS constant**

Remove these lines (the comment + const, ~lines 6-8):

```tsx
// Values must match REGIONAL_ROUTING keys in sidecar/riot_client.py — any value not
// in that map silently falls through to the "americas" routing cluster.
const REGIONS = ['NA1', 'EUW1', 'EUNE1', 'KR', 'BR1', 'LAN', 'LAS', 'OC1', 'TR1', 'RU', 'JP1']
```

- [ ] **Step 3: Replace the Riot-ID inner flex row**

Find this block inside the "Riot ID" label `<div>`:

```tsx
          <div className="flex gap-2">
            <input
              className="flex-1 bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
              placeholder="Game Name"
              value={summonerName}
              onChange={e => { setSummonerName(e.target.value); dirty() }}
            />
            <span className="text-gray-500 self-center">#</span>
            <input
              className="w-20 bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
              placeholder="TAG"
              value={tagLine}
              onChange={e => { setTagLine(e.target.value); dirty() }}
            />
          </div>
```

Replace it with:

```tsx
          <RiotIdInput
            gameName={summonerName}
            tagLine={tagLine}
            onGameNameChange={v => { setSummonerName(v); dirty() }}
            onTagLineChange={v => { setTagLine(v); dirty() }}
          />
```

- [ ] **Step 4: Replace the region select**

Find:

```tsx
        <select
          className="w-full bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none [color-scheme:dark]"
          value={region}
          onChange={e => { setRegion(e.target.value); dirty() }}
        >
          {REGIONS.map(r => <option key={r} value={r} className="bg-[#1a1a2e] text-white">{r}</option>)}
        </select>
```

Replace it with:

```tsx
        <RegionSelect value={region} onChange={v => { setRegion(v); dirty() }} />
```

- [ ] **Step 5: Verify typecheck + lint + tests pass**

Run: `npm run typecheck`
Expected: no errors.

Run: `npm run lint`
Expected: 0 errors (the 10 `react-refresh/only-export-components` warnings on window entry files are pre-existing and expected).

Run: `npm test`
Expected: all tests pass (12 existing + 6 new).

- [ ] **Step 6: Commit**

```bash
git add src/setup/App.tsx
git commit -m "refactor: use shared RegionSelect + RiotIdInput in setup window"
```

---

## Task 4: Use shared components in the in-chat setup form

**Files:**
- Modify: `src/chat/Setup.tsx`

This form has no "Riot ID" label wrapper — the `<div className="flex gap-2">` (lines ~44-58) sits directly in the layout, followed by the `<select>` (~60-68). Its state vars are `gameName` / `tagLine` and change handlers just call the setter (no `dirty()`).

- [ ] **Step 1: Add the imports**

In `src/chat/Setup.tsx`, after the existing imports (after `import { sidecarUrl } from '../shared/api'` on line 2), add:

```tsx
import { RegionSelect } from '../shared/components/RegionSelect'
import { RiotIdInput } from '../shared/components/RiotIdInput'
```

- [ ] **Step 2: Replace the Riot-ID flex row**

Find:

```tsx
        <div className="flex gap-2">
          <input
            className="flex-1 bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
            placeholder="Game Name"
            value={gameName}
            onChange={e => setGameName(e.target.value)}
          />
          <span className="text-gray-500 self-center">#</span>
          <input
            className="w-20 bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
            placeholder="TAG"
            value={tagLine}
            onChange={e => setTagLine(e.target.value)}
          />
        </div>
```

Replace it with:

```tsx
        <RiotIdInput
          gameName={gameName}
          tagLine={tagLine}
          onGameNameChange={setGameName}
          onTagLineChange={setTagLine}
        />
```

- [ ] **Step 3: Replace the region select**

Find:

```tsx
        <select
          className="w-full bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none [color-scheme:dark]"
          value={region}
          onChange={e => setRegion(e.target.value)}
        >
          {['NA1','EUW1','EUNE1','KR','BR1','LAN','LAS','OC1','TR1','RU','JP1'].map(r => (
            <option key={r} value={r} className="bg-[#1a1a2e] text-white">{r}</option>
          ))}
        </select>
```

Replace it with:

```tsx
        <RegionSelect value={region} onChange={setRegion} />
```

- [ ] **Step 4: Verify typecheck + lint + tests pass**

Run: `npm run typecheck`
Expected: no errors.

Run: `npm run lint`
Expected: 0 errors (10 expected pre-existing warnings only).

Run: `npm test`
Expected: all tests pass (18 total).

- [ ] **Step 5: Commit**

```bash
git add src/chat/Setup.tsx
git commit -m "refactor: use shared RegionSelect + RiotIdInput in chat setup form"
```

---

## Task 5: Final full verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full gate including build**

Run: `npm run typecheck`
Expected: no errors.

Run: `npm run lint`
Expected: 0 errors (10 expected `react-refresh` warnings only).

Run: `npm test`
Expected: all tests pass (18 total: 12 pre-existing + 3 RegionSelect + 3 RiotIdInput).

Run: `npm run build`
Expected: Vite renderer build + `tsc -p tsconfig.electron.json` both succeed, no errors.

- [ ] **Step 2: Confirm no stray duplication remains**

Run: `git grep -n "EUNE1" -- src`
Expected: the region list appears in exactly one source location — `src/shared/components/RegionSelect.tsx` — plus the two test files (`RegionSelect.test.tsx` and the inline `ALL` array). Neither `src/setup/App.tsx` nor `src/chat/Setup.tsx` should contain a region list anymore.

---

## Self-Review Notes

- **Spec coverage:** RegionSelect (Task 1) + RiotIdInput (Task 2) cover the two extracted components; Tasks 3-4 cover both integration targets with handlers preserving each save path (`dirty()` vs plain setter); Task 5 covers the verification gate (typecheck/lint/test/build) and confirms single-source. All spec sections map to a task.
- **Behavior preservation:** the IPC + rollback save path (`setup/App.tsx`) and the direct-POST recovery path (`chat/Setup.tsx`) are untouched — only JSX is swapped.
- **Type consistency:** `RegionSelect` props `{ value, onChange }` and `RiotIdInput` props `{ gameName, tagLine, onGameNameChange, onTagLineChange }` are used identically across Tasks 1-4.
