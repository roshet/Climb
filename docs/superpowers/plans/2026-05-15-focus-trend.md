# Focus Trend Dot Trail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-game history dot trail to the chat tab's focus card showing the player's last 10 games as green (clean) or red (had the issue), with an "improving" / "regressing" trend label.

**Architecture:** Two independent file changes. Backend extracts `_compute_focus_history` and `_compute_focus_trend` as testable functions and adds `history` and `trend` to the `/focus` response. Frontend adds optional `history` and `trend` fields to `FocusCardData` and renders the dot trail in `FocusCard`. No schema changes.

**Tech Stack:** Python 3 / FastAPI (backend), React 18 / TypeScript / Tailwind CSS (frontend). No frontend test framework — frontend verification is build + manual.

---

### Task 1: Add `history` and `trend` to the `/focus` endpoint

**Files:**
- Modify: `sidecar/main.py`
- Modify: `sidecar/tests/test_focus_card.py`

**Context:** The `/focus` endpoint already computes `recent_ids` (list of match IDs, newest-first) and `moments_by_match` (dict mapping match_id → set of moment_types seen in that game). The new fields are derived from those two variables. `_compute_streak_clean` was already extracted as a standalone function — follow the same pattern.

---

- [ ] **Step 1: Write failing tests for `_compute_focus_history`**

First, add this import at the top of `sidecar/tests/test_focus_card.py` alongside the existing `from main import _compute_streak_clean` line:

```python
from main import _compute_focus_history
```

Then add these tests at the bottom of the file:

```python
def test_focus_history_oldest_to_newest():
    # recent_ids is newest-first: m3=newest, m1=oldest
    recent_ids = ["m3", "m2", "m1"]
    moments_by_match = {"m1": {"lane_death"}, "m2": set(), "m3": {"lane_death"}}
    history = _compute_focus_history(recent_ids, moments_by_match, "lane_death")
    # reversed to oldest-first: [m1=False, m2=True, m3=False]
    assert history == [False, True, False]


def test_focus_history_caps_at_10():
    recent_ids = [f"m{i}" for i in range(15)]  # 15 games newest-first
    history = _compute_focus_history(recent_ids, {}, "lane_death")
    assert len(history) == 10


def test_focus_history_fewer_than_10_games():
    recent_ids = ["m2", "m1"]  # m2=newest, m1=oldest
    moments_by_match = {"m1": {"lane_death"}, "m2": set()}
    history = _compute_focus_history(recent_ids, moments_by_match, "lane_death")
    # oldest-first: [m1=False, m2=True]
    assert history == [False, True]


def test_focus_history_empty():
    assert _compute_focus_history([], {}, "lane_death") == []


def test_focus_history_missing_match_treated_as_clean():
    recent_ids = ["m1"]
    history = _compute_focus_history(recent_ids, {}, "lane_death")
    assert history == [True]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sidecar && python -m pytest tests/test_focus_card.py::test_focus_history_oldest_to_newest tests/test_focus_card.py::test_focus_history_caps_at_10 tests/test_focus_card.py::test_focus_history_fewer_than_10_games tests/test_focus_card.py::test_focus_history_empty tests/test_focus_card.py::test_focus_history_missing_match_treated_as_clean -v
```

Expected: 5 failures — `ImportError: cannot import name '_compute_focus_history' from 'main'`

- [ ] **Step 3: Implement `_compute_focus_history` in `main.py`**

Add this function to `sidecar/main.py` immediately after `_compute_streak_clean`:

```python
def _compute_focus_history(
    recent_ids: list[str],
    moments_by_match: dict[str, set],
    moment_type: str,
    n: int = 10,
) -> list[bool]:
    history_ids = list(reversed(recent_ids[:n]))
    return [
        moment_type not in moments_by_match.get(mid, set())
        for mid in history_ids
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd sidecar && python -m pytest tests/test_focus_card.py::test_focus_history_oldest_to_newest tests/test_focus_card.py::test_focus_history_caps_at_10 tests/test_focus_card.py::test_focus_history_fewer_than_10_games tests/test_focus_card.py::test_focus_history_empty tests/test_focus_card.py::test_focus_history_missing_match_treated_as_clean -v
```

Expected: 5 PASS

- [ ] **Step 5: Write failing tests for `_compute_focus_trend`**

Add this import at the top of `sidecar/tests/test_focus_card.py` alongside the other imports:

```python
from main import _compute_focus_trend
```

Then add these tests at the bottom of the file:

```python
def test_trend_improving():
    # first 5: 2 clean, last 5: 4 clean → improving
    history = [False, False, True, False, True, True, True, True, True, False]
    assert _compute_focus_trend(history) == "improving"


def test_trend_regressing():
    # first 5: 4 clean, last 5: 1 clean → regressing
    history = [True, True, True, True, False, False, False, False, True, False]
    assert _compute_focus_trend(history) == "regressing"


def test_trend_none_when_equal_halves():
    # first 3: 2 clean, last 3: 2 clean → None
    history = [True, False, True, False, True, False]
    assert _compute_focus_trend(history) is None


def test_trend_none_when_fewer_than_6_games():
    history = [True, False, True, True, False]  # only 5
    assert _compute_focus_trend(history) is None


def test_trend_none_on_empty():
    assert _compute_focus_trend([]) is None
```

