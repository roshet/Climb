# Improvement Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "vs your patterns" section to the post-game popup that shows whether the player improved on or repeated their champion-specific patterns in the game that just ended.

**Architecture:** A new `improvement_tracker.py` module computes per-game pattern comparisons (had_in_game, streak, recent_rate) from existing DB tables. A new `GET /improvement/{match_id}` endpoint exposes it. The existing `src/popup/App.tsx` fetches it in parallel with the analysis and renders a compact comparison section between the stat tiles and moment filter bar.

**Tech Stack:** Python 3.11+, SQLAlchemy, FastAPI, React 18, TypeScript, Tailwind CSS

---

## File Structure

- **Create:** `sidecar/improvement_tracker.py` — `get_improvement_data(db, match_id)` function
- **Create:** `sidecar/tests/test_improvement_tracker.py` — 6 unit tests
- **Modify:** `sidecar/main.py` — add `GET /improvement/{match_id}` route
- **Modify:** `src/popup/App.tsx` — parallel fetch + "vs your patterns" section

---

### Task 1: `get_improvement_data` — improvement computation

**Files:**
- Create: `sidecar/improvement_tracker.py`
- Create: `sidecar/tests/test_improvement_tracker.py`

- [ ] **Step 1: Write 6 failing tests**

Create `sidecar/tests/test_improvement_tracker.py`:

```python
import pytest
from datetime import datetime
from database import save_match, save_pivotal_moments
from improvement_tracker import get_improvement_data


def make_match(db, match_id, champion="Graves", result="loss", day=1, moment_types=None):
    save_match(db, {
        "match_id": match_id,
        "played_at": datetime(2026, 1, day, 12, 0),
        "champion": champion,
        "role": "JUNGLE",
        "result": result,
        "duration_secs": 1800,
        "kda": "2/3/4",
        "cs": 100,
        "gold_earned": 9000,
        "vision_score": 15,
        "raw_timeline": {},
    })
    if moment_types:
        save_pivotal_moments(db, match_id, [
            {"timestamp_secs": 300, "moment_type": mt,
             "description": "", "counterfactual": "", "gold_impact": 0}
            for mt in moment_types
        ])


def test_returns_empty_when_insufficient_history(db):
    for i in range(2):
        make_match(db, f"m{i}", day=i + 1, moment_types=["lane_death"])
    result = get_improvement_data(db, "m1")
    assert result is not None
    assert result["patterns"] == []


def test_had_in_game_true_when_moment_present(db):
    for i in range(5):
        make_match(db, f"m{i}", day=i + 1, moment_types=["lane_death"])
    result = get_improvement_data(db, "m4")
    issue = next(p for p in result["patterns"] if p["moment_type"] == "lane_death")
    assert issue["had_in_game"] is True


def test_had_in_game_false_when_moment_absent(db):
    for i in range(4):
        make_match(db, f"m{i}", day=i + 1, moment_types=["lane_death"])
    make_match(db, "m4", day=5, moment_types=[])
    result = get_improvement_data(db, "m4")
    issue = next(p for p in result["patterns"] if p["moment_type"] == "lane_death")
    assert issue["had_in_game"] is False


def test_streak_counts_consecutive_clean_games(db):
    # 4 games with lane_death (days 1-4), 3 clean (days 5-7), this game clean (day 8)
    for i in range(4):
        make_match(db, f"dirty_{i}", day=i + 1, moment_types=["lane_death"])
    for i in range(3):
        make_match(db, f"clean_{i}", day=i + 5, moment_types=[])
    make_match(db, "this_game", day=8, moment_types=[])
    result = get_improvement_data(db, "this_game")
    issue = next(p for p in result["patterns"] if p["moment_type"] == "lane_death")
    assert issue["streak"] == 4  # this_game + 3 preceding clean games


def test_recent_rate_counts_last_5_games(db):
    # 10 games + this game, all with lane_death → last 5 all hit → recent_rate == 5
    for i in range(10):
        make_match(db, f"old_{i}", day=i + 1, moment_types=["lane_death"])
    make_match(db, "this_game", day=11, moment_types=["lane_death"])
    result = get_improvement_data(db, "this_game")
    issue = next(p for p in result["patterns"] if p["moment_type"] == "lane_death")
    assert issue["recent_rate"] == 5


def test_win_condition_filtered_when_rare_and_absent(db):
    # 7 early wins with solo_kill (days 1-7), 3 recent wins without (days 8-10), this game no solo_kill (day 11)
    # recent_rate in last 5 (days 7-11): only day 7 has solo_kill → recent_rate=1, had_in_game=False → filtered
    for i in range(7):
        make_match(db, f"old_win_{i}", result="win", day=i + 1,
                   moment_types=["solo_kill", "lane_death"])
    for i in range(3):
        make_match(db, f"recent_{i}", result="win", day=i + 8,
                   moment_types=["lane_death"])
    make_match(db, "this_game", result="loss", day=11, moment_types=["lane_death"])
    result = get_improvement_data(db, "this_game")
    win_cond = next((p for p in result["patterns"] if p["label"] == "win_condition"), None)
    assert win_cond is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar && venv/Scripts/pytest tests/test_improvement_tracker.py -v
```

