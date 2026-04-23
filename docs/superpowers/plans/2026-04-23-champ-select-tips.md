# Champ Select Tips Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a transparent always-on-top overlay window during champ select with the player's win rate, patterns, and coaching tips for the champion they just locked in.

**Architecture:** A new `LcuClient` reads the League lockfile and fetches champ select session data. A new `ChampSelectMonitor` polls it every 2 seconds, detects champion lock-in, and builds champion-specific stats + patterns from the DB. A new `GET /champ-select` endpoint exposes this state. A new Electron window (`src/champ-select/`) polls the endpoint and renders the tips overlay. The Electron main process creates/destroys this window based on the `in_champ_select` flag.

**Tech Stack:** Python 3.11+, httpx, FastAPI, SQLAlchemy, React 18, TypeScript, Tailwind CSS, Electron

---

## File Structure

- **Create:** `sidecar/lcu_client.py` — lockfile discovery, LCU auth, `get_champ_select_session()`, `get_champion_name()`
- **Create:** `sidecar/tests/test_lcu_client.py` — 3 unit tests for lockfile parsing and session fetch
- **Create:** `sidecar/champ_select_monitor.py` — `ChampSelectMonitor`: polls LCU, detects lock-in, builds champ data
- **Create:** `sidecar/tests/test_champ_select_monitor.py` — 8 unit tests
- **Modify:** `sidecar/main.py` — import + instantiate `LcuClient` + `ChampSelectMonitor`, wire into lifespan, add `GET /champ-select`
- **Create:** `src/champ-select/index.html` — Electron window entry (matches overlay pattern)
- **Create:** `src/champ-select/App.tsx` — React component polling `/champ-select`, renders tips
- **Modify:** `vite.config.ts` — add `champ-select` build entry
- **Modify:** `electron/main.ts` — add `champSelectWindow`, `createChampSelectWindow`, `destroyChampSelectWindow`, poll `/champ-select` in `pollStatus`

---

### Task 1: `LcuClient` — lockfile discovery + LCU API

**Files:**
- Create: `sidecar/lcu_client.py`
- Create: `sidecar/tests/test_lcu_client.py`

- [ ] **Step 1: Write 3 failing tests**

Create `sidecar/tests/test_lcu_client.py`:

```python
import pytest
from unittest.mock import patch
from lcu_client import LcuClient


def test_read_lockfile_parses_port_and_password(tmp_path):
    lockfile = tmp_path / "lockfile"
    lockfile.write_text("LeagueClient:12345:54321:mysecretpassword:https")
    with patch("lcu_client.LOCKFILE_PATHS", [str(lockfile)]):
        client = LcuClient()
        result = client._read_lockfile()
    assert result == (54321, "mysecretpassword")


def test_read_lockfile_returns_none_when_missing():
    with patch("lcu_client.LOCKFILE_PATHS", ["/nonexistent/path1", "/nonexistent/path2"]):
        client = LcuClient()
        assert client._read_lockfile() is None


async def test_get_champ_select_session_returns_none_when_no_lockfile():
    with patch("lcu_client.LOCKFILE_PATHS", ["/nonexistent/path"]):
        client = LcuClient()
        result = await client.get_champ_select_session()
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar
venv/Scripts/pytest tests/test_lcu_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'lcu_client'`

- [ ] **Step 3: Create `sidecar/lcu_client.py`**

