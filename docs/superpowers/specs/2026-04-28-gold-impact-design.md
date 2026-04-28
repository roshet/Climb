# Gold Impact Dashboard Design Spec

## Goal

Surface the `gold_impact` field — already computed by Claude and stored on every pivotal moment — throughout the UI so players feel the cost of their mistakes in LoL's native currency. "You lost 2,140g to mistakes" is a coaching message. No other tool quantifies errors this way.

## Problem

Every pivotal moment in the DB has a `gold_impact` field (Claude-estimated gold value of the event), but it is never shown anywhere in the UI. The data exists; it just needs to be exposed.

## Decisions

- **Scope:** Cost of mistakes only — sum of negative `gold_impact` values. Positive moments (solo kills, objectives secured) are excluded. The goal is actionable coaching, not a balanced scorecard.
- **Surfaces:** Post-game popup + history list + game detail view (three places total).
- **Granularity:** Game-level total shown as a stat tile, plus per-moment cost inline on each moment card.

## Architecture

Four components, all small:

| Component | File | Change |
|---|---|---|
| Matches endpoint | `sidecar/main.py` | Add `gold_lost` field to `/matches` response |
| Moment card | `src/popup/MomentCard.tsx` | Show per-moment gold cost badge |
| Post-game popup | `src/popup/App.tsx` | Replace Duration tile with Gold Lost tile |
| History list | `src/chat/HistoryList.tsx` | Add `gold_lost` to each game row |

`GameDetail.tsx` gets per-moment cost for free once `MomentCard` is updated (it already uses `MomentCard` and fetches from `/analysis/{match_id}` which already returns `gold_impact` on each moment).

## Data Flow

### Gold Lost Total (history list)

`GET /matches` gains a `gold_lost: int` field per match — the sum of negative `gold_impact` values across that match's pivotal moments. Computed at query time via a SQLAlchemy subquery or Python post-processing; no schema change needed.

```python
# In list_matches() in main.py, after fetching matches:
match_ids = [m.match_id for m in matches]
all_moments = get_pivotal_moments(db, match_ids)  # already imported
gold_by_match: dict[str, int] = {}
for moment in all_moments:
    if moment.gold_impact and moment.gold_impact < 0:
        gold_by_match[moment.match_id] = gold_by_match.get(moment.match_id, 0) + abs(moment.gold_impact)
```

Each match in the response gains: `"gold_lost": gold_by_match.get(m.match_id, 0)`.

### Gold Lost Total (popup / game detail)

`GET /analysis/{match_id}` already returns `gold_impact` on each moment. The frontend computes the total client-side:

```ts
const goldLost = moments
  .filter(m => m.gold_impact < 0)
  .reduce((sum, m) => sum + Math.abs(m.gold_impact), 0)
```

No backend change needed for the popup or game detail.

## API Contract

### GET /matches (updated)

Each match object gains one field:

```json
{
  "match_id": "NA1_123",
  "champion": "Graves",
  "role": "JUNGLE",
  "result": "loss",
  "kda": "3/5/2",
  "duration_secs": 1694,
  "played_at": "2026-04-28T14:00:00",
  "moment_count": 3,
  "gold_lost": 2140
}
```

`gold_lost` is always a non-negative integer (0 if no negative-impact moments).

### GET /analysis/{match_id} (unchanged)

Already returns `gold_impact` (signed int) on each moment. Frontend derives the total.

## UI Spec

### MomentCard (`src/popup/MomentCard.tsx`)

Add a gold cost badge next to the timestamp on every card where `gold_impact < 0`. Shown in both collapsed and expanded states.

```
[LANE DEATH]  −680g  4:32
Died to Renekton before level 6...
```

- Badge: `text-red-400 text-xs font-mono`
- Format: `−${gold_impact.toLocaleString()}g` (e.g. `−680g`, `−1,460g`)
- Only rendered when `gold_impact < 0`. Zero and positive values: no badge.

### Post-Game Popup (`src/popup/App.tsx`)

Replace the Duration stat tile with a Gold Lost tile. Duration is already available from `analysis.duration_secs` if needed elsewhere; it is not shown in the tile grid after this change.

**Gold Lost tile:**
- Label: `Gold Lost`
- Value: `−${goldLost.toLocaleString()}g`
- Background: `bg-red-950` with `border border-red-800`
- Text: `text-red-200` (label), `text-white font-bold` (value)
- When `goldLost === 0`: show `−0g` in muted style (`text-gray-500`)

### History List (`src/chat/HistoryList.tsx`)

Add gold lost below the moment count on the right side of each game row.

```
Graves · JGL          3/5/2 · 28:14    [3 moments]
                                        −2,140g
```

Color-coded by severity:
- `< 500g`: `text-green-400` (clean game)
- `500–1500g`: `text-yellow-400` (moderate)
- `> 1500g`: `text-red-400` (costly game)

Format: `−${gold_lost.toLocaleString()}g`
When `gold_lost === 0`: show nothing (omit the field entirely — a clean game needs no label).

## Error Handling

- `gold_impact` missing or null on a moment: treat as 0 (skip in sum).
- Match has no moments at all: `gold_lost: 0`, no tile shown (history) / tile shows `−0g` muted (popup).
- `/matches` fetch fails: history list renders without gold column — existing graceful degradation handles this.

## Testing

`sidecar/tests/test_main.py` — add 2 tests to the existing matches endpoint tests:

1. `test_matches_includes_gold_lost` — match with 2 negative moments and 1 positive → `gold_lost` equals sum of the two negative values only
2. `test_matches_gold_lost_zero_when_no_moments` — match with no moments → `gold_lost: 0`

No frontend tests (existing build verification is sufficient).
