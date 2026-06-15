# Setup UI Consolidation — Design

**Date:** 2026-06-15
**Status:** Approved

## Problem

Two setup UIs exist and share overlapping markup:

- **`src/setup/App.tsx`** — the standalone Electron window. Dual-purpose (first-run
  Setup *and* tray → Settings). Collects API keys + Riot ID + region; saves via the
  main-process `setup-complete` IPC with validate-before-persist, rollback, and sidecar
  restart.
- **`src/chat/Setup.tsx`** — a stripped-down form rendered *inside* the chat window,
  shown only when `/player` returns 404 (config exists but the DB has no player row —
  a DB-reset recovery case). Collects only Riot ID + region; POSTs straight to the
  sidecar `/setup` so the user re-creates the player row without re-entering API keys.

The overlap is the region `<select>` (list + dark-mode styling) and the Riot-ID
`GameName # TAG` input pair. This duplication already caused a real bug: the region
list diverged between the two files, and the `setup/App.tsx` copy offered `EUN1`/`LA1`/
`LA2` (not keys in `riot_client.py:REGIONAL_ROUTING`), silently mis-routing EU-East /
LATAM users to the `americas` cluster (fixed 2026-06-15 in `50668c0`, but in two
places). The dark-mode whiteout fix (`1652a8f`) likewise had to be applied twice.

## Goal

Eliminate the duplicated markup so the region list and Riot-ID inputs live in exactly
one place each and can never drift again — **without** changing the behavior of either
save flow. Both surfaces are kept; only the shared building blocks are extracted.

(Considered and rejected: deleting `chat/Setup.tsx` and routing the 404 recovery case to
the Electron window via a new IPC. More behavior change + a new IPC for the rarest path,
for marginal gain. Also rejected: extracting the page shell / input styles / button —
broad blast radius, low value.)

## Design

### New components — `src/shared/components/`

A new folder signals "React components" vs. the existing non-component util modules in
`src/shared/` (`types.ts`, `api.ts`, `constants.ts`, `log.ts`).

**`RegionSelect.tsx`** — single source of truth for the region dropdown.
- Owns the `REGIONS` list (with the comment tying it to `riot_client.py:REGIONAL_ROUTING`)
  and the `[color-scheme:dark]` select styling + dark `<option>` styling.
- Interface: `{ value: string; onChange: (region: string) => void; className?: string }`.
- The `REGIONS` list lives inside this file (its only consumer), not in `constants.ts`.

**`RiotIdInput.tsx`** — the `GameName # TAG` input pair.
- Interface:
  `{ gameName: string; tagLine: string; onGameNameChange: (v: string) => void; onTagLineChange: (v: string) => void }`.
- The parent owns the change side-effects, so each consumer keeps its current behavior.

### Integration (behavior preserved exactly)

- **`src/setup/App.tsx`** — replace the inline `<select>` (current lines ~126–132) and
  the Riot-ID block (~107–124) with the shared components; delete its local `REGIONS`
  const. Region `onChange` stays `v => { setRegion(v); dirty() }`; Riot-ID change handlers
  keep calling `dirty()`.
- **`src/chat/Setup.tsx`** — replace the inline `<select>` (~60–68) and Riot-ID block
  (~44–58) with the shared components; delete its inline region array. Region `onChange`
  stays `setRegion`. The direct-POST `/setup` save path is untouched.

### Data flow

Unchanged. `setup/App.tsx` still saves through the `setup-complete` IPC (validate →
rollback → restart). `chat/Setup.tsx` still POSTs directly to the sidecar `/setup`. Only
the JSX for the region select and Riot-ID inputs is sourced from shared components.

## Testing

TDD — tests written first. Add RTL component tests under the existing Vitest setup:

- **RegionSelect:** renders all 11 region options (NA1, EUW1, EUNE1, KR, BR1, LAN, LAS,
  OC1, TR1, RU, JP1); fires `onChange` with the selected value; reflects the `value` prop
  as the selected option.
- **RiotIdInput:** renders both fields with the passed values; typing fires
  `onGameNameChange` / `onTagLineChange` respectively.

The existing 12 smoke tests must stay green.

## Verification gate

Frontend change, affects build output:
`npm run typecheck`, `npm run lint` (0 errors), `npm test`, `npm run build`.

## Out of scope

- Deleting either setup surface or changing any save/validation path.
- Extracting the page shell, button, or generic input styles.
- Touching the sidecar `/setup` endpoint or the `setup-complete` IPC handler.
