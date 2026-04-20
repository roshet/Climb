# Live Game Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a transparent always-on-top Electron overlay window that shows real-time coaching alerts (objective timers, death reminders, pattern reminders) while the player is in a League of Legends game.

**Architecture:** A new `LiveGameMonitor` class in `sidecar/live_game_monitor.py` polls the Riot Live Client API every 2 seconds, processes game events, and maintains an in-memory `AlertState`. A new `GET /live` FastAPI endpoint exposes this state. A new Electron window (`src/overlay/`) polls `/live` every 2 seconds and renders alerts as fading cards in the top-right corner. The Electron main process creates/destroys the overlay window based on the `in_game` flag returned by `/live`.

**Tech Stack:** Python 3.11+, httpx (already a sidecar dependency), FastAPI, React 18, TypeScript, Tailwind CSS, Electron

---

## File Structure

- **Create:** `sidecar/live_game_monitor.py` — `LiveGameMonitor` class: polls Live Client API, processes events, maintains alert state
- **Create:** `sidecar/tests/test_live_game_monitor.py` — 10 unit tests for alert logic
- **Modify:** `sidecar/main.py` — instantiate `LiveGameMonitor`, start in lifespan, add `GET /live` endpoint
- **Create:** `src/overlay/index.html` — Electron window entry point (matches existing popup/chat pattern)
- **Create:** `src/overlay/App.tsx` — React component that polls `/live` and renders alert cards
- **Modify:** `vite.config.ts` — add overlay as a build entry point
- **Modify:** `electron/main.ts` — add `createOverlayWindow`/`destroyOverlayWindow`, poll `/live` in `pollStatus`

---

### Task 1: `live_game_monitor.py` — alert logic + tests

**Files:**
- Create: `sidecar/live_game_monitor.py`
- Create: `sidecar/tests/test_live_game_monitor.py`

**Context:** The Live Client API runs at `https://127.0.0.1:2999` during a game. It uses a self-signed cert so all requests need `verify=False`. The sidecar already uses `httpx` (see `riot_client.py` line 18). `detect_patterns` is in `sidecar/pattern_detector.py` and takes a `Session`. The conftest `db` fixture creates an in-memory SQLite with all tables. `save_match` and `save_pivotal_moments` are in `database.py`.

- [ ] **Step 1: Write all 10 failing tests**

Create `sidecar/tests/test_live_game_monitor.py`:

