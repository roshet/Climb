# Back Timing Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect bad recall timing in post-game analysis — flagging backs near objective spawn windows and backs with too little gold to buy anything meaningful.

**Architecture:** Two new helper functions added to `sidecar/laner_analyzer.py`: `_collect_backs()` detects backs from ITEM_PURCHASED events and frame position jumps (with death exclusion and deduplication), and `_detect_bad_backs()` checks each back against objective spawn windows and gold tier thresholds to produce `PivotalMomentData` moments. Called from `analyze_laner()` for all non-jungle roles.

**Tech Stack:** Python, Riot Match Timeline API (frames + events), existing `PivotalMomentData` dataclass, pytest.

---

## File Structure

- **Modify:** `sidecar/laner_analyzer.py` — add constants, `_in_fountain()`, `_collect_backs()`, `_compute_objective_spawn_times()`, `_detect_bad_backs()`, call from `analyze_laner()`
- **Create:** `sidecar/tests/test_back_timing.py` — 8 unit tests

---

### Task 1: Back collection infrastructure

**Files:**
- Modify: `sidecar/laner_analyzer.py`
- Create: `sidecar/tests/test_back_timing.py`

- [ ] **Step 1: Create test file with helper and write the two failing infrastructure tests**

Create `sidecar/tests/test_back_timing.py`:

```python
import pytest
from laner_analyzer import _collect_backs


def make_frame(
    timestamp_ms: int,
    events: list,
    positions: dict | None = None,
    current_gold: dict | None = None,
    levels: dict | None = None,
) -> dict:
    pf = {}
    for pid in range(1, 11):
        pos = (positions or {}).get(pid, (5000, 5000))
        pf[str(pid)] = {
            "position": {"x": pos[0], "y": pos[1]},
            "currentGold": (current_gold or {}).get(pid, 1000),
            "totalGold": (current_gold or {}).get(pid, 1000),
            "minionsKilled": 0,
            "level": (levels or {}).get(pid, 5),
        }
    return {"timestamp": timestamp_ms, "participantFrames": pf, "events": events}


PLAYER = 1  # blue side, team 100


def test_deduplication():
    # ITEM_PURCHASED at 30s + position jump at 60s frame → one back, not two
    frames = [
        make_frame(0, [], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 400}),
        make_frame(60_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 1001, "timestamp": 30_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 100}),
    ]
    backs = _collect_backs(frames, participant_id=PLAYER)
    assert len(backs) == 1


def test_back_excluded_after_death():
    # Player dies at 5s (level 5 → respawn ~20s), buys at 15s → within respawn window → excluded
    frames = [
        make_frame(0, [
            {"type": "CHAMPION_KILL", "timestamp": 5_000,
             "victimId": PLAYER, "killerId": 6, "assistingParticipantIds": []},
        ], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 400}, levels={PLAYER: 5}),
        make_frame(60_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 1001, "timestamp": 15_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 100}),
    ]
    backs = _collect_backs(frames, participant_id=PLAYER)
    assert len(backs) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar && pytest tests/test_back_timing.py -v
```

Expected: `ImportError: cannot import name '_collect_backs' from 'laner_analyzer'`

- [ ] **Step 3: Add constants and `_in_fountain` + `_collect_backs` to `laner_analyzer.py`**

Add these constants after the existing constants block (after line 25, before the `BLUE_TURRETS` section — insert after `WARD_KILL_CAP = 3`):

```python
# --- Back timing ---
FOUNTAIN_BLUE = (523, 523)
FOUNTAIN_RED = (14340, 14390)
FOUNTAIN_RADIUS = 1500
OBJECTIVE_DANGER_WINDOW_SECS = 90
LATE_GAME_CUTOFF_SECS = 1200
BACK_DEDUP_WINDOW_SECS = 60
GOLD_WASTE_THRESHOLD = 300
GOLD_MINOR_THRESHOLD = 500
RESPAWN_BASE_SECS = 8
RESPAWN_PER_LEVEL_SECS = 2.5
RESPAWN_CAP_SECS = 60
DRAGON_FIRST_SPAWN = 300
DRAGON_RESPAWN_DELAY = 300
BARON_FIRST_SPAWN = 1200
BARON_RESPAWN_DELAY = 360
HERALD_FIRST_SPAWN = 480
HERALD_SECOND_SPAWN = 840
OBJECTIVE_GOLD: dict[str, int] = {"Dragon": 350, "Baron": 900, "Rift Herald": 400}
```

Then add these two functions anywhere before `analyze_laner` (e.g. after `_check_low_vision`):

