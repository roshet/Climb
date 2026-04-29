# Session Focus Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pre-game focus card to the champ select overlay showing the player's top recurring mistake, how often it happens, and its average gold cost.

**Architecture:** One backend change extends `_build_champ_data()` in `champ_select_monitor.py` to compute a `focus` field using already-fetched moments; champion-specific when 3+ games, cross-champion fallback otherwise. One frontend change adds a `FocusCard` component to `src/champ-select/App.tsx` rendered above the pattern list when `focus` is present.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, React 18, TypeScript, Tailwind CSS

---

## File Structure

| File | Change |
|---|---|
| `sidecar/champ_select_monitor.py` | Add `_compute_focus()` helper; extend `_build_champ_data()` to attach `focus` field |
| `sidecar/tests/test_champ_select_focus.py` | New — 3 tests covering champion-specific, cross-champion fallback, and null cases |
| `src/champ-select/App.tsx` | Add `Focus` interface, update `ChampData`, add `FocusCard` component, render it |

---

### Task 1: Compute focus field in `_build_champ_data()`

**Files:**
- Create: `sidecar/tests/test_champ_select_focus.py`
- Modify: `sidecar/champ_select_monitor.py`

- [ ] **Step 1: Write 3 failing tests**

Create `sidecar/tests/test_champ_select_focus.py`:

```python
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock
from database import save_match, save_pivotal_moments
from champ_select_monitor import ChampSelectMonitor
from lcu_client import LcuClient


def make_match(db, match_id, champion, result, day):
    save_match(db, {
        "match_id": match_id,
        "played_at": datetime(2026, 1, day, 12, 0),
        "champion": champion,
        "role": "JUNGLE",
        "result": result,
        "duration_secs": 1800,
        "kda": "3/5/2",
        "cs": 100,
        "gold_earned": 9000,
        "vision_score": 15,
        "raw_timeline": {},
    })


@pytest.fixture
def lcu():
    mock = MagicMock(spec=LcuClient)
    mock.get_champ_select_session = AsyncMock(return_value=None)
    mock.get_champion_name = AsyncMock(return_value=None)
    return mock


def test_focus_champion_specific(db, lcu):
    monitor = ChampSelectMonitor(db, lcu)
    # 5 games on Graves, lane_death in 4 games with -680g each
    for i in range(5):
        make_match(db, f"m_{i}", "Graves", "loss", i + 1)
        moments = []
        if i < 4:
            moments.append({
                "timestamp_secs": 300, "moment_type": "lane_death",
                "description": "", "counterfactual": "", "gold_impact": -680,
            })
        save_pivotal_moments(db, f"m_{i}", moments)

    data = monitor._build_champ_data("Graves")
    focus = data["focus"]
    assert focus is not None
    assert focus["moment_type"] == "lane_death"
    assert focus["games_seen"] == 4
    assert focus["total_games"] == 5
    assert focus["avg_gold_lost"] == 680
    assert focus["champion_specific"] is True


def test_focus_cross_champion_fallback(db, lcu):
    monitor = ChampSelectMonitor(db, lcu)
    # 2 Graves games — below the 3-game threshold
    for i in range(2):
        make_match(db, f"graves_{i}", "Graves", "loss", i + 1)
        save_pivotal_moments(db, f"graves_{i}", [{
            "timestamp_secs": 300, "moment_type": "lane_death",
            "description": "", "counterfactual": "", "gold_impact": -500,
        }])
    # 5 Jinx games with objective_missed (more games than lane_death)
    for i in range(5):
        make_match(db, f"jinx_{i}", "Jinx", "loss", i + 3)
        save_pivotal_moments(db, f"jinx_{i}", [{
            "timestamp_secs": 600, "moment_type": "objective_missed",
            "description": "", "counterfactual": "", "gold_impact": -900,
        }])

    data = monitor._build_champ_data("Graves")
    focus = data["focus"]
    assert focus is not None
    assert focus["champion_specific"] is False
    assert focus["total_games"] == 7  # 2 Graves + 5 Jinx
    assert focus["moment_type"] == "objective_missed"  # 5 games > 2 games


def test_focus_null_when_no_negatives(db, lcu):
    monitor = ChampSelectMonitor(db, lcu)
    # 5 games with only positive moments
    for i in range(5):
        make_match(db, f"m_{i}", "Graves", "win", i + 1)
        save_pivotal_moments(db, f"m_{i}", [{
            "timestamp_secs": 300, "moment_type": "solo_kill",
            "description": "", "counterfactual": "", "gold_impact": 300,
        }])

    data = monitor._build_champ_data("Graves")
    assert data["focus"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar && venv/Scripts/pytest tests/test_champ_select_focus.py -v
```

Expected: 3 failures — `KeyError: 'focus'` or `AssertionError` since `_build_champ_data` doesn't return `focus` yet.

- [ ] **Step 3: Add `_compute_focus()` and update `_build_champ_data()` in `sidecar/champ_select_monitor.py`**