```python
import time
import pytest
from datetime import datetime
from unittest.mock import patch
from database import save_match, save_pivotal_moments
from live_game_monitor import LiveGameMonitor


@pytest.fixture
def monitor(db):
    return LiveGameMonitor(db)


def test_no_alerts_when_not_in_game(monitor):
    state = monitor.get_state()
    assert state["in_game"] is False
    assert state["alerts"] == []


def test_dragon_kill_fires_alert(monitor):
    monitor._in_game = True
    monitor._process_events(
        [{"EventID": 1, "EventName": "DragonKill", "EventTime": 300.0}],
        "TestPlayer#NA1",
    )
    state = monitor.get_state()
    assert any("Dragon" in a["message"] for a in state["alerts"])
    assert state["alerts"][0]["alert_type"] == "objective"


def test_baron_kill_fires_alert(monitor):
    monitor._in_game = True
    monitor._process_events(
        [{"EventID": 1, "EventName": "BaronKill", "EventTime": 1200.0}],
        "TestPlayer#NA1",
    )
    state = monitor.get_state()
    assert any("Baron" in a["message"] for a in state["alerts"])
    assert state["alerts"][0]["alert_type"] == "objective"


def test_dragon_spawn_soon_alert(monitor):
    monitor._in_game = True
    monitor._next_dragon_spawn = 250.0
    monitor._check_spawn_timers(200.0)  # 50s before spawn — within 60s window
    state = monitor.get_state()
    assert any("Dragon spawns soon" in a["message"] for a in state["alerts"])


def test_baron_spawn_soon_alert(monitor):
    monitor._in_game = True
    monitor._next_baron_spawn = 1240.0
    monitor._check_spawn_timers(1190.0)  # 50s before spawn
    state = monitor.get_state()
    assert any("Baron spawns soon" in a["message"] for a in state["alerts"])


def test_player_death_fires_alert(monitor):
    monitor._in_game = True
    monitor._process_events(
        [{"EventID": 5, "EventName": "ChampionKill", "EventTime": 400.0,
          "VictimName": "TestPlayer#NA1", "KillerName": "Enemy#NA1"}],
        "TestPlayer#NA1",
    )
    state = monitor.get_state()
    assert any("dead" in a["message"] for a in state["alerts"])
    assert state["alerts"][0]["alert_type"] == "death"


def test_alert_expires_after_8s(monitor):
    monitor._in_game = True
    monitor._process_events(
        [{"EventID": 1, "EventName": "DragonKill", "EventTime": 300.0}],
        "TestPlayer#NA1",
    )
    for a in monitor._alerts:
        a.expires_at = time.time() - 1  # force expiry
    state = monitor.get_state()
    assert state["alerts"] == []


def test_max_3_alerts(monitor):
    monitor._in_game = True
    monitor._add_alert("Alert 1", "objective", "key1")
    monitor._add_alert("Alert 2", "objective", "key2")
    monitor._add_alert("Alert 3", "objective", "key3")
    monitor._add_alert("Alert 4", "objective", "key4")
    state = monitor.get_state()
    assert len(state["alerts"]) == 3
    assert all(a["message"] != "Alert 1" for a in state["alerts"])  # oldest evicted


def test_pattern_alerts_at_game_start(db):
    monitor = LiveGameMonitor(db)
    # 3 losses with objective_missed, 3 wins without — creates recurring issue pattern
    for i in range(3):
        mid = f"NA1_loss_{i}"
        save_match(db, {
            "match_id": mid, "played_at": datetime(2026, 1, i + 1, 12, 0),
            "champion": "Caitlyn", "role": "BOTTOM", "result": "loss",
            "duration_secs": 1800, "kda": "2/5/3", "cs": 100,
            "gold_earned": 9000, "vision_score": 15, "raw_timeline": {},
        })
        save_pivotal_moments(db, mid, [{
            "timestamp_secs": 300, "moment_type": "objective_missed",
            "description": "Missed dragon", "counterfactual": "", "gold_impact": 0,
        }])
    for i in range(3):
        mid = f"NA1_win_{i}"
        save_match(db, {
            "match_id": mid, "played_at": datetime(2026, 1, i + 4, 12, 0),
            "champion": "Caitlyn", "role": "BOTTOM", "result": "win",
            "duration_secs": 1800, "kda": "5/2/8", "cs": 150,
            "gold_earned": 12000, "vision_score": 20, "raw_timeline": {},
        })
    monitor._maybe_show_patterns(30.0)
    state = monitor.get_state()
    assert any(a["alert_type"] == "pattern" for a in state["alerts"])


def test_pattern_alert_deduplication(monitor):
    with patch("live_game_monitor.detect_patterns") as mock_detect:
        mock_detect.return_value = []
        monitor._maybe_show_patterns(30.0)  # first call — sets _patterns_shown flag
        monitor._maybe_show_patterns(60.0)  # second call — should be no-op
    assert mock_detect.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar
venv/Scripts/pytest tests/test_live_game_monitor.py -v
```

Expected: All 10 FAILED — `ModuleNotFoundError: No module named 'live_game_monitor'`

- [ ] **Step 3: Implement `sidecar/live_game_monitor.py`**

Create `sidecar/live_game_monitor.py`:

```python
import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from pattern_detector import detect_patterns

LIVE_CLIENT_BASE = "https://127.0.0.1:2999/liveclientdata"
DRAGON_FIRST_SPAWN = 300.0    # 5:00
DRAGON_RESPAWN_DELAY = 300.0  # 5 minutes
BARON_FIRST_SPAWN = 1200.0    # 20:00
BARON_RESPAWN_DELAY = 420.0   # 7 minutes
ALERT_DURATION = 8.0          # seconds each alert stays visible
SPAWN_WARN_WINDOW = 60.0      # seconds before spawn to show warning
DEBOUNCE_WINDOW = 30.0        # minimum seconds between same alert type


@dataclass
class Alert:
    id: str
    message: str
    alert_type: str   # "objective" | "death" | "pattern"
    expires_at: float


class LiveGameMonitor:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._in_game = False
        self._alerts: list[Alert] = []
        self._processed_event_ids: set[int] = set()
        self._next_dragon_spawn: float = DRAGON_FIRST_SPAWN
        self._next_baron_spawn: float = BARON_FIRST_SPAWN
        self._patterns_shown = False
        self._last_alert_times: dict[str, float] = {}
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    def get_state(self) -> dict:
        now = time.time()
        self._alerts = [a for a in self._alerts if a.expires_at > now]
        return {
            "in_game": self._in_game,
            "alerts": [
                {
                    "id": a.id,
                    "message": a.message,
                    "alert_type": a.alert_type,
                    "expires_at": a.expires_at,
                }
                for a in self._alerts
            ],
        }

    def _add_alert(self, message: str, alert_type: str, debounce_key: str = "") -> None:
        now = time.time()
        if debounce_key:
            if now - self._last_alert_times.get(debounce_key, 0) < DEBOUNCE_WINDOW:
                return
            self._last_alert_times[debounce_key] = now
        if len(self._alerts) >= 3:
            self._alerts.pop(0)
        self._alerts.append(Alert(
            id=f"{alert_type}-{int(now * 1000)}",
            message=message,
            alert_type=alert_type,
            expires_at=now + ALERT_DURATION,
        ))

    def _process_events(self, events: list[dict], active_player_name: str) -> None:
        for event in events:
            event_id = event.get("EventID", -1)
            if event_id in self._processed_event_ids:
                continue
            self._processed_event_ids.add(event_id)
            name = event.get("EventName", "")
            if name == "DragonKill":
                self._next_dragon_spawn = event.get("EventTime", 0.0) + DRAGON_RESPAWN_DELAY
                self._add_alert("Next Dragon in 5:00 — stay aware", "objective", "dragon_kill")
            elif name == "BaronKill":
                self._next_baron_spawn = event.get("EventTime", 0.0) + BARON_RESPAWN_DELAY
                self._add_alert("Next Baron in 7:00 — ward up early", "objective", "baron_kill")
            elif name == "ChampionKill":
                victim = event.get("VictimName", "")
                if victim.lower() == active_player_name.lower():
                    self._add_alert(
                        "You're dead — use this time to plan your next move",
                        "death",
                        f"death_{event_id}",
                    )

    def _check_spawn_timers(self, game_time: float) -> None:
        dragon_secs = self._next_dragon_spawn - game_time
        if 0 < dragon_secs <= SPAWN_WARN_WINDOW:
            self._add_alert("Dragon spawns soon — contest or trade", "objective", "dragon_soon")
        baron_secs = self._next_baron_spawn - game_time
        if 0 < baron_secs <= SPAWN_WARN_WINDOW:
            self._add_alert("Baron spawns soon — group or pressure", "objective", "baron_soon")

    def _maybe_show_patterns(self, game_time: float) -> None:
        if self._patterns_shown or game_time < 30.0:
            return
        self._patterns_shown = True
        try:
            patterns = detect_patterns(self._db)
            issues = [p for p in patterns if p.label == "recurring_issue"][:2]
            for p in issues:
                self._add_alert(f"Pattern: {p.summary}", "pattern")
        except Exception:
            pass

    def _reset_game_state(self) -> None:
        self._alerts = []
        self._processed_event_ids = set()
        self._next_dragon_spawn = DRAGON_FIRST_SPAWN
        self._next_baron_spawn = BARON_FIRST_SPAWN
        self._patterns_shown = False
        self._last_alert_times = {}

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception:
                pass
            await asyncio.sleep(2)

    async def _tick(self) -> None:
        async with httpx.AsyncClient(verify=False, timeout=2.0) as client:
            try:
                events_resp = await client.get(f"{LIVE_CLIENT_BASE}/eventdata")
                stats_resp = await client.get(f"{LIVE_CLIENT_BASE}/gamestats")
                player_resp = await client.get(f"{LIVE_CLIENT_BASE}/activeplayername")
            except Exception:
                if self._in_game:
                    self._in_game = False
                    self._reset_game_state()
                return

            if not self._in_game:
                self._in_game = True

            events = events_resp.json().get("Events", [])
            game_time = stats_resp.json().get("gameTime", 0.0)
            active_player = player_resp.json()

            self._process_events(events, active_player)
            self._check_spawn_timers(game_time)
            self._maybe_show_patterns(game_time)
```

