# Personalized Death Alert Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Personalize the in-game death alert to reference the player's focus card (display label + clean streak), falling back to the existing generic message when no focus card exists.

**Architecture:** Single file change to `sidecar/live_game_monitor.py`. Add `_focus: dict | None` state, load it from `AppState(key="focus_card")` when the game is first detected, and use it in a `_death_message()` helper that replaces the hardcoded string in `_process_events`.

**Tech Stack:** Python 3, SQLAlchemy ORM, pytest. No frontend changes.

---

### Task 1: Add personalized death message to LiveGameMonitor

**Files:**
- Modify: `sidecar/live_game_monitor.py`
- Modify: `sidecar/tests/test_live_game_monitor.py`

---

- [ ] **Step 1: Write failing tests for `_death_message()`**

Add these four tests to the bottom of `sidecar/tests/test_live_game_monitor.py`:

```python
def test_death_message_no_focus(monitor):
    monitor._focus = None
    assert monitor._death_message() == "You're dead — use this time to plan your next move"


def test_death_message_with_streak_plural(monitor):
    monitor._focus = {"display": "Early Deaths", "streak_clean": 3}
    assert monitor._death_message() == "You're dead — 3 clean games on Early Deaths. Don't let it slip."


def test_death_message_with_streak_singular(monitor):
    monitor._focus = {"display": "Early Deaths", "streak_clean": 1}
    assert monitor._death_message() == "You're dead — 1 clean game on Early Deaths. Don't let it slip."


def test_death_message_no_streak(monitor):
    monitor._focus = {"display": "Early Deaths", "streak_clean": 0}
    assert monitor._death_message() == "You're dead — think about Early Deaths while you wait."
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sidecar && python -m pytest tests/test_live_game_monitor.py::test_death_message_no_focus tests/test_live_game_monitor.py::test_death_message_with_streak_plural tests/test_live_game_monitor.py::test_death_message_with_streak_singular tests/test_live_game_monitor.py::test_death_message_no_streak -v
```

Expected: 4 failures — `AttributeError: 'LiveGameMonitor' object has no attribute '_death_message'`

- [ ] **Step 3: Add imports and `_focus` state to `LiveGameMonitor`**

In `sidecar/live_game_monitor.py`, add to the top-level imports. After `import asyncio`:

```python
import json
```

After `from pattern_detector import detect_patterns`:

```python
from database import AppState
```

In `__init__`, add after `self._task`:

```python
self._focus: dict | None = None
```

In `_reset_game_state`, add at the end of the method body:

```python
self._focus = None
```

- [ ] **Step 4: Implement `_death_message()`**

Add this method to `LiveGameMonitor` immediately after `_add_alert`:

```python
def _death_message(self) -> str:
    if not self._focus:
        return "You're dead — use this time to plan your next move"
    display = self._focus.get("display", "")
    streak = self._focus.get("streak_clean", 0)
    if streak >= 1:
        s = "s" if streak != 1 else ""
        return f"You're dead — {streak} clean game{s} on {display}. Don't let it slip."
    return f"You're dead — think about {display} while you wait."
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd sidecar && python -m pytest tests/test_live_game_monitor.py::test_death_message_no_focus tests/test_live_game_monitor.py::test_death_message_with_streak_plural tests/test_live_game_monitor.py::test_death_message_with_streak_singular tests/test_live_game_monitor.py::test_death_message_no_streak -v
```

Expected: 4 PASS

- [ ] **Step 6: Write failing tests for focus loading and death event integration**

Add these imports to the top of `sidecar/tests/test_live_game_monitor.py` (alongside the existing imports):

```python
import json
from database import AppState
```

Then add these three tests at the bottom of the file:

```python
def test_load_focus_reads_from_db(db):
    db.merge(AppState(key="focus_card", value=json.dumps({
        "display": "Early Deaths", "streak_clean": 2, "moment_type": "early_death"
    })))
    db.commit()
    monitor = LiveGameMonitor(db)
    monitor._load_focus()
    assert monitor._focus is not None
    assert monitor._focus["display"] == "Early Deaths"


def test_load_focus_missing_returns_none(monitor):
    monitor._load_focus()
    assert monitor._focus is None


def test_death_alert_uses_focus(db):
    db.merge(AppState(key="focus_card", value=json.dumps({
        "display": "Early Deaths", "streak_clean": 0, "moment_type": "early_death"
    })))
    db.commit()
    monitor = LiveGameMonitor(db)
    monitor._in_game = True
    monitor._load_focus()
    monitor._process_events(
        [{"EventID": 10, "EventName": "ChampionKill", "EventTime": 400.0,
          "VictimName": "TestPlayer#NA1", "KillerName": "Enemy#NA1"}],
        "TestPlayer#NA1",
    )
    state = monitor.get_state()
    death_alerts = [a for a in state["alerts"] if a["alert_type"] == "death"]
    assert len(death_alerts) == 1
    assert "Early Deaths" in death_alerts[0]["message"]
```

- [ ] **Step 7: Run new tests to verify they fail**

```bash
cd sidecar && python -m pytest tests/test_live_game_monitor.py::test_load_focus_reads_from_db tests/test_live_game_monitor.py::test_load_focus_missing_returns_none tests/test_live_game_monitor.py::test_death_alert_uses_focus -v
```

Expected: 3 failures — `_load_focus` not yet defined, death alert still uses hardcoded string.

- [ ] **Step 8: Implement `_load_focus()`, update `_process_events`, and update `_tick`**

Add `_load_focus` method immediately after `_death_message`:

```python
def _load_focus(self) -> None:
    try:
        row = self._db.query(AppState).filter(AppState.key == "focus_card").first()
        self._focus = json.loads(row.value) if row and row.value else None
    except Exception:
        self._focus = None
```

In `_process_events`, replace the hardcoded death message string. Find this block:

```python
elif name == "ChampionKill":
    victim = event.get("VictimName", "")
    if victim.lower() == active_player_name.lower():
        self._add_alert(
            "You're dead — use this time to plan your next move",
            "death",
            f"death_{event_id}",
        )
```

Replace with:

```python
elif name == "ChampionKill":
    victim = event.get("VictimName", "")
    if victim.lower() == active_player_name.lower():
        self._add_alert(
            self._death_message(),
            "death",
            f"death_{event_id}",
        )
```

In `_tick`, load focus when the game is first detected. Find:

```python
if not self._in_game:
    self._in_game = True
```

Replace with:

```python
if not self._in_game:
    self._in_game = True
    self._load_focus()
```

- [ ] **Step 9: Run all live_game_monitor tests**

```bash
cd sidecar && python -m pytest tests/test_live_game_monitor.py -v
```

Expected: all 17 tests pass (10 existing + 7 new)

- [ ] **Step 10: Run the full test suite**

```bash
cd sidecar && python -m pytest --tb=short -q
```

Expected: all tests pass, no regressions.

- [ ] **Step 11: Commit**

```bash
git add sidecar/live_game_monitor.py sidecar/tests/test_live_game_monitor.py
git commit -m "feat: personalize death alert with focus card data"
```