```python
def _in_fountain(position: dict, participant_id: int) -> bool:
    fx, fy = FOUNTAIN_BLUE if participant_id in TEAM_100_IDS else FOUNTAIN_RED
    px, py = position.get("x", 0), position.get("y", 0)
    return math.sqrt((px - fx) ** 2 + (py - fy) ** 2) < FOUNTAIN_RADIUS


def _collect_backs(frames: list, participant_id: int) -> list[dict]:
    """Return list of {timestamp_secs, gold} for each detected voluntary recall."""
    # Collect death windows for exclusion
    death_windows: list[tuple[float, float]] = []
    for frame in frames:
        pf = frame.get("participantFrames", {}).get(str(participant_id), {})
        level = pf.get("level", 1)
        for event in frame.get("events", []):
            if (event.get("type") == "CHAMPION_KILL"
                    and event.get("victimId") == participant_id):
                ts = event["timestamp"] / 1000
                respawn = min(
                    RESPAWN_BASE_SECS + level * RESPAWN_PER_LEVEL_SECS,
                    RESPAWN_CAP_SECS,
                )
                death_windows.append((ts, ts + respawn))

    def _is_respawn(ts: float) -> bool:
        return any(start <= ts <= end for start, end in death_windows)

    purchase_backs: list[dict] = []
    position_backs: list[dict] = []
    prev_pf: dict | None = None

    for frame in frames:
        curr_pf = frame.get("participantFrames", {}).get(str(participant_id), {})

        for event in frame.get("events", []):
            if (event.get("type") == "ITEM_PURCHASED"
                    and event.get("participantId") == participant_id):
                ts = event["timestamp"] / 1000
                if not _is_respawn(ts):
                    gold = (prev_pf or {}).get("currentGold", 0)
                    purchase_backs.append({"timestamp_secs": ts, "gold": gold})

        if prev_pf is not None:
            prev_pos = prev_pf.get("position", {"x": 0, "y": 0})
            curr_pos = curr_pf.get("position", {"x": 0, "y": 0})
            frame_ts = frame["timestamp"] / 1000
            if (not _in_fountain(prev_pos, participant_id)
                    and _in_fountain(curr_pos, participant_id)
                    and not _is_respawn(frame_ts)):
                gold = prev_pf.get("currentGold", 0)
                position_backs.append({"timestamp_secs": frame_ts, "gold": gold})

        prev_pf = curr_pf

    # Merge: keep purchase backs, add position backs not covered by a purchase back
    all_backs = list(purchase_backs)
    for pb in position_backs:
        if not any(
            abs(pb["timestamp_secs"] - ex["timestamp_secs"]) <= BACK_DEDUP_WINDOW_SECS
            for ex in purchase_backs
        ):
            all_backs.append(pb)

    all_backs.sort(key=lambda b: b["timestamp_secs"])
    return all_backs
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd sidecar && pytest tests/test_back_timing.py::test_deduplication tests/test_back_timing.py::test_back_excluded_after_death -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add sidecar/laner_analyzer.py sidecar/tests/test_back_timing.py
git commit -m "feat: back timing infrastructure — _collect_backs with dedup and death exclusion"
```

---

### Task 2: Objective spawn tracking + `bad_back_objective` signal

**Files:**
- Modify: `sidecar/laner_analyzer.py`
- Modify: `sidecar/tests/test_back_timing.py`

- [ ] **Step 1: Add two failing objective signal tests to `test_back_timing.py`**

Add these imports at the top of the test file:

```python
from laner_analyzer import _collect_backs, _detect_bad_backs
```

Add these tests:

```python
def test_objective_window_back():
    # Back at 4:00 (240s), dragon first spawns at 5:00 (300s) → 60s before → flagged
    frames = [
        make_frame(0, [], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 800}),
        make_frame(240_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 3006, "timestamp": 240_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 800}),
    ]
    moments = _detect_bad_backs(frames, participant_id=PLAYER, role="TOP")
    obj = [m for m in moments if m.moment_type == "bad_back_objective"]
    assert len(obj) == 1
    assert "Dragon" in obj[0].description


def test_back_after_objective_safe():
    # Dragon killed at 5:00 (300s) → respawns at 10:00 (600s)
    # Player backs at 6:00 (360s) → 240s before next dragon → not flagged
    frames = [
        make_frame(0, [], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 800}),
        make_frame(300_000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 300_000,
             "monsterType": "DRAGON", "killerId": 6},
        ], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 800}),
        make_frame(360_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 3006, "timestamp": 360_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 800}),
    ]
    moments = _detect_bad_backs(frames, participant_id=PLAYER, role="TOP")
    obj = [m for m in moments if m.moment_type == "bad_back_objective"]
    assert len(obj) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar && pytest tests/test_back_timing.py::test_objective_window_back tests/test_back_timing.py::test_back_after_objective_safe -v
```