```python
from pathlib import Path
from typing import Optional

import httpx

LOCKFILE_PATHS = [
    r"C:\Riot Games\League of Legends\lockfile",
    r"C:\Program Files\Riot Games\League of Legends\lockfile",
]


class LcuClient:
    def __init__(self) -> None:
        self._champion_cache: dict[int, str] = {}

    def _read_lockfile(self) -> Optional[tuple[int, str]]:
        """Returns (port, password) or None if lockfile not found."""
        for path_str in LOCKFILE_PATHS:
            try:
                text = Path(path_str).read_text()
                parts = text.strip().split(":")
                if len(parts) >= 5:
                    return int(parts[2]), parts[3]
            except (FileNotFoundError, PermissionError, ValueError):
                continue
        return None

    async def get_champ_select_session(self) -> Optional[dict]:
        creds = self._read_lockfile()
        if not creds:
            return None
        port, password = creds
        async with httpx.AsyncClient(verify=False, timeout=2.0) as client:
            try:
                resp = await client.get(
                    f"https://127.0.0.1:{port}/lol-champ-select/v1/session",
                    auth=("riot", password),
                )
                if resp.status_code != 200:
                    return None
                return resp.json()
            except Exception:
                return None

    async def get_champion_name(self, champion_id: int) -> Optional[str]:
        if champion_id <= 0:
            return None
        if champion_id in self._champion_cache:
            return self._champion_cache[champion_id]
        creds = self._read_lockfile()
        if not creds:
            return None
        port, password = creds
        async with httpx.AsyncClient(verify=False, timeout=5.0) as client:
            try:
                resp = await client.get(
                    f"https://127.0.0.1:{port}/lol-game-data/assets/v1/champion-summary.json",
                    auth=("riot", password),
                )
                if resp.status_code != 200:
                    return None
                for champ in resp.json():
                    cid = champ.get("id", -1)
                    if cid > 0:
                        self._champion_cache[cid] = champ["name"]
                return self._champion_cache.get(champion_id)
            except Exception:
                return None
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd sidecar
venv/Scripts/pytest tests/test_lcu_client.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add sidecar/lcu_client.py sidecar/tests/test_lcu_client.py
git commit -m "feat: LcuClient — lockfile discovery and LCU session/champion-name fetching"
```

---

### Task 2: `ChampSelectMonitor` — lock-in detection + champion data

**Files:**
- Create: `sidecar/champ_select_monitor.py`
- Create: `sidecar/tests/test_champ_select_monitor.py`

- [ ] **Step 1: Write 8 failing tests**

Create `sidecar/tests/test_champ_select_monitor.py`:

```python
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from database import save_match, save_pivotal_moments
from champ_select_monitor import ChampSelectMonitor
from lcu_client import LcuClient


def make_session(cell_id: int, champion_id: int, completed: bool) -> dict:
    return {
        "localPlayerCellId": cell_id,
        "myTeam": [{"cellId": cell_id, "championId": champion_id}],
        "actions": [[{
            "type": "pick",
            "actorCellId": cell_id,
            "completed": completed,
        }]],
    }


@pytest.fixture
def lcu():
    mock = MagicMock(spec=LcuClient)
    mock.get_champ_select_session = AsyncMock(return_value=None)
    mock.get_champion_name = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def monitor(db, lcu):
    return ChampSelectMonitor(db, lcu)


def test_no_state_when_not_in_champ_select(monitor):
    state = monitor.get_state()
    assert state["in_champ_select"] is False
    assert state["locked_champion"] is None
    assert state["champ_data"] is None


def test_lock_in_detected(monitor):
    session = make_session(cell_id=0, champion_id=104, completed=True)
    monitor._process_session(session, "Graves")
    assert monitor._in_champ_select is True
    assert monitor._locked_champion == "Graves"
    assert monitor._champ_data is not None


def test_no_lock_without_completed_action(monitor):
    session = make_session(cell_id=0, champion_id=104, completed=False)
    monitor._process_session(session, "Graves")
    assert monitor._in_champ_select is True
    assert monitor._locked_champion is None


def test_champ_data_with_history(db, lcu):
    monitor = ChampSelectMonitor(db, lcu)
    for i in range(4):
        save_match(db, {
            "match_id": f"win_{i}", "played_at": datetime(2026, 1, i + 1, 12, 0),
            "champion": "Graves", "role": "JUNGLE", "result": "win",
            "duration_secs": 1800, "kda": "5/2/8", "cs": 150,
            "gold_earned": 12000, "vision_score": 20, "raw_timeline": {},
        })
        save_pivotal_moments(db, f"win_{i}", [
            {"timestamp_secs": 300, "moment_type": "solo_kill",
             "description": "", "counterfactual": "", "gold_impact": 0},
        ])
    for i in range(3):
        save_match(db, {
            "match_id": f"loss_{i}", "played_at": datetime(2026, 1, i + 5, 12, 0),
            "champion": "Graves", "role": "JUNGLE", "result": "loss",
            "duration_secs": 1800, "kda": "2/5/3", "cs": 100,
            "gold_earned": 9000, "vision_score": 15, "raw_timeline": {},
        })
        save_pivotal_moments(db, f"loss_{i}", [
            {"timestamp_secs": 300, "moment_type": "lane_death",
             "description": "", "counterfactual": "", "gold_impact": 0},
        ])
    data = monitor._build_champ_data("Graves")
    assert data["games"] == 7
    assert data["wins"] == 4
    assert data["win_rate"] == 0.57
    assert data["no_history"] is False
    assert len(data["patterns"]) > 0


def test_champ_data_no_history(monitor):
    data = monitor._build_champ_data("NewChamp")
    assert data["games"] == 0
    assert data["no_history"] is True
    assert data["patterns"] == []


def test_pattern_top_2_issues(db, lcu):
    monitor = ChampSelectMonitor(db, lcu)
    for i in range(5):
        save_match(db, {
            "match_id": f"m_{i}", "played_at": datetime(2026, 1, i + 1, 12, 0),
            "champion": "Jinx", "role": "BOTTOM", "result": "loss",
            "duration_secs": 1800, "kda": "2/5/3", "cs": 100,
            "gold_earned": 9000, "vision_score": 15, "raw_timeline": {},
        })
        save_pivotal_moments(db, f"m_{i}", [
            {"timestamp_secs": 300, "moment_type": "lane_death",
             "description": "", "counterfactual": "", "gold_impact": 0},
            {"timestamp_secs": 600, "moment_type": "objective_missed",
             "description": "", "counterfactual": "", "gold_impact": 0},
            {"timestamp_secs": 900, "moment_type": "tower_lost",
             "description": "", "counterfactual": "", "gold_impact": 0},
        ])
    data = monitor._build_champ_data("Jinx")
    issues = [p for p in data["patterns"] if p["label"] == "recurring_issue"]
    assert len(issues) == 2


def test_win_condition_extracted(db, lcu):
    monitor = ChampSelectMonitor(db, lcu)
    for i in range(3):
        save_match(db, {
            "match_id": f"win_{i}", "played_at": datetime(2026, 1, i + 1, 12, 0),
            "champion": "Jinx", "role": "BOTTOM", "result": "win",
            "duration_secs": 1800, "kda": "5/2/8", "cs": 150,
            "gold_earned": 12000, "vision_score": 20, "raw_timeline": {},
        })
        save_pivotal_moments(db, f"win_{i}", [
            {"timestamp_secs": 300, "moment_type": "solo_kill",
             "description": "", "counterfactual": "", "gold_impact": 0},
        ])
    data = monitor._build_champ_data("Jinx")
    win_conds = [p for p in data["patterns"] if p["label"] == "win_condition"]
    assert len(win_conds) == 1
    assert win_conds[0]["moment_type"] == "solo_kill"


async def test_session_exit_resets_state(monitor, lcu):
    monitor._in_champ_select = True
    monitor._locked_champion = "Graves"
    monitor._champ_data = {"games": 7}
    lcu.get_champ_select_session.return_value = None
    await monitor._tick()
    assert monitor._in_champ_select is False
    assert monitor._locked_champion is None
    assert monitor._champ_data is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar
venv/Scripts/pytest tests/test_champ_select_monitor.py -v
```

Expected: `ModuleNotFoundError: No module named 'champ_select_monitor'`

- [ ] **Step 3: Create `sidecar/champ_select_monitor.py`**

