# Post-Game Focus Feedback Design

## Goal

Close the coaching loop: after each game, explicitly tell the player whether they achieved their pre-game focus goal.

## Architecture

No backend changes. The popup adds a third parallel fetch to `/focus` alongside its existing `/analysis/{match_id}` and `/improvement/{match_id}` fetches. All logic is client-side.

**Data sources:**
- `/focus` → `moment_type`, `display`, `streak_clean` (returns null if no focus exists)
- `/analysis/{match_id}` → `moments[]` (already fetched) — filter by `moment_type === focus.moment_type` to get `had_in_game` and `count`

## UI

A `FocusResult` component rendered in `src/popup/App.tsx`, placed **above** the "vs your patterns" section and **below** the stat tiles. Only rendered when `/focus` returns a non-null value.

**Clean game (streak_clean > 0):**
```
🎯 YOUR FOCUS
✓  Lane Deaths — clean game! 3 in a row
```
(If streak_clean === 1: "✓ Lane Deaths — clean game!")

**Had the issue (streak_clean === 0):**
```
🎯 YOUR FOCUS
⚠  Lane Deaths — 2 times this game
```
(If count === 1: "1 time this game")

**Styling:** indigo border-left + indigo background tint, matching the focus card aesthetic from the Chat tab. Distinct from the red/green pattern rows below.

## Component

Inline in `src/popup/App.tsx` — no new file needed.

```tsx
interface FocusResult {
  moment_type: string
  display: string
  streak_clean: number
}
```

`had_in_game` and `count` are derived from `analysis.moments`, not stored.

## State and fetching

Add `focusResult` state (`FocusResult | null`) to `PopupApp`. Fetch `/focus` in the existing `Promise.all` call alongside the other two fetches. Failure or null response → `focusResult` stays null, section hidden.

## Edge cases

- No focus card (player hasn't played enough games, or top issue changed): section hidden, no visible change.
- Focus moment_type not in this game's moments: `had_in_game = false`, `count = 0` → show clean game message.
- `/focus` fetch fails: treat as null, section hidden.
