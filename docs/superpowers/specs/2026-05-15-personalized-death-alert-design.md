# Personalized Death Alert Design

## Goal

Personalize the in-game death alert to reference the player's focus card, making the coaching feel continuous rather than generic.

## Context

The overlay (`src/overlay/App.tsx`) shows alerts from `LiveGameMonitor`. When the player dies, it fires:

> "You're dead — use this time to plan your next move"

This message is identical for every player on every death. Since we now have a focus card (the player's top recurring issue), the death moment is the ideal time to reinforce it — the player is forced to stop and wait, giving them a moment to reflect.

## Architecture

Single file change: `sidecar/live_game_monitor.py`. No backend changes, no new endpoints, no frontend changes.

**Data source:** `AppState(key="focus_card")` — the same JSON blob the `/focus` endpoint reads. Fields used: `display` (human-readable label) and `streak_clean` (consecutive clean games count).

**Load strategy:** Load once when the game is first detected (when `_in_game` transitions to `True`). Cache in `_focus: dict | None`. Reset in `_reset_game_state()` so it reloads fresh for the next game.

**Failure handling:** If the DB query fails or `focus_card` is not set, `_focus` stays `None` and the existing fallback message fires unchanged.

## Changes

### New state field

```python
self._focus: dict | None = None
```

Reset in `_reset_game_state()`:

```python
self._focus = None
```

### Load focus on game start

In `_tick()`, when transitioning to in-game:

```python
if not self._in_game:
    self._in_game = True
    self._load_focus()
```

### New `_load_focus()` method

Add `import json` and `from database import AppState` to the top-level imports in `live_game_monitor.py`.

```python
def _load_focus(self) -> None:
    try:
        row = self._db.query(AppState).filter(AppState.key == "focus_card").first()
        self._focus = json.loads(row.value) if row and row.value else None
    except Exception:
        self._focus = None
```

### New `_death_message()` helper

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

### Updated death event handler

Replace the hardcoded message in `_process_events`:

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

## Message Examples

| State | Message |
|-------|---------|
| No focus card | "You're dead — use this time to plan your next move" |
| streak_clean = 1 | "You're dead — 1 clean game on Early Deaths. Don't let it slip." |
| streak_clean = 3 | "You're dead — 3 clean games on Early Deaths. Don't let it slip." |
| streak_clean = 0 | "You're dead — think about Early Deaths while you wait." |

## Edge Cases

- No focus card (fresh install / not enough games): `_focus` is None → fallback message unchanged
- DB query fails: exception caught → `_focus` stays None → fallback message
- `display` field missing from stored JSON: `.get("display", "")` returns empty string — message is a bit odd but not broken
- Champion swaps mid-session: focus loads at game start and doesn't reload — acceptable, focus card doesn't change mid-game