```python
import asyncio
from collections import Counter
from typing import Optional

from sqlalchemy.orm import Session

from database import get_matches, get_pivotal_moments
from lcu_client import LcuClient

MOMENT_LABELS: dict[str, str] = {
    "lane_death": "Lane Deaths",
    "cs_differential": "CS Deficit",
    "gold_differential": "Gold Deficit",
    "turret_plates_lost": "Plates Lost",
    "split_push_death": "Split Push Deaths",
    "enemy_roam_kill": "Enemy Roams",
    "low_vision": "Low Vision",
    "objective_missed": "Missed Objectives",
    "tower_lost": "Towers Lost",
    "death": "Deaths",
    "solo_kill": "Solo Kills",
    "objective_secured": "Objectives Secured",
    "gank_assist": "Gank Assists",
    "baron_secured": "Baron Secured",
    "dragon_stack": "Dragon Stacks",
    "roam_kill": "Roam Kills",
    "roam_assist": "Roam Assists",
    "ward_kill": "Vision Control",
    "bad_back_objective": "Bad Backs (Objective)",
    "bad_back_gold": "Bad Backs (Low Gold)",
}

POSITIVE_TYPES = {
    "solo_kill", "objective_secured", "gank_assist", "baron_secured",
    "dragon_stack", "roam_kill", "roam_assist", "ward_kill",
}


class ChampSelectMonitor:
    def __init__(self, db: Session, lcu: LcuClient) -> None:
        self._db = db
        self._lcu = lcu
        self._in_champ_select = False
        self._locked_champion: Optional[str] = None
        self._champ_data: Optional[dict] = None
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    def get_state(self) -> dict:
        return {
            "in_champ_select": self._in_champ_select,
            "locked_champion": self._locked_champion,
            "champ_data": self._champ_data,
        }

    def _process_session(self, session: dict, champion_name: Optional[str]) -> None:
        local_cell = session.get("localPlayerCellId", -1)
        my_team = session.get("myTeam", [])
        player_entry = next((p for p in my_team if p.get("cellId") == local_cell), None)
        if not player_entry:
            self._in_champ_select = True
            return

        champion_id = player_entry.get("championId", 0)
        if champion_id == 0:
            self._in_champ_select = True
            return

        actions_flat = [a for row in session.get("actions", []) for a in row]
        locked = any(
            a.get("type") == "pick"
            and a.get("actorCellId") == local_cell
            and a.get("completed") is True
            for a in actions_flat
        )

        if locked and champion_name and self._locked_champion != champion_name:
            self._in_champ_select = True
            self._locked_champion = champion_name
            try:
                self._champ_data = self._build_champ_data(champion_name)
            except Exception:
                self._champ_data = None
        elif not locked:
            self._in_champ_select = True

    def _build_champ_data(self, champion: str) -> dict:
        matches = get_matches(self._db, champion=champion, last_n=20)
        if not matches:
            return {"games": 0, "wins": 0, "win_rate": 0.0, "no_history": True, "patterns": []}

        games = len(matches)
        wins = sum(1 for m in matches if m.result == "win")
        win_rate = round(wins / games, 2)

        match_ids = [m.match_id for m in matches]
        moments = get_pivotal_moments(self._db, match_ids)

        negative_counts = Counter(
            m.moment_type for m in moments if m.moment_type not in POSITIVE_TYPES
        )
        positive_counts = Counter(
            m.moment_type for m in moments if m.moment_type in POSITIVE_TYPES
        )

        patterns = []
        for moment_type, count in negative_counts.most_common(2):
            label = MOMENT_LABELS.get(moment_type, moment_type.replace("_", " ").title())
            patterns.append({
                "label": "recurring_issue",
                "moment_type": moment_type,
                "summary": f"{label} in {count}/{games} games",
            })
        for moment_type, _count in positive_counts.most_common(1):
            label = MOMENT_LABELS.get(moment_type, moment_type.replace("_", " ").title())
            patterns.append({
                "label": "win_condition",
                "moment_type": moment_type,
                "summary": f"{label} in your wins",
            })

        return {"games": games, "wins": wins, "win_rate": win_rate, "no_history": False, "patterns": patterns}

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception:
                pass
            await asyncio.sleep(2)

    async def _tick(self) -> None:
        session = await self._lcu.get_champ_select_session()
        if session is None:
            if self._in_champ_select:
                self._in_champ_select = False
                self._locked_champion = None
                self._champ_data = None
            return

        if self._locked_champion is None:
            local_cell = session.get("localPlayerCellId", -1)
            my_team = session.get("myTeam", [])
            player_entry = next((p for p in my_team if p.get("cellId") == local_cell), None)
            champion_id = player_entry.get("championId", 0) if player_entry else 0
            champion_name: Optional[str] = None
            if champion_id > 0:
                champion_name = await self._lcu.get_champion_name(champion_id) or "Unknown"
        else:
            champion_name = self._locked_champion

        self._process_session(session, champion_name)
```

