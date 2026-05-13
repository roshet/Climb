# Jungle Death Catch-All Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flag every jungler death as a pivotal moment, not just invade deaths and counter-ganks, so the coaching AI has full visibility into all 6 deaths instead of just 2.

**Architecture:** Add `_in_own_jungle` position helper and `_detect_death_fallback` function to `jungle_analyzer.py`. Wire the fallback into the existing OR chain in `analyze_jungle` as the last detector — it fires only when all specific detectors return None. Position-based classification: own jungle → `jungle_death`; everything else → `death`.

**Tech Stack:** Python 3.11, pytest

---

## File Structure

| File | Change |
|---|---|
| `sidecar/jungle_analyzer.py` | Add `_in_own_jungle`, `_detect_death_fallback`, wire into OR chain |
| `sidecar/tests/test_jungle_analyzer.py` | Add tests for the two new catch-all cases |

---

### Task 1: Add catch-all death detector

**Files:**
- Modify: `sidecar/jungle_analyzer.py`
- Modify: `sidecar/tests/test_jungle_analyzer.py`

- [ ] **Step 1: Write the failing tests**

Open `sidecar/tests/test_jungle_analyzer.py` and append these two tests at the end of the file:

```python
def test_death_fallback_own_jungle():
    # Blue side jungler dies at (3000, 9000) — inside blue side jungle (own jungle)
    # Not in enemy jungle (x < 8000 or y > 7500), not in a lane
    timeline = {"info": {"frames": [
        make_frame(600000, [
            {"type": "CHAMPION_KILL", "timestamp": 600000,
             "killerId": 6, "victimId": JUNGLE_ID,
             "assistingParticipantIds": [],
             "position": {"x": 3000, "y": 9000}}
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    assert len(moments) == 1
    assert moments[0].moment_type == "jungle_death"
    assert "jungle" in moments[0].description.lower()
    assert moments[0].gold_impact == 300


def test_death_fallback_skirmish():
    # Blue side jungler dies at (7500, 6000) — mid-map, not own jungle, not enemy jungle, not lane
    timeline = {"info": {"frames": [
        make_frame(900000, [
            {"type": "CHAMPION_KILL", "timestamp": 900000,
             "killerId": 7, "victimId": JUNGLE_ID,
             "assistingParticipantIds": [],
             "position": {"x": 7500, "y": 6000}}
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    assert len(moments) == 1
    assert moments[0].moment_type == "death"
    assert moments[0].gold_impact == 300
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar && python -m pytest tests/test_jungle_analyzer.py::test_death_fallback_own_jungle tests/test_jungle_analyzer.py::test_death_fallback_skirmish -v
```

Expected: both tests FAIL (no moment produced, `len(moments) == 0` ≠ 1).

- [ ] **Step 3: Add `_in_own_jungle` helper to `jungle_analyzer.py`**

In `sidecar/jungle_analyzer.py`, after the `_in_ally_lane` function (around line 44), insert:

```python
def _in_own_jungle(position: dict, participant_id: int) -> bool:
    """True if position is inside the player's own jungle quadrant."""
    px, py = position.get("x", 0), position.get("y", 0)
    if _is_blue_side(participant_id):
        return px <= BLUE_JUNGLE_X_MAX and py >= BLUE_JUNGLE_Y_MIN
    else:
        return px >= RED_JUNGLE_X_MIN and py <= RED_JUNGLE_Y_MAX
```

- [ ] **Step 4: Add `_detect_death_fallback` to `jungle_analyzer.py`**

In `sidecar/jungle_analyzer.py`, after the `_detect_gank_assist` function (around line 174), insert:

```python
def _detect_death_fallback(event: dict, participant_id: int) -> PivotalMomentData | None:
    """Catch-all: fires for any jungler death not caught by a more specific detector."""
    if event.get("victimId") != participant_id:
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    time_str = f"{mins}:{secs:02d}"
    position = event.get("position", {"x": 0, "y": 0})
    if _in_own_jungle(position, participant_id):
        return PivotalMomentData(
            timestamp_secs=ts,
            moment_type="jungle_death",
            description=f"You were caught in your jungle at {time_str}.",
            counterfactual="",
            gold_impact=GOLD_VALUES["DEATH"],
        )
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="death",
        description=f"You died in a skirmish at {time_str}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )
```

- [ ] **Step 5: Wire the fallback into `analyze_jungle`**

In `sidecar/jungle_analyzer.py`, find this block inside `analyze_jungle` (around line 82–86):

```python
                moment = (
                    _detect_invade_death(event, participant_id)
                    or _detect_counter_ganked(event, participant_id, enemy_jungler_id)
                    or _detect_gank_assist(event, participant_id)
                )
```

Replace with:

```python
                moment = (
                    _detect_invade_death(event, participant_id)
                    or _detect_counter_ganked(event, participant_id, enemy_jungler_id)
                    or _detect_gank_assist(event, participant_id)
                    or _detect_death_fallback(event, participant_id)
                )
```

- [ ] **Step 6: Run the new tests to verify they pass**

```
cd sidecar && python -m pytest tests/test_jungle_analyzer.py::test_death_fallback_own_jungle tests/test_jungle_analyzer.py::test_death_fallback_skirmish -v
```

Expected: both PASS.

- [ ] **Step 7: Run the full jungle analyzer test suite to verify no regressions**

```
cd sidecar && python -m pytest tests/test_jungle_analyzer.py -v
```

Expected: all tests PASS. The existing `test_invade_death_not_triggered_in_own_jungle` test now verifies a different thing — it previously checked that no moment was produced; now it will produce a `jungle_death` moment instead of `invade_death`. Update that test:

Find `test_invade_death_not_triggered_in_own_jungle` in `sidecar/tests/test_jungle_analyzer.py` and replace with:

```python
def test_invade_death_not_triggered_in_own_jungle():
    # Blue side jungler dies at (2000, 10000) — inside blue side jungle (own jungle)
    # Should produce jungle_death (catch-all), NOT invade_death
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
    jungle_deaths = [m for m in moments if m.moment_type == "jungle_death"]
    assert len(jungle_deaths) == 1
```

Re-run after updating:

```
cd sidecar && python -m pytest tests/test_jungle_analyzer.py -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add sidecar/jungle_analyzer.py sidecar/tests/test_jungle_analyzer.py
git commit -m "feat: flag all jungler deaths as pivotal moments with catch-all classifier"
```