Add `_compute_focus` as a new method of `ChampSelectMonitor`, and replace `_build_champ_data` entirely. The full updated file for both methods (place `_compute_focus` before `_build_champ_data`):

```python
def _compute_focus(self, moments: list, total_games: int, champion_specific: bool) -> dict | None:
    negative_moments = [m for m in moments if m.moment_type not in POSITIVE_TYPES]
    if not negative_moments:
        return None
    games_by_type: dict[str, set] = {}
    for m in negative_moments:
        games_by_type.setdefault(m.moment_type, set()).add(m.match_id)
    top_type = max(games_by_type, key=lambda t: len(games_by_type[t]))
    games_seen = len(games_by_type[top_type])
    type_moments = [m for m in negative_moments if m.moment_type == top_type]
    total_gold = sum(abs(m.gold_impact) for m in type_moments if m.gold_impact < 0)
    avg_gold_lost = total_gold // games_seen if games_seen > 0 else 0
    label = MOMENT_LABELS.get(top_type, top_type.replace("_", " ").title())
    return {
        "moment_type": top_type,
        "label": label,
        "games_seen": games_seen,
        "total_games": total_games,
        "avg_gold_lost": avg_gold_lost,
        "champion_specific": champion_specific,
    }

def _build_champ_data(self, champion: str) -> dict:
    matches = get_matches(self._db, champion=champion, last_n=20)
    if not matches:
        return {"games": 0, "wins": 0, "win_rate": 0.0, "no_history": True, "patterns": [], "focus": None}

    games = len(matches)
    wins = sum(1 for m in matches if m.result == "win")
    win_rate = round(wins / games, 2)

    match_ids = [m.match_id for m in matches]
    moments = get_pivotal_moments(self._db, match_ids)

    negative_counts = Counter(
        m.moment_type for m in moments if m.moment_type not in POSITIVE_TYPES
    )
    win_ids = {m.match_id for m in matches if m.result == "win"}
    positive_counts = Counter(
        m.moment_type for m in moments
        if m.moment_type in POSITIVE_TYPES and m.match_id in win_ids
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

    if games >= 3:
        focus = self._compute_focus(moments, games, champion_specific=True)
    else:
        all_matches = get_matches(self._db, last_n=20)
        if len(all_matches) >= 3:
            all_match_ids = [m.match_id for m in all_matches]
            all_moments = get_pivotal_moments(self._db, all_match_ids)
            focus = self._compute_focus(all_moments, len(all_matches), champion_specific=False)
        else:
            focus = None

    return {
        "games": games,
        "wins": wins,
        "win_rate": win_rate,
        "no_history": False,
        "patterns": patterns,
        "focus": focus,
    }
```

- [ ] **Step 4: Run the 3 new tests**

```
cd sidecar && venv/Scripts/pytest tests/test_champ_select_focus.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Run the full test suite**

```
cd sidecar && venv/Scripts/pytest tests/ -v
```

Expected: all tests pass (183+ passing).

- [ ] **Step 6: Commit**

```bash
git add sidecar/tests/test_champ_select_focus.py sidecar/champ_select_monitor.py
git commit -m "feat: compute focus field in champ select data"
```

---

### Task 2: Render FocusCard in the champ select overlay

**Files:**
- Modify: `src/champ-select/App.tsx`

- [ ] **Step 1: Update the file with `Focus` interface, updated `ChampData`, and `FocusCard` component**

Replace the entire `src/champ-select/App.tsx` with:

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

interface Focus {
  moment_type: string
  label: string
  games_seen: number
  total_games: number
  avg_gold_lost: number
  champion_specific: boolean
}

interface ChampData {
  games: number
  wins: number
  win_rate: number
  no_history: boolean
  patterns: Pattern[]
  focus: Focus | null
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

function FocusCard({ focus, champion }: { focus: Focus; champion: string }) {
  const scope = focus.champion_specific ? champion : 'All Champions'
  return (
    <div className="mx-2 mt-2 bg-[#1e1b4b] border border-indigo-500/60 rounded-lg px-3 py-2">
      <p className="text-indigo-300 text-[7px] font-bold uppercase tracking-widest mb-1">
        ⚡ Today's Focus · {scope}
      </p>
      <p className="text-white text-[11px] font-bold">{focus.label}</p>
      <p className="text-gray-400 text-[8px] mt-0.5">
        {focus.games_seen} of your last {focus.total_games} games
      </p>
      {focus.avg_gold_lost > 0 && (
        <p className="text-red-400 text-[8px] font-semibold mt-1">
          avg −{focus.avg_gold_lost.toLocaleString()}g per game
        </p>
      )}
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
        {champ_data?.focus && (
          <FocusCard focus={champ_data.focus} champion={locked_champion} />
        )}
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

- [ ] **Step 2: Build and verify**

```
npm run build
```

Expected: zero TypeScript errors, build completes.

- [ ] **Step 3: Run full sidecar test suite**

```
cd sidecar && venv/Scripts/pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/champ-select/App.tsx
git commit -m "feat: show session focus card in champ select overlay"
```