- [ ] **Step 4: Run 8 tests**

```
cd sidecar
venv/Scripts/pytest tests/test_champ_select_monitor.py -v
```

Expected: 8 passed

- [ ] **Step 5: Run full suite to verify no regressions**

```
cd sidecar
venv/Scripts/pytest tests/ -v
```

Expected: all tests pass (existing + 11 new)

- [ ] **Step 6: Commit**

```bash
git add sidecar/champ_select_monitor.py sidecar/tests/test_champ_select_monitor.py
git commit -m "feat: ChampSelectMonitor — lock-in detection and champion pattern data"
```

---

### Task 3: `GET /champ-select` endpoint

**Files:**
- Modify: `sidecar/main.py`

- [ ] **Step 1: Add imports and global instances**

In `sidecar/main.py`, add after the `from live_game_monitor import LiveGameMonitor` import:

```python
from champ_select_monitor import ChampSelectMonitor
from lcu_client import LcuClient
```

Add after the `live_monitor = LiveGameMonitor(db)` line:

```python
lcu = LcuClient()
champ_select_monitor = ChampSelectMonitor(db, lcu)
```

- [ ] **Step 2: Wire monitor into lifespan**

Replace the existing `lifespan` function:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _watcher_task
    _watcher_task = asyncio.create_task(game_end_watcher())
    asyncio.create_task(backfill_history())
    live_monitor.start()
    champ_select_monitor.start()
    yield
    if _watcher_task:
        _watcher_task.cancel()
    monitor_task = live_monitor._task
    live_monitor.stop()
    if monitor_task:
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
    cs_task = champ_select_monitor._task
    champ_select_monitor.stop()
    if cs_task:
        try:
            await cs_task
        except asyncio.CancelledError:
            pass
    await riot.close()
    db.close()
```

- [ ] **Step 3: Add `GET /champ-select` endpoint**

Add after the `GET /live` route:

```python
@app.get("/champ-select")
def get_champ_select():
    return champ_select_monitor.get_state()
```

- [ ] **Step 4: Run full test suite**

```
cd sidecar
venv/Scripts/pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Verify endpoint manually**

Start the sidecar:
```
cd sidecar
venv/Scripts/uvicorn main:app --port 8765
```

In a second terminal:
```
curl http://localhost:8765/champ-select
```

Expected (no League running):
```json
{"in_champ_select": false, "locked_champion": null, "champ_data": null}
```

- [ ] **Step 6: Commit**

```bash
git add sidecar/main.py
git commit -m "feat: GET /champ-select endpoint with ChampSelectMonitor wired into sidecar"
```

---

### Task 4: Champ select React window + Vite config

**Files:**
- Create: `src/champ-select/index.html`
- Create: `src/champ-select/App.tsx`
- Modify: `vite.config.ts`

