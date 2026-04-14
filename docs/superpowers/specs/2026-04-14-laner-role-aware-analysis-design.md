# Laner Role-Aware Analysis — Design Spec
**Date:** 2026-04-14
**Status:** Approved

---

## Overview

Extend the post-game analysis pipeline to produce role-specific coaching moments for the four laner roles (TOP, MIDDLE, BOTTOM, UTILITY). Currently only JUNGLE has dedicated analysis (`jungle_analyzer.py`); all other roles fall through to a generic event detector that produces shallow, non-role-aware moments.

The goal is expert coaching that feels specific to what each role is responsible for — CS leads for laners, roam timing for mid, vision for support — not just "you died at 5:30."

---

## Architecture

### New File
- `sidecar/laner_analyzer.py` — entry point `analyze_laner(timeline, participant_id, lane_opponent_id, role)`. Follows the same pattern as `jungle_analyzer.py`: one entry point, `_detect_*` helpers per signal type. Handles all four laner roles with shared helpers and role-specific sections.

### Modified Files
- `sidecar/main.py` — find `lane_opponent_id` by scanning `participants` for the enemy team member whose `teamPosition` matches the player's role. Same pattern as the existing `enemy_jungler_id` lookup. Pass `lane_opponent_id` to `analyze_timeline()`.
- `sidecar/timeline_analyzer.py` — add `lane_opponent_id: int | None = None` parameter to `analyze_timeline()`. Add dispatch to `analyze_laner()` for TOP/MIDDLE/BOTTOM/UTILITY roles. UNKNOWN role keeps the generic path.
- `sidecar/counterfactual.py` — add handlers for all 7 new moment types in `enrich_moments()`.
- `sidecar/tests/test_laner_analyzer.py` — new test file covering all signals.

---

## Data Sources

### participantFrames (per frame, ~60s intervals)
- `minionsKilled` — CS count
- `totalGold` — total gold earned
- `position` — {x, y} map coordinates

### Events used
- `CHAMPION_KILL` — killerId, victimId, assistingParticipantIds, position
- `ELITE_MONSTER_KILL` — monsterType, killerId, killerTeamId
- `BUILDING_KILL` — buildingType, laneType, towerType, teamId (team that LOST it), killerId
- `TURRET_PLATE_DESTROYED` — killerId, teamId (team that LOST it), laneType
- `WARD_PLACED` — creatorId, wardType
- `WARD_KILL` — killerId, wardType

### Finding lane_opponent_id
In `main.py`, after resolving `participant_index` and `role`:
```python
enemy_team_participants = [
    (i + 1, p) for i, p in enumerate(participants)
    if (i + 1) not in player_team_ids
]
lane_opponent_entry = next(
    ((pid, p) for pid, p in enemy_team_participants
     if p.get("teamPosition") == role),
    None,
)
lane_opponent_id = lane_opponent_entry[0] if lane_opponent_entry else None
```

---

## Map Position Constants

