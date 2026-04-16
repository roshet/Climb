# Cross-Game Pattern Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect recurring patterns across the last 20 games and surface them in a patterns panel above the chat UI and injected into the Claude chat context.

**Architecture:** A new `pattern_detector.py` module computes patterns on-demand from existing `matches` and `pivotal_moments` tables. `main.py` gains a `GET /patterns` endpoint and injects pattern summaries into the `/chat` system context. `App.tsx` fetches patterns on mount and renders clickable cards above the message list.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, React, TypeScript, Tailwind CSS

---

## File Structure

- **Create:** `sidecar/pattern_detector.py` — `detect_patterns(db, last_n=20) -> list[PatternResult]`
- **Create:** `sidecar/tests/test_pattern_detector.py` — 8 unit tests
- **Modify:** `sidecar/main.py` — add `GET /patterns` endpoint; inject patterns into `/chat`
- **Modify:** `src/chat/App.tsx` — add pattern cards above `<MessageList>`

---

### Task 1: `pattern_detector.py` — core detection logic

**Files:**
- Create: `sidecar/pattern_detector.py`
- Create: `sidecar/tests/test_pattern_detector.py`

**Context:** The `db` fixture used in tests is already defined in `sidecar/tests/conftest.py` — it creates an in-memory SQLite DB. Tests use `save_match` and `save_pivotal_moments` from `database.py` to seed data. `get_matches` returns matches ordered by `played_at` desc; `get_pivotal_moments` takes a list of match IDs.

- [ ] **Step 1: Write failing tests**

Create `sidecar/tests/test_pattern_detector.py`:

```python
from datetime import datetime, timedelta
import pytest
from database import save_match, save_pivotal_moments
from pattern_detector import detect_patterns, PatternResult


def _make_match(db, match_id: str, result: str, played_at: datetime, moment_types: list[str]) -> None:
    save_match(db, {
        "match_id": match_id,
        "played_at": played_at,
        "champion": "Caitlyn",
        "role": "BOTTOM",
        "result": result,
        "duration_secs": 1800,
        "kda": "5/2/8",
        "cs": 150,
        "gold_earned": 12000,
        "vision_score": 20,
        "raw_timeline": {},
    })
    save_pivotal_moments(db, match_id, [
        {
            "timestamp_secs": 300,
            "moment_type": t,
            "description": f"test {t}",
            "counterfactual": "",
            "gold_impact": 300,
        }
        for t in moment_types
    ])


BASE_DATE = datetime(2026, 4, 1)


def test_empty_when_no_games(db):
    assert detect_patterns(db) == []


def test_empty_when_fewer_than_3_games(db):
    for i in range(2):
        _make_match(db, f"NA1_{i}", "loss", BASE_DATE + timedelta(days=i), ["lane_death"])
    assert detect_patterns(db) == []


def test_detects_recurring_issue(db):
    # lane_death in 7/10 games, all losses → win_rate_with = 0.0, overall = 0.3
    for i in range(10):
        result = "win" if i < 3 else "loss"
        types = ["lane_death"] if i >= 3 else []
        _make_match(db, f"NA1_{i}", result, BASE_DATE + timedelta(days=i), types)
    patterns = detect_patterns(db)
    issue = next((p for p in patterns if p.moment_type == "lane_death"), None)
    assert issue is not None
    assert issue.label == "recurring_issue"
    assert issue.games_seen == 7
    assert issue.total_games == 10


def test_detects_win_condition(db):
    # objective_secured in 6/10 games, all wins → win_rate_with = 1.0, overall = 0.6
    for i in range(10):
        result = "win" if i < 6 else "loss"
        types = ["objective_secured"] if i < 6 else []
        _make_match(db, f"NA1_{i}", result, BASE_DATE + timedelta(days=i), types)
    patterns = detect_patterns(db)
    cond = next((p for p in patterns if p.moment_type == "objective_secured"), None)
    assert cond is not None
    assert cond.label == "win_condition"
    assert cond.games_seen == 6
    assert cond.total_games == 10


def test_drops_below_win_rate_threshold(db):
    # cs_differential in 10/10 games, win_rate_with = 0.45, overall = 0.5 — delta < 0.10
    for i in range(10):
        result = "win" if i < 5 else "loss"
        _make_match(db, f"NA1_{i}", result, BASE_DATE + timedelta(days=i), ["cs_differential"])
    # All 10 games have cs_differential, 5 wins out of 10 (win_rate_with = 0.5, overall = 0.5, delta = 0)
    patterns = detect_patterns(db)
    assert all(p.moment_type != "cs_differential" for p in patterns)


def test_drops_below_min_games(db):
    # lane_death in only 2 games — below threshold of 3
    for i in range(10):
        types = ["lane_death"] if i < 2 else []
        _make_match(db, f"NA1_{i}", "loss", BASE_DATE + timedelta(days=i), types)
    patterns = detect_patterns(db)
    assert all(p.moment_type != "lane_death" for p in patterns)


def test_sorted_issues_first_then_conditions(db):
    # recurring issue: death in 8/10 games, all losses
    # win condition: solo_kill in 5/10 games, all wins (overall win rate = 0.5)
    for i in range(10):
        result = "win" if i < 5 else "loss"
        types = []
        if i >= 2:  # death in games 2-9 = 8 games, all losses
            types.append("death")
        if i < 5:   # solo_kill in games 0-4 = 5 games, all wins
            types.append("solo_kill")
        _make_match(db, f"NA1_{i}", result, BASE_DATE + timedelta(days=i), types)
    patterns = detect_patterns(db)
    labels = [p.label for p in patterns]
    # All recurring issues must appear before all win conditions
    seen_win_condition = False
    for label in labels:
        if label == "win_condition":
            seen_win_condition = True
        if seen_win_condition:
            assert label == "win_condition", "recurring_issue appeared after win_condition"


def test_capped_at_five(db):
    # Create 10 distinct moment types each appearing in 8/10 loss games
    # overall win rate = 0.2, all 10 types have win_rate_with = 0.0 → all recurring issues
    moment_types = [
        "lane_death", "cs_differential", "gold_differential",
        "turret_plates_lost", "split_push_death", "enemy_roam_kill",
        "low_vision", "objective_missed", "tower_lost", "death",
    ]
    for i in range(10):
        result = "win" if i < 2 else "loss"
        # All 10 types appear in losses (games 2-9 = 8 games), none in wins
        types = moment_types if i >= 2 else []
        _make_match(db, f"NA1_{i}", result, BASE_DATE + timedelta(days=i), types)
    patterns = detect_patterns(db)
    assert len(patterns) == 5
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar
venv/Scripts/pytest tests/test_pattern_detector.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'pattern_detector'`

- [ ] **Step 3: Create `sidecar/pattern_detector.py`**