- [ ] **Step 1: Create `src/champ-select/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Climb Champ Select</title></head>
<body style="margin:0;background:transparent;">
  <div id="root"></div>
  <script type="module" src="./App.tsx"></script>
</body>
</html>
```

- [ ] **Step 2: Create `src/champ-select/App.tsx`**

```tsx
import { useState, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import '../index.css'

declare global {
  interface Window { sidecar: { port: string } }
}

interface Pattern {
  label: 'recurring_issue' | 'win_condition'
  moment_type: string
  summary: string
}

interface ChampData {
  games: number
  wins: number
  win_rate: number
  no_history: boolean
  patterns: Pattern[]
}

interface ChampSelectState {
  in_champ_select: boolean
  locked_champion: string | null
  champ_data: ChampData | null
}

function PatternRow({ pattern }: { pattern: Pattern }) {
  const isIssue = pattern.label === 'recurring_issue'
  return (
    <div className={`border-l-2 rounded px-3 py-1.5 text-xs ${
      isIssue
        ? 'border-red-500 bg-red-950/80 text-red-200'
        : 'border-green-500 bg-green-950/80 text-green-200'
    }`}>
      <span className="mr-1">{isIssue ? '⚠' : '✓'}</span>
      {pattern.summary}
    </div>
  )
}

function ChampSelectApp() {
  const [state, setState] = useState<ChampSelectState | null>(null)
  const port = window.sidecar?.port ?? '8765'

  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch(`http://localhost:${port}/champ-select`)
        if (!res.ok) return
        const data = await res.json() as ChampSelectState
        setState(data)
      } catch { /* sidecar not ready */ }
    }
    poll()
    const interval = setInterval(poll, 2000)
    return () => clearInterval(interval)
  }, [port])

  if (!state?.in_champ_select || !state.locked_champion) return null

  const { locked_champion, champ_data } = state

  return (
    <div className="fixed top-4 right-4 w-72 pointer-events-none select-none">
      <div className="bg-[#0d0d1f]/90 border border-indigo-900 rounded-xl shadow-2xl overflow-hidden">
        <div className="px-3 py-2 flex items-center gap-2 border-b border-white/10">
          <div className="w-7 h-7 rounded-full bg-purple-700 flex items-center justify-center text-white text-xs font-bold shrink-0">
            {locked_champion[0]}
          </div>
          <div className="flex-1 min-w-0">
            <span className="text-white text-sm font-semibold">{locked_champion}</span>
            {champ_data && !champ_data.no_history && (
              <span className="text-gray-400 text-xs ml-2">
                {champ_data.games} games · {Math.round(champ_data.win_rate * 100)}% WR
              </span>
            )}
          </div>
        </div>
        <div className="px-3 py-2 flex flex-col gap-1.5">
          {!champ_data || champ_data.no_history ? (
            <p className="text-gray-500 text-xs">No history yet for {locked_champion} — good luck!</p>
          ) : champ_data.patterns.length === 0 ? (
            <p className="text-gray-500 text-xs">No strong patterns found yet.</p>
          ) : (
            champ_data.patterns.map((p) => (
              <PatternRow key={p.moment_type} pattern={p} />
            ))
          )}
        </div>
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<ChampSelectApp />)
```

- [ ] **Step 3: Add champ-select entry to `vite.config.ts`**

Replace the `rollupOptions.input` block:

```typescript
      input: {
        chat: path.resolve(__dirname, 'src/chat/index.html'),
        popup: path.resolve(__dirname, 'src/popup/index.html'),
        setup: path.resolve(__dirname, 'src/setup/index.html'),
        overlay: path.resolve(__dirname, 'src/overlay/index.html'),
        'champ-select': path.resolve(__dirname, 'src/champ-select/index.html'),
      }