Expected: `ModuleNotFoundError: No module named 'improvement_tracker'`

- [ ] **Step 3: Create `sidecar/improvement_tracker.py`**

```python
import logging
from collections import Counter

from sqlalchemy.orm import Session

from champ_select_monitor import MOMENT_LABELS, POSITIVE_TYPES
from database import Match, get_matches, get_pivotal_moments

log = logging.getLogger(__name__)


def get_improvement_data(db: Session, match_id: str) -> dict | None:
    this_match = db.query(Match).filter(Match.match_id == match_id).first()
    if this_match is None:
        return None

    champion = this_match.champion
    matches = get_matches(db, champion=champion, last_n=20)  # newest first

    if len(matches) < 3:
        return {"champion": champion, "patterns": []}

    match_ids = [m.match_id for m in matches]
    moments = get_pivotal_moments(db, match_ids)

    # Group moments by match_id for fast lookup
    moments_by_match: dict[str, list] = {}
    for m in moments:
        moments_by_match.setdefault(m.match_id, []).append(m)

    this_match_types = {m.moment_type for m in moments_by_match.get(match_id, [])}

    # Top 2 negative patterns
    negative_counts = Counter(
        m.moment_type for m in moments if m.moment_type not in POSITIVE_TYPES
    )

    # Top 1 positive pattern — wins only
    win_ids = {m.match_id for m in matches if m.result == "win"}
    positive_counts = Counter(
        m.moment_type for m in moments
        if m.moment_type in POSITIVE_TYPES and m.match_id in win_ids
    )

    recent_5_ids = [m.match_id for m in matches[:5]]  # newest first

    def recent_rate(moment_type: str) -> int:
        return sum(
            1 for mid in recent_5_ids
            if any(m.moment_type == moment_type for m in moments_by_match.get(mid, []))
        )

    def streak_clean(moment_type: str) -> int:
        count = 0
        for mid in match_ids:  # newest first
            types = {m.moment_type for m in moments_by_match.get(mid, [])}
            if moment_type not in types:
                count += 1
            else:
                break
        return count

    patterns = []

    for moment_type, _ in negative_counts.most_common(2):
        display = MOMENT_LABELS.get(moment_type, moment_type.replace("_", " ").title())
        had_in_game = moment_type in this_match_types
        patterns.append({
            "label": "recurring_issue",
            "moment_type": moment_type,
            "display": display,
            "had_in_game": had_in_game,
            "streak": streak_clean(moment_type) if not had_in_game else 0,
            "recent_rate": recent_rate(moment_type),
        })

    if positive_counts:
        moment_type, _ = positive_counts.most_common(1)[0]
        display = MOMENT_LABELS.get(moment_type, moment_type.replace("_", " ").title())
        had_in_game = moment_type in this_match_types
        rate = recent_rate(moment_type)
        if had_in_game or rate >= 3:
            patterns.append({
                "label": "win_condition",
                "moment_type": moment_type,
                "display": display,
                "had_in_game": had_in_game,
                "streak": 0,
                "recent_rate": rate,
            })

    return {"champion": champion, "patterns": patterns}
```

- [ ] **Step 4: Run 6 tests**

```
cd sidecar && venv/Scripts/pytest tests/test_improvement_tracker.py -v
```

Expected: 6 passed

- [ ] **Step 5: Run full suite to verify no regressions**

```
cd sidecar && venv/Scripts/pytest tests/ -v
```

Expected: all tests pass (pre-existing `test_backfill_uses_start_time_30_days_ago` failure is acceptable if still present)

- [ ] **Step 6: Commit**

```bash
git add sidecar/improvement_tracker.py sidecar/tests/test_improvement_tracker.py
git commit -m "feat: improvement_tracker — per-game pattern comparison with streak and recent rate"
```

---

### Task 2: `GET /improvement/{match_id}` endpoint

**Files:**
- Modify: `sidecar/main.py`

- [ ] **Step 1: Add import after the existing `from live_game_monitor import LiveGameMonitor` block**

In `sidecar/main.py`, add after the `from champ_select_monitor import ChampSelectMonitor` import line:

```python
from improvement_tracker import get_improvement_data
```

- [ ] **Step 2: Add the route after the `GET /champ-select` route**

```python
@app.get("/improvement/{match_id}")
def get_improvement(match_id: str):
    data = get_improvement_data(db, match_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return data
```

- [ ] **Step 3: Run full test suite**

```
cd sidecar && venv/Scripts/pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Verify endpoint manually**

Start the sidecar:
```
cd sidecar && venv/Scripts/uvicorn main:app --port 8765
```

Hit the endpoint with a nonexistent ID:
```
curl http://localhost:8765/improvement/FAKE_ID
```

Expected: `{"detail":"Match not found"}` with HTTP 404.

- [ ] **Step 5: Commit**

```bash
git add sidecar/main.py
git commit -m "feat: GET /improvement/{match_id} endpoint"
```

---

### Task 3: Popup "vs your patterns" section

**Files:**
- Modify: `src/popup/App.tsx`

- [ ] **Step 1: Add new interfaces above `PopupApp`**

Add these interfaces directly above the `function getMatchId()` line in `src/popup/App.tsx`:

```tsx
interface ImprovementPattern {
  label: 'recurring_issue' | 'win_condition'
  moment_type: string
  display: string
  had_in_game: boolean
  streak: number
  recent_rate: number
}

interface ImprovementData {
  champion: string
  patterns: ImprovementPattern[]
}
```

- [ ] **Step 2: Add `ImprovementRow` component above `PopupApp`**

Add this component directly above `function PopupApp()`:

```tsx
function ImprovementRow({ pattern }: { pattern: ImprovementPattern }) {
  const { label, display, had_in_game, streak, recent_rate } = pattern
  const isIssue = label === 'recurring_issue'
  const name = display.toLowerCase()

  let text: string
  if (isIssue) {
    if (!had_in_game) {
      text = streak >= 2 ? `No ${name} · ${streak} clean in a row` : `No ${name} this game`
    } else {
      text = `${display} again · ${recent_rate}/5 recent games`
    }
  } else {
    text = had_in_game ? `${display} — keep it up` : `No ${name} — usually your win condition`
  }

  const isPositive = (isIssue && !had_in_game) || (!isIssue && had_in_game)
  return (
    <div className={`border-l-2 rounded px-3 py-1.5 text-xs ${
      isPositive
        ? 'border-green-500 bg-green-950/80 text-green-200'
        : 'border-red-500 bg-red-950/80 text-red-200'
    }`}>
      <span className="mr-1">{isPositive ? '✓' : '⚠'}</span>
      {text}
    </div>
  )
}
```

- [ ] **Step 3: Update `PopupApp` state and data fetching**

Replace the existing `useState` and `useEffect` block in `PopupApp` (lines 41–54 of the current file) with:

```tsx
function PopupApp() {
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [improvement, setImprovement] = useState<ImprovementData | null>(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<Filter>('all')

  const port = window.sidecar?.port ?? '8765'
  const matchId = getMatchId()

  useEffect(() => {
    if (!matchId) { setLoading(false); return }
    Promise.all([
      fetch(`http://localhost:${port}/analysis/${matchId}`)
        .then(r => { if (!r.ok) throw new Error('not ok'); return r.json() as Promise<Analysis> }),
      fetch(`http://localhost:${port}/improvement/${matchId}`)
        .then(r => r.ok ? r.json() as Promise<ImprovementData> : null)
        .catch(() => null),
    ]).then(([analysisData, improvementData]) => {
      setAnalysis(analysisData)
      setImprovement(improvementData)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [matchId, port])
```

- [ ] **Step 4: Add the "vs your patterns" section to the render output**

In the `return (...)` block of `PopupApp`, add the improvement section between the stat tiles block (`</div>` ending the grid) and the filter bar block (`{/* Filter bar */}`):

```tsx
      {/* Improvement: vs your patterns */}
      {improvement && improvement.patterns.length > 0 && (
        <div className="mb-3">
          <p className="text-gray-500 text-[9px] uppercase tracking-wide mb-1.5">
            vs your patterns ({improvement.champion})
          </p>
          <div className="flex flex-col gap-1.5">
            {improvement.patterns.map(p => (
              <ImprovementRow key={p.moment_type} pattern={p} />
            ))}
          </div>
        </div>
      )}
```

- [ ] **Step 5: Verify TypeScript build**

```
npm run build
```

Expected: build completes with no errors. `dist/renderer/popup/` is updated.

- [ ] **Step 6: Run full sidecar test suite one final time**

```
cd sidecar && venv/Scripts/pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/popup/App.tsx
git commit -m "feat: post-game popup 'vs your patterns' improvement section"
```