```python
from dataclasses import dataclass
from sqlalchemy.orm import Session
from database import get_matches, get_pivotal_moments

MOMENT_TYPE_LABELS: dict[str, str] = {
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
    "roam_kill": "Roam Kills",
    "roam_assist": "Roam Assists",
    "ward_kill": "Vision Control",
}


@dataclass
class PatternResult:
    moment_type: str
    label: str            # "recurring_issue" or "win_condition"
    games_seen: int
    total_games: int
    win_rate_with: float
    overall_win_rate: float
    summary: str


def detect_patterns(db: Session, last_n: int = 20) -> list[PatternResult]:
    matches = get_matches(db, last_n=last_n)
    total_games = len(matches)
    if total_games < 3:
        return []

    overall_wins = sum(1 for m in matches if m.result == "win")
    overall_win_rate = overall_wins / total_games

    match_ids = [m.match_id for m in matches]
    result_by_id = {m.match_id: m.result for m in matches}

    all_moments = get_pivotal_moments(db, match_ids)

    # Build match_id -> set of distinct moment_types (one game counts once per type)
    types_by_match: dict[str, set[str]] = {mid: set() for mid in match_ids}
    for moment in all_moments:
        types_by_match[moment.match_id].add(moment.moment_type)

    # Invert: moment_type -> list of match_ids where it appeared
    type_games: dict[str, list[str]] = {}
    for mid, types in types_by_match.items():
        for t in types:
            type_games.setdefault(t, []).append(mid)

    results: list[PatternResult] = []
    for moment_type, game_ids in type_games.items():
        games_seen = len(game_ids)
        if games_seen < 3:
            continue

        wins_with = sum(1 for mid in game_ids if result_by_id[mid] == "win")
        win_rate_with = wins_with / games_seen

        if win_rate_with < overall_win_rate - 0.10:
            label = "recurring_issue"
        elif win_rate_with > overall_win_rate + 0.10:
            label = "win_condition"
        else:
            continue

        human = MOMENT_TYPE_LABELS.get(moment_type, moment_type.replace("_", " ").title())
        summary = (
            f"{human.lower()} in {games_seen} of your last {total_games} games "
            f"({int(win_rate_with * 100)}% win rate)"
        )

        results.append(PatternResult(
            moment_type=moment_type,
            label=label,
            games_seen=games_seen,
            total_games=total_games,
            win_rate_with=win_rate_with,
            overall_win_rate=overall_win_rate,
            summary=summary,
        ))

    recurring = sorted(
        [r for r in results if r.label == "recurring_issue"],
        key=lambda r: r.games_seen,
        reverse=True,
    )
    win_conds = sorted(
        [r for r in results if r.label == "win_condition"],
        key=lambda r: r.win_rate_with,
        reverse=True,
    )
    return (recurring + win_conds)[:5]
```

- [ ] **Step 4: Run tests**

```
cd sidecar
venv/Scripts/pytest tests/test_pattern_detector.py -v
```

Expected: All 8 PASS.

- [ ] **Step 5: Run full suite to confirm no regressions**

```
cd sidecar
venv/Scripts/pytest tests/ -v
```

Expected: All tests PASS (115 + 8 = 123 passing).

- [ ] **Step 6: Commit**

```bash
git add sidecar/pattern_detector.py sidecar/tests/test_pattern_detector.py
git commit -m "feat: pattern_detector — detect recurring issues and win conditions"
```

---

### Task 2: `GET /patterns` endpoint and chat injection

**Files:**
- Modify: `sidecar/main.py`

**Context:** `main.py` already imports from `backfill`, `database`, `claude_client`, etc. The `claude.chat()` method accepts `match_context: str | None` which is appended to the system prompt. The `/chat` endpoint already builds `match_context` from pivotal moments for a specific game — we append pattern context to that same string. No changes needed to `claude_client.py`.

No new tests for this task — `detect_patterns` is already tested in Task 1, and the endpoint is a thin wrapper. Manual verification is sufficient (see Step 4).

- [ ] **Step 1: Add import and `GET /patterns` endpoint to `sidecar/main.py`**

Add this import at line 13 (after the `from backfill import ...` line):

```python
from pattern_detector import detect_patterns
```

Add this endpoint after the `/status/clear` route (around line 121):

```python
@app.get("/patterns")
def get_patterns():
    patterns = detect_patterns(db)
    return {
        "patterns": [
            {
                "moment_type": p.moment_type,
                "label": p.label,
                "games_seen": p.games_seen,
                "total_games": p.total_games,
                "win_rate_with": round(p.win_rate_with, 3),
                "overall_win_rate": round(p.overall_win_rate, 3),
                "summary": p.summary,
            }
            for p in patterns
        ]
    }
```

- [ ] **Step 2: Inject patterns into `/chat` context**

Replace the existing `/chat` endpoint:

```python
@app.post("/chat")
def chat(req: ChatRequest):
    player = get_player(db)
    if not player:
        raise HTTPException(status_code=400, detail="Player profile not set up")

    save_chat_message(db, session_id=req.session_id, match_id=req.match_id, role="user", content=req.message)

    history = get_chat_history(db, session_id=req.session_id)
    messages = [{"role": m.role, "content": m.content} for m in history]

    match_context = None
    if req.match_id:
        moments = get_pivotal_moments(db, [req.match_id])
        if moments:
            match_context = "\n".join(f"- {m.description} {m.counterfactual}" for m in moments)

    try:
        patterns = detect_patterns(db)
        if patterns:
            issues = [p for p in patterns if p.label == "recurring_issue"]
            wins = [p for p in patterns if p.label == "win_condition"]
            lines: list[str] = []
            if issues:
                lines.append("Recurring issues (last 20 games):")
                lines.extend(
                    f"- {p.moment_type}: {p.games_seen}/{p.total_games} games, "
                    f"{int(p.win_rate_with * 100)}% win rate (overall {int(p.overall_win_rate * 100)}%)"
                    for p in issues
                )
            if wins:
                lines.append("Win conditions:")
                lines.extend(
                    f"- {p.moment_type}: {p.games_seen}/{p.total_games} games, "
                    f"{int(p.win_rate_with * 100)}% win rate"
                    for p in wins
                )
            pattern_context = "\n".join(lines)
            match_context = (match_context + "\n\n" + pattern_context) if match_context else pattern_context
    except Exception:
        pass  # pattern injection is best-effort; chat works without it

    response = claude.chat(
        summoner_name=player.summoner_name,
        messages=messages,
        match_context=match_context,
    )

    save_chat_message(db, session_id=req.session_id, match_id=req.match_id, role="assistant", content=response)
    return {"response": response}
```

- [ ] **Step 3: Run the full test suite**

```
cd sidecar
venv/Scripts/pytest tests/ -v
```

Expected: All 123 tests PASS.

- [ ] **Step 4: Manual smoke test**

Start the sidecar:
```
cd sidecar
venv/Scripts/uvicorn main:app --port 8765 --reload
```

Hit the endpoint:
```
curl http://localhost:8765/patterns
```

Expected response (if you have game history in DB):
```json
{"patterns": [...]}
```

Or `{"patterns": []}` if fewer than 3 games are stored. Either is correct.

- [ ] **Step 5: Commit**

```bash
git add sidecar/main.py
git commit -m "feat: GET /patterns endpoint and pattern injection into chat context"
```

---

### Task 3: Frontend patterns panel

**Files:**
- Modify: `src/chat/App.tsx`

**Context:** `App.tsx` is the single-file React frontend. The current render tree inside the main `ChatApp` return is:
1. Header div (with "Climb" title)
2. `<MessageList messages={messages} />`
3. Loading indicator
4. `<InputBar onSend={sendMessage} disabled={loading} />`

We add pattern cards between the header and `<MessageList>`. The panel is only rendered when patterns are non-empty. Clicking a card fires `sendMessage(...)` with a pre-filled prompt.

No test file for this task — it's thin UI over a single fetch.

- [ ] **Step 1: Add the `Pattern` interface and patterns state**

After the `Message` interface definition (around line 12), add:

```typescript
interface Pattern {
  moment_type: string
  label: 'recurring_issue' | 'win_condition'
  games_seen: number
  total_games: number
  win_rate_with: number
  overall_win_rate: number
  summary: string
}
```

Inside the `ChatApp` function, after the `const [matchId]` line, add:

```typescript
const [patterns, setPatterns] = useState<Pattern[]>([])
```

- [ ] **Step 2: Fetch patterns on mount**

Add a `useEffect` after the existing player-check `useEffect`:

```typescript
useEffect(() => {
  if (!isSetup) return
  fetch(`http://localhost:${port}/patterns`)
    .then(r => r.ok ? r.json() : { patterns: [] })
    .then((data: { patterns: Pattern[] }) => setPatterns(data.patterns))
    .catch(() => {})
}, [port, isSetup])
```

- [ ] **Step 3: Add pattern label map and cards to render**

Add this constant outside the `ChatApp` function (after the `SESSION_ID` line):

```typescript
const MOMENT_LABELS: Record<string, string> = {
  lane_death: 'Lane Deaths',
  cs_differential: 'CS Deficit',
  gold_differential: 'Gold Deficit',
  turret_plates_lost: 'Plates Lost',
  split_push_death: 'Split Push Deaths',
  enemy_roam_kill: 'Enemy Roams',
  low_vision: 'Low Vision',
  objective_missed: 'Missed Objectives',
  tower_lost: 'Towers Lost',
  death: 'Deaths',
  solo_kill: 'Solo Kills',
  objective_secured: 'Objectives Secured',
  roam_kill: 'Roam Kills',
  roam_assist: 'Roam Assists',
  ward_kill: 'Vision Control',
}
```

In the main return, replace:

```tsx
      <MessageList messages={messages} />
