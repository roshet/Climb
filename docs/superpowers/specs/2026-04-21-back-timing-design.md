# Back Timing Analysis — Design Spec
**Date:** 2026-04-21
**Status:** Approved

---

## Overview

Add post-game back timing analysis to detect when a player recalled at a costly moment. Two signals are detected: recalling within 90 seconds of an objective spawning, and recalling with too little gold to buy anything meaningful (before 20:00). Both signals produce `PivotalMomentData` entries that feed into the existing Claude coaching pipeline.

---

## Architecture

All logic lives in `sidecar/laner_analyzer.py` as a new `_detect_bad_backs()` function. It is called from `analyze_laner()` at the end, alongside the existing `_cs_differential_at_14` and `_gold_differential_at_14` checks. The jungle role is excluded — jungler backing patterns differ fundamentally from laners.

No new files are required in the sidecar. Tests go in a new `sidecar/tests/test_back_timing.py`.

---

## Back Detection

Backs are inferred from two sources, then deduplicated:

### Primary: ITEM_PURCHASED events
When a player buys an item, they were in base. The event timestamp is the back time. Pre-back gold is estimated as `currentGold` from the preceding frame plus any gold earned between that frame and the purchase (approximated as 0 — close enough given 60s frame resolution).

### Secondary: Frame position jumps
For each consecutive frame pair, if the player's position moves from a non-base location to within 1500 units of their fountain, a back is recorded at the later frame's timestamp.

**Fountain coordinates:**
- Blue side (Team 100): `(523, 523)`
- Red side (Team 200): `(14340, 14390)`
- Radius: 1500 units

### Deduplication
If a purchase event and a position jump fall within 60 seconds of each other, they are treated as one back (purchase timestamp takes priority).

### Death exclusion
Any back within the player's respawn timer of a preceding `CHAMPION_KILL` event where `victimId == participant_id` is ignored. The player was already in base respawning — not a voluntary recall.

Respawn timer approximation: `8 + (level * 2.5)` seconds, capped at 60 seconds.

---

## Bad Back Signals

### Signal 1: `bad_back_objective`

**Condition:** A back occurs within 90 seconds before a dragon, baron, or rift herald spawn time.

**Spawn times tracked:**
- First dragon: 5:00 (300s). Respawn: 5 minutes after kill event.
- First baron: 20:00 (1200s). Respawn: 6 minutes after kill event.
- First rift herald: 8:00 (480s). Second spawn: 14:00 (840s). No respawn after that.

Spawn times are computed dynamically from `ELITE_MONSTER_KILL` events — when a kill event is seen, the next spawn time for that objective is recorded. First spawn times are hardcoded constants.

**Message format:**
`"You recalled {N}s before {Objective} spawned at {time_str} — your team may have been short-handed for the contest."`

**Counterfactual (passed to Claude):**
`"If you were healthy when you recalled here, waiting until after the objective spawned or asking your team to delay could have avoided giving up {objective} control."`

**Gold impact:** Dragon: 350g, Baron: 900g, Rift Herald: 400g (the objective value forfeited by being absent).

---

### Signal 2: `bad_back_gold`

**Condition:** Back occurs before 20:00 (1200s) with pre-back gold below threshold.

**Tiers:**

| Pre-back gold | Tier | Message |
|---|---|---|
| < 300g | waste | "You recalled with only {gold}g — not enough to buy any component." |
| 300–499g | minor | "You recalled with only {gold}g — enough for a minor component (Long Sword / Dagger / Tome) but little else." |

Gold 500–899g is only flagged if ALSO within an objective window (caught by Signal 1). Gold ≥ 900g is never flagged for gold alone.

**Counterfactual (passed to Claude):**
`"If you were healthy when you recalled, staying in lane a bit longer to accumulate gold for a meaningful purchase would have been more efficient."`

**Gold impact:** `900 - pre_back_gold` (approximate cost of the cheapest meaningful component they couldn't afford).

---

## HP/Mana Caveat

The Riot Match Timeline API does not expose current HP or mana — only max values. We cannot determine whether the player was at 10% HP or 90% HP when they recalled. All flagged backs include the qualifier *"if you were healthy when you recalled"* in the counterfactual to avoid falsely blaming low-health recalls.

---

## Constants

```python
# Fountain detection
FOUNTAIN_BLUE = (523, 523)
FOUNTAIN_RED = (14340, 14390)
FOUNTAIN_RADIUS = 1500

# Objective spawn times (seconds)
DRAGON_FIRST_SPAWN = 300
DRAGON_RESPAWN_DELAY = 300
BARON_FIRST_SPAWN = 1200
BARON_RESPAWN_DELAY = 360
HERALD_FIRST_SPAWN = 480
HERALD_SECOND_SPAWN = 840

# Back timing windows
OBJECTIVE_DANGER_WINDOW_SECS = 90   # Flag back if objective spawns within this
LATE_GAME_CUTOFF_SECS = 1200        # No gold-tier flags after 20:00
BACK_DEDUP_WINDOW_SECS = 60         # Purchase + position jump = one back

# Gold tiers
GOLD_WASTE_THRESHOLD = 300          # < 300g: waste tier
GOLD_MINOR_THRESHOLD = 500          # 300-499g: minor tier

# Respawn exclusion
RESPAWN_BASE_SECS = 8
RESPAWN_PER_LEVEL_SECS = 2.5
RESPAWN_CAP_SECS = 60
```

---

## New Moment Types

| moment_type | Description |
|---|---|
| `bad_back_objective` | Recalled within 90s of objective spawn |
| `bad_back_gold` | Recalled with < 500g before 20:00 |

Both are added to the `pattern_detector.py` moment type awareness so they can surface as cross-game patterns (e.g., "you recall before dragon in 6 of 20 games").

---

## Tests (`sidecar/tests/test_back_timing.py`)

- `test_objective_window_back` — back 60s before dragon → `bad_back_objective` fired
- `test_back_after_objective_safe` — back 30s after dragon spawned → not flagged
- `test_low_gold_back_under_300` — back with 250g before 20:00 → waste tier flagged
- `test_low_gold_back_300_to_500` — back with 400g before 20:00 → minor tier flagged
- `test_gold_back_after_20min` — back with 200g after 20:00 → not flagged
- `test_back_excluded_after_death` — back within respawn timer → not flagged
- `test_deduplication` — purchase + position jump within 60s → one back recorded
- `test_high_gold_not_flagged` — back with 1000g → not flagged for gold

---

## Out of Scope

- Jungle role back timing (backing patterns differ: between camps, not on wave timer)
- HP/mana-based back detection (data not available in timeline API)
- Live overlay back warnings (live overlay already covers "objective spawning soon")
- Build-path-aware gold thresholds (requires tracking full build state per champion)
