# Cross-Game Pattern Detection — Design Spec
**Date:** 2026-04-16
**Status:** Approved

---

## Overview

Detect recurring patterns across the last 20 games and surface them in two places: a patterns panel above the chat UI (proactive, always visible) and injected into the Claude chat context (so data-backed answers are automatic without the user asking).

Patterns come in two flavors: **recurring issues** (moment types that appear often and correlate with losses) and **win conditions** (moment types that appear often and correlate with wins).

---

## Architecture

No new DB tables, no schema changes, no background jobs.

### New Files
- `sidecar/pattern_detector.py` — pure function `detect_patterns(db, last_n=20) -> list[PatternResult]`

### Modified Files
- `sidecar/main.py` — add `GET /patterns` endpoint; inject pattern summary into `/chat` context
- `src/chat/App.tsx` — add pattern cards above the message list

---

## Data Model

```python
@dataclass
class PatternResult:
    moment_type: str          # e.g. "lane_death"
    label: str                # "recurring_issue" or "win_condition"
    games_seen: int           # how many of last N games had this moment_type
    total_games: int          # N (actual games analyzed, may be < last_n if DB has fewer)
    win_rate_with: float      # win rate in games where this moment_type appeared
    overall_win_rate: float   # win rate across all last_n games
    summary: str              # "lane deaths in 7 of your last 10 games (29% win rate)"
```

---

## Pattern Detection Algorithm

`detect_patterns(db, last_n=20) -> list[PatternResult]`

1. Fetch the last `last_n` matches ordered by `played_at` desc, with their pivotal moments (via JOIN or two queries)
2. If total games < 3, return `[]` — not enough data
3. For each game, collect the **set** of distinct `moment_type` values that appeared (one game counts once per type regardless of how many times it occurred)
4. Compute `overall_win_rate` = wins / total_games
5. For each `moment_type` seen across all games:
   - `games_seen` = number of games containing this type
   - `wins_with` = wins among those games
   - `win_rate_with` = wins_with / games_seen
6. **Threshold filter:** drop any moment_type where `games_seen < 3`
7. **Label assignment:**
   - `recurring_issue` if `win_rate_with < overall_win_rate - 0.10` (correlates with losses)
   - `win_condition` if `win_rate_with > overall_win_rate + 0.10` (correlates with wins)
   - Drop if neither threshold met
8. **Generate `summary` string:** `f"{human_label(moment_type).lower()} in {games_seen} of your last {total_games} games ({int(win_rate_with * 100)}% win rate)"`
9. **Sort:** recurring issues first (by `games_seen` desc), then win conditions (by `win_rate_with` desc)
10. **Cap:** return at most 5 patterns total

### Moment Type Labels (for display)

| moment_type | Human label |
|---|---|
| `lane_death` | Lane Deaths |
| `cs_differential` | CS Deficit |
| `gold_differential` | Gold Deficit |
| `turret_plates_lost` | Plates Lost |
| `split_push_death` | Split Push Deaths |
| `enemy_roam_kill` | Enemy Roams |
| `low_vision` | Low Vision |
| `objective_missed` | Missed Objectives |
| `tower_lost` | Towers Lost |
| `death` | Deaths |
| `solo_kill` | Solo Kills |
| `objective_secured` | Objectives Secured |
| `roam_kill` | Roam Kills |
| `roam_assist` | Roam Assists |
| `ward_kill` | Vision Control |

---

## API

### `GET /patterns`

Response:
```json
{
  "patterns": [
    {
      "moment_type": "lane_death",
      "label": "recurring_issue",
      "games_seen": 7,
      "total_games": 10,
      "win_rate_with": 0.29,
      "overall_win_rate": 0.50,
      "summary": "lane deaths in 7 of your last 10 games (29% win rate)"
    },
    {
      "moment_type": "objective_secured",
      "label": "win_condition",
      "games_seen": 6,
      "total_games": 10,
      "win_rate_with": 0.83,
      "overall_win_rate": 0.50,
      "summary": "objectives secured in 6 of your last 10 games (83% win rate)"
    }
  ]
}
```

Returns `{"patterns": []}` if fewer than 3 games or no significant patterns found.

### `/chat` — Pattern Injection

Before calling `claude.chat(...)`, the endpoint calls `detect_patterns(db)` and prepends a context block to the system prompt:

```
Recurring issues (last 20 games):
- lane_death: 7/10 games, 29% win rate (overall 50%)
- low_vision: 5/10 games, 30% win rate

Win conditions:
- objective_secured: 6/10 games, 83% win rate
```

If `detect_patterns` returns an empty list, no context block is prepended — the chat call proceeds unchanged.

---

## Frontend

A `PatternCard` component renders above `<MessageList>` in `App.tsx`. On mount it fetches `GET /patterns`. If patterns load successfully and the list is non-empty, a horizontal scrollable row of up to 5 cards is shown.

**Card layout:**
- Left border: red/orange for `recurring_issue`, green for `win_condition`
- Line 1: human-readable moment type label (bold)
- Line 2: e.g. "7 of 10 games · 29% WR"

**Click behavior:** clicking a card sends a pre-filled chat message, e.g. "Tell me about my lane deaths pattern" — immediately triggering a data-backed Claude response.

**Empty/loading state:** section is hidden (not rendered) — no spinner, no empty state message.

All frontend changes are in `App.tsx`. No new files.

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Fewer than 3 games in DB | `detect_patterns` returns `[]` |
| `/patterns` endpoint throws | Frontend silently hides the panel |
| Pattern injection in `/chat` fails | Chat proceeds without pattern context |
| No patterns meet threshold | `[]` returned, panel hidden |

---

## Testing

`sidecar/tests/test_pattern_detector.py`:

- `test_empty_when_no_games` — returns `[]` with 0 games
- `test_empty_when_fewer_than_3_games` — returns `[]` with 2 games
- `test_detects_recurring_issue` — moment_type in 7/10 games, win_rate 0.2 vs overall 0.5 → labelled `recurring_issue`
- `test_detects_win_condition` — moment_type in 6/10 games, win_rate 0.83 vs overall 0.5 → labelled `win_condition`
- `test_drops_below_threshold` — moment_type in 10/10 games but win_rate 0.45 vs overall 0.5 (delta < 0.10) → dropped
- `test_drops_below_min_games` — moment_type in 2/10 games → dropped regardless of win rate
- `test_sorted_issues_first_then_conditions` — recurring issues precede win conditions in output
- `test_capped_at_five` — 10 qualifying patterns → only 5 returned

---

## Out of Scope

- Champion-specific patterns (e.g. "on Caitlyn you always fall behind on CS") — future enhancement
- Trend over time (getting better/worse) — future enhancement
- Pattern notifications / push alerts — future enhancement
- Configurable window (last_n is fixed at 20)