```

With:

```tsx
      {patterns.length > 0 && (
        <div className="px-4 py-2 border-b border-white/10 flex gap-2 overflow-x-auto flex-shrink-0">
          {patterns.map((p) => (
            <button
              key={p.moment_type}
              onClick={() => sendMessage(
                `Tell me about my ${(MOMENT_LABELS[p.moment_type] ?? p.moment_type.replace(/_/g, ' ')).toLowerCase()} pattern`
              )}
              className={`flex-shrink-0 text-left px-3 py-2 rounded-lg border-l-4 bg-white/5 hover:bg-white/10 transition-colors ${
                p.label === 'recurring_issue' ? 'border-red-400' : 'border-green-400'
              }`}
            >
              <div className="text-xs font-semibold whitespace-nowrap">
                {MOMENT_LABELS[p.moment_type] ?? p.moment_type}
              </div>
              <div className="text-xs text-gray-400 whitespace-nowrap">
                {p.games_seen} of {p.total_games} · {Math.round(p.win_rate_with * 100)}% WR
              </div>
            </button>
          ))}
        </div>
      )}
      <MessageList messages={messages} />
```

- [ ] **Step 4: Run the full backend test suite**

```
cd sidecar
venv/Scripts/pytest tests/ -v
```

Expected: All 123 tests PASS (frontend has no test suite).

- [ ] **Step 5: Build the frontend and verify no TypeScript errors**

```
cd c:\Users\rohan\OneDrive\Desktop\NewProject
npm run build
```

Expected: Build succeeds with no errors.

- [ ] **Step 6: Commit**

```bash
git add src/chat/App.tsx
git commit -m "feat: patterns panel in chat UI with click-to-ask cards"
```

---

## Self-Review

**Spec coverage:**
- ✅ `detect_patterns(db, last_n=20) -> list[PatternResult]` — Task 1
- ✅ Fewer than 3 games → `[]` — Task 1, `test_empty_when_fewer_than_3_games`
- ✅ Recurring issue label (win_rate_with < overall - 0.10) — Task 1, Step 3
- ✅ Win condition label (win_rate_with > overall + 0.10) — Task 1, Step 3
- ✅ Threshold: games_seen ≥ 3 — Task 1, Step 3
- ✅ Sort: recurring issues first, then win conditions — Task 1, Step 3
- ✅ Cap at 5 — Task 1, Step 3
- ✅ Summary string format — Task 1, Step 3
- ✅ `GET /patterns` endpoint — Task 2, Step 1
- ✅ Pattern injection into `/chat` context — Task 2, Step 2
- ✅ Injection failure is silent (try/except) — Task 2, Step 2
- ✅ Pattern cards above MessageList — Task 3, Step 3
- ✅ Red border for recurring_issue, green for win_condition — Task 3, Step 3
- ✅ Click sends pre-filled chat message — Task 3, Step 3
- ✅ Panel hidden when patterns empty — Task 3, Step 3
- ✅ `MOMENT_TYPE_LABELS` map — Task 1 (Python) and Task 3 (TypeScript)
- ✅ All 8 tests from spec — Task 1

**Placeholder scan:** No TBDs. All code blocks are complete and self-contained.

**Type consistency:** `PatternResult` dataclass fields (`moment_type`, `label`, `games_seen`, `total_games`, `win_rate_with`, `overall_win_rate`, `summary`) match across Task 1 definition, Task 2 endpoint serialization, and Task 3 `Pattern` TypeScript interface. `detect_patterns` signature is consistent across all three tasks.
