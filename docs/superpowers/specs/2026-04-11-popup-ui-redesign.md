# Popup UI Redesign — Design Spec

**Date:** 2026-04-11  
**Status:** Approved  

---

## Goal

Redesign the post-game popup to be more scannable and polished. The current design shows a flat list of cards with all coaching text always visible, no game summary at a glance, and no way to filter. The new design fixes all four pain points: game summary, collapsible coaching, type labels, and filtering.

---

## Layout

### Stat Tiles (top)

Four equal-width tiles in a 4-column grid below the "Game Analysis" header:

| Tile | Value | Color |
|---|---|---|
| Champion | champion name | purple (#a78bfa) |
| Result | WIN / LOSS | green (#34d399) / red (#f87171) |
| KDA | e.g. 8/3/12 | white |
| Time | e.g. 31m | white |

Each tile has a small uppercase grey label above the value. Result tile background tints green on WIN, red on LOSS.

The existing `Takeaway` component is **removed** — these tiles replace it.

---

### Filter Bar

Three pill-shaped filter tabs below the stat tiles:

- **All · N** (selected by default, indigo background)
- **✓ Good · N** (count of positive moment types)
- **⚠ Fix · N** (count of negative moment types)

Clicking a tab filters the visible cards. Active tab has a solid indigo background; inactive tabs are dark with grey text. Counts are computed from `analysis.moments` on render.

Positive types (green cards): `solo_kill`, `objective_secured`, `gank_assist`, `baron_secured`, `dragon_stack`  
Negative types (yellow cards): everything else

---

### Moment Cards

Each card shows:

1. **Type label** — uppercase, letter-spaced, color-coded (green or yellow), e.g. `GANK ASSIST`
2. **Timestamp** — same row as label, muted opacity, e.g. `3:14`
3. **Description** — white text, 12px
4. **Expand arrow** (▼/▲) — right-aligned, clicking toggles the coaching note

**Collapsed state:** label + timestamp + description + arrow. No coaching text visible.

**Expanded state:** same as collapsed, plus a divider line and the full coaching note in grey 11px text. Gold impact shown at the bottom of the expanded section in muted color.

Cards are sorted chronologically (existing behavior, unchanged). Expand state is per-card local React state — expanding one card does not affect others.

---

## Component Changes

### `MomentCard.tsx` (modify)

- Add `useState<boolean>(false)` for `expanded`
- Render type label + timestamp row above description
- Render expand arrow, toggle `expanded` on click
- Conditionally render coaching note + gold impact when `expanded`
- Remove always-visible counterfactual and gold impact from collapsed view

### `App.tsx` (modify)

- Add `useState<'all' | 'positive' | 'negative'>('all')` for active filter
- Replace `<Takeaway />` with the 4 stat tiles grid
- Add filter bar below stat tiles
- Filter `analysis.moments` before mapping to `<MomentCard />` based on active filter
- Pass `role` from `analysis` to display in header (future-proofing — `analysis` already returns `role` from the `/analysis/:matchId` endpoint via `match.role`)

### `Takeaway.tsx` (delete)

No longer needed — replaced by stat tiles in `App.tsx`.

---

## Data

No backend changes needed. The `/analysis/:matchId` endpoint already returns:
- `champion`, `result`, `duration_secs`, `kda`, `moments[]`

The `role` field is already saved in the `matches` table — expose it from the endpoint by adding it to the response in `main.py`.

---

## Out of Scope

- Pagination or virtual scrolling (26 moments is fine to render all at once)
- Animations on expand/collapse (keep it simple)
- Champion icons or images
- Any backend changes beyond adding `role` to the analysis response
