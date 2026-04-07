# Phase 2: Role-Aware Analysis + AI Coaching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add jungle-specific moment detection (8 new types), replace static counterfactual strings with a single Gemini-powered coaching call per game, and degrade gracefully for non-jungle roles.

**Architecture:** `jungle_analyzer.py` handles all jungle detection using position-based logic. `timeline_analyzer.py` routes to it when role=JUNGLE. `claude_client.py` gains a `generate_coaching_notes()` method that builds a context window per moment and calls Gemini once per game. `main.py` passes role/champion through the pipeline and calls the AI coach instead of static `enrich_moments`.

**Tech Stack:** Python 3.11, pytest, google-genai SDK, FastAPI, React 18 + TypeScript

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `sidecar/jungle_analyzer.py` | **CREATE** | All 8 jungle-specific moment detections |
| `sidecar/tests/test_jungle_analyzer.py` | **CREATE** | Tests for all 8 detections |
| `sidecar/tests/test_timeline_analyzer.py` | **MODIFY** | Remove stale cap test, fix sort test |
| `sidecar/timeline_analyzer.py` | **MODIFY** | Add role/champion params + jungle routing |
| `sidecar/claude_client.py` | **MODIFY** | Add `generate_coaching_notes()` method |
| `sidecar/main.py` | **MODIFY** | Pass role/champion, use AI coach |
| `sidecar/trigger_analysis.py` | **MODIFY** | Same as main.py |
| `src/popup/MomentCard.tsx` | **MODIFY** | Add new positive types to POSITIVE_TYPES set |

---

## Task 1: Fix Two Stale Tests in `test_timeline_analyzer.py`

**Files:**
- Modify: `sidecar/tests/test_timeline_analyzer.py`

The cap was removed from `analyze_timeline` (now returns all moments sorted chronologically). Two existing tests will fail because they were written for the old behavior.