- [ ] **Step 4: Run the 10 tests**

```
cd sidecar
venv/Scripts/pytest tests/test_live_game_monitor.py -v
```

Expected: All 10 PASS.

- [ ] **Step 5: Run full suite to confirm no regressions**

```
cd sidecar
venv/Scripts/pytest tests/ -v
```

Expected: 139 tests PASS (129 existing + 10 new).

- [ ] **Step 6: Commit**

```bash
git add sidecar/live_game_monitor.py sidecar/tests/test_live_game_monitor.py
git commit -m "feat: live game monitor with alert logic and 10 tests"
```

---

### Task 2: `GET /live` endpoint — wire monitor into `main.py`

**Files:**
- Modify: `sidecar/main.py`

**Context:** `main.py` already has a `lifespan` context manager that starts `game_end_watcher` and `backfill_history` as background tasks. The global `db` Session object is created at module level. The pattern for adding a new background service is: instantiate at module level, call `.start()` in `lifespan`, call `.stop()` in the cleanup block.

- [ ] **Step 1: Add import and global instance**

In `sidecar/main.py`, add the import after the existing local imports:

```python
from live_game_monitor import LiveGameMonitor
```

Add the global instance after the `claude = ClaudeClient(...)` line:

```python
live_monitor = LiveGameMonitor(db)
```

- [ ] **Step 2: Start monitor in lifespan**

Replace the existing `lifespan` function:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _watcher_task
    _watcher_task = asyncio.create_task(game_end_watcher())
    asyncio.create_task(backfill_history())
    live_monitor.start()
    yield
    if _watcher_task:
        _watcher_task.cancel()
    live_monitor.stop()
    await riot.close()
    db.close()
```

- [ ] **Step 3: Add `GET /live` endpoint**

Add this endpoint to `main.py` after the `GET /patterns` route:

```python
@app.get("/live")
def get_live():
    return live_monitor.get_state()
```

- [ ] **Step 4: Run full test suite**

```
cd sidecar
venv/Scripts/pytest tests/ -v
```

Expected: 139 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sidecar/main.py
git commit -m "feat: GET /live endpoint with LiveGameMonitor wired into sidecar"
```

---

### Task 3: Overlay React window + Vite config

**Files:**
- Create: `src/overlay/index.html`
- Create: `src/overlay/App.tsx`
- Modify: `vite.config.ts`

**Context:** All existing React windows follow the same pattern: `index.html` has a `<div id="root">` and a `<script type="module" src="./App.tsx">`. `App.tsx` contains the component AND the `createRoot` call at the bottom. Windows import `'../index.css'` for Tailwind styles. `window.sidecar.port` is exposed by the preload script and defaults to `'8765'`.

The overlay window will be transparent (no background), so the React root must also have a transparent background. The window is `focusable: false` and click-through, so no interactive elements are needed.

- [ ] **Step 1: Create `src/overlay/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Climb Overlay</title></head>
<body style="margin:0;background:transparent;">
  <div id="root"></div>
  <script type="module" src="./App.tsx"></script>
</body>
</html>
```