- [ ] **Step 6: Run tests to verify they fail**

```bash
cd sidecar && python -m pytest tests/test_focus_card.py::test_trend_improving tests/test_focus_card.py::test_trend_regressing tests/test_focus_card.py::test_trend_none_when_equal_halves tests/test_focus_card.py::test_trend_none_when_fewer_than_6_games tests/test_focus_card.py::test_trend_none_on_empty -v
```

Expected: 5 failures — `ImportError: cannot import name '_compute_focus_trend' from 'main'`

- [ ] **Step 7: Implement `_compute_focus_trend` in `main.py`**

Add immediately after `_compute_focus_history`:

```python
def _compute_focus_trend(history: list[bool]) -> Optional[str]:
    if len(history) < 6:
        return None
    mid = len(history) // 2
    first_half = sum(history[:mid])
    second_half = sum(history[mid:])
    if second_half > first_half:
        return "improving"
    if second_half < first_half:
        return "regressing"
    return None
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
cd sidecar && python -m pytest tests/test_focus_card.py::test_trend_improving tests/test_focus_card.py::test_trend_regressing tests/test_focus_card.py::test_trend_none_when_equal_halves tests/test_focus_card.py::test_trend_none_when_fewer_than_6_games tests/test_focus_card.py::test_trend_none_on_empty -v
```

Expected: 5 PASS

- [ ] **Step 9: Wire `history` and `trend` into the `/focus` endpoint**

In the `/focus` endpoint in `sidecar/main.py`, the existing code already has `recent_ids` and `moments_by_match` computed. Find the `return {` block at the end of `get_focus()` and add the two new fields:

```python
    history = _compute_focus_history(recent_ids, moments_by_match, top_issue.moment_type)
    trend = _compute_focus_trend(history)
    return {
        "moment_type": top_issue.moment_type,
        "display": display,
        "coaching_sentence": stored.get("coaching_sentence", ""),
        "cta_message": stored.get("cta_message", ""),
        "win_rate": round(top_issue.win_rate_with, 3),
        "games_seen": top_issue.games_seen,
        "total_games": top_issue.total_games,
        "streak_clean": streak_clean,
        "history": history,
        "trend": trend,
    }
```

- [ ] **Step 10: Run the full test suite**

```bash
cd sidecar && python -m pytest --tb=short -q
```

Expected: all tests pass (at least 213 total — 203 existing + 10 new).

- [ ] **Step 11: Commit**

```bash
git add sidecar/main.py sidecar/tests/test_focus_card.py
git commit -m "feat: add history and trend fields to /focus endpoint"
```

---

### Task 2: Render dot trail in the chat tab FocusCard

**Files:**
- Modify: `src/chat/FocusCard.tsx`

**Context:** `FocusCard.tsx` exports `FocusCardData` (interface) and `FocusCard` (component). The dot trail renders below the coaching sentence and streak banner. There is no frontend test framework — verification is `npm run build` (TypeScript errors) and manual inspection.

---

- [ ] **Step 1: Add `history` and `trend` to `FocusCardData`**

In `src/chat/FocusCard.tsx`, update the `FocusCardData` interface:

```tsx
export interface FocusCardData {
  moment_type: string
  display: string
  coaching_sentence: string
  cta_message: string
  win_rate: number
  games_seen: number
  total_games: number
  streak_clean: number
  history?: boolean[]
  trend?: string | null
}
```

- [ ] **Step 2: Add the dot trail render**

In `FocusCard`, add the dot trail after the streak banner block (after the closing `}`  of the `{card.streak_clean >= 1 && (...)}` block) and before the `<div className="flex items-center">` stats row:

```tsx
      {card.history && card.history.length > 0 && (
        <div className="flex items-center gap-1.5 mt-1.5 mb-1">
          <span className="text-gray-600 text-[9px]">last {card.history.length}</span>
          <div className="flex gap-1">
            {card.history.map((clean, i) => (
              <span
                key={i}
                className={`w-2 h-2 rounded-full ${clean ? 'bg-green-400' : 'bg-red-500'}`}
              />
            ))}
          </div>
          {card.trend && (
            <span className={`text-[9px] font-semibold ml-0.5 ${
              card.trend === 'improving' ? 'text-green-400' : 'text-red-400'
            }`}>
              {card.trend === 'improving' ? '↑ improving' : '↓ regressing'}
            </span>
          )}
        </div>
      )}
```

- [ ] **Step 3: Build to verify no TypeScript errors**

```bash
npm run build
```

Expected: build completes with no errors. Output ends with `✓ built in ...`

- [ ] **Step 4: Commit**

```bash
git add src/chat/FocusCard.tsx
git commit -m "feat: render focus trend dot trail in chat tab focus card"
```
