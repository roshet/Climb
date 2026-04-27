# Improvement Tracking Design Spec

## Goal

Show players whether they are actually getting better over time by adding a "vs your patterns" section to the existing post-game popup. After each game, the popup compares what happened in this game against the player's established champion-specific patterns — highlighting streaks of improvement and flagging recurring issues they keep repeating.

## Problem

The app diagnoses patterns but never closes the loop. A player told "you die early in 5/7 Graves games" has no way to know whether that's getting better or worse. This feature surfaces that signal at the one moment of peak engagement: right after a game ends.

## Architecture

Four components, all small:

| Component | File | Change |
|---|---|---|
| Improvement tracker | `sidecar/improvement_tracker.py` (new) | `get_improvement_data(db, match_id)` |
| API endpoint | `sidecar/main.py` | `GET /improvement/{match_id}` |
| Tests | `sidecar/tests/test_improvement_tracker.py` (new) | 6 unit tests |
| Popup UI | `src/popup/App.tsx` | New "vs your patterns" section |

No new DB schema — everything computed from existing matches and moments tables.

## Data Computation

`get_improvement_data(db, match_id)` in `sidecar/improvement_tracker.py`:

1. Load the match by `match_id` from DB → get `champion`
2. Fetch last 20 matches for this champion via `get_matches(db, champion=champion, last_n=20)`
3. If fewer than 3 matches for this champion → return `{"champion": champion, "patterns": []}` (not enough history)
4. Fetch all moments for those 20 matches via `get_pivotal_moments(db, match_ids)`
5. Compute top 2 most frequent negative moment types (not in `POSITIVE_TYPES`) → recurring issues
6. Compute top 1 most frequent positive moment type (in `POSITIVE_TYPES`, wins-only) → win condition
7. For each pattern compute:
   - `had_in_game`: whether any moment for `match_id` has this `moment_type`
   - `streak`: count of consecutive most-recent games (newest first, including this game if clean) without this `moment_type` for recurring issues; count of consecutive recent games with this `moment_type` for win conditions
   - `recent_rate`: count of games with this `moment_type` in the last 5 games (of the 20)
8. Filter win condition: only include if `had_in_game` is true OR `recent_rate >= 3` (don't penalise missing a win condition once)

`POSITIVE_TYPES` and `MOMENT_LABELS` are imported from `champ_select_monitor.py` — no duplication.

## API Contract

`GET /improvement/{match_id}` response:

```json
{
  "champion": "Graves",
  "patterns": [
    {
      "label": "recurring_issue",
      "moment_type": "lane_death",
      "display": "Lane Deaths",
      "had_in_game": false,
      "streak": 3,
      "recent_rate": 1
    },
    {
      "label": "recurring_issue",
      "moment_type": "objective_missed",
      "display": "Missed Objectives",
      "had_in_game": true,
      "streak": 0,
      "recent_rate": 4
    },
    {
      "label": "win_condition",
      "moment_type": "solo_kill",
      "display": "Solo Kills",
      "had_in_game": true,
      "streak": 0,
      "recent_rate": 3
    }
  ]
}
```

No history / insufficient data:
```json
{"champion": "Graves", "patterns": []}
```

Match not found in DB: `404`

## Display Logic

Each pattern renders as a coloured row in the "vs your patterns" section:

| Condition | Display | Colour |
|---|---|---|
`display` values come from `MOMENT_LABELS` (e.g. `"Lane Deaths"`). The frontend lowercases them for sentence rendering (e.g. `"lane deaths"`).

| Condition | Display | Colour |
|---|---|---|
| Recurring issue, `had_in_game` false, `streak >= 2` | `✓ No {display.lower()} · {streak} clean in a row` | Green |
| Recurring issue, `had_in_game` false, `streak == 1` | `✓ No {display.lower()} this game` | Green |
| Recurring issue, `had_in_game` true | `⚠ {display} again · {recent_rate}/5 recent games` | Red |
| Win condition, `had_in_game` true | `✓ {display} — keep it up` | Green |
| Win condition, `had_in_game` false, `recent_rate >= 3` | `⚠ No {display.lower()} — usually your win condition` | Red |

Section is silently hidden when `patterns` is empty or the `/improvement` fetch fails.

## Popup UI

`src/popup/App.tsx` fetches `/analysis/{match_id}` and `/improvement/{match_id}` in parallel on mount. The improvement section renders below the existing moments list when patterns are non-empty:

```
─────────────────────────────────────
  vs your patterns (Graves)
  ✓ No early deaths · 3 clean in a row
  ⚠ Missed objectives again · 4/5
  ✓ Solo kills — keep it up
```

Each row uses the same colour scheme as the champ select window: `border-red-500 bg-red-950/80` for issues, `border-green-500 bg-green-950/80` for positive outcomes.

## Error Handling

- Fewer than 3 games on this champion → section hidden, no error shown
- `match_id` not in DB → 404 from endpoint; popup silently skips the section
- DB query fails → `patterns: []`; section hidden
- `/improvement` fetch fails in frontend → section silently hidden; rest of popup unaffected

## Testing

`sidecar/tests/test_improvement_tracker.py` — 6 unit tests:

1. `test_returns_empty_when_insufficient_history` — fewer than 3 matches → `patterns == []`
2. `test_had_in_game_true_when_moment_present` — match has a `lane_death` moment → `had_in_game == True` for that pattern
3. `test_had_in_game_false_when_moment_absent` — match has no `lane_death` → `had_in_game == False`
4. `test_streak_counts_consecutive_clean_games` — 3 recent games without `lane_death`, this game also clean → `streak == 4`
5. `test_recent_rate_counts_last_5_games` — 4 of last 5 games have `objective_missed` → `recent_rate == 4`
6. `test_win_condition_filtered_when_rare_and_absent` — win condition not in this game and `recent_rate < 3` → not included in patterns