- [ ] **Step 1: Run the full test suite to confirm which tests fail**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/test_timeline_analyzer.py -v
```

Expected failures:
- `test_returns_top_5_max` — cap is gone, more than 5 moments can now be returned
- `test_sorted_by_gold_impact_descending` — sort is now chronological, not by gold

- [ ] **Step 2: Remove `test_returns_top_5_max` and update `test_sorted_by_gold_impact_descending`**

In `sidecar/tests/test_timeline_analyzer.py`, delete the entire `test_returns_top_5_max` function (the cap is intentionally gone — the user wants to see all moments).

Then replace `test_sorted_by_gold_impact_descending` with a chronological sort test:

```python
def test_sorted_chronologically():
    # Baron at 905000ms, death at 502000ms — death should come first
    timeline = {"info": {"frames": [
        make_frame(900000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 905000,
             "killerId": 6, "monsterType": "BARON_NASHOR",
             "position": {"x": 5007, "y": 10471}}
        ]),
        make_frame(500000, [
            {"type": "CHAMPION_KILL", "timestamp": 502000,
             "killerId": 3, "victimId": PARTICIPANT_ID,
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    if len(moments) >= 2:
        assert moments[0].timestamp_secs <= moments[1].timestamp_secs
```

- [ ] **Step 3: Run tests to confirm all pass**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/test_timeline_analyzer.py -v
```

Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add sidecar/tests/test_timeline_analyzer.py
git commit -m "test: remove stale cap test, update sort assertion to chronological"
```

---

## Task 2: Create `jungle_analyzer.py` with Position Helpers

**Files:**
- Create: `sidecar/jungle_analyzer.py`

This file has one responsibility: detect jungle-specific pivotal moments. All position logic lives here.

- [ ] **Step 1: Create `sidecar/jungle_analyzer.py` with constants and helpers**

```python
import math
from timeline_analyzer import PivotalMomentData, TEAM_100_IDS, TEAM_200_IDS, GOLD_VALUES

# --- Map position constants ---

# Enemy jungle quadrant boundaries
BLUE_JUNGLE_X_MAX = 7000   # blue side jungle (top-left): x < 7000
BLUE_JUNGLE_Y_MIN = 7500   # blue side jungle (top-left): y > 7500

RED_JUNGLE_X_MIN = 8000    # red side jungle (bottom-right): x > 8000
RED_JUNGLE_Y_MAX = 7500    # red side jungle (bottom-right): y < 7500

# Lane position boundaries (approximate)
TOP_LANE_X_MAX = 4000      # top lane hugs left edge of map
BOT_LANE_Y_MAX = 4000      # bot lane hugs bottom edge of map

# Timing
ALIVE_WINDOW_SECS = 30     # jungler must not have died within 30s to be "alive"
VOID_GRUBS_TOTAL = 3       # Season 2025: 3 total void grubs per game


def _is_blue_side(participant_id: int) -> bool:
    return participant_id in TEAM_100_IDS


def _in_enemy_jungle(position: dict, participant_id: int) -> bool:
    """True if position is inside the enemy team's jungle quadrant."""
    px, py = position.get("x", 0), position.get("y", 0)
    if _is_blue_side(participant_id):
        # Enemy = red side = bottom-right quadrant
        return px >= RED_JUNGLE_X_MIN and py <= RED_JUNGLE_Y_MAX
    else:
        # Enemy = blue side = top-left quadrant
        return px <= BLUE_JUNGLE_X_MAX and py >= BLUE_JUNGLE_Y_MIN


def _in_ally_lane(position: dict, participant_id: int) -> bool:
    """True if position is in a lane (not jungle interior)."""
    px, py = position.get("x", 0), position.get("y", 0)
    return (
        px < TOP_LANE_X_MAX          # near top lane (left edge)
        or py < BOT_LANE_Y_MAX       # near bot lane (bottom edge)
        or abs(px - py) < 3000       # near mid lane diagonal
    )


def _jungler_position_at(frames: list, timestamp_ms: int, participant_id: int) -> dict | None:
    """Get jungler's position from the most recent frame at or before timestamp_ms."""
    best_frame = None
    for frame in frames:
        if frame["timestamp"] <= timestamp_ms:
            best_frame = frame
        else:
            break
    if best_frame is None:
        return None
    pf = best_frame.get("participantFrames", {})
    return pf.get(str(participant_id), {}).get("position")


def analyze_jungle(
    timeline: dict,
    participant_id: int,
    enemy_jungler_id: int | None = None,
) -> list[PivotalMomentData]:
    """Main entry point — detect all jungle-specific moments from a timeline."""
    moments: list[PivotalMomentData] = []
    frames = timeline.get("info", {}).get("frames", [])
    enemy_team = TEAM_200_IDS if participant_id in TEAM_100_IDS else TEAM_100_IDS
    enemy_void_grub_count = 0
    last_death_ts: int | None = None

    for frame in frames:
        for event in frame.get("events", []):
            event_type = event.get("type")
            moment = None

            if event_type == "CHAMPION_KILL":
                if event.get("victimId") == participant_id:
                    last_death_ts = event["timestamp"] // 1000
                # Detection order: invade > counter-gank > gank assist
                moment = (
                    _detect_invade_death(event, participant_id)
                    or _detect_counter_ganked(event, participant_id, enemy_jungler_id)
                    or _detect_gank_assist(event, participant_id)
                )

            elif event_type == "ELITE_MONSTER_KILL":
                killer_id = event.get("killerId", 0)
                monster = event.get("monsterType", "")

                if monster == "HORDE" and killer_id in enemy_team:
                    enemy_void_grub_count += 1
                    if enemy_void_grub_count == VOID_GRUBS_TOTAL:
                        moment = _detect_void_grubs_missed(event)
                elif monster != "HORDE":
                    moment = (
                        _detect_dragon_missed(event, frames, participant_id, last_death_ts)
                        or _detect_baron_missed(event, frames, participant_id, last_death_ts)
                        or _detect_dragon_stack(event, participant_id)
                        or _detect_baron_secured(event, participant_id)
                    )

            if moment:
                moments.append(moment)

    moments.sort(key=lambda m: m.timestamp_secs)
    return moments


def _detect_invade_death(event: dict, participant_id: int) -> PivotalMomentData | None:
    pass  # implemented in Task 3


def _detect_counter_ganked(event: dict, participant_id: int, enemy_jungler_id: int | None) -> PivotalMomentData | None:
    pass  # implemented in Task 3


def _detect_gank_assist(event: dict, participant_id: int) -> PivotalMomentData | None:
    pass  # implemented in Task 4


def _detect_dragon_missed(event: dict, frames: list, participant_id: int, last_death_ts: int | None) -> PivotalMomentData | None:
    pass  # implemented in Task 5


def _detect_baron_missed(event: dict, frames: list, participant_id: int, last_death_ts: int | None) -> PivotalMomentData | None:
    pass  # implemented in Task 5


def _detect_void_grubs_missed(event: dict) -> PivotalMomentData | None:
    pass  # implemented in Task 5


def _detect_dragon_stack(event: dict, participant_id: int) -> PivotalMomentData | None:
    pass  # implemented in Task 4


def _detect_baron_secured(event: dict, participant_id: int) -> PivotalMomentData | None:
    pass  # implemented in Task 4
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
cd sidecar && venv/Scripts/python -c "from jungle_analyzer import analyze_jungle; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add sidecar/jungle_analyzer.py
git commit -m "feat: jungle_analyzer skeleton with position helpers and analyze_jungle"
```

---

## Task 3: TDD — Death Detections (`invade_death`, `counter_ganked`)

**Files:**
- Create: `sidecar/tests/test_jungle_analyzer.py`
- Modify: `sidecar/jungle_analyzer.py`

- [ ] **Step 1: Create `sidecar/tests/test_jungle_analyzer.py` with helpers and death detection tests**

```python
from jungle_analyzer import analyze_jungle

JUNGLE_ID = 1   # blue side jungler (participant 1, team 100)

def make_frame(timestamp_ms: int, events: list, positions: dict | None = None) -> dict:
    """
    positions: {participant_id: (x, y)} — optional per-participant positions.
    Defaults to (5000, 5000) for all participants if not provided.
    """
    participant_frames = {}
    for pid in range(1, 11):
        pos = (positions or {}).get(pid, (5000, 5000))
        participant_frames[str(pid)] = {
            "totalGold": 5000,
            "currentGold": 1000,
            "position": {"x": pos[0], "y": pos[1]},
        }
    return {"timestamp": timestamp_ms, "participantFrames": participant_frames, "events": events}


def test_invade_death_in_enemy_jungle():
    # Blue side jungler dies at (12000, 4000) — inside red side jungle
    timeline = {"info": {"frames": [
        make_frame(300000, [
            {"type": "CHAMPION_KILL", "timestamp": 300000,
             "killerId": 6, "victimId": JUNGLE_ID,
             "assistingParticipantIds": [],
             "position": {"x": 12000, "y": 4000}}
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    invades = [m for m in moments if m.moment_type == "invade_death"]
    assert len(invades) == 1
    assert "enemy jungle" in invades[0].description.lower()


def test_invade_death_not_triggered_in_own_jungle():
    # Blue side jungler dies at (2000, 10000) — inside blue side jungle (own jungle)
    timeline = {"info": {"frames": [
        make_frame(300000, [
            {"type": "CHAMPION_KILL", "timestamp": 300000,
             "killerId": 6, "victimId": JUNGLE_ID,
             "assistingParticipantIds": [],
             "position": {"x": 2000, "y": 10000}}
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    invades = [m for m in moments if m.moment_type == "invade_death"]
    assert len(invades) == 0


def test_counter_ganked_in_ally_lane():
    # Jungler ganking bot lane (y=2000), killed by enemy laner + enemy jungler
    timeline = {"info": {"frames": [
        make_frame(480000, [
            {"type": "CHAMPION_KILL", "timestamp": 480000,
             "killerId": 6, "victimId": JUNGLE_ID,
             "assistingParticipantIds": [7],  # enemy jungler assists
             "position": {"x": 8000, "y": 2000}}  # bot lane position
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID, enemy_jungler_id=7)
    counter_ganks = [m for m in moments if m.moment_type == "counter_ganked"]
    assert len(counter_ganks) == 1
    assert "counter-ganked" in counter_ganks[0].description.lower()


def test_counter_ganked_requires_enemy_jungler():
    # Same event but no enemy_jungler_id provided — should NOT flag as counter-gank
    timeline = {"info": {"frames": [
        make_frame(480000, [
            {"type": "CHAMPION_KILL", "timestamp": 480000,
             "killerId": 6, "victimId": JUNGLE_ID,
             "assistingParticipantIds": [7],
             "position": {"x": 8000, "y": 2000}}
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID, enemy_jungler_id=None)
    counter_ganks = [m for m in moments if m.moment_type == "counter_ganked"]
    assert len(counter_ganks) == 0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/test_jungle_analyzer.py::test_invade_death_in_enemy_jungle tests/test_jungle_analyzer.py::test_invade_death_not_triggered_in_own_jungle tests/test_jungle_analyzer.py::test_counter_ganked_in_ally_lane tests/test_jungle_analyzer.py::test_counter_ganked_requires_enemy_jungler -v
```

Expected: all 4 FAIL (functions return None)

- [ ] **Step 3: Implement `_detect_invade_death` and `_detect_counter_ganked` in `jungle_analyzer.py`**

Replace the `pass` stubs with:

```python
def _detect_invade_death(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("victimId") != participant_id:
        return None
    position = event.get("position", {"x": 0, "y": 0})
    if not _in_enemy_jungle(position, participant_id):
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="invade_death",
        description=f"You were caught in the enemy jungle at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _detect_counter_ganked(
    event: dict,
    participant_id: int,
    enemy_jungler_id: int | None,
) -> PivotalMomentData | None:
    if event.get("victimId") != participant_id:
        return None
    if enemy_jungler_id is None:
        return None
    killer_id = event.get("killerId", 0)
    assisters = event.get("assistingParticipantIds", [])
    if killer_id != enemy_jungler_id and enemy_jungler_id not in assisters:
        return None
    position = event.get("position", {"x": 0, "y": 0})
    if not _in_ally_lane(position, participant_id):
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="counter_ganked",
        description=f"You were counter-ganked at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )
```

- [ ] **Step 4: Run the 4 tests to confirm they pass**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/test_jungle_analyzer.py::test_invade_death_in_enemy_jungle tests/test_jungle_analyzer.py::test_invade_death_not_triggered_in_own_jungle tests/test_jungle_analyzer.py::test_counter_ganked_in_ally_lane tests/test_jungle_analyzer.py::test_counter_ganked_requires_enemy_jungler -v
```

Expected: all 4 PASS

- [ ] **Step 5: Commit**

```bash
git add sidecar/jungle_analyzer.py sidecar/tests/test_jungle_analyzer.py
git commit -m "feat: jungle death detections — invade_death, counter_ganked"
```

---

## Task 4: TDD — Positive Detections (`gank_assist`, `dragon_stack`, `baron_secured`)

**Files:**
- Modify: `sidecar/tests/test_jungle_analyzer.py`
- Modify: `sidecar/jungle_analyzer.py`

- [ ] **Step 1: Add 4 positive detection tests to `test_jungle_analyzer.py`**

Append to the existing test file:

```python
def test_gank_assist_in_lane():
    # Jungler assists a kill in bot lane (y=2000)
    timeline = {"info": {"frames": [
        make_frame(480000, [
            {"type": "CHAMPION_KILL", "timestamp": 480000,
             "killerId": 2, "victimId": 7,  # teammate kills enemy
             "assistingParticipantIds": [JUNGLE_ID],  # jungler assisted
             "position": {"x": 8000, "y": 2000}}  # bot lane
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    ganks = [m for m in moments if m.moment_type == "gank_assist"]
    assert len(ganks) == 1
    assert "ganked" in ganks[0].description.lower() or "kill" in ganks[0].description.lower()


def test_gank_assist_not_in_jungle():
    # Jungler kills enemy but in jungle (not a lane gank)
    timeline = {"info": {"frames": [
        make_frame(480000, [
            {"type": "CHAMPION_KILL", "timestamp": 480000,
             "killerId": JUNGLE_ID, "victimId": 7,
             "assistingParticipantIds": [],
             "position": {"x": 5000, "y": 5000}}  # mid-map, not in a lane
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    ganks = [m for m in moments if m.moment_type == "gank_assist"]
    assert len(ganks) == 0


def test_dragon_stack_secured():
    # Player's team (team 100) secures Dragon
    timeline = {"info": {"frames": [
        make_frame(325000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 323000,
             "killerId": 3,  # teammate on team 100
             "monsterType": "DRAGON",
             "position": {"x": 9866, "y": 4414}}
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    stacks = [m for m in moments if m.moment_type == "dragon_stack"]
    assert len(stacks) == 1
    assert "Dragon" in stacks[0].description
    assert stacks[0].gold_impact == 350


def test_baron_secured():
    # Player's team (team 100) secures Baron
    timeline = {"info": {"frames": [
        make_frame(1205000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 1203000,
             "killerId": 1,  # jungler themselves smites Baron
             "monsterType": "BARON_NASHOR",
             "position": {"x": 5007, "y": 10471}}
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    secured = [m for m in moments if m.moment_type == "baron_secured"]
    assert len(secured) == 1
    assert "Baron" in secured[0].description
    assert secured[0].gold_impact == 900
```

- [ ] **Step 2: Run 4 new tests to confirm they fail**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/test_jungle_analyzer.py::test_gank_assist_in_lane tests/test_jungle_analyzer.py::test_gank_assist_not_in_jungle tests/test_jungle_analyzer.py::test_dragon_stack_secured tests/test_jungle_analyzer.py::test_baron_secured -v
```

Expected: all 4 FAIL

- [ ] **Step 3: Implement `_detect_gank_assist`, `_detect_dragon_stack`, `_detect_baron_secured`**

Replace the stubs in `jungle_analyzer.py`:

```python
def _detect_gank_assist(event: dict, participant_id: int) -> PivotalMomentData | None:
    killer_id = event.get("killerId", 0)
    assisters = event.get("assistingParticipantIds", [])
    if killer_id != participant_id and participant_id not in assisters:
        return None
    victim_id = event.get("victimId", 0)
    if victim_id == participant_id or victim_id == 0:
        return None
    position = event.get("position", {"x": 0, "y": 0})
    if not _in_ally_lane(position, participant_id):
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="gank_assist",
        description=f"You ganked and got a kill at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _detect_dragon_stack(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("monsterType") != "DRAGON":
        return None
    player_team = TEAM_100_IDS if participant_id in TEAM_100_IDS else TEAM_200_IDS
    if event.get("killerId", 0) not in player_team:
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="dragon_stack",
        description=f"Your team secured Dragon at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DRAGON"],
    )


def _detect_baron_secured(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("monsterType") != "BARON_NASHOR":
        return None
    player_team = TEAM_100_IDS if participant_id in TEAM_100_IDS else TEAM_200_IDS
    if event.get("killerId", 0) not in player_team:
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="baron_secured",
        description=f"Your team secured Baron Nashor at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["BARON_NASHOR"],
    )
```

- [ ] **Step 4: Run the 4 tests to confirm they pass**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/test_jungle_analyzer.py::test_gank_assist_in_lane tests/test_jungle_analyzer.py::test_gank_assist_not_in_jungle tests/test_jungle_analyzer.py::test_dragon_stack_secured tests/test_jungle_analyzer.py::test_baron_secured -v
```

Expected: all 4 PASS

- [ ] **Step 5: Commit**

```bash
git add sidecar/jungle_analyzer.py sidecar/tests/test_jungle_analyzer.py
git commit -m "feat: jungle positive detections — gank_assist, dragon_stack, baron_secured"
```

---

## Task 5: TDD — Objective Miss Detections (`dragon_missed`, `baron_missed`, `void_grubs_missed`)

**Files:**
- Modify: `sidecar/tests/test_jungle_analyzer.py`
- Modify: `sidecar/jungle_analyzer.py`

These detections require frame position data (jungler location at objective time) and alive tracking.

- [ ] **Step 1: Add 5 objective miss tests to `test_jungle_analyzer.py`**

Append to the existing test file:

```python
def test_dragon_missed_wrong_side():
    # Jungler is top-side (y=10000) when enemy takes Dragon at 5:23
    timeline = {"info": {"frames": [
        make_frame(280000, [], positions={JUNGLE_ID: (2000, 10000)}),  # jungler top-side
        make_frame(325000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 323000,
             "killerId": 6, "monsterType": "DRAGON",
             "position": {"x": 9866, "y": 4414}}
        ], positions={JUNGLE_ID: (2000, 10000)}),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    misses = [m for m in moments if m.moment_type == "dragon_missed"]
    assert len(misses) == 1
    assert "Dragon" in misses[0].description


def test_dragon_not_missed_if_jungler_recently_dead():
    # Jungler died 23s before Dragon — correct concede, should NOT flag
    timeline = {"info": {"frames": [
        make_frame(300000, [
            {"type": "CHAMPION_KILL", "timestamp": 300000,
             "killerId": 6, "victimId": JUNGLE_ID,
             "assistingParticipantIds": [],
             "position": {"x": 2000, "y": 10000}}
        ], positions={JUNGLE_ID: (2000, 10000)}),
        make_frame(325000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 323000,
             "killerId": 6, "monsterType": "DRAGON",
             "position": {"x": 9866, "y": 4414}}
        ], positions={JUNGLE_ID: (2000, 10000)}),
    ]}}
    # Jungler died at 300s, Dragon at 323s — 23s gap (within ALIVE_WINDOW_SECS=30)
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    misses = [m for m in moments if m.moment_type == "dragon_missed"]
    assert len(misses) == 0


def test_baron_missed_wrong_side():
    # Jungler is bot-side (y=2000) when enemy takes Baron at 20:00
    timeline = {"info": {"frames": [
        make_frame(1195000, [], positions={JUNGLE_ID: (8000, 2000)}),  # jungler bot-side
        make_frame(1205000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 1203000,
             "killerId": 6, "monsterType": "BARON_NASHOR",
             "position": {"x": 5007, "y": 10471}}
        ], positions={JUNGLE_ID: (8000, 2000)}),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    misses = [m for m in moments if m.moment_type == "baron_missed"]
    assert len(misses) == 1
    assert "Baron" in misses[0].description


def test_void_grubs_missed_all_three():
    # Enemy takes all 3 void grubs
    grub_events = [
        {"type": "ELITE_MONSTER_KILL", "timestamp": 305000 + i * 60000,
         "killerId": 6, "monsterType": "HORDE"}
        for i in range(3)
    ]
    timeline = {"info": {"frames": [
        make_frame(300000 + i * 60000, [grub_events[i]])
        for i in range(3)
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    grub_misses = [m for m in moments if m.moment_type == "void_grubs_missed"]
    assert len(grub_misses) == 1
    assert "Void Grub" in grub_misses[0].description


def test_void_grubs_not_flagged_if_player_team_gets_them():
    # Player's team takes all 3 void grubs — should NOT flag
    grub_events = [
        {"type": "ELITE_MONSTER_KILL", "timestamp": 305000 + i * 60000,
         "killerId": 1, "monsterType": "HORDE"}  # team 100 jungler
        for i in range(3)
    ]
    timeline = {"info": {"frames": [
        make_frame(300000 + i * 60000, [grub_events[i]])
        for i in range(3)
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    grub_misses = [m for m in moments if m.moment_type == "void_grubs_missed"]
    assert len(grub_misses) == 0
```

- [ ] **Step 2: Run the 5 new tests to confirm they fail**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/test_jungle_analyzer.py::test_dragon_missed_wrong_side tests/test_jungle_analyzer.py::test_dragon_not_missed_if_jungler_recently_dead tests/test_jungle_analyzer.py::test_baron_missed_wrong_side tests/test_jungle_analyzer.py::test_void_grubs_missed_all_three tests/test_jungle_analyzer.py::test_void_grubs_not_flagged_if_player_team_gets_them -v
```

Expected: all 5 FAIL

- [ ] **Step 3: Implement `_detect_dragon_missed`, `_detect_baron_missed`, `_detect_void_grubs_missed`**

Replace the stubs in `jungle_analyzer.py`:

```python
def _detect_dragon_missed(
    event: dict,
    frames: list,
    participant_id: int,
    last_death_ts: int | None,
) -> PivotalMomentData | None:
    if event.get("monsterType") != "DRAGON":
        return None
    enemy_team = TEAM_200_IDS if participant_id in TEAM_100_IDS else TEAM_100_IDS
    if event.get("killerId", 0) not in enemy_team:
        return None
    ts = event["timestamp"] // 1000
    # Alive check: jungler must not have died within ALIVE_WINDOW_SECS
    if last_death_ts is not None and ts - last_death_ts <= ALIVE_WINDOW_SECS:
        return None
    # Position check: jungler must have been on the wrong side (away from Dragon)
    jungler_pos = _jungler_position_at(frames, event["timestamp"], participant_id)
    if jungler_pos is None:
        return None
    py = jungler_pos.get("y", 0)
    # Dragon is in bot river (low y). Wrong side = top-heavy position (high y).
    # Blue side: wrong side = y > 7000. Red side: wrong side = y > 7000 (also top-heavy for red).
    on_wrong_side = py > 7000
    if not on_wrong_side:
        return None
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="dragon_missed",
        description=f"Enemy secured Dragon at {mins}:{secs:02d} while you were on the wrong side of the map.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DRAGON"],
    )


def _detect_baron_missed(
    event: dict,
    frames: list,
    participant_id: int,
    last_death_ts: int | None,
) -> PivotalMomentData | None:
    if event.get("monsterType") != "BARON_NASHOR":
        return None
    enemy_team = TEAM_200_IDS if participant_id in TEAM_100_IDS else TEAM_100_IDS
    if event.get("killerId", 0) not in enemy_team:
        return None
    ts = event["timestamp"] // 1000
    if last_death_ts is not None and ts - last_death_ts <= ALIVE_WINDOW_SECS:
        return None
    jungler_pos = _jungler_position_at(frames, event["timestamp"], participant_id)
    if jungler_pos is None:
        return None
    py = jungler_pos.get("y", 0)
    # Baron is in top river (high y). Wrong side = bot-heavy position (low y).
    on_wrong_side = py < 7500
    if not on_wrong_side:
        return None
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="baron_missed",
        description=f"Enemy secured Baron Nashor at {mins}:{secs:02d} while you were on the wrong side of the map.",
        counterfactual="",
        gold_impact=GOLD_VALUES["BARON_NASHOR"],
    )


def _detect_void_grubs_missed(event: dict) -> PivotalMomentData | None:
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="void_grubs_missed",
        description=f"Enemy secured all {VOID_GRUBS_TOTAL} Void Grubs at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=300,
    )
```

- [ ] **Step 4: Run all 5 tests to confirm they pass**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/test_jungle_analyzer.py::test_dragon_missed_wrong_side tests/test_jungle_analyzer.py::test_dragon_not_missed_if_jungler_recently_dead tests/test_jungle_analyzer.py::test_baron_missed_wrong_side tests/test_jungle_analyzer.py::test_void_grubs_missed_all_three tests/test_jungle_analyzer.py::test_void_grubs_not_flagged_if_player_team_gets_them -v
```

Expected: all 5 PASS

- [ ] **Step 5: Run full jungle test suite**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/test_jungle_analyzer.py -v
```

Expected: all 13 tests PASS

- [ ] **Step 6: Commit**

```bash
git add sidecar/jungle_analyzer.py sidecar/tests/test_jungle_analyzer.py
git commit -m "feat: jungle objective miss detections — dragon_missed, baron_missed, void_grubs_missed"
```

---

## Task 6: Wire Jungle Routing into `timeline_analyzer.py`

**Files:**
- Modify: `sidecar/timeline_analyzer.py`

Add `role` and `champion` parameters to `analyze_timeline`. When role is JUNGLE, delegate to `jungle_analyzer.analyze_jungle`.

- [ ] **Step 1: Update `analyze_timeline` signature and add routing**

In `sidecar/timeline_analyzer.py`, replace the `analyze_timeline` function signature and first few lines:

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

    moments: list[PivotalMomentData] = []
    frames = timeline.get("info", {}).get("frames", [])
    # ... rest of existing function unchanged
```

The rest of the existing `analyze_timeline` body (the loop over frames) stays exactly as-is. Only the signature and the two routing lines at the top are new.

- [ ] **Step 2: Run full test suite to confirm nothing broke**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/ -v
```

Expected: all tests PASS (existing timeline tests use default role="UNKNOWN" so they take the non-jungle path)

- [ ] **Step 3: Commit**

```bash
git add sidecar/timeline_analyzer.py
git commit -m "feat: role routing in analyze_timeline — JUNGLE delegates to jungle_analyzer"
```

---

## Task 7: Add `generate_coaching_notes` to `claude_client.py`

**Files:**
- Modify: `sidecar/claude_client.py`

Add two module-level helpers and a new method on `ClaudeClient`. This replaces `counterfactual.enrich_moments` in the main pipeline.

- [ ] **Step 1: Add `import json` and two helper functions at the top of `claude_client.py`**

Add `import json` to the imports at the top of the file (after existing imports).

Then add these two functions before the `ClaudeClient` class definition:

```python
def _summarize_event(event: dict, participant_id: int) -> str | None:
    """Convert a raw timeline event to a one-line readable summary."""
    ts = event.get("timestamp", 0) // 1000
    mins, secs = divmod(ts, 60)
    t = f"{mins}:{secs:02d}"
    event_type = event.get("type", "")
    player_team = TEAM_100_IDS if participant_id in TEAM_100_IDS else TEAM_200_IDS

    if event_type == "CHAMPION_KILL":
        killer = event.get("killerId", 0)
        victim = event.get("victimId", 0)
        assisters = event.get("assistingParticipantIds", [])
        if victim == participant_id:
            assist_str = f" (assists: {assisters})" if assisters else ""
            return f"{t} — You were killed by participant {killer}{assist_str}"
        elif killer == participant_id:
            return f"{t} — You killed participant {victim}"
        elif participant_id in assisters:
            return f"{t} — You assisted killing participant {victim}"
        else:
            return f"{t} — Fight: participant {killer} killed participant {victim}"

    elif event_type == "ELITE_MONSTER_KILL":
        monster = event.get("monsterType", "UNKNOWN")
        killer = event.get("killerId", 0)
        team = "your team" if killer in player_team else "enemy team"
        return f"{t} — {team} secured {monster}"

    elif event_type == "BUILDING_KILL":
        lane = event.get("laneType", "UNKNOWN").replace("_LANE", "")
        tower = event.get("towerType", "TURRET").replace("_TURRET", "").lower()
        team_id = event.get("teamId", 0)
        player_team_id = 100 if participant_id in TEAM_100_IDS else 200
        loser = "your team" if team_id == player_team_id else "enemy team"
        return f"{t} — {lane} {tower} tower lost by {loser}"

    return None


def _build_context_window(
    all_events: list[dict],
    moment_ts_secs: int,
    participant_id: int,
    window_secs: int = 90,
) -> str:
    """Return readable summary of all events within window_secs of moment_ts_secs."""
    lines = []
    for event in all_events:
        ts = event.get("timestamp", 0) // 1000
        if abs(ts - moment_ts_secs) <= window_secs:
            summary = _summarize_event(event, participant_id)
            if summary:
                lines.append(summary)
    return "\n".join(lines) if lines else "No notable events in this window."
```

Also add this import at the top of `claude_client.py` alongside the existing imports:
```python
from timeline_analyzer import TEAM_100_IDS, TEAM_200_IDS
```

- [ ] **Step 2: Add `generate_coaching_notes` method to `ClaudeClient`**

Add this method inside the `ClaudeClient` class, after the existing `chat` method:

```python
def generate_coaching_notes(
    self,
    moments: list,
    game_context: dict,
    timeline: dict,
) -> list:
    """
    Generate AI coaching notes for all moments in a single Gemini call.
    Falls back to counterfactual.enrich_moments on failure.
    Mutates and returns the moments list with counterfactual filled in.
    """
    from counterfactual import enrich_moments as fallback_enrich

    if not moments:
        return moments

    participant_id = game_context.get("participant_id", 1)

    # Collect all events from timeline for context window lookups
    all_events: list[dict] = []
    for frame in timeline.get("info", {}).get("frames", []):
        all_events.extend(frame.get("events", []))

    # Build game context header
    champion = game_context.get("champion", "Unknown")
    role = game_context.get("role", "JUNGLE")
    side = game_context.get("side", "blue")
    result = game_context.get("result", "unknown")
    kda = game_context.get("kda", "0/0/0")
    duration_secs = game_context.get("duration_secs", 0)
    dur_mins, dur_secs_r = divmod(duration_secs, 60)
    header = (
        f"Champion: {champion} | Role: {role} | Side: {side} side\n"
        f"Result: {result.upper()} | KDA: {kda} | Duration: {dur_mins}:{dur_secs_r:02d}"
    )

    # Build one block per moment
    moment_blocks = []
    for i, m in enumerate(moments):
        ctx = _build_context_window(all_events, m.timestamp_secs, participant_id)
        moment_blocks.append(
            f"[{i}] {m.moment_type} — {m.description}\n"
            f"Context (±90s):\n{ctx}"
        )

    moments_text = "\n---\n".join(moment_blocks)

    prompt = (
        f"You are coaching a {champion} {role.lower()}. {header}\n\n"
        f"For each moment below, write a 3-4 sentence coaching note. Rules:\n"
        f"- Be specific to the {role.lower()} role\n"
        f"- Reference what was happening in the surrounding context\n"
        f"- Give one concrete, achievable alternative action\n"
        f"- Use encouraging language for positive moments "
        f"(gank_assist, baron_secured, dragon_stack, solo_kill, objective_secured)\n"
        f"- Describe game state for mistakes — don't moralize\n"
        f"- Keep each note to 3-4 sentences maximum\n\n"
        f"{moments_text}\n\n"
        f"Return ONLY valid JSON, no other text: "
        f'[{{"id": 0, "coaching": "..."}}, ...]'
    )

    try:
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
        )
        raw = response.text.strip()
        # Strip markdown code fences if Gemini wraps with ```json ... ```
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1]
            if raw.startswith("json"):
                raw = raw[4:]
        coaching_list = json.loads(raw)
        coaching_map = {item["id"]: item["coaching"] for item in coaching_list}
        for i, m in enumerate(moments):
            if i in coaching_map:
                m.counterfactual = coaching_map[i]
    except Exception as e:
        print(f"[coaching] Gemini call failed ({e}). Using static fallback.")
        fallback_enrich(moments)

    return moments
```

- [ ] **Step 3: Verify the module imports cleanly**

```bash
cd sidecar && venv/Scripts/python -c "from claude_client import ClaudeClient; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Run full test suite to confirm nothing broke**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add sidecar/claude_client.py
git commit -m "feat: AI coaching notes — generate_coaching_notes in ClaudeClient"
```

---

## Task 8: Wire Everything Together in `main.py` and `trigger_analysis.py`

**Files:**
- Modify: `sidecar/main.py`
- Modify: `sidecar/trigger_analysis.py`

Pass `role` and `champion` through to `analyze_timeline`. Replace `enrich_moments` with `claude.generate_coaching_notes`.

- [ ] **Step 1: Update `main.py`**

In `sidecar/main.py`:

1. Remove this import line:
```python
from counterfactual import enrich_moments
```

2. In `run_post_game_analysis`, after `participant_index` is computed, add two new lines:
```python
role = participant.get("teamPosition", "UNKNOWN")
champion = participant["championName"]
```

3. Replace the `analyze_timeline` call:
```python
moments = analyze_timeline(
    timeline_data,
    participant_id=participant_index,
    enemy_jungler_id=enemy_jungler_id,
    role=role,
    champion=champion,
)
```

4. Replace `enriched = enrich_moments(moments)` with:
```python
side = "blue" if participant_index in TEAM_100_IDS else "red"
game_context = {
    "participant_id": participant_index,
    "champion": champion,
    "role": role,
    "side": side,
    "result": "win" if participant["win"] else "loss",
    "kda": f"{participant['kills']}/{participant['deaths']}/{participant['assists']}",
    "duration_secs": info["gameDuration"],
}
enriched = claude.generate_coaching_notes(moments, game_context, timeline_data)
```

5. The `save_pivotal_moments` call and everything after remain unchanged.

- [ ] **Step 2: Update `trigger_analysis.py`**

Apply the same changes to `sidecar/trigger_analysis.py`:

1. Remove `from counterfactual import enrich_moments`

2. After `participant_index = participants.index(participant) + 1`, add:
```python
role = participant.get('teamPosition', 'UNKNOWN')
champion = participant['championName']
```

3. Update `analyze_timeline` call:
```python
moments = analyze_timeline(timeline_data, participant_id=participant_index, enemy_jungler_id=enemy_jungler_id, role=role, champion=champion)
```

4. Replace `enriched = enrich_moments(moments)` with:
```python
side = 'blue' if participant_index in TEAM_100_IDS else 'red'
game_context = {
    'participant_id': participant_index,
    'champion': champion,
    'role': role,
    'side': side,
    'result': 'win' if participant['win'] else 'loss',
    'kda': f"{participant['kills']}/{participant['deaths']}/{participant['assists']}",
    'duration_secs': info['gameDuration'],
}
enriched = claude.generate_coaching_notes(moments, game_context, timeline_data)
```

5. Also add `from claude_client import ClaudeClient` at the top (it's already there via the existing import of `ClaudeClient`). Make sure the `claude` object is created before calling `generate_coaching_notes`:
```python
claude = ClaudeClient(api_key=os.environ['GEMINI_API_KEY'], db=db)
```
This line should already exist in `trigger_analysis.py` from the existing setup — verify it's there and add if missing.

- [ ] **Step 3: Verify sidecar imports cleanly**

```bash
cd sidecar && venv/Scripts/python -c "import main; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Run full test suite**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add sidecar/main.py sidecar/trigger_analysis.py
git commit -m "feat: wire role/champion into pipeline, replace enrich_moments with AI coaching"
```

---

## Task 9: Update `MomentCard.tsx` — Add New Positive Types

**Files:**
- Modify: `src/popup/MomentCard.tsx`

- [ ] **Step 1: Update `POSITIVE_TYPES` set**

In `src/popup/MomentCard.tsx`, find:
```tsx
const POSITIVE_TYPES = new Set(['solo_kill', 'objective_secured'])
```

Replace with:
```tsx
const POSITIVE_TYPES = new Set(['solo_kill', 'objective_secured', 'gank_assist', 'baron_secured', 'dragon_stack'])
```

- [ ] **Step 2: TypeScript check**

```bash
cd c:/Users/rohan/OneDrive/Desktop/NewProject && npx tsc --noEmit
```

Expected: zero errors

- [ ] **Step 3: Commit**

```bash
git add src/popup/MomentCard.tsx
git commit -m "feat: green cards for gank_assist, baron_secured, dragon_stack"
```

---

## Task 10: Final Verification

**Files:** None (verification only)

- [ ] **Step 1: Run the complete test suite**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 2: Run TypeScript check**

```bash
cd c:/Users/rohan/OneDrive/Desktop/NewProject && npx tsc --noEmit
```

Expected: zero errors

- [ ] **Step 3: Start the app and run trigger_analysis.py against a real game**

Terminal 1 (PowerShell, from NewProject):
```
npm run dev
```

Terminal 2 (from NewProject\sidecar):
```
venv/Scripts/python trigger_analysis.py
```

Expected output shows:
- `Role: JUNGLE` (or whatever role was played)
- At least one jungle-specific moment type (invade_death, gank_assist, dragon_missed, etc.) if a jungle game
- Moments with non-empty counterfactual strings generated by Gemini

- [ ] **Step 4: Verify popup shows correctly**

The popup should appear with:
- Green cards for `gank_assist`, `baron_secured`, `dragon_stack`
- Yellow cards for `invade_death`, `counter_ganked`, `dragon_missed`, `baron_missed`, `void_grubs_missed`
- All moments in chronological order
- AI-generated coaching text (3-4 sentences, role-specific)

- [ ] **Step 5: Git log review**

```bash
git log --oneline -12
```

Expected: clean commit trail showing all Phase 2 tasks
