# Laner Role-Aware Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `laner_analyzer.py` with role-specific coaching moments for TOP/MID/BOT/SUPPORT, replacing the generic fallback path in `analyze_timeline()` for all laner roles.

**Architecture:** Single `laner_analyzer.py` with shared helpers and role-specific signal detectors, following `jungle_analyzer.py`'s pattern. `main.py` finds `lane_opponent_id` by matching `teamPosition` on the enemy team. `analyze_timeline()` dispatches to `analyze_laner()` for all laner roles. `counterfactual.py` gets handlers for all new moment types.

**Tech Stack:** Python 3.11+, pytest (run from `sidecar/` directory), Riot Games Match Timeline API v5

---

## File Structure

- **Create:** `sidecar/laner_analyzer.py` — entry point + all signal detectors
- **Create:** `sidecar/tests/test_laner_analyzer.py` — all laner signal tests
- **Modify:** `sidecar/main.py` — add `lane_opponent_id` lookup, pass to `analyze_timeline`
- **Modify:** `sidecar/timeline_analyzer.py` — add `lane_opponent_id` param, dispatch to `analyze_laner`
- **Modify:** `sidecar/counterfactual.py` — handlers for all new moment types

---

### Task 1: Plumbing — lane_opponent_id lookup + analyze_timeline dispatch

**Files:**
- Modify: `sidecar/main.py:87-108`
- Modify: `sidecar/timeline_analyzer.py:219-251`
- Create (stub): `sidecar/laner_analyzer.py`

- [ ] **Step 1: Write the failing dispatch test**

Add to `sidecar/tests/test_timeline_analyzer.py`:

```python
def test_analyze_timeline_dispatches_to_laner_for_top():
    # role="TOP" should dispatch to laner_analyzer (not generic path)
    # Empty frames: no moments, but must not crash and must return a list
    timeline = {"info": {"frames": []}}
    result = analyze_timeline(timeline, participant_id=1, role="TOP", lane_opponent_id=6)
    assert isinstance(result, list)

def test_analyze_timeline_dispatches_to_laner_for_support():
    timeline = {"info": {"frames": []}}
    result = analyze_timeline(timeline, participant_id=1, role="UTILITY", lane_opponent_id=6)
    assert isinstance(result, list)

def test_analyze_timeline_generic_path_still_works_for_unknown():
    # UNKNOWN role must still hit the generic path (existing behavior unchanged)
    timeline = {"info": {"frames": [
        make_frame(480000, [
            {"type": "CHAMPION_KILL", "timestamp": 480000,
             "killerId": 7, "victimId": 1,
             "assistingParticipantIds": [],
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    result = analyze_timeline(timeline, participant_id=1, role="UNKNOWN")
    assert any(m.moment_type == "death" for m in result)
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar
pytest tests/test_timeline_analyzer.py::test_analyze_timeline_dispatches_to_laner_for_top -v
```

Expected: `FAILED` — `TypeError: analyze_timeline() got an unexpected keyword argument 'lane_opponent_id'`

- [ ] **Step 3: Create stub `sidecar/laner_analyzer.py`**

```python
from timeline_analyzer import PivotalMomentData


def analyze_laner(
    timeline: dict,
    participant_id: int,
    lane_opponent_id: int | None,
    role: str,
    enemy_jungler_id: int | None = None,
) -> list[PivotalMomentData]:
    return []
```

- [ ] **Step 4: Update `analyze_timeline` signature and add dispatch**

In `sidecar/timeline_analyzer.py`, replace the `analyze_timeline` function signature and add the laner dispatch:

```python
def analyze_timeline(
    timeline: dict,
    participant_id: int,
    enemy_jungler_id: int | None = None,
    role: str = "UNKNOWN",
    champion: str = "Unknown",
    lane_opponent_id: int | None = None,
) -> list[PivotalMomentData]:
    if role == "JUNGLE":
        from jungle_analyzer import analyze_jungle
        return analyze_jungle(timeline, participant_id, enemy_jungler_id)

    if role in ("TOP", "MIDDLE", "BOTTOM", "UTILITY"):
        from laner_analyzer import analyze_laner
        return analyze_laner(timeline, participant_id, lane_opponent_id, role, enemy_jungler_id)

    moments: list[PivotalMomentData] = []
    frames = timeline.get("info", {}).get("frames", [])

    for frame in frames:
        for event in frame.get("events", []):
            event_type = event.get("type")
            moment = None
            if event_type == "CHAMPION_KILL":
                death = _classify_death(event, participant_id, enemy_jungler_id)
                solo = _score_solo_kill(event, participant_id)
                moment = death or solo
            elif event_type == "ELITE_MONSTER_KILL":
                missed = _score_objective_missed(event, participant_id)
                secured = _score_objective_secured(event, participant_id)
                moment = missed or secured
            elif event_type == "BUILDING_KILL":
                moment = _score_tower(event, participant_id)
            if moment:
                moments.append(moment)

    moments.sort(key=lambda m: m.timestamp_secs)
    return moments
```

- [ ] **Step 5: Add `lane_opponent_id` lookup to `main.py`**

In `sidecar/main.py`, after line 87 (`enemy_jungler_id = enemy_jungler_entry[0] if ...`):

```python
        lane_opponent_entry = next(
            ((i + 1, p) for i, p in enumerate(participants)
             if (i + 1) not in player_team_ids
             and p.get("teamPosition") == role),
            None,
        )
        lane_opponent_id = lane_opponent_entry[0] if lane_opponent_entry else None
```

Then update the `analyze_timeline` call (currently at line 103) to pass the new parameter:

```python
        moments = analyze_timeline(
            timeline_data,
            participant_id=participant_index,
            enemy_jungler_id=enemy_jungler_id,
            role=role,
            champion=champion,
            lane_opponent_id=lane_opponent_id,
        )
```

- [ ] **Step 6: Run all three new tests**

```
cd sidecar
pytest tests/test_timeline_analyzer.py -v
```

Expected: All tests PASS (including all pre-existing tests — the generic path is unchanged for role="UNKNOWN")

- [ ] **Step 7: Commit**

```bash
git add sidecar/laner_analyzer.py sidecar/timeline_analyzer.py sidecar/main.py sidecar/tests/test_timeline_analyzer.py
git commit -m "feat: wire lane_opponent_id lookup and analyze_laner dispatch"
```

---

### Task 2: Core signals — lane_death, solo_kill, objectives, towers

**Files:**
- Modify: `sidecar/laner_analyzer.py`
- Create: `sidecar/tests/test_laner_analyzer.py`

**Context:** The participant IDs we'll use throughout: `TOP_ID = 1` (blue side, team 100), `OPPONENT_ID = 6` (red side, team 200), `ENEMY_JUNGLER_ID = 7`. Blue side is top-left; top lane has `x < 4500`. Bot lane has `y < 4500`. Mid lane runs diagonally where `|x - y| < 2500` and `3000 < x < 12000`.

- [ ] **Step 1: Write failing tests**

Create `sidecar/tests/test_laner_analyzer.py`:

```python
import pytest
from laner_analyzer import analyze_laner

TOP_ID = 1          # blue side top (team 100, participants 1-5)
OPPONENT_ID = 6     # red side top (team 200, participants 6-10)
ENEMY_JUNGLER_ID = 7


def make_frame(
    timestamp_ms: int,
    events: list,
    positions: dict | None = None,
    cs: dict | None = None,
    gold: dict | None = None,
) -> dict:
    """
    positions: {pid: (x, y)} — defaults to (5000, 5000)
    cs: {pid: minionsKilled} — defaults to 0
    gold: {pid: totalGold} — defaults to 3000
    """
    pf = {}
    for pid in range(1, 11):
        pos = (positions or {}).get(pid, (5000, 5000))
        pf[str(pid)] = {
            "position": {"x": pos[0], "y": pos[1]},
            "minionsKilled": (cs or {}).get(pid, 0),
            "totalGold": (gold or {}).get(pid, 3000),
        }
    return {"timestamp": timestamp_ms, "participantFrames": pf, "events": events}


# --- lane_death ---

def test_lane_death_ganked_top_lane():
    # TOP_ID dies at (2000, 12000) — top lane (x < 4500), enemy jungler involved
    timeline = {"info": {"frames": [
        make_frame(300_000, [
            {"type": "CHAMPION_KILL", "timestamp": 300_000,
             "killerId": ENEMY_JUNGLER_ID, "victimId": TOP_ID,
             "assistingParticipantIds": [OPPONENT_ID],
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP", ENEMY_JUNGLER_ID)
    deaths = [m for m in moments if m.moment_type == "lane_death"]
    assert len(deaths) == 1
    assert "ganked" in deaths[0].description.lower()


def test_lane_death_dove_top_lane():
    # TOP_ID dies with 3 enemies at (981, 10441) — near blue top turret, x < 4500
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": OPPONENT_ID, "victimId": TOP_ID,
             "assistingParticipantIds": [7, 8],   # 3 total enemies
             "position": {"x": 981, "y": 10441}},  # near Blue top tower
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP", ENEMY_JUNGLER_ID)
    deaths = [m for m in moments if m.moment_type == "lane_death"]
    assert len(deaths) == 1
    assert "dove" in deaths[0].description.lower()


def test_lane_death_1v1_loss_top_lane():
    # TOP_ID dies to only OPPONENT_ID, no jungler, in top lane
    timeline = {"info": {"frames": [
        make_frame(300_000, [
            {"type": "CHAMPION_KILL", "timestamp": 300_000,
             "killerId": OPPONENT_ID, "victimId": TOP_ID,
             "assistingParticipantIds": [],
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP", ENEMY_JUNGLER_ID)
    deaths = [m for m in moments if m.moment_type == "lane_death"]
    assert len(deaths) == 1
    assert "1v1" in deaths[0].description.lower()


def test_lane_death_not_flagged_after_14min():
    # Same death but at 15:00 — laning phase is over, should NOT produce lane_death
    timeline = {"info": {"frames": [
        make_frame(900_000, [
            {"type": "CHAMPION_KILL", "timestamp": 900_000,
             "killerId": OPPONENT_ID, "victimId": TOP_ID,
             "assistingParticipantIds": [],
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP", ENEMY_JUNGLER_ID)
    deaths = [m for m in moments if m.moment_type == "lane_death"]
    assert len(deaths) == 0


def test_lane_death_not_flagged_outside_lane():
    # TOP_ID dies at mid-map (8000, 8000) — not in top lane, not a lane_death
    timeline = {"info": {"frames": [
        make_frame(300_000, [
            {"type": "CHAMPION_KILL", "timestamp": 300_000,
             "killerId": OPPONENT_ID, "victimId": TOP_ID,
             "assistingParticipantIds": [],
             "position": {"x": 8000, "y": 8000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP", ENEMY_JUNGLER_ID)
    deaths = [m for m in moments if m.moment_type == "lane_death"]
    assert len(deaths) == 0


# --- solo_kill ---

def test_solo_kill_in_lane_on_opponent():
    # TOP_ID solo kills OPPONENT_ID in top lane
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": TOP_ID, "victimId": OPPONENT_ID,
             "assistingParticipantIds": [],
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP", ENEMY_JUNGLER_ID)
    kills = [m for m in moments if m.moment_type == "solo_kill"]
    assert len(kills) == 1
    assert "solo kill" in kills[0].description.lower()


def test_solo_kill_not_flagged_with_assists():
    # Assisted kill — not a solo kill
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": TOP_ID, "victimId": OPPONENT_ID,
             "assistingParticipantIds": [2],
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP", ENEMY_JUNGLER_ID)
    kills = [m for m in moments if m.moment_type == "solo_kill"]
    assert len(kills) == 0


def test_solo_kill_not_flagged_outside_lane():
    # Kill on opponent but outside top lane area
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": TOP_ID, "victimId": OPPONENT_ID,
             "assistingParticipantIds": [],
             "position": {"x": 8000, "y": 8000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP", ENEMY_JUNGLER_ID)
    kills = [m for m in moments if m.moment_type == "solo_kill"]
    assert len(kills) == 0


# --- objectives ---

def test_objective_missed_dragon():
    timeline = {"info": {"frames": [
        make_frame(325_000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 323_000,
             "killerId": OPPONENT_ID, "monsterType": "DRAGON"},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    missed = [m for m in moments if m.moment_type == "objective_missed"]
    assert len(missed) == 1


def test_objective_secured_baron():
    timeline = {"info": {"frames": [
        make_frame(1_205_000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 1_203_000,
             "killerId": 3, "monsterType": "BARON_NASHOR"},  # teammate, team 100
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    secured = [m for m in moments if m.moment_type == "objective_secured"]
    assert len(secured) == 1
    assert secured[0].gold_impact == 900


# --- tower ---

def test_tower_lost():
    # teamId=100 means team 100 (player's team) LOST the tower
    timeline = {"info": {"frames": [
        make_frame(720_000, [
            {"type": "BUILDING_KILL", "timestamp": 725_000,
             "killerId": OPPONENT_ID, "teamId": 100,
             "buildingType": "TOWER_BUILDING",
             "laneType": "TOP_LANE", "towerType": "OUTER_TURRET"},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    towers = [m for m in moments if m.moment_type == "tower_lost"]
    assert len(towers) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar
pytest tests/test_laner_analyzer.py -v
```

Expected: All FAIL with `ImportError` or assertions since `analyze_laner` is a stub.

- [ ] **Step 3: Implement laner_analyzer.py with core signals**

Replace `sidecar/laner_analyzer.py` entirely:

```python
import math
from timeline_analyzer import (
    PivotalMomentData,
    TEAM_100_IDS, TEAM_200_IDS, GOLD_VALUES,
    BLUE_TURRETS, RED_TURRETS, TOWER_DIVE_RADIUS,
)

# --- Timing ---
LANING_PHASE_END_SECS = 840   # 14:00
POST_LANING_SECS = 1200       # 20:00

# --- Lane position thresholds (Summoner's Rift ~0-14800 coordinate space) ---
TOP_LANE_X_MAX = 4500
BOT_LANE_Y_MAX = 4500

# --- Plate tracking ---
PLATE_FLAG_THRESHOLD = 3
PLATE_GOLD = 160

# --- Support vision ---
SUPPORT_WARD_MINIMUM = 4
SUPPORT_VISION_WINDOW_MS = 1_200_000   # 20:00
WARD_KILL_CAP = 3


# --- Position helpers ---

def _in_top_lane(position: dict) -> bool:
    return position.get("x", 0) < TOP_LANE_X_MAX


def _in_bot_lane(position: dict) -> bool:
    return position.get("y", 0) < BOT_LANE_Y_MAX


def _in_mid_lane(position: dict) -> bool:
    px, py = position.get("x", 0), position.get("y", 0)
    return abs(px - py) < 2500 and 3000 < px < 12000


def _in_any_side_lane(position: dict) -> bool:
    return _in_top_lane(position) or _in_bot_lane(position)


def _in_player_lane(position: dict, role: str) -> bool:
    if role == "TOP":
        return _in_top_lane(position)
    if role == "MIDDLE":
        return _in_mid_lane(position)
    if role in ("BOTTOM", "UTILITY"):
        return _in_bot_lane(position)
    return False


def _near_friendly_turret(position: dict, participant_id: int) -> bool:
    px, py = position.get("x", 0), position.get("y", 0)
    turrets = BLUE_TURRETS if participant_id in TEAM_100_IDS else RED_TURRETS
    return any(
        math.sqrt((px - tx) ** 2 + (py - ty) ** 2) < TOWER_DIVE_RADIUS
        for tx, ty in turrets
    )


# --- Shared signal detectors ---

def _detect_lane_death(
    event: dict,
    participant_id: int,
    enemy_jungler_id: int | None,
    role: str,
) -> PivotalMomentData | None:
    if event.get("victimId") != participant_id:
        return None
    ts = event["timestamp"] // 1000
    if ts >= LANING_PHASE_END_SECS:
        return None
    position = event.get("position", {"x": 0, "y": 0})
    if not _in_player_lane(position, role):
        return None

    killer_id = event.get("killerId", 0)
    assisters = event.get("assistingParticipantIds", [])
    total_enemies = len(set([killer_id] + list(assisters)) - {0})
    mins, secs = divmod(ts, 60)
    time_str = f"{mins}:{secs:02d}"

    # Ganked: enemy jungler involved
    if enemy_jungler_id and (killer_id == enemy_jungler_id or enemy_jungler_id in assisters):
        return PivotalMomentData(
            timestamp_secs=ts,
            moment_type="lane_death",
            description=f"You were ganked at {time_str}.",
            counterfactual="",
            gold_impact=GOLD_VALUES["DEATH"],
        )

    # Dove: 3+ enemies AND near friendly turret
    if total_enemies >= 3 and _near_friendly_turret(position, participant_id):
        return PivotalMomentData(
            timestamp_secs=ts,
            moment_type="lane_death",
            description=f"You were dove at {time_str} ({total_enemies} enemies collapsed under your tower).",
            counterfactual="",
            gold_impact=GOLD_VALUES["DEATH"],
        )

    # 1v1 loss
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="lane_death",
        description=f"You lost a 1v1 trade at {time_str}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _detect_solo_kill_in_lane(
    event: dict,
    participant_id: int,
    lane_opponent_id: int | None,
    role: str,
) -> PivotalMomentData | None:
    if event.get("killerId") != participant_id:
        return None
    if event.get("assistingParticipantIds"):
        return None
    if lane_opponent_id is None or event.get("victimId") != lane_opponent_id:
        return None
    position = event.get("position", {"x": 0, "y": 0})
    if not _in_player_lane(position, role):
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="solo_kill",
        description=f"You got a solo kill on your lane opponent at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _score_objective_missed(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("type") != "ELITE_MONSTER_KILL":
        return None
    enemy_team = TEAM_200_IDS if participant_id in TEAM_100_IDS else TEAM_100_IDS
    if event.get("killerId", 0) not in enemy_team:
        return None
    monster = event.get("monsterType", "UNKNOWN")
    gold = GOLD_VALUES.get(monster, 300)
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="objective_missed",
        description=f"Enemy team secured {monster.replace('_', ' ').title()} at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=gold,
    )


def _score_objective_secured(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("type") != "ELITE_MONSTER_KILL":
        return None
    player_team = TEAM_100_IDS if participant_id in TEAM_100_IDS else TEAM_200_IDS
    if event.get("killerId", 0) not in player_team:
        return None
    monster = event.get("monsterType", "UNKNOWN")
    gold = GOLD_VALUES.get(monster, 300)
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="objective_secured",
        description=f"Your team secured {monster.replace('_', ' ').title()} at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=gold,
    )


def _score_tower_lost(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("type") != "BUILDING_KILL":
        return None
    player_team_id = 100 if participant_id in TEAM_100_IDS else 200
    if event.get("teamId") != player_team_id:
        return None
    tower_type = event.get("towerType", "OUTER_TURRET")
    gold = GOLD_VALUES.get(f"TOWER_{tower_type.replace('_TURRET', '')}", 150)
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    lane = event.get("laneType", "").replace("_LANE", "").title()
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="tower_lost",
        description=f"Enemy took your {lane} {tower_type.replace('_', ' ').lower()} at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=gold,
    )


# --- Entry point (shared signals only for now, role-specific added in later tasks) ---

def analyze_laner(
    timeline: dict,
    participant_id: int,
    lane_opponent_id: int | None,
    role: str,
    enemy_jungler_id: int | None = None,
) -> list[PivotalMomentData]:
    moments: list[PivotalMomentData] = []
    frames = timeline.get("info", {}).get("frames", [])

    for frame in frames:
        for event in frame.get("events", []):
            event_type = event.get("type")
            moment = None

            if event_type == "CHAMPION_KILL":
                moment = (
                    _detect_lane_death(event, participant_id, enemy_jungler_id, role)
                    or _detect_solo_kill_in_lane(event, participant_id, lane_opponent_id, role)
                )
            elif event_type == "ELITE_MONSTER_KILL":
                moment = (
                    _score_objective_missed(event, participant_id)
                    or _score_objective_secured(event, participant_id)
                )
            elif event_type == "BUILDING_KILL":
                moment = _score_tower_lost(event, participant_id)

            if moment:
                moments.append(moment)

    moments.sort(key=lambda m: m.timestamp_secs)
    return moments
```

- [ ] **Step 4: Run tests**

```
cd sidecar
pytest tests/test_laner_analyzer.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sidecar/laner_analyzer.py sidecar/tests/test_laner_analyzer.py
git commit -m "feat: laner_analyzer core — lane_death, solo_kill, objectives, towers"
```

---

### Task 3: CS and gold differential

**Files:**
- Modify: `sidecar/laner_analyzer.py`
- Modify: `sidecar/tests/test_laner_analyzer.py`

- [ ] **Step 1: Write failing tests**

Append to `sidecar/tests/test_laner_analyzer.py`:

```python
# --- CS differential ---

def test_cs_differential_flagged_when_15_behind():
    # Frame at 14:00 (840_000ms): player has 60 CS, opponent has 80 CS — 20 behind
    timeline = {"info": {"frames": [
        make_frame(840_000, [],
                   cs={TOP_ID: 60, OPPONENT_ID: 80}),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    cs_moments = [m for m in moments if m.moment_type == "cs_differential"]
    assert len(cs_moments) == 1
    assert "20 CS" in cs_moments[0].description
    assert cs_moments[0].timestamp_secs == 840


def test_cs_differential_not_flagged_when_less_than_15_behind():
    # 10 CS behind — below threshold
    timeline = {"info": {"frames": [
        make_frame(840_000, [],
                   cs={TOP_ID: 70, OPPONENT_ID: 80}),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    cs_moments = [m for m in moments if m.moment_type == "cs_differential"]
    assert len(cs_moments) == 0


def test_cs_differential_not_flagged_for_support():
    # SUPPORT role must never produce cs_differential
    timeline = {"info": {"frames": [
        make_frame(840_000, [],
                   cs={1: 0, 6: 80}),
    ]}}
    moments = analyze_laner(timeline, 1, 6, "UTILITY")
    cs_moments = [m for m in moments if m.moment_type == "cs_differential"]
    assert len(cs_moments) == 0


def test_cs_differential_not_flagged_when_ahead():
    # Player is ahead — no moment produced
    timeline = {"info": {"frames": [
        make_frame(840_000, [],
                   cs={TOP_ID: 90, OPPONENT_ID: 70}),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    cs_moments = [m for m in moments if m.moment_type == "cs_differential"]
    assert len(cs_moments) == 0


# --- Gold differential ---

def test_gold_differential_flagged_when_1000_behind():
    # Player: 4000g, opponent: 5500g — 1500g behind
    timeline = {"info": {"frames": [
        make_frame(840_000, [],
                   gold={TOP_ID: 4000, OPPONENT_ID: 5500}),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    gold_moments = [m for m in moments if m.moment_type == "gold_differential"]
    assert len(gold_moments) == 1
    assert "1500" in gold_moments[0].description
    assert gold_moments[0].timestamp_secs == 840


def test_gold_differential_flagged_for_support():
    # Support should get gold_differential (no CS exemption for gold)
    timeline = {"info": {"frames": [
        make_frame(840_000, [],
                   gold={1: 2000, 6: 4000}),
    ]}}
    moments = analyze_laner(timeline, 1, 6, "UTILITY")
    gold_moments = [m for m in moments if m.moment_type == "gold_differential"]
    assert len(gold_moments) == 1


def test_gold_differential_not_flagged_when_less_than_1000_behind():
    # 800g behind — below threshold
    timeline = {"info": {"frames": [
        make_frame(840_000, [],
                   gold={TOP_ID: 4200, OPPONENT_ID: 5000}),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    gold_moments = [m for m in moments if m.moment_type == "gold_differential"]
    assert len(gold_moments) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar
pytest tests/test_laner_analyzer.py::test_cs_differential_flagged_when_15_behind -v
```

Expected: `FAILED` — `AssertionError` (no cs_differential moments returned)

- [ ] **Step 3: Implement `_cs_differential_at_14` and `_gold_differential_at_14`**

Add these two functions to `sidecar/laner_analyzer.py` (before `analyze_laner`):

```python
def _cs_differential_at_14(
    frames: list,
    participant_id: int,
    lane_opponent_id: int,
) -> PivotalMomentData | None:
    snapshot = next(
        (f for f in frames if f["timestamp"] >= 840_000),
        None,
    )
    if snapshot is None:
        return None
    pf = snapshot.get("participantFrames", {})
    player_cs = pf.get(str(participant_id), {}).get("minionsKilled", 0)
    opponent_cs = pf.get(str(lane_opponent_id), {}).get("minionsKilled", 0)
    diff = opponent_cs - player_cs
    if diff < 15:
        return None
    return PivotalMomentData(
        timestamp_secs=840,
        moment_type="cs_differential",
        description=f"You were {diff} CS behind your lane opponent at 14:00.",
        counterfactual="",
        gold_impact=diff * 21,  # ~21g per minion average
    )


def _gold_differential_at_14(
    frames: list,
    participant_id: int,
    lane_opponent_id: int,
) -> PivotalMomentData | None:
    snapshot = next(
        (f for f in frames if f["timestamp"] >= 840_000),
        None,
    )
    if snapshot is None:
        return None
    pf = snapshot.get("participantFrames", {})
    player_gold = pf.get(str(participant_id), {}).get("totalGold", 0)
    opponent_gold = pf.get(str(lane_opponent_id), {}).get("totalGold", 0)
    diff = opponent_gold - player_gold
    if diff < 1000:
        return None
    return PivotalMomentData(
        timestamp_secs=840,
        moment_type="gold_differential",
        description=f"You were {diff}g behind your lane opponent at 14:00.",
        counterfactual="",
        gold_impact=diff,
    )
```

Then add calls in `analyze_laner`, after the main loop (before the `moments.sort` line):

```python
    # Frame-based signals: CS and gold differential
    if lane_opponent_id is not None:
        if role in ("TOP", "MIDDLE", "BOTTOM"):
            cs_moment = _cs_differential_at_14(frames, participant_id, lane_opponent_id)
            if cs_moment:
                moments.append(cs_moment)
        gold_moment = _gold_differential_at_14(frames, participant_id, lane_opponent_id)
        if gold_moment:
            moments.append(gold_moment)

    moments.sort(key=lambda m: m.timestamp_secs)
    return moments
```

- [ ] **Step 4: Run tests**

```
cd sidecar
pytest tests/test_laner_analyzer.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sidecar/laner_analyzer.py sidecar/tests/test_laner_analyzer.py
git commit -m "feat: laner_analyzer CS and gold differential signals"
```

---

### Task 4: TOP and MID role-specific signals

**Files:**
- Modify: `sidecar/laner_analyzer.py`
- Modify: `sidecar/tests/test_laner_analyzer.py`

- [ ] **Step 1: Write failing tests**

Append to `sidecar/tests/test_laner_analyzer.py`:

```python
# --- Turret plates ---

def test_turret_plates_lost_flagged_at_3():
    # 3 TURRET_PLATE_DESTROYED events in TOP_LANE, teamId=100 (player's team lost them)
    plate_events = [
        {"type": "TURRET_PLATE_DESTROYED", "timestamp": (300_000 + i * 60_000),
         "teamId": 100, "laneType": "TOP_LANE", "killerId": OPPONENT_ID}
        for i in range(3)
    ]
    timeline = {"info": {"frames": [
        make_frame(300_000 + i * 60_000, [plate_events[i]])
        for i in range(3)
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    plates = [m for m in moments if m.moment_type == "turret_plates_lost"]
    assert len(plates) == 1
    assert "480" in plates[0].description  # 3 * 160g = 480g


def test_turret_plates_not_flagged_before_3():
    # Only 2 plates — below threshold
    plate_events = [
        {"type": "TURRET_PLATE_DESTROYED", "timestamp": (300_000 + i * 60_000),
         "teamId": 100, "laneType": "TOP_LANE", "killerId": OPPONENT_ID}
        for i in range(2)
    ]
    timeline = {"info": {"frames": [
        make_frame(300_000 + i * 60_000, [plate_events[i]])
        for i in range(2)
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    plates = [m for m in moments if m.moment_type == "turret_plates_lost"]
    assert len(plates) == 0


def test_turret_plates_not_flagged_wrong_lane():
    # Plates lost in MID_LANE — TOP player should not be flagged
    plate_events = [
        {"type": "TURRET_PLATE_DESTROYED", "timestamp": (300_000 + i * 60_000),
         "teamId": 100, "laneType": "MID_LANE", "killerId": OPPONENT_ID}
        for i in range(3)
    ]
    timeline = {"info": {"frames": [
        make_frame(300_000 + i * 60_000, [plate_events[i]])
        for i in range(3)
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    plates = [m for m in moments if m.moment_type == "turret_plates_lost"]
    assert len(plates) == 0


# --- Split push death (TOP) ---

def test_split_push_death_post_20min():
    # TOP_ID dies in top lane (x < 4500) after 20 min with 3 enemies
    timeline = {"info": {"frames": [
        make_frame(1_200_000, [
            {"type": "CHAMPION_KILL", "timestamp": 1_200_000,
             "killerId": OPPONENT_ID, "victimId": TOP_ID,
             "assistingParticipantIds": [7, 8],  # 3 total enemies
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    splits = [m for m in moments if m.moment_type == "split_push_death"]
    assert len(splits) == 1
    assert "3" in splits[0].description


def test_split_push_death_not_flagged_before_20min():
    # Same event but at 19:59 — not post-laning enough
    timeline = {"info": {"frames": [
        make_frame(1_199_000, [
            {"type": "CHAMPION_KILL", "timestamp": 1_199_000,
             "killerId": OPPONENT_ID, "victimId": TOP_ID,
             "assistingParticipantIds": [7, 8],
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    splits = [m for m in moments if m.moment_type == "split_push_death"]
    assert len(splits) == 0


def test_split_push_death_not_flagged_with_fewer_than_3_enemies():
    # Only 2 enemies — not a collapse, maybe just a skirmish
    timeline = {"info": {"frames": [
        make_frame(1_200_000, [
            {"type": "CHAMPION_KILL", "timestamp": 1_200_000,
             "killerId": OPPONENT_ID, "victimId": TOP_ID,
             "assistingParticipantIds": [7],  # 2 total enemies
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    splits = [m for m in moments if m.moment_type == "split_push_death"]
    assert len(splits) == 0


# --- Roam kill (MID) ---
# MID_ID = 3 (blue team), OPPONENT_MID_ID = 8 (red team)
MID_ID = 3
OPPONENT_MID_ID = 8

def test_roam_kill_mid_in_bot_lane():
    # MID_ID kills someone in bot lane (y < 4500) during laning phase
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": MID_ID, "victimId": 9,
             "assistingParticipantIds": [],
             "position": {"x": 10000, "y": 2000}},  # bot lane
        ]),
    ]}}
    moments = analyze_laner(timeline, MID_ID, OPPONENT_MID_ID, "MIDDLE")
    roams = [m for m in moments if m.moment_type == "roam_kill"]
    assert len(roams) == 1
    assert "roam" in roams[0].description.lower()


def test_roam_kill_not_flagged_in_mid_lane():
    # Kill happens in mid lane — not a roam
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": MID_ID, "victimId": OPPONENT_MID_ID,
             "assistingParticipantIds": [],
             "position": {"x": 7000, "y": 7000}},  # mid lane diagonal
        ]),
    ]}}
    moments = analyze_laner(timeline, MID_ID, OPPONENT_MID_ID, "MIDDLE")
    roams = [m for m in moments if m.moment_type == "roam_kill"]
    assert len(roams) == 0


def test_roam_kill_not_flagged_after_14min():
    # Kill in bot lane but after laning phase — not tracked as a roam
    timeline = {"info": {"frames": [
        make_frame(900_000, [
            {"type": "CHAMPION_KILL", "timestamp": 900_000,
             "killerId": MID_ID, "victimId": 9,
             "assistingParticipantIds": [],
             "position": {"x": 10000, "y": 2000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, MID_ID, OPPONENT_MID_ID, "MIDDLE")
    roams = [m for m in moments if m.moment_type == "roam_kill"]
    assert len(roams) == 0


# --- Enemy roam kill (MID) ---

def test_enemy_roam_kill_opponent_roams_top():
    # OPPONENT_MID_ID gets a kill in top lane (x < 4500) during laning phase
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": OPPONENT_MID_ID, "victimId": 1,
             "assistingParticipantIds": [],
             "position": {"x": 2000, "y": 12000}},  # top lane
        ]),
    ]}}
    moments = analyze_laner(timeline, MID_ID, OPPONENT_MID_ID, "MIDDLE")
    enemy_roams = [m for m in moments if m.moment_type == "enemy_roam_kill"]
    assert len(enemy_roams) == 1
    assert "enemy mid" in enemy_roams[0].description.lower()


def test_enemy_roam_kill_not_flagged_when_killing_player():
    # Opponent kills MID_ID directly — that's a lane_death, not an enemy_roam_kill
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": OPPONENT_MID_ID, "victimId": MID_ID,
             "assistingParticipantIds": [],
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, MID_ID, OPPONENT_MID_ID, "MIDDLE")
    enemy_roams = [m for m in moments if m.moment_type == "enemy_roam_kill"]
    assert len(enemy_roams) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar
pytest tests/test_laner_analyzer.py::test_turret_plates_lost_flagged_at_3 tests/test_laner_analyzer.py::test_split_push_death_post_20min tests/test_laner_analyzer.py::test_roam_kill_mid_in_bot_lane -v
```

Expected: All FAIL.

- [ ] **Step 3: Implement TOP/MID signal detectors**

Add these functions to `sidecar/laner_analyzer.py` (before `analyze_laner`):