Lane position detection (approximate Summoner's Rift coordinates, 0–14800 range):

```python
LANING_PHASE_END_SECS = 840  # 14:00

# Lane detection thresholds
TOP_LANE_X_MAX = 4500       # top lane hugs left edge
BOT_LANE_Y_MAX = 4500       # bot lane hugs bottom edge
# Mid lane: roughly diagonal, |x - y| < 2500 and away from bases

# Objective positions
DRAGON_PIT = (9866, 4414)
BARON_PIT = (5007, 10471)

# Plate tracking
PLATES_PER_TOWER = 5
PLATE_GOLD = 160
PLATE_FLAG_THRESHOLD = 3    # flag if 3+ plates lost in player's lane
```

---

## Signals

### Shared — All Laners

**`lane_death`** (negative)
- `CHAMPION_KILL` where `victimId == participant_id`, timestamp < 840s
- Position must be in player's lane area (or adjacent river)
- Subcategories (affect description + counterfactual):
  - `ganked`: `enemy_jungler_id` in killerId or assistingParticipantIds
  - `dove`: 3+ total enemies involved AND position near friendly turret
  - `1v1_loss`: only lane opponent involved, no tower
- If death doesn't match lane position, skip (handled by generic objective-area death fallback)

**`solo_kill`** (positive)
- `CHAMPION_KILL` where `killerId == participant_id`, no assisters, `victimId == lane_opponent_id`
- Position must be in player's lane area
- Confirms 1v1 kill specifically on the lane opponent (not random skirmish kill)

**`gold_differential`** (negative, all roles including SUPPORT)
- Snapshot `totalGold` for player and `lane_opponent_id` at the frame with timestamp ≥ 840,000ms
- Flag if player is 1000+ gold behind opponent
- Produces one moment at timestamp_secs = 840

**`cs_differential`** (negative, TOP / MIDDLE / BOTTOM only — not SUPPORT)
- Snapshot `minionsKilled` for player and `lane_opponent_id` at frame ≥ 840,000ms
- Flag if player is 15+ CS behind opponent
- Produces one moment at timestamp_secs = 840

**Objectives + towers** (all laners, carried from generic path)
- `objective_missed`: enemy team takes Dragon/Baron/Herald
- `objective_secured`: player's team takes Dragon/Baron/Herald
- `tower_lost`: enemy team destroys a tower on player's side

### TOP-Specific

**`turret_plates_lost`** (negative)
- Accumulate `TURRET_PLATE_DESTROYED` events where teamId = player's team AND laneType = `TOP_LANE`
- Flag once when accumulated count reaches `PLATE_FLAG_THRESHOLD` (3 plates = 480g given up)
- Moment timestamp = timestamp of the 3rd plate

**`split_push_death`** (negative)
- `CHAMPION_KILL` where `victimId == participant_id`, timestamp > 1200s (post-20 min)
- Position in top or bot lane area (side lane split push position)
- 3+ total enemies involved (collapsed on)

### MID-Specific

**`turret_plates_lost`** (negative)
- Same as TOP but laneType = `MID_LANE`

**`roam_kill`** (positive)
- `CHAMPION_KILL` where player is `killerId` or in `assistingParticipantIds`
- Position is in top or bot lane area (not mid lane area, not jungle)
- Timestamp < 840s (laning phase — roam timing window)

**`enemy_roam_kill`** (negative)
- `CHAMPION_KILL` where `lane_opponent_id` is `killerId` or in `assistingParticipantIds`
- Position is in top or bot lane area
- Timestamp < 840s
- Coaching: enemy mid was active on the map while you stayed in lane

### BOT (ADC)-Specific

**`turret_plates_lost`** (negative)
- Same as TOP but laneType = `BOT_LANE`

### SUPPORT-Specific

**`low_vision`** (negative)
- Count `WARD_PLACED` events where `creatorId == participant_id` AND timestamp < 1,200,000ms (20:00)
- Flag if total < 4 wards in first 20 minutes
- Produces one moment at timestamp_secs = 1200

**`ward_kill`** (positive)
- `WARD_KILL` event where `killerId == participant_id`
- One moment per ward killed (cap at 3 to avoid noise)

**`roam_assist`** (positive)
- `CHAMPION_KILL` where player is `killerId` or in `assistingParticipantIds`
- Position is in mid or top lane area (roamed away from bot lane)
- Timestamp < 840s

---

## Counterfactual Handlers (counterfactual.py additions)

New entries needed in `enrich_moments()`:

| moment_type | Coaching angle |
|---|---|
| `cs_differential` | "X CS = ~Yg lost. CS leads compound — farm under tower, prioritize waves over risky trades" |
| `gold_differential` | "Xg behind means your opponent will have a significant item advantage. Identify whether this came from deaths, missed CS, or missed plates." |
| `lane_death` (ganked) | "Enemy jungler was in your lane — check minimap before extending, ward river/tribush" |
| `lane_death` (dove) | "You were dove — play away from tower edge when low, have an escape route ready" |
| `lane_death` (1v1) | "You lost a straight-up trade — consider whether your champion wins this matchup at current items" |
| `turret_plates_lost` | "X plates = Yg given to the enemy for free. Crashing waves before recalling denies plates." |
| `split_push_death` | "You were collapsed on while split pushing — check team fight indicators before committing deep in a side lane" |
| `roam_kill` / `roam_assist` | Positive: reinforce the roam timing and map pressure |
| `enemy_roam_kill` | "While you farmed mid, their mid created a lead elsewhere. Match roams or shove wave first to deny the tempo." |
| `low_vision` | "Under 4 wards in 20 min is below the minimum for a support. Control wards at Dragon/Baron timers are the highest-value placements." |
| `ward_kill` | Positive: reinforce vision denial habit |

---

## Testing

`sidecar/tests/test_laner_analyzer.py` covers:

- `cs_differential`: flagged when 15+ behind, not flagged when even or ahead
- `gold_differential`: flagged when 1000+ behind, not flagged when even
- `lane_death`: each subcategory (ganked, dove, 1v1) produces correct moment_type + description
- `lane_death`: not flagged when death is outside lane area
- `solo_kill`: flagged when 1v1 in lane on opponent, not flagged when assisted or not in lane
- `turret_plates_lost`: flagged at exactly 3 plates, not before
- `split_push_death`: flagged post-20 min in side lane with 3+ enemies, not flagged pre-20 min
- `roam_kill`: flagged when kill in top/bot lane during laning phase
- `enemy_roam_kill`: flagged when opponent kills in top/bot lane
- `low_vision`: flagged when <4 wards in 20 min, not flagged when ≥4
- `ward_kill`: each ward kill produces a moment (capped at 3)
- `roam_assist`: flagged when assist in mid/top lane during laning phase
- SUPPORT: `cs_differential` NOT produced (support exemption confirmed)

---

## Out of Scope

- `caught_out` for ADC: requires tracking all teammate positions each second — not detectable reliably. Claude's coaching notes will handle contextually.
- `objective_vision` for support: `WARD_PLACED` events have no position field.
- TP flank detection: no summoner spell cast events in timeline API.
- Level 6 power spike tracking: detectable via `SKILL_LEVEL_UP` but low signal-to-noise ratio.