Expected: `ImportError: cannot import name '_detect_bad_backs' from 'laner_analyzer'`

- [ ] **Step 3: Add `_compute_objective_spawn_times` and a stub `_detect_bad_backs` with objective logic**

Add `_compute_objective_spawn_times` after `_collect_backs`:

```python
def _compute_objective_spawn_times(frames: list) -> list[tuple[int, str]]:
    """Return sorted list of (spawn_timestamp_secs, objective_name) for the whole game."""
    spawns: set[tuple[int, str]] = {
        (DRAGON_FIRST_SPAWN, "Dragon"),
        (BARON_FIRST_SPAWN, "Baron"),
        (HERALD_FIRST_SPAWN, "Rift Herald"),
        (HERALD_SECOND_SPAWN, "Rift Herald"),
    }
    for frame in frames:
        for event in frame.get("events", []):
            if event.get("type") != "ELITE_MONSTER_KILL":
                continue
            monster = event.get("monsterType", "")
            ts = event["timestamp"] // 1000
            if monster == "DRAGON":
                spawns.add((ts + DRAGON_RESPAWN_DELAY, "Dragon"))
            elif monster == "BARON_NASHOR":
                spawns.add((ts + BARON_RESPAWN_DELAY, "Baron"))
    return sorted(spawns)
```

Add `_detect_bad_backs` after `_compute_objective_spawn_times`:

```python
def _detect_bad_backs(
    frames: list,
    participant_id: int,
    role: str,
) -> list[PivotalMomentData]:
    moments: list[PivotalMomentData] = []
    backs = _collect_backs(frames, participant_id)
    spawn_times = _compute_objective_spawn_times(frames)

    for back in backs:
        ts = back["timestamp_secs"]
        gold = back["gold"]

        # Signal 1: back within objective spawn window
        for spawn_secs, obj_name in spawn_times:
            gap = spawn_secs - ts
            if 0 < gap <= OBJECTIVE_DANGER_WINDOW_SECS:
                spawn_mins, spawn_secs_rem = divmod(spawn_secs, 60)
                moments.append(PivotalMomentData(
                    timestamp_secs=int(ts),
                    moment_type="bad_back_objective",
                    description=(
                        f"You recalled {int(gap)}s before {obj_name} spawned "
                        f"at {spawn_mins}:{spawn_secs_rem:02d}."
                    ),
                    counterfactual=(
                        "If you were healthy when you recalled, staying to contest "
                        "or waiting until after the spawn would have kept your team "
                        "at full strength for the objective."
                    ),
                    gold_impact=OBJECTIVE_GOLD.get(obj_name, 350),
                ))
                break  # one flag per back

        # Signal 2: low gold back — added in Task 3

    return moments
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd sidecar && pytest tests/test_back_timing.py::test_objective_window_back tests/test_back_timing.py::test_back_after_objective_safe -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add sidecar/laner_analyzer.py sidecar/tests/test_back_timing.py
git commit -m "feat: objective-window back detection"
```

---

### Task 3: Gold tier signal + full integration

**Files:**
- Modify: `sidecar/laner_analyzer.py`
- Modify: `sidecar/tests/test_back_timing.py`

- [ ] **Step 1: Add four failing gold tier tests to `test_back_timing.py`**