```

- [ ] **Step 4: Verify build succeeds**

```
npm run build
```

Expected: Build completes with no errors. `dist/renderer/champ-select/index.html` exists.

- [ ] **Step 5: Commit**

```bash
git add src/champ-select/index.html src/champ-select/App.tsx vite.config.ts
git commit -m "feat: champ select React window with stats header and pattern bullets"
```

---

### Task 5: Electron champ select window management

**Files:**
- Modify: `electron/main.ts`

- [ ] **Step 1: Add `champSelectWindow` variable and `_wasInChampSelect` flag**

After the `let overlayWindow: BrowserWindow | null = null` line, add:

```typescript
let champSelectWindow: BrowserWindow | null = null
let _wasInChampSelect = false
```

- [ ] **Step 2: Add `createChampSelectWindow` and `destroyChampSelectWindow`**

Add after the `destroyOverlayWindow` function:

```typescript
function createChampSelectWindow() {
  if (champSelectWindow) return
  const { width } = screen.getPrimaryDisplay().workAreaSize
  champSelectWindow = new BrowserWindow({
    width: 320,
    height: 260,
    x: width - 340,
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
  champSelectWindow.setAlwaysOnTop(true, 'screen-saver')
  const url = isDev
    ? 'http://localhost:5173/champ-select/index.html'
    : `file://${path.join(__dirname, '../renderer/champ-select/index.html')}`
  champSelectWindow.loadURL(url)
  champSelectWindow.on('closed', () => { champSelectWindow = null })
}

function destroyChampSelectWindow() {
  if (champSelectWindow && !champSelectWindow.isDestroyed()) {
    champSelectWindow.close()
  }
  champSelectWindow = null
}
```

- [ ] **Step 3: Poll `/champ-select` in `pollStatus`**

Replace the existing `pollStatus` function:

```typescript
async function pollStatus() {
  try {
    const statusRes = await fetch(`${SIDECAR_URL}/status`)
    if (statusRes.ok) {
      const data = await statusRes.json() as { pending_popup: string | null; open_chat: string | null }
      if (data.pending_popup) {
        showPopup(data.pending_popup)
        await fetch(`${SIDECAR_URL}/status/clear`, { method: 'POST' })
      }
      if (data.open_chat !== null && data.open_chat !== undefined) {
        createChatWindow(data.open_chat || undefined)
      }
    }
  } catch { /* sidecar not ready */ }

  try {
    const liveRes = await fetch(`${SIDECAR_URL}/live`)
    if (liveRes.ok) {
      const liveData = await liveRes.json() as { in_game: boolean }
      if (typeof liveData.in_game === 'boolean') {
        if (liveData.in_game && !_wasInGame) {
          createOverlayWindow()
        } else if (!liveData.in_game && _wasInGame) {
          destroyOverlayWindow()
        }
        _wasInGame = liveData.in_game
      }
    }
  } catch { /* sidecar not ready */ }

  try {
    const csRes = await fetch(`${SIDECAR_URL}/champ-select`)
    if (csRes.ok) {
      const csData = await csRes.json() as { in_champ_select: boolean }
      if (typeof csData.in_champ_select === 'boolean') {
        if (csData.in_champ_select && !_wasInChampSelect) {
          createChampSelectWindow()
        } else if (!csData.in_champ_select && _wasInChampSelect) {
          destroyChampSelectWindow()
        }
        _wasInChampSelect = csData.in_champ_select
      }
    }
  } catch { /* sidecar not ready */ }
}
```

- [ ] **Step 4: Clean up on quit**

Replace the existing `app.on('before-quit', ...)` handler:

```typescript
app.on('before-quit', () => {
  if (statusPollInterval) clearInterval(statusPollInterval)
  _wasInGame = false
  _wasInChampSelect = false
  destroyOverlayWindow()
  destroyChampSelectWindow()
  stopSidecar()
})
```

- [ ] **Step 5: Verify TypeScript build**

```
npm run build
```

Expected: Build completes with no errors.

- [ ] **Step 6: Run full sidecar test suite one more time**

```
cd sidecar
venv/Scripts/pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add electron/main.ts
git commit -m "feat: Electron champ select window — created on lock-in, destroyed on game start"
```