```python
def _detect_split_push_death(
    event: dict,
    participant_id: int,
) -> PivotalMomentData | None:
    if event.get("victimId") != participant_id:
        return None
    ts = event["timestamp"] // 1000
    if ts < POST_LANING_SECS:
        return None
    position = event.get("position", {"x": 0, "y": 0})
    if not _in_any_side_lane(position):
        return None
    killer_id = event.get("killerId", 0)
    assisters = event.get("assistingParticipantIds", [])
    total_enemies = len(set([killer_id] + list(assisters)) - {0})
    if total_enemies < 3:
        return None
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="split_push_death",
        description=f"You were collapsed on by {total_enemies} enemies while split pushing at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _detect_roam_kill(
    event: dict,
    participant_id: int,
) -> PivotalMomentData | None:
    killer_id = event.get("killerId", 0)
    assisters = event.get("assistingParticipantIds", [])
    if killer_id != participant_id and participant_id not in assisters:
        return None
    victim_id = event.get("victimId", 0)
    if victim_id == participant_id or victim_id == 0:
        return None
    ts = event["timestamp"] // 1000
    if ts >= LANING_PHASE_END_SECS:
        return None
    position = event.get("position", {"x": 0, "y": 0})
    if not _in_any_side_lane(position):
        return None
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="roam_kill",
        description=f"Your roam resulted in a kill at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _detect_enemy_roam_kill(
    event: dict,
    participant_id: int,
    lane_opponent_id: int,
) -> PivotalMomentData | None:
    killer_id = event.get("killerId", 0)
    assisters = event.get("assistingParticipantIds", [])
    if killer_id != lane_opponent_id and lane_opponent_id not in assisters:
        return None
    # Only flag if they killed someone OTHER than the player (killing player = lane_death)
    if event.get("victimId") == participant_id:
        return None
    ts = event["timestamp"] // 1000
    if ts >= LANING_PHASE_END_SECS:
        return None
    position = event.get("position", {"x": 0, "y": 0})
    if not _in_any_side_lane(position):
        return None
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="enemy_roam_kill",
        description=f"Enemy mid roamed for a kill at {mins}:{secs:02d} while you were in lane.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )
```

Now update `analyze_laner`'s main event loop to wire these in. Replace the `if event_type == "CHAMPION_KILL":` block:

```python
            if event_type == "CHAMPION_KILL":
                moment = (
                    _detect_lane_death(event, participant_id, enemy_jungler_id, role)
                    or _detect_solo_kill_in_lane(event, participant_id, lane_opponent_id, role)
                )
                if moment is None and role == "TOP":
                    moment = _detect_split_push_death(event, participant_id)
                if moment is None and role == "MIDDLE":
                    moment = _detect_roam_kill(event, participant_id)
                    if moment is None and lane_opponent_id is not None:
                        moment = _detect_enemy_roam_kill(event, participant_id, lane_opponent_id)
```

Also add plate tracking. Add these variables before the `for frame in frames:` loop:

```python
    plate_count = 0
    plates_flagged = False
    player_team_id = 100 if participant_id in TEAM_100_IDS else 200
    role_to_lane = {"TOP": "TOP_LANE", "MIDDLE": "MID_LANE", "BOTTOM": "BOT_LANE"}
```

And add a new `elif` branch inside the events loop (after the BUILDING_KILL branch):

```python
            elif event_type == "TURRET_PLATE_DESTROYED" and not plates_flagged and role in role_to_lane:
                if (event.get("teamId") == player_team_id
                        and event.get("laneType") == role_to_lane[role]):
                    plate_count += 1
                    if plate_count == PLATE_FLAG_THRESHOLD:
                        plates_flagged = True
                        ts = event["timestamp"] // 1000
                        mins, secs = divmod(ts, 60)
                        total_gold = PLATE_FLAG_THRESHOLD * PLATE_GOLD
                        moment = PivotalMomentData(
                            timestamp_secs=ts,
                            moment_type="turret_plates_lost",
                            description=f"Enemy took {PLATE_FLAG_THRESHOLD} tower plates in your lane by {mins}:{secs:02d} ({total_gold}g given up).",
                            counterfactual="",
                            gold_impact=total_gold,
                        )
```

- [ ] **Step 4: Run tests**

```
cd sidecar
pytest tests/test_laner_analyzer.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sidecar/laner_analyzer.py sidecar/tests/test_laner_analyzer.py
git commit -m "feat: laner_analyzer TOP and MID role signals"
```

---

### Task 5: SUPPORT-specific signals

**Files:**
- Modify: `sidecar/laner_analyzer.py`
- Modify: `sidecar/tests/test_laner_analyzer.py`

- [ ] **Step 1: Write failing tests**

Append to `sidecar/tests/test_laner_analyzer.py`:

```python
# --- Support signals ---
# SUPP_ID = 5 (blue team), OPPONENT_SUPP_ID = 10 (red team)
SUPP_ID = 5
OPPONENT_SUPP_ID = 10


def test_low_vision_flagged_when_under_4_wards():
    # 3 wards placed in 20 min — below SUPPORT_WARD_MINIMUM (4)
    ward_events = [
        {"type": "WARD_PLACED", "timestamp": 200_000 + i * 200_000,
         "creatorId": SUPP_ID, "wardType": "YELLOW_TRINKET"}
        for i in range(3)
    ]
    timeline = {"info": {"frames": [
        make_frame(200_000 + i * 200_000, [ward_events[i]])
        for i in range(3)
    ] + [make_frame(1_200_000, [])]}}
    moments = analyze_laner(timeline, SUPP_ID, OPPONENT_SUPP_ID, "UTILITY")
    vision = [m for m in moments if m.moment_type == "low_vision"]
    assert len(vision) == 1
    assert "3" in vision[0].description
    assert vision[0].timestamp_secs == 1200


def test_low_vision_not_flagged_when_4_or_more_wards():
    # 4 wards — meets minimum
    ward_events = [
        {"type": "WARD_PLACED", "timestamp": 200_000 + i * 200_000,
         "creatorId": SUPP_ID, "wardType": "YELLOW_TRINKET"}
        for i in range(4)
    ]
    timeline = {"info": {"frames": [
        make_frame(200_000 + i * 200_000, [ward_events[i]])
        for i in range(4)
    ] + [make_frame(1_200_000, [])]}}
    moments = analyze_laner(timeline, SUPP_ID, OPPONENT_SUPP_ID, "UTILITY")
    vision = [m for m in moments if m.moment_type == "low_vision"]
    assert len(vision) == 0


def test_low_vision_wards_after_20min_not_counted():
    # All wards placed after 20 min — should flag as 0 wards in first 20 min
    ward_events = [
        {"type": "WARD_PLACED", "timestamp": 1_300_000 + i * 60_000,
         "creatorId": SUPP_ID, "wardType": "YELLOW_TRINKET"}
        for i in range(4)
    ]
    timeline = {"info": {"frames": [
        make_frame(1_200_000, []),
        make_frame(1_300_000 + i * 60_000, [ward_events[i]])
        for i in range(4)
    ]}}
    moments = analyze_laner(timeline, SUPP_ID, OPPONENT_SUPP_ID, "UTILITY")
    vision = [m for m in moments if m.moment_type == "low_vision"]
    assert len(vision) == 1
    assert "0" in vision[0].description


def test_ward_kill_flagged():
    timeline = {"info": {"frames": [
        make_frame(300_000, [
            {"type": "WARD_KILL", "timestamp": 300_000,
             "killerId": SUPP_ID, "wardType": "YELLOW_TRINKET"},
        ]),
    ]}}
    moments = analyze_laner(timeline, SUPP_ID, OPPONENT_SUPP_ID, "UTILITY")
    ward_kills = [m for m in moments if m.moment_type == "ward_kill"]
    assert len(ward_kills) == 1
    assert "ward" in ward_kills[0].description.lower()


def test_ward_kill_capped_at_3():
    # 5 ward kills — only first 3 should produce moments
    ward_kill_events = [
        {"type": "WARD_KILL", "timestamp": 300_000 + i * 60_000,
         "killerId": SUPP_ID, "wardType": "YELLOW_TRINKET"}
        for i in range(5)
    ]
    timeline = {"info": {"frames": [
        make_frame(300_000 + i * 60_000, [ward_kill_events[i]])
        for i in range(5)
    ]}}
    moments = analyze_laner(timeline, SUPP_ID, OPPONENT_SUPP_ID, "UTILITY")
    ward_kills = [m for m in moments if m.moment_type == "ward_kill"]
    assert len(ward_kills) == 3


def test_roam_assist_support_in_mid_lane():
    # SUPP_ID assists a kill in mid lane during laning phase
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": 3, "victimId": 8,
             "assistingParticipantIds": [SUPP_ID],
             "position": {"x": 7000, "y": 7000}},  # mid lane
        ]),
    ]}}
    moments = analyze_laner(timeline, SUPP_ID, OPPONENT_SUPP_ID, "UTILITY")
    roams = [m for m in moments if m.moment_type == "roam_assist"]
    assert len(roams) == 1
    assert "roam" in roams[0].description.lower()


def test_roam_assist_not_flagged_in_bot_lane():
    # Kill in bot lane — that's the support's own lane, not a roam
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": 4, "victimId": 9,
             "assistingParticipantIds": [SUPP_ID],
             "position": {"x": 10000, "y": 2000}},  # bot lane
        ]),
    ]}}
    moments = analyze_laner(timeline, SUPP_ID, OPPONENT_SUPP_ID, "UTILITY")
    roams = [m for m in moments if m.moment_type == "roam_assist"]
    assert len(roams) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar
pytest tests/test_laner_analyzer.py::test_low_vision_flagged_when_under_4_wards tests/test_laner_analyzer.py::test_ward_kill_flagged tests/test_laner_analyzer.py::test_roam_assist_support_in_mid_lane -v
```

