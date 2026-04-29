# Session Focus Card Design Spec

## Goal

Prime the player before each game with their single most costly recurring mistake. The focus card appears in the champ select overlay when a champion is locked in, showing the top recurring issue, how often it happens, and its average gold cost — so the player enters the game with one clear thing to fix.

## Problem

The app detects patterns and tracks improvement post-game, but nothing tells the player what to focus on *before* they play. The champ select overlay already pops up automatically at the right moment; it just shows historical patterns without directing attention.

## Decisions

- **Surface:** Champ select overlay only. Right before the game is the highest-impact moment for a behavioral nudge.
- **Scope:** Champion-specific when 3+ games on the locked champion; cross-champion fallback otherwise. Falls back so new champions still show useful coaching.
- **Content:** Issue name + frequency (X of Y games) + avg gold cost. No coaching tip — keep the card punchy and scannable.
- **Selection:** Top recurring issue by frequency (highest game count with that moment type). Same signal the pattern detector already uses.

## Architecture

Two files change:

| File | Change |
|---|---|
| `sidecar/champ_select_monitor.py` | Extend `_build_champ_data()` to compute and attach `focus` field |
| `src/champ-select/App.tsx` | Add `FocusCard` component, render above pattern list when `focus` is present |

One new test file:

| File | Change |
|---|---|
| `sidecar/tests/test_champ_select_focus.py` | 3 tests covering champion-specific, fallback, and null cases |

## Data Flow

1. Champion locked → `_build_champ_data(champion)` called once, result cached
2. Fetch champion matches (up to 20). If `len(matches) < 3`: re-fetch without champion filter (cross-champion fallback)
3. Fetch moments for those match_ids (already done for pattern computation)
4. Top recurring issue = `negative_counts.most_common(1)[0]` — the moment type appearing in the most games
5. Avg gold cost = `sum(abs(m.gold_impact) for m in moments if m.moment_type == top_type) / games_seen`
   - `games_seen` = number of distinct match_ids that had at least one moment of that type
6. Attach `focus` dict to `champ_data` response

## API Contract

`GET /champ-select` — `champ_data` gains a `focus` field:

```json
{
  "in_champ_select": true,
  "locked_champion": "Graves",
  "champ_data": {
    "games": 10,
    "wins": 6,
    "win_rate": 0.6,
    "no_history": false,
    "patterns": [...],
    "focus": {
      "moment_type": "lane_death",
      "label": "Lane Deaths",
      "games_seen": 4,
      "total_games": 10,
      "avg_gold_lost": 1800,
      "champion_specific": true
    }
  }
}
```

- `avg_gold_lost` — non-negative integer; 0 if all moments of that type had `gold_impact = 0`
- `champion_specific` — `true` when computed from champion games; `false` when cross-champion fallback fired
- `focus` — `null` when there are no recurring negative issues or fewer than 3 games on any champion

## UI Spec

### FocusCard (`src/champ-select/App.tsx`)

Rendered above the existing pattern list when `champ_data.focus !== null`.

```
⚡ TODAY'S FOCUS · GRAVES          (or · ALL CHAMPIONS for fallback)
Stop dying in lane
4 of your last 10 games
avg −1,800g per game
```

Styling:
- Container: `bg-[#1e1b4b] border border-indigo-500/60 rounded-lg px-3 py-2 mx-2 mt-2`
- Label row: `text-indigo-300 text-[7px] font-bold uppercase tracking-widest`
  - Champion-specific: `⚡ TODAY'S FOCUS · {champion}`
  - Fallback: `⚡ TODAY'S FOCUS · ALL CHAMPIONS`
- Issue name: `text-white text-[11px] font-bold`
- Frequency: `text-gray-400 text-[8px]` — `{games_seen} of your last {total_games} games`
- Gold cost: `text-red-400 text-[8px] font-semibold` — `avg −{avg_gold_lost.toLocaleString()}g per game`
  - Omitted when `avg_gold_lost === 0`

## Error Handling

- `focus: null` → `FocusCard` not rendered; existing pattern list shows as before
- `avg_gold_lost === 0` → gold line omitted from card; issue + frequency still shown
- Fewer than 3 total games across all champions (no cross-champ signal either) → `focus: null`
- `gold_impact` missing or 0 for a moment → treated as 0 in the sum (pre-existing guarantee: `gold_impact` is non-nullable `int`)

## Testing

`sidecar/tests/test_champ_select_focus.py` — 3 tests:

1. **`test_focus_champion_specific`** — 5 champion games, lane_death in 4 with known gold values → correct `games_seen`, `avg_gold_lost`, `champion_specific: true`
2. **`test_focus_cross_champion_fallback`** — 2 champion games (below threshold), 8 cross-champ games with recurring issue → `champion_specific: false`, correct aggregation
3. **`test_focus_null_when_no_negatives`** — champion games with only positive moment types → `focus: null`
