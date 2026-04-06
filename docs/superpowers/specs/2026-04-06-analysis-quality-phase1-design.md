# Analysis Quality — Phase 1 Design

**Date:** 2026-04-06  
**Scope:** Smarter death detection + positive moments + color-coded popup cards

---

## Problem

The current analyzer produces generic, unhelpful moments:

- *"You died at 3:22."* — same text regardless of context
- No positive moments — the popup is a pure list of mistakes
- Deaths classified the same whether you were ganked, dove under tower, or lost a 1v1

## Goals

1. Deaths are classified into meaningful subtypes with specific coaching text
2. Positive moments (solo kills, secured objectives) appear in the popup
3. Popup cards are color-coded: green for wins, yellow for mistakes
4. All existing tests continue to pass; new tests cover new behavior

---

## Architecture

Three files change. No new files needed.

### `sidecar/timeline_analyzer.py`

#### New parameter: `enemy_jungler_id`

`analyze_timeline()` gains a second parameter:

```python
def analyze_timeline(timeline: dict, participant_id: int, enemy_jungler_id: int | None = None) -> list[PivotalMomentData]:
```

`enemy_jungler_id` is resolved in `main.py` before calling `analyze_timeline()` by scanning `match_data["info"]["participants"]` for the enemy participant whose `summoner1Id == 11` or `summoner2Id == 11` (Smite). If no smite is found (ARAM, etc.), passes `None`.

#### Death classification

Priority order (first match wins):

1. **tower_dive** — death position within 1000 units of any friendly turret (hardcoded Summoner's Rift turret positions, see below)
2. **ganked** — timestamp < 840 seconds (14:00) AND `enemy_jungler_id` is killer or in `assistingParticipantIds`
3. **outnumbered** — total enemies involved (killer + assisters) >= 2
4. **1v1_loss** — exactly 1 enemy, no assists

Death descriptions by subtype:
- `tower_dive`: *"You were tower dived at {time}."*
- `ganked`: *"You were ganked at {time}."*
- `outnumbered`: *"You were caught {n}v1 at {time}."* (n = number of enemies)
- `1v1_loss`: *"You lost a 1v1 at {time}."*

#### Turret positions (Summoner's Rift, approximate)

Team 100 (blue side) friendly turrets — used when player is on team 100:

```python
BLUE_TURRETS = [
    # Top lane
    (981, 10441), (1512, 6699), (1169, 4287),
    # Mid lane
    (5846, 6396), (5048, 4812), (3651, 3696),
    # Bot lane
    (10504, 1029), (6919, 1483), (4281, 1241),
    # Base
    (1748, 2270), (2177, 1807), (1364, 1485),
]

RED_TURRETS = [
    # Top lane
    (13866, 4357), (13327, 8143), (13604, 10474),
    # Mid lane
    (8955, 8510), (9767, 10175), (11134, 11207),
    # Bot lane
    (4318, 13875), (8955, 13411), (10961, 13654),
    # Base
    (12611, 13084), (13052, 12612), (13846, 13372),
]
```

Player is on team 100 if `participant_id` in 1–5, team 200 if 6–10. Use the appropriate turret list as "friendly turrets."

Distance formula: Euclidean distance from death `position` dict (`{"x": ..., "y": ...}`) to each turret. If min distance < 1000 → tower dive.

#### New positive moment detectors

**solo_kill** — `CHAMPION_KILL` where `killerId == participant_id` AND `assistingParticipantIds` is empty or absent:
```
description: "You got a solo kill at {time}."
moment_type: "solo_kill"
gold_impact: 300  # standard kill gold
counterfactual: ""  # filled in by counterfactual.py
```

**objective_secured** — `ELITE_MONSTER_KILL` where `killerId` is on the player's team:
```
description: "Your team secured {monster} at {time}."
moment_type: "objective_secured"
gold_impact: GOLD_VALUES[monster]
counterfactual: ""
```

#### Sorting and limit

All moments (positive + negative) sorted by `gold_impact` descending, capped at 5. This naturally surfaces the most impactful events regardless of type.

---

### `sidecar/counterfactual.py`

New branches added to `enrich_moments()`:

**Death subtypes** (keyed off description prefix, or better: use `moment_type` subtype field — see note below):

Since `moment_type` is always `"death"`, the subtype is encoded in the description. Alternatively, we use a sentinel prefix in description to branch. Simplest: check description for keywords.

| Subtype | Counterfactual text |
|---|---|
| tower_dive | *"Enemies who dive your tower are gambling — if you can avoid the all-in and let the tower do damage, it's often a losing trade for them. Positioning away from the tower edge and having an escape ready denies the dive."* |
| ganked | *"Your opponent had jungle help here. Check your minimap before extending — if the enemy jungler isn't visible on the map, assume they could be in your lane. Ward tri-bush and river to spot this earlier."* |
| outnumbered | *"Fighting outnumbered is almost never correct. Disengage early when you see multiple enemies collapsing — the longer you stay, the worse your odds. A flash to safety is worth more than trying to trade back."* |
| 1v1_loss | *"You lost a straight-up 1v1. Consider whether your champion wins this matchup at your current item level, or play for farm over fighting until you have your power spike."* |

**Positive moments:**

| Type | Counterfactual text |
|---|---|
| solo_kill | *"Clean 1v1 — you identified the right window to commit and won the trade. Look for similar patterns where your opponent is low or out of cooldowns."* |
| objective_secured | *"Good macro — converting map pressure into an objective is how leads become wins. Keep looking for these trades."* |

---

### `src/popup/MomentCard.tsx`

`momentType` is already a prop but unused in rendering. Use it to switch card styling:

**Positive types** (`solo_kill`, `objective_secured`):
- Border: `border-green-500/30`
- Background: `bg-green-500/5`
- Icon: `✓` in `text-green-400`
- Gold text: `text-green-500/70`

**Negative types** (all others):
- Existing yellow styling (unchanged)

No new props. No interface changes.

---

### `sidecar/main.py`

In `run_post_game_analysis()`, resolve `enemy_jungler_id` before calling `analyze_timeline()`:

```python
SMITE_ID = 11
enemy_team_ids = [p for p in participants if p["puuid"] != puuid and participants.index(p) + 1 not in player_team_ids]
enemy_jungler = next(
    (p for p in enemy_participants if p.get("summoner1Id") == SMITE_ID or p.get("summoner2Id") == SMITE_ID),
    None
)
enemy_jungler_id = participants.index(enemy_jungler) + 1 if enemy_jungler else None
moments = analyze_timeline(timeline_data, participant_id=participant_index, enemy_jungler_id=enemy_jungler_id)
```

Same change in `trigger_analysis.py` (the manual test script).

---

## Tests

Update `sidecar/tests/test_timeline_analyzer.py`:

| Test | What it checks |
|---|---|
| `test_death_ganked` | killerId = enemy jungler → moment_type death, description contains "ganked" |
| `test_death_outnumbered` | 2 assisters, no jungler → description contains "v1" |
| `test_death_1v1` | no assisters, not jungler → description contains "1v1" |
| `test_death_tower_dive` | death position within 1000 units of a blue turret → description contains "tower dived" |
| `test_solo_kill` | killerId == participant_id, no assists → moment_type solo_kill |
| `test_objective_secured` | friendly team kills Baron → moment_type objective_secured |
| `test_gank_only_before_14min` | same event at 15:00 → classified as outnumbered, not ganked |

---

## Out of Scope (Phase 2+)

- Recall timing analysis
- Wave state (minion tracking)
- Fighting near objective spawn timers
- Multi-game pattern detection