```python
def test_low_gold_back_under_300():
    # Back at 3:00 with 250g → waste tier flagged
    frames = [
        make_frame(0, [], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 250}),
        make_frame(180_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 2003, "timestamp": 180_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 50}),
    ]
    moments = _detect_bad_backs(frames, participant_id=PLAYER, role="TOP")
    gold_m = [m for m in moments if m.moment_type == "bad_back_gold"]
    assert len(gold_m) == 1
    assert "not enough" in gold_m[0].description.lower()


def test_low_gold_back_300_to_500():
    # Back at 3:00 with 400g → minor tier flagged
    frames = [
        make_frame(0, [], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 400}),
        make_frame(180_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 1036, "timestamp": 180_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 50}),
    ]
    moments = _detect_bad_backs(frames, participant_id=PLAYER, role="TOP")
    gold_m = [m for m in moments if m.moment_type == "bad_back_gold"]
    assert len(gold_m) == 1
    assert "minor component" in gold_m[0].description.lower()


def test_gold_back_after_20min():
    # Back at 21:00 with 200g → not flagged (late game)
    frames = [
        make_frame(0, [], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 200}),
        make_frame(1260_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 2003, "timestamp": 1260_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 50}),
    ]
    moments = _detect_bad_backs(frames, participant_id=PLAYER, role="TOP")
    gold_m = [m for m in moments if m.moment_type == "bad_back_gold"]
    assert len(gold_m) == 0


def test_high_gold_not_flagged():
    # Back at 3:00 with 1000g → not flagged for gold
    frames = [
        make_frame(0, [], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 1000}),
        make_frame(180_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 3006, "timestamp": 180_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 150}),
    ]
    moments = _detect_bad_backs(frames, participant_id=PLAYER, role="TOP")
    gold_m = [m for m in moments if m.moment_type == "bad_back_gold"]
    assert len(gold_m) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar && pytest tests/test_back_timing.py::test_low_gold_back_under_300 tests/test_back_timing.py::test_low_gold_back_300_to_500 tests/test_back_timing.py::test_gold_back_after_20min tests/test_back_timing.py::test_high_gold_not_flagged -v
```

Expected: 4 failed (gold signal not implemented yet)

- [ ] **Step 3: Add gold tier logic to `_detect_bad_backs` in `laner_analyzer.py`**

Replace the `# Signal 2: low gold back — added in Task 3` comment with:

```python
        # Signal 2: low gold back (before 20:00 only)
        if ts < LATE_GAME_CUTOFF_SECS:
            mins, secs_rem = divmod(int(ts), 60)
            if gold < GOLD_WASTE_THRESHOLD:
                moments.append(PivotalMomentData(
                    timestamp_secs=int(ts),
                    moment_type="bad_back_gold",
                    description=(
                        f"You recalled with only {gold}g at {mins}:{secs_rem:02d} "
                        f"— not enough to buy any component."
                    ),
                    counterfactual=(
                        "If you were healthy when you recalled, staying in lane to "
                        "accumulate gold for a meaningful purchase would have been "
                        "more efficient."
                    ),
                    gold_impact=900 - gold,
                ))
            elif gold < GOLD_MINOR_THRESHOLD:
                moments.append(PivotalMomentData(
                    timestamp_secs=int(ts),
                    moment_type="bad_back_gold",
                    description=(
                        f"You recalled with only {gold}g at {mins}:{secs_rem:02d} "
                        f"— enough for only a minor component."
                    ),
                    counterfactual=(
                        "If you were healthy when you recalled, staying in lane a "
                        "bit longer to reach a more meaningful purchase threshold "
                        "would have been more efficient."
                    ),
                    gold_impact=900 - gold,
                ))
```

- [ ] **Step 4: Run all 8 tests to verify they all pass**

```
cd sidecar && pytest tests/test_back_timing.py -v
```

Expected: 8 passed

- [ ] **Step 5: Wire `_detect_bad_backs` into `analyze_laner()`**

In `analyze_laner()`, add this block just before the final `moments.sort(...)` line:

```python
    # Back timing analysis (all laner roles)
    back_moments = _detect_bad_backs(frames, participant_id, role)
    moments.extend(back_moments)
```

The final section of `analyze_laner` should look like:

```python
    # Support: low vision check
    if role == "UTILITY":
        vision_moment = _check_low_vision(frames, participant_id)
        if vision_moment:
            moments.append(vision_moment)

    # Frame-based signals: CS and gold differential
    if lane_opponent_id is not None:
        if role in ("TOP", "MIDDLE", "BOTTOM"):
            cs_moment = _cs_differential_at_14(frames, participant_id, lane_opponent_id)
            if cs_moment:
                moments.append(cs_moment)
        gold_moment = _gold_differential_at_14(frames, participant_id, lane_opponent_id)
        if gold_moment:
            moments.append(gold_moment)

    # Back timing analysis (all laner roles)
    back_moments = _detect_bad_backs(frames, participant_id, role)
    moments.extend(back_moments)

    moments.sort(key=lambda m: m.timestamp_secs)
    return moments
```

- [ ] **Step 6: Run the full test suite to verify nothing is broken**

```
cd sidecar && pytest tests/ -v
```

Expected: all tests pass (139 existing + 8 new = 147 total)

- [ ] **Step 7: Commit**

```bash
git add sidecar/laner_analyzer.py sidecar/tests/test_back_timing.py
git commit -m "feat: back timing analysis — gold tier signal and integration into analyze_laner"
```