Expected: All FAIL.

- [ ] **Step 3: Implement SUPPORT signal detectors**

Add these functions to `sidecar/laner_analyzer.py` (before `analyze_laner`):

```python
def _detect_ward_kill(
    event: dict,
    participant_id: int,
    ward_kill_count: int,
) -> PivotalMomentData | None:
    if event.get("killerId") != participant_id:
        return None
    if ward_kill_count >= WARD_KILL_CAP:
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="ward_kill",
        description=f"You destroyed an enemy ward at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=0,
    )


def _detect_roam_assist(
    event: dict,
    participant_id: int,
) -> PivotalMomentData | None:
    killer_id = event.get("killerId", 0)
    assisters = event.get("assistingParticipantIds", [])
    if killer_id != participant_id and participant_id not in assisters:
        return None
    victim_id = event.get("victimId", 0)
    if victim_id == participant_id or victim_id == 0:
        return None
    ts = event["timestamp"] // 1000
    if ts >= LANING_PHASE_END_SECS:
        return None
    position = event.get("position", {"x": 0, "y": 0})
    # Support roams to mid or top — NOT their own bot lane
    if not (_in_top_lane(position) or _in_mid_lane(position)):
        return None
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="roam_assist",
        description=f"Your roam contributed to a kill at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _check_low_vision(
    frames: list,
    participant_id: int,
) -> PivotalMomentData | None:
    ward_count = 0
    for frame in frames:
        if frame["timestamp"] > SUPPORT_VISION_WINDOW_MS:
            break
        for event in frame.get("events", []):
            if (event.get("type") == "WARD_PLACED"
                    and event.get("creatorId") == participant_id):
                ward_count += 1
    if ward_count >= SUPPORT_WARD_MINIMUM:
        return None
    return PivotalMomentData(
        timestamp_secs=SUPPORT_VISION_WINDOW_MS // 1000,
        moment_type="low_vision",
        description=f"You placed only {ward_count} wards in the first 20 minutes (minimum: {SUPPORT_WARD_MINIMUM}).",
        counterfactual="",
        gold_impact=0,
    )
```

Now update `analyze_laner` to wire support signals in. Add `ward_kill_count = 0` to the variables before the main loop:

```python
    ward_kill_count = 0
```

Inside the events loop, add a new branch after the TURRET_PLATE branch:

```python
            elif event_type == "WARD_KILL" and role == "UTILITY":
                wk = _detect_ward_kill(event, participant_id, ward_kill_count)
                if wk:
                    ward_kill_count += 1
                    moment = wk
```

And wire roam_assist for UTILITY inside the CHAMPION_KILL block, alongside the other role checks:

```python
                if moment is None and role == "UTILITY":
                    moment = _detect_roam_assist(event, participant_id)
```

After the main loop (alongside the CS/gold differential calls), add the low vision check:

```python
    # Support: low vision check
    if role == "UTILITY":
        vision_moment = _check_low_vision(frames, participant_id)
        if vision_moment:
            moments.append(vision_moment)
```

- [ ] **Step 4: Run all tests**

```
cd sidecar
pytest tests/test_laner_analyzer.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Run full test suite to confirm nothing is broken**

```
cd sidecar
pytest tests/ -v
```

Expected: All tests PASS (including jungle and timeline tests).

- [ ] **Step 6: Commit**

```bash
git add sidecar/laner_analyzer.py sidecar/tests/test_laner_analyzer.py
git commit -m "feat: laner_analyzer SUPPORT signals — ward_kill, low_vision, roam_assist"
```

---

### Task 6: Counterfactual handlers for new moment types

**Files:**
- Modify: `sidecar/counterfactual.py`

- [ ] **Step 1: Write failing tests**

Create `sidecar/tests/test_laner_counterfactuals.py`:

```python
from timeline_analyzer import PivotalMomentData
from counterfactual import enrich_moments


def make_moment(moment_type: str, description: str = "", gold_impact: int = 300) -> PivotalMomentData:
    return PivotalMomentData(
        timestamp_secs=300,
        moment_type=moment_type,
        description=description,
        counterfactual="",
        gold_impact=gold_impact,
    )


def test_lane_death_ganked_counterfactual():
    m = make_moment("lane_death", "You were ganked at 5:00.")
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
    assert "jungler" in enriched.counterfactual.lower() or "ward" in enriched.counterfactual.lower()


def test_lane_death_dove_counterfactual():
    m = make_moment("lane_death", "You were dove at 8:00 (3 enemies collapsed under your tower).")
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
    assert "tower" in enriched.counterfactual.lower() or "dive" in enriched.counterfactual.lower()


def test_lane_death_1v1_counterfactual():
    m = make_moment("lane_death", "You lost a 1v1 trade at 5:00.")
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
    assert "trade" in enriched.counterfactual.lower() or "matchup" in enriched.counterfactual.lower()


def test_cs_differential_counterfactual():
    m = make_moment("cs_differential", "You were 25 CS behind your lane opponent at 14:00.", gold_impact=525)
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
    assert "cs" in enriched.counterfactual.lower() or "farm" in enriched.counterfactual.lower()


