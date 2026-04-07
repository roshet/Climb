# Phase 2: Role-Aware Analysis + AI Coaching — Design Spec

**Date:** 2026-04-07  
**Status:** Approved  
**Scope:** Jungle role (other roles degrade gracefully to Phase 1 + AI coaching text)

---

## Goal

Replace generic, role-blind coaching with context-aware analysis that understands what role the player played and what the important moments were for that role. For jungle specifically: detect invade deaths, counter-ganks, missed objective rotations, successful ganks, and objective steals. Replace static counterfactual strings with Gemini-generated 3–4 sentence coaching notes that use the surrounding game context to reason about whether a decision was correct or not.

---

## Architecture: Hybrid — Rules Detect, AI Explains

The system has two distinct jobs:

1. **Detection (rules):** Identify *what* happened — invade death, missed Dragon, successful gank. Fast, deterministic, testable.
2. **Explanation (Gemini):** Write a coaching note that explains *why* it mattered and *what the correct play was* given the full game context surrounding the moment. One Gemini call per game (not per moment) to stay within free tier limits (20 RPD).

This separation handles the scenario the user raised — "bot lane died on a bad timer so you couldn't contest Dragon" — because Gemini sees the surrounding events (bot lane death at 4:47, jungler position, who was alive) and reasons through them rather than applying a static rule.

---

## Role Routing

`timeline_analyzer.py` reads `role` (from match data `teamPosition` field) and routes:

- `JUNGLE` → `jungle_analyzer.py` (8 new moment types + existing generic detection)
- All other roles → existing Phase 1 generic detection (deaths, solo kills, objectives, towers)

For non-jungle roles, Gemini still generates the coaching text (replacing static `counterfactual.py` strings), but no new moment types are added. The app works for all roles — just less tailored outside jungle.

---

## New File: `sidecar/jungle_analyzer.py`

Single responsibility: detect jungle-specific pivotal moments from the timeline. Returns `list[PivotalMomentData]`. Accepts `timeline`, `participant_id`, `enemy_jungler_id`. Team side is inferred from `participant_id` using `TEAM_100_IDS`/`TEAM_200_IDS` (same pattern as `timeline_analyzer.py`).

### Mistake Detections (moment_type stays "death" or new types)

| Moment Type | Detection Logic |
|---|---|
| `invade_death` | `CHAMPION_KILL` where `victimId == participant_id` AND death position is inside enemy jungle quadrant |
| `counter_ganked` | `CHAMPION_KILL` where `victimId == participant_id`, position is in an ally lane, AND `enemy_jungler_id` is in `assistingParticipantIds` or is `killerId` |
| `dragon_missed` | `ELITE_MONSTER_KILL` monsterType=DRAGON by enemy team, jungler was alive (no CHAMPION_KILL victimId==participant_id in prior 30s), AND jungler's position in the most recent timeline frame before the objective was top-side (y > 7000 for blue side, y < 7500 for red side) |
| `baron_missed` | Same as dragon_missed but monsterType=BARON_NASHOR. Position check: jungler was bot-side (y < 7500 for blue, y > 7000 for red) |
| `void_grubs_missed` | Count `ELITE_MONSTER_KILL` monsterType=HORDE by enemy team — if enemy gets all 3, flag once |

### Positive Detections

| Moment Type | Detection Logic |
|---|---|
| `gank_assist` | `CHAMPION_KILL` where `participant_id` is `killerId` or in `assistingParticipantIds`, victim is an enemy, AND position is inside an ally lane (not jungle) |
| `baron_secured` | `ELITE_MONSTER_KILL` monsterType=BARON_NASHOR by player's team |
| `dragon_stack` | `ELITE_MONSTER_KILL` monsterType=DRAGON by player's team (each stack) |

### Map Position Constants

```python
# Approximate quadrant boundaries for Summoner's Rift
# Blue side jungle: top-left quadrant
BLUE_JUNGLE_X_MAX = 7000
BLUE_JUNGLE_Y_MIN = 7500

# Red side jungle: bottom-right quadrant  
RED_JUNGLE_X_MIN = 8000
RED_JUNGLE_Y_MAX = 7500

# Lane detection (approximate)
TOP_LANE_X_MAX = 4000       # top lane hugs left edge
BOT_LANE_Y_MAX = 4000       # bot lane hugs bottom edge
# Mid lane = diagonal strip (neither top nor bot lane position)

# Objective proximity
DRAGON_PIT = (9866, 4414)
BARON_PIT = (5007, 10471)
OBJECTIVE_RADIUS = 2000     # within 2000 units = near objective
```

---

## Modified: `sidecar/timeline_analyzer.py`

Add role routing at the top of `analyze_timeline`:

```python
def analyze_timeline(
    timeline: dict,
    participant_id: int,
    enemy_jungler_id: int | None = None,
    role: str = "UNKNOWN",
    champion: str = "Unknown",
) -> list[PivotalMomentData]:
    if role == "JUNGLE":
        from jungle_analyzer import analyze_jungle
        return analyze_jungle(timeline, participant_id, enemy_jungler_id)
    # existing generic detection for all other roles
    ...
```

The generic path (all non-jungle roles) is unchanged from Phase 1.

---

## Modified: `sidecar/claude_client.py`

Add a new method `generate_coaching_notes(moments, game_context)` that:

1. Builds a context window for each moment: all events within ±90 seconds of the moment's timestamp, summarised as a readable list (event type, participants, timestamp)
2. Constructs a single prompt with all moments and their context windows
3. Calls Gemini once, asks it to return JSON: `[{"id": 0, "coaching": "..."}, ...]`
4. Fills `moment.counterfactual` for each moment with the returned coaching text

### Game Context Header (sent with every call)

```
Champion: {champion} | Role: Jungler | Side: {blue/red}
Result: {win/loss} | KDA: {k}/{d}/{a} | Game duration: {mm:ss}
Gold diff at 15min: {+/- Xg} (if available)
```

### Prompt Structure

```
You are coaching a {champion} jungler. {game_context_header}

For each moment below, write a 3-4 sentence coaching note. Be specific to the jungler role. 
Reference what was happening in the context. Give one concrete, achievable alternative action.
Use encouraging language for positive moments. Don't moralize — describe game state, not character.

[0] {moment_type} — {description}
Context (±90s): {summarised_surrounding_events}
---
[1] ...

Return ONLY valid JSON: [{"id": 0, "coaching": "..."}, ...]
```

### Fallback

If Gemini call fails (rate limit, timeout): fall back to `counterfactual.py` static strings. No crash.

---

## Modified: `sidecar/main.py` and `sidecar/trigger_analysis.py`

Pass `role` and `champion` to `analyze_timeline` and `generate_coaching_notes`:

```python
role = participant.get("teamPosition", "UNKNOWN")      # JUNGLE, TOP, MID, etc.
champion = participant["championName"]

moments = analyze_timeline(
    timeline_data,
    participant_id=participant_index,
    enemy_jungler_id=enemy_jungler_id,
    role=role,
    champion=champion,
)
enriched = await client.generate_coaching_notes(moments, game_context)
```

`counterfactual.enrich_moments()` is removed from the main pipeline — Gemini replaces it for all roles. `counterfactual.py` is kept as the fallback only.

---

## Modified: `sidecar/counterfactual.py`

No longer called in the main pipeline. Kept as fallback, called only when `generate_coaching_notes` fails. No code changes needed — just removed from the happy path in `main.py`.

---

## Popup UI

No changes needed. `MomentCard.tsx` already handles all moment types via the `momentType` prop. New types (`invade_death`, `gank_assist`, etc.) will display correctly:

- `gank_assist`, `baron_secured`, `dragon_stack` → green (already in `POSITIVE_TYPES` set — needs `gank_assist`, `baron_secured`, `dragon_stack` added)
- `invade_death`, `counter_ganked`, `dragon_missed`, `baron_missed`, `void_grubs_missed` → yellow

Update `MomentCard.tsx`:
```tsx
const POSITIVE_TYPES = new Set(['solo_kill', 'objective_secured', 'gank_assist', 'baron_secured', 'dragon_stack'])
```

---

## New File: `sidecar/tests/test_jungle_analyzer.py`

One test per detection type (8 tests minimum):

- `test_invade_death` — death position in enemy jungle quadrant
- `test_counter_ganked` — death in ally lane with enemy jungler in kill
- `test_gank_assist` — kill in enemy laner's lane with jungler participating
- `test_dragon_missed` — enemy Dragon kill, jungler alive and top-side
- `test_dragon_not_missed_if_dead` — enemy Dragon kill, but jungler died 5s prior (not flagged)
- `test_baron_missed` — enemy Baron kill, jungler alive
- `test_void_grubs_missed` — enemy gets all 3 HORDE kills
- `test_dragon_stack_secured` — team gets Dragon

---

## What Stays the Same

- Electron app, React popup, database schema — no changes
- Phase 1 moment types (tower_dive, ganked, outnumbered, 1v1, solo_kill, objective_secured, objective_missed, tower_lost) — still detected for non-jungle roles
- Popup display (chronological order, green/yellow cards) — no changes
- Riot API integration — no changes

---

## Out of Scope (Phase 3)

- Role-aware detection for TOP, MID, ADC, SUPPORT
- Personal pattern detection across 50+ games (ML/trend analysis)
- Smite steal detection (requires HP tracking not in timeline API)
- TP usage analysis (requires item activation event inference)
