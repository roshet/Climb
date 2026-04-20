# Live Game Overlay — Design Spec
**Date:** 2026-04-20
**Status:** Approved

---

## Overview

Add a real-time in-game overlay that surfaces two types of information while the player is in a League of Legends match:

1. **Live game cues** — event-driven alerts triggered by objective kills, upcoming spawns, and player death
2. **Pattern reminders** — the player's top cross-game recurring issues shown once at game start

The overlay appears as a transparent, always-on-top Electron window in the top-right corner of the screen. Alerts slide in when triggered and auto-dismiss after 8 seconds. The window is click-through so it never interferes with gameplay.

---

## Architecture

### Approach: Sidecar-owned logic, Electron overlay renderer

The Python sidecar owns all game logic. The Electron overlay window is a dumb renderer that polls a new `GET /live` endpoint every 2 seconds and displays whatever alerts the sidecar returns. This is consistent with the existing pattern (popup window polls `/status`, chat window polls `/analysis`).

### New files

- **`sidecar/live_game_monitor.py`** — polls Riot Live Client API, processes events, maintains `AlertState`
- **`src/overlay/`** — new React window (index.html, App.tsx, main.tsx) for the overlay UI

### Modified files

- **`sidecar/main.py`** — add `GET /live` endpoint, wire `live_game_monitor` into game lifecycle
- **`electron/main.ts`** — create/destroy overlay window on game start/end
- **`vite.config.ts`** — add overlay as a build entry point

---

## Sidecar: `live_game_monitor.py`

### Lifecycle

`live_game_monitor` starts polling when `game_end_watcher` detects a game has started (Live Client API becomes reachable). It stops when the game ends. The existing `game_end_watcher` already tracks this transition — `live_game_monitor` hooks into the same flag.

### Polling

Polls `https://127.0.0.1:2999/liveclientdata/eventdata` every 2 seconds. The Live Client API uses a self-signed cert — requests must disable SSL verification (`verify=False`). If the API is unreachable, the poll is silently skipped.

### AlertState

```python
@dataclass
class Alert:
    id: str          # unique per alert instance
    message: str
    alert_type: str  # "objective" | "death" | "pattern"
    expires_at: float  # Unix timestamp
```

`AlertState` is a list of up to 3 active `Alert` objects. When a new alert is added and there are already 3, the oldest is removed. Each alert expires after 8 seconds (`expires_at = time.time() + 8`). The `GET /live` endpoint filters out expired alerts before returning.

### Alert triggers

| Event | Condition | Message | Type |
|---|---|---|---|
| Dragon killed | `DragonKill` event received | "Next Dragon in 5:00 — stay aware" | `objective` |
| Baron killed | `BaronKill` event received | "Next Baron in 7:00 — ward up early" | `objective` |
| Dragon spawning soon | game clock within 60s of next Dragon spawn | "Dragon spawns soon — contest or trade" | `objective` |
| Baron spawning soon | game clock within 60s of next Baron spawn (20:00, then every 7 min) | "Baron spawns soon — group or pressure" | `objective` |
| Player death | `ChampionKill` event where victim is active player | "You're dead — use this time to plan your next move" | `death` |
| Game start | game clock reaches 0:30 | Top 2 recurring issue patterns from `detect_patterns()` | `pattern` |

**Spawn timer logic:**
- First Dragon: 5:00. Respawn: 5 minutes after kill.
- First Baron: 20:00. Respawn: 7 minutes after kill.
- Dragon/Baron "spawning soon" alert fires when spawn time minus current game clock ≤ 60 seconds.
- Spawn timers are tracked in-memory in `live_game_monitor` — reset when a kill event is received.

**Pattern reminders:**
- Called once at game start (0:30). Calls `detect_patterns(db)` — if it fails or returns `[]`, no pattern alerts are shown.
- Only `label == "recurring_issue"` patterns are shown (top 2 by `games_seen`).
- Message format: `"Pattern: {pattern.summary}"`