def test_gold_differential_counterfactual():
    m = make_moment("gold_differential", "You were 1500g behind your lane opponent at 14:00.", gold_impact=1500)
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
    assert len(enriched.counterfactual) > 20


def test_turret_plates_lost_counterfactual():
    m = make_moment("turret_plates_lost", "Enemy took 3 tower plates in your lane by 8:00 (480g given up).", gold_impact=480)
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
    assert "plate" in enriched.counterfactual.lower() or "wave" in enriched.counterfactual.lower()


def test_split_push_death_counterfactual():
    m = make_moment("split_push_death", "You were collapsed on by 3 enemies while split pushing at 22:00.")
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
    assert "split" in enriched.counterfactual.lower() or "side lane" in enriched.counterfactual.lower()


def test_roam_kill_counterfactual():
    m = make_moment("roam_kill", "Your roam resulted in a kill at 7:00.")
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""


def test_enemy_roam_kill_counterfactual():
    m = make_moment("enemy_roam_kill", "Enemy mid roamed for a kill at 6:00 while you were in lane.")
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
    assert "roam" in enriched.counterfactual.lower()


def test_low_vision_counterfactual():
    m = make_moment("low_vision", "You placed only 2 wards in the first 20 minutes (minimum: 4).")
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
    assert "ward" in enriched.counterfactual.lower()


def test_ward_kill_counterfactual():
    m = make_moment("ward_kill", "You destroyed an enemy ward at 5:00.")
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""


def test_roam_assist_counterfactual():
    m = make_moment("roam_assist", "Your roam contributed to a kill at 7:30.")
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar
pytest tests/test_laner_counterfactuals.py -v
```

Expected: All FAIL — new moment types fall through to the generic gold-impact fallback, which doesn't satisfy the keyword assertions.

- [ ] **Step 3: Add handlers in `sidecar/counterfactual.py`**

In `enrich_moments`, add the new `elif` branches before the final `elif not moment.counterfactual:` fallback:

```python
        elif moment.moment_type == "lane_death":
            desc = moment.description.lower()
            if "ganked" in desc:
                moment.counterfactual = (
                    "The enemy jungler was in your lane. Before extending past the halfway point, "
                    "check that the enemy jungler is visible on the map — if they're not, assume they "
                    "could be nearby. Ward your river and tribush to get earlier warning."
                )
            elif "dove" in desc:
                moment.counterfactual = (
                    "You were dove under your tower. Position away from the tower edge when low so "
                    "enemies can't pin you against it. Having an escape (Flash or dash) ready "
                    "dramatically improves your odds of surviving a dive attempt."
                )
            else:
                moment.counterfactual = (
                    "You lost a 1v1 trade in lane. Check whether your champion wins this matchup at "
                    "your current item level — some matchups are unwinnable pre-spike. If so, play "
                    "for farm over fighting until you hit your power item."
                )

        elif moment.moment_type == "cs_differential":
            moment.counterfactual = (
                "Every 10 CS missed is roughly 200g — falling behind in CS compounds like a death. "
                "Focus on last-hitting under tower, use wave freezes to farm safely when behind, "
                "and prioritize safe CS over risky trades until the gap closes."
            )

        elif moment.moment_type == "gold_differential":
            moment.counterfactual = (
                "Your opponent had a significant gold lead at 14 minutes. Identify the main source: "
                "CS deficit means work on wave management; kill gold means play safer until your "
                "first item spike; plates mean crash your wave before recalling."
            )

        elif moment.moment_type == "turret_plates_lost":
            moment.counterfactual = (
                "Each plate is 160g — losing 3 gave the enemy 480g for free. Crashing your wave "
                "into the tower before recalling denies plates. A full wave crash takes ~10 seconds "
                "and prevents the enemy from freely taking plates while you're gone."
            )

        elif moment.moment_type == "split_push_death":
            moment.counterfactual = (
                "You were collapsed on in a side lane. Before committing deep in a split push, "
                "check that 3+ enemies are accounted for on the minimap. If they're missing, "
                "back off to safety — a teleport escape or recall is worth more than the tower."
            )

        elif moment.moment_type in ("roam_kill", "roam_assist"):
            moment.counterfactual = (
                "Good roam — you created a lead by transferring lane pressure to another part of the "
                "map. Repeat this pattern: shove your wave first so you lose minimal CS, then rotate "
                "before the enemy can respond."
            )

        elif moment.moment_type == "enemy_roam_kill":
            moment.counterfactual = (
                "While you farmed, your opponent created a lead on the map. Match their roam by "
                "following, or shove your wave before they leave so they lose CS in exchange. "
                "Letting them roam for free means they get the kill and keep their CS lead."
            )

        elif moment.moment_type == "low_vision":
            moment.counterfactual = (
                "Low ward count limits your team's ability to react to flanks and objective setups. "
                "As support, aim for a ward every 90 seconds — prioritize river control near Dragon "
                "and Baron timers. A Control Ward in the objective pit before it spawns is the "
                "highest-value placement in the game."
            )

        elif moment.moment_type == "ward_kill":
            moment.counterfactual = (
                "Destroying enemy wards forces them to spend gold and time re-establishing vision. "
                "Keep sweeping high-traffic corridors and the areas around upcoming objective "
                "timers — vision denial before Dragon or Baron is especially impactful."
            )
```

- [ ] **Step 4: Run tests**

```
cd sidecar
pytest tests/test_laner_counterfactuals.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Run full test suite**

```
cd sidecar
pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add sidecar/counterfactual.py sidecar/tests/test_laner_counterfactuals.py
git commit -m "feat: counterfactual handlers for all laner moment types"
```

---

## Self-Review

**Spec coverage:**
- ✅ `cs_differential` (TOP/MID/BOT only) — Task 3
- ✅ `gold_differential` (ALL roles) — Task 3
- ✅ `lane_death` with ganked/dove/1v1 subcategories — Task 2
- ✅ `solo_kill` in-lane on opponent — Task 2
- ✅ Objectives + towers carried — Task 2
- ✅ `turret_plates_lost` TOP/MID/BOT — Task 4
- ✅ `split_push_death` TOP — Task 4
- ✅ `roam_kill` MID — Task 4
- ✅ `enemy_roam_kill` MID — Task 4
- ✅ `low_vision` SUPPORT — Task 5
- ✅ `ward_kill` SUPPORT — Task 5
- ✅ `roam_assist` SUPPORT — Task 5
- ✅ `lane_opponent_id` lookup in main.py — Task 1
- ✅ `analyze_timeline` dispatch — Task 1
- ✅ All counterfactual handlers — Task 6
- ✅ CS exemption for SUPPORT confirmed by test — Task 3

**Placeholder scan:** No TBDs. All code blocks are complete and runnable.

**Type consistency:** `analyze_laner(timeline, participant_id, lane_opponent_id, role, enemy_jungler_id=None)` is consistent across Task 1 stub, Task 2 implementation, and all test call sites. `PivotalMomentData` fields (`timestamp_secs`, `moment_type`, `description`, `counterfactual`, `gold_impact`) are used consistently throughout.