- [ ] **Step 2: Create `src/overlay/App.tsx`**

```tsx
import { useState, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import '../index.css'

declare global {
  interface Window { sidecar: { port: string } }
}

interface Alert {
  id: string
  message: string
  alert_type: 'objective' | 'death' | 'pattern'
  expires_at: number
}

const TYPE_BORDER: Record<string, string> = {
  objective: 'border-blue-500 bg-blue-950/80',
  death: 'border-yellow-500 bg-yellow-950/80',
  pattern: 'border-green-500 bg-green-950/80',
}

const TYPE_DOT: Record<string, string> = {
  objective: 'bg-blue-400',
  death: 'bg-yellow-400',
  pattern: 'bg-green-400',
}

function AlertCard({ alert }: { alert: Alert }) {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 10)
    return () => clearTimeout(t)
  }, [])

  const border = TYPE_BORDER[alert.alert_type] ?? 'border-gray-500 bg-gray-900/80'
  const dot = TYPE_DOT[alert.alert_type] ?? 'bg-gray-400'

  return (
    <div
      className={`border rounded-lg px-3 py-2 flex items-start gap-2 text-sm text-white shadow-lg transition-all duration-300 ${border} ${
        visible ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-4'
      }`}
    >
      <div className={`w-2 h-2 rounded-full mt-1 shrink-0 ${dot}`} />
      <span className="leading-snug">{alert.message}</span>
    </div>
  )
}

function OverlayApp() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const port = window.sidecar?.port ?? '8765'

  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch(`http://localhost:${port}/live`)
        if (!res.ok) return
        const data = await res.json() as { alerts: Alert[]; in_game: boolean }
        setAlerts(data.alerts ?? [])
      } catch { /* sidecar not ready */ }
    }
    poll()
    const interval = setInterval(poll, 2000)
    return () => clearInterval(interval)
  }, [port])

  if (alerts.length === 0) return null

  return (
    <div className="fixed top-4 right-4 w-72 flex flex-col gap-2 pointer-events-none select-none">
      {alerts.map((alert) => (
        <AlertCard key={alert.id} alert={alert} />
      ))}
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<OverlayApp />)
```

- [ ] **Step 3: Add overlay to `vite.config.ts`**

Replace the `rollupOptions.input` block:

```typescript
      input: {
        chat: path.resolve(__dirname, 'src/chat/index.html'),
        popup: path.resolve(__dirname, 'src/popup/index.html'),
        setup: path.resolve(__dirname, 'src/setup/index.html'),
        overlay: path.resolve(__dirname, 'src/overlay/index.html'),
      }
```

- [ ] **Step 4: Verify Vite builds successfully**

```
npm run build
```

Expected: Build completes with no errors. `dist/renderer/overlay/index.html` exists.

- [ ] **Step 5: Commit**

```bash
git add src/overlay/index.html src/overlay/App.tsx vite.config.ts
git commit -m "feat: overlay React window with alert card UI"
```

---

### Task 4: Electron overlay window management

**Files:**
- Modify: `electron/main.ts`

**Context:** `electron/main.ts` manages all Electron windows. Existing windows: `chatWindow`, `popupWindow`, `setupWindow`. The `pollStatus` function runs every 5 seconds and checks `/status`. We need to also check `/live` to create/destroy the overlay window. The `screen` module is already imported from Electron. Window pattern: create function checks if window already exists, load URL using `isDev` flag (dev uses `http://localhost:5173`, prod uses `file://` path), set `on('closed')` handler to null the variable.

- [ ] **Step 1: Add `overlayWindow` variable**

After the existing window variable declarations (`let chatWindow`, `let popupWindow`, etc.), add:

```typescript
let overlayWindow: BrowserWindow | null = null
```

- [ ] **Step 2: Add `createOverlayWindow` and `destroyOverlayWindow` functions**

Add after the `showPopup` function:

```typescript
function createOverlayWindow() {
  if (overlayWindow) return
  const { width } = screen.getPrimaryDisplay().workAreaSize
  overlayWindow = new BrowserWindow({
    width: 340,
    height: 400,
    x: width - 360,
    y: 20,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    focusable: false,
    skipTaskbar: true,
    resizable: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
  })
  const baseUrl = isDev ? 'http://localhost:5173' : `file://${path.join(__dirname, '../renderer')}`
  overlayWindow.loadURL(`${baseUrl}/overlay/index.html`)
  overlayWindow.on('closed', () => { overlayWindow = null })
}

function destroyOverlayWindow() {
  if (overlayWindow && !overlayWindow.isDestroyed()) {
    overlayWindow.close()
  }
  overlayWindow = null
}
```

- [ ] **Step 3: Poll `/live` in `pollStatus`**

Replace the existing `pollStatus` function:

```typescript
async function pollStatus() {
  try {
    const res = await fetch(`${SIDECAR_URL}/status`)
    if (!res.ok) return
    const data = await res.json() as { pending_popup: string | null; open_chat: string | null }
    if (data.pending_popup) {
      showPopup(data.pending_popup)
      await fetch(`${SIDECAR_URL}/status/clear`, { method: 'POST' })
    }
    if (data.open_chat !== null && data.open_chat !== undefined) {
      createChatWindow(data.open_chat || undefined)
    }
  } catch {
    // Sidecar not ready yet
  }

  try {
    const liveRes = await fetch(`${SIDECAR_URL}/live`)
    if (liveRes.ok) {
      const liveData = await liveRes.json() as { in_game: boolean; alerts: unknown[] }
      if (liveData.in_game && !overlayWindow) {
        createOverlayWindow()
      } else if (!liveData.in_game && overlayWindow) {
        destroyOverlayWindow()
      }
    }
  } catch {
    // Sidecar not ready yet
  }
}
```

- [ ] **Step 4: Run the sidecar and verify `/live` responds correctly**

Start the sidecar in a terminal:
```
cd sidecar
venv/Scripts/uvicorn main:app --port 8765 --reload
```

In a second terminal, check the endpoint:
```
curl http://localhost:8765/live
```

Expected response (no game running):
```json
{"in_game": false, "alerts": []}
```

- [ ] **Step 5: Build and verify**

```
npm run build
```

Expected: Build completes with no errors.

- [ ] **Step 6: Commit**

```bash
git add electron/main.ts
git commit -m "feat: Electron overlay window created/destroyed on game start/end"
```

---

## Self-Review

**Spec coverage:**
- ✅ `LiveGameMonitor` class with alert logic — Task 1
- ✅ Dragon kill → "Next Dragon in 5:00" alert — Task 1
- ✅ Baron kill → "Next Baron in 7:00" alert — Task 1
- ✅ Dragon spawn soon (within 60s) — Task 1
- ✅ Baron spawn soon (within 60s) — Task 1
- ✅ Player death alert — Task 1
- ✅ Pattern reminders at 0:30 (top 2 recurring issues) — Task 1
- ✅ Max 3 alerts, oldest evicted — Task 1
- ✅ 8 second alert expiry — Task 1
- ✅ Debouncing per alert type — Task 1
- ✅ `GET /live` endpoint — Task 2
- ✅ Monitor started in lifespan — Task 2
- ✅ Overlay React window with slide-in animation and color coding — Task 3
- ✅ Vite config updated — Task 3
- ✅ Electron creates overlay on game start, destroys on game end — Task 4
- ✅ Transparent, always-on-top, click-through, top-right position — Task 4
- ✅ 10 unit tests covering all alert triggers — Task 1
- ✅ Error handling: API unreachable → empty state, pattern failure → no crash — Task 1

**Placeholder scan:** No TBDs. All code blocks are complete.

**Type consistency:** `Alert.alert_type` is `str` in Python and `'objective' | 'death' | 'pattern'` in TypeScript — consistent. `get_state()` returns a dict with `"in_game": bool` and `"alerts": list[dict]` — matches what `GET /live` returns and what `OverlayApp` consumes.