**Deduplication:** Each alert trigger is debounced — a second Dragon kill event within 30 seconds of the first does not fire a second alert.

### `GET /live` response

```json
{
  "alerts": [
    {
      "id": "dragon-1745123456",
      "message": "Next Dragon in 5:00 — stay aware",
      "alert_type": "objective",
      "expires_at": 1745123464.0
    }
  ],
  "in_game": true
}
```

Returns `{"alerts": [], "in_game": false}` when no game is active.

---

## Frontend: Overlay Window (`src/overlay/`)

### Electron window properties

Created in `electron/main.ts` when `game_end_watcher` detects game start:

```typescript
new BrowserWindow({
  width: 340,
  height: 400,
  x: screenWidth - 360,  // top-right, 20px from edge
  y: 20,
  transparent: true,
  frame: false,
  alwaysOnTop: true,
  focusable: false,
  skipTaskbar: true,
  webPreferences: { preload: ... }
})
```

Destroyed when game ends (same lifecycle hook as `game_end_watcher` game-end transition).

**Fullscreen note:** Electron always-on-top windows render over borderless windowed mode. They do not render over fullscreen exclusive mode. Players must use borderless windowed for the overlay to appear.

### React app (`src/overlay/App.tsx`)

Polls `GET /live` every 2 seconds. Maintains local alert list synced to server response (adds new alerts, removes expired ones). Each alert renders as a card that animates in from the right using a CSS slide-in transition and fades out as `expires_at` approaches.

**Color coding:**
- `objective` → blue accent (`#3b82f6`)
- `death` → yellow accent (`#f59e0b`)
- `pattern` → green accent (`#22c55e`)

Alert card layout:
```
┌─────────────────────────────────┐
│ 🔵  Next Dragon in 5:00         │
│     stay aware                  │
└─────────────────────────────────┘
```

No close button — alerts are ephemeral, auto-dismissed only.

---

## Vite Config

Add `overlay` as a new entry in `vite.config.ts` alongside the existing `chat`, `popup`, and `setup` entries:

```typescript
overlay: resolve(__dirname, 'src/overlay/index.html'),
```

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Game not running | `GET /live` returns `{"alerts": [], "in_game": false}` |
| Live Client API unreachable | Poll silently skipped, `in_game` remains false |
| `detect_patterns` fails at game start | Pattern alerts omitted, no crash |
| Overlay window loses focus | `focusable: false` prevents focus steal |
| Game ends mid-alert | Overlay window destroyed, alerts discarded |
| Player uses fullscreen exclusive | Overlay not visible — borderless windowed required |

---

## Testing

**`sidecar/tests/test_live_game_monitor.py`** — unit tests with mocked Live Client API:

- `test_no_alerts_when_not_in_game` — API unreachable → empty alert list
- `test_dragon_kill_fires_alert` — DragonKill event → objective alert added
- `test_baron_kill_fires_alert` — BaronKill event → objective alert added
- `test_dragon_spawn_soon_alert` — game clock 4:10 → Dragon spawn alert fires
- `test_baron_spawn_soon_alert` — game clock 19:10 → Baron spawn alert fires
- `test_player_death_fires_alert` — ChampionKill with active player as victim → death alert
- `test_alert_expires_after_8s` — alert with past `expires_at` filtered from `GET /live` response
- `test_max_3_alerts` — adding 4th alert evicts oldest
- `test_pattern_alerts_at_game_start` — game clock ≥ 30s, patterns exist → pattern alerts added
- `test_pattern_alert_deduplication` — pattern alerts only fire once per game

Electron overlay window behavior is verified manually — no automated UI tests.

---

## Out of Scope

- Fullscreen exclusive mode support (requires a different rendering approach)
- Customizable alert positions
- Per-champion objective timing variations (e.g. Smite interactions)
- Sound/audio alerts
- Ally death alerts (only active player death)
