# Focus for Next Game Coaching Card — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent "Focus for Next Game" coaching card to the top of the Chat tab that surfaces the player's #1 recurring issue with a Gemini-generated coaching sentence and a one-tap path to getting coached on it.

**Architecture:** `ClaudeClient.generate_focus_card()` calls Gemini once with the top recurring pattern's stats and returns `{coaching_sentence, cta_message}`; this runs after every post-game analysis and after backfill, storing the result in `AppState(key="focus_card")`; a new `GET /focus` endpoint reads the stored card, joins it with fresh live stats and a cross-champion streak count, and returns a flat JSON response; a new `FocusCard.tsx` React component renders the card above the pattern pills in the Chat tab.

**Tech Stack:** Python/FastAPI sidecar, Google Gemini (`google-genai`, model `gemini-2.5-flash`), React 18, TypeScript, Tailwind CSS

---

## File Structure

| File | Change |
|---|---|
| `sidecar/claude_client.py` | Add `generate_focus_card(pattern, summoner_name)` method |
| `sidecar/main.py` | Add `import json`, add `MOMENT_LABELS` to champ_select_monitor import, add `_generate_and_store_focus_card()` async helper, wire it into `backfill_history` and `run_post_game_analysis`, add `GET /focus` endpoint |
| `src/chat/FocusCard.tsx` | New component: renders the focus card with coaching sentence, streak indicator, and Ask Claude CTA |
| `src/chat/App.tsx` | Import `FocusCard` and `FocusCardData`, add `focusCard` state, fetch `/focus` on mount, render `<FocusCard>` above pattern pills |
| `sidecar/tests/test_claude_client.py` | Add 3 tests for `generate_focus_card` |

---

### Task 1: `generate_focus_card` method in `ClaudeClient`

**Files:**
- Modify: `sidecar/claude_client.py`
- Test: `sidecar/tests/test_claude_client.py`

- [ ] **Step 1: Write the failing tests**

In `sidecar/tests/test_claude_client.py`, append these functions after the last test:

```python
def _make_focus_client():
    db = MagicMock()
    with patch("claude_client.genai.Client"):
        client = ClaudeClient(api_key="test", db=db)
    mock_response = MagicMock()
    mock_response.text = '{"coaching_sentence": "You died early 5/8 games.", "cta_message": "I keep dying early. How do I fix this?"}'
    client.client.models.generate_content.return_value = mock_response
    return client


def _make_focus_pattern():
    return PatternResult(
        moment_type="jungle_death",
        label="recurring_issue",
        games_seen=5,
        total_games=8,
        win_rate_with=0.40,
        overall_win_rate=0.55,
        summary="jungle deaths in 5 of your last 8 games (40% win rate)",
    )


def test_generate_focus_card_returns_sentence_and_cta():
    client = _make_focus_client()
    result = client.generate_focus_card(_make_focus_pattern(), "TestPlayer")
    assert "coaching_sentence" in result
    assert "cta_message" in result
    assert isinstance(result["coaching_sentence"], str)
    assert isinstance(result["cta_message"], str)


def test_generate_focus_card_prompt_includes_stats():
    client = _make_focus_client()
    client.generate_focus_card(_make_focus_pattern(), "TestPlayer")
    prompt = client.client.models.generate_content.call_args[1]["contents"]
    assert "jungle_death" in prompt
    assert "5" in prompt
    assert "8" in prompt
    assert "TestPlayer" in prompt


def test_generate_focus_card_fallback_on_exception():
    db = MagicMock()
    with patch("claude_client.genai.Client"):
        client = ClaudeClient(api_key="test", db=db)
    client.client.models.generate_content.side_effect = Exception("quota exceeded")
    result = client.generate_focus_card(_make_focus_pattern(), "TestPlayer")
    assert "coaching_sentence" in result
    assert "cta_message" in result
    assert len(result["coaching_sentence"]) > 0
    assert len(result["cta_message"]) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sidecar && python -m pytest tests/test_claude_client.py::test_generate_focus_card_returns_sentence_and_cta tests/test_claude_client.py::test_generate_focus_card_prompt_includes_stats tests/test_claude_client.py::test_generate_focus_card_fallback_on_exception -v
```

Expected: FAIL with `AttributeError: 'ClaudeClient' object has no attribute 'generate_focus_card'`

- [ ] **Step 3: Implement `generate_focus_card` at the end of the `ClaudeClient` class**

In `sidecar/claude_client.py`, find the end of the `ClaudeClient` class (after `generate_coaching_notes` closes at the last `return moments` line). Add this method inside the class (same indentation level as `generate_coaching_notes`):

```python
    def generate_focus_card(self, pattern, summoner_name: str) -> dict:
        win_rate_pct = int(pattern.win_rate_with * 100)
        overall_pct = int(pattern.overall_win_rate * 100)
        prompt = (
            f"You are a League of Legends coach. Write a focus card for {summoner_name} "
            f"with this recurring issue:\n\n"
            f"Pattern: {pattern.moment_type}\n"
            f"Frequency: {pattern.games_seen} of last {pattern.total_games} games\n"
            f"Win rate with this issue: {win_rate_pct}% (overall: {overall_pct}%)\n\n"
            f'Return ONLY valid JSON: {{"coaching_sentence": "...", "cta_message": "..."}}\n\n'
            f"coaching_sentence: 1-2 sentences. Use the player's actual numbers. "
            f"Describe what's happening and one concrete fix.\n"
            f"cta_message: The first-person question {summoner_name} would ask a coach. "
            f"Start with 'I' and end with a question mark."
        )
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            raw = response.text.strip()
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception as e:
            print(f"[focus_card] Gemini call failed ({e}). Using fallback.")
            return {
                "coaching_sentence": pattern.summary,
                "cta_message": f"Help me fix my {pattern.moment_type.replace('_', ' ')} habit.",
            }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd sidecar && python -m pytest tests/test_claude_client.py::test_generate_focus_card_returns_sentence_and_cta tests/test_claude_client.py::test_generate_focus_card_prompt_includes_stats tests/test_claude_client.py::test_generate_focus_card_fallback_on_exception -v
```

Expected: PASS (3 tests)

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
cd sidecar && python -m pytest --tb=short -q
```

Expected: all previously passing tests still pass; 3 new tests added

- [ ] **Step 6: Commit**

```bash
git add sidecar/claude_client.py sidecar/tests/test_claude_client.py
git commit -m "feat: add generate_focus_card method to ClaudeClient"
```

---

### Task 2: `/focus` endpoint and generation triggers in `main.py`

**Files:**
- Modify: `sidecar/main.py`

No unit tests — the endpoint composes already-tested functions. Verified by import check and manual curl in Task 5.

- [ ] **Step 1: Add `import json` to `sidecar/main.py`**

Find:
```python
import asyncio
import os
```

Replace with:
```python
import asyncio
import json
import os
```

- [ ] **Step 2: Add `MOMENT_LABELS` to the existing `champ_select_monitor` import**

Find:
```python
from champ_select_monitor import ChampSelectMonitor, POSITIVE_TYPES
```

Replace with:
```python
from champ_select_monitor import ChampSelectMonitor, MOMENT_LABELS, POSITIVE_TYPES
```

- [ ] **Step 3: Add `_generate_and_store_focus_card` async helper before `backfill_history`**

Find:
```python
async def backfill_history() -> None:
```

Insert directly before it:

```python
async def _generate_and_store_focus_card() -> None:
    try:
        patterns = detect_patterns(db)
        top_issue = next((p for p in patterns if p.label == "recurring_issue"), None)
        if not top_issue:
            return
        player = get_player(db)
        if not player:
            return
        focus = claude.generate_focus_card(top_issue, player.summoner_name)
        db.merge(AppState(key="focus_card", value=json.dumps(focus)))
        db.commit()
    except Exception as e:
        print(f"[focus_card] Failed to generate: {e}")


```

- [ ] **Step 4: Wire the trigger into `backfill_history`**

Find:
```python
        await run_backfill(riot, db, claude, player)
    finally:
        _backfill_running = False
```

Replace with:
```python
        await run_backfill(riot, db, claude, player)
        await _generate_and_store_focus_card()
    finally:
        _backfill_running = False
```

- [ ] **Step 5: Wire the trigger into `run_post_game_analysis`**

Find:
```python
        set_pending_popup(db, match_id=match_id)
    except Exception as e:
        print(f"[watcher] Error during post-game analysis: {e}")
```

Replace with:
```python
        set_pending_popup(db, match_id=match_id)
        await _generate_and_store_focus_card()
    except Exception as e:
        print(f"[watcher] Error during post-game analysis: {e}")
```

- [ ] **Step 6: Add `GET /focus` endpoint**

In `sidecar/main.py`, find the `GET /improvement/{match_id}` endpoint:

```python
@app.get("/improvement/{match_id}")
def get_improvement(match_id: str):
    data = get_improvement_data(db, match_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return data
```

Insert after it (leave a blank line between):

```python

@app.get("/focus")
def get_focus():
    row = db.query(AppState).filter(AppState.key == "focus_card").first()
    if not row or not row.value:
        return None
    stored = json.loads(row.value)
    patterns = detect_patterns(db)
    top_issue = next((p for p in patterns if p.label == "recurring_issue"), None)
    if not top_issue:
        return None
    recent_matches = get_matches(db, last_n=20)
    recent_ids = [m.match_id for m in recent_matches]
    recent_moments = get_pivotal_moments(db, recent_ids)
    moments_by_match: dict[str, set] = {}
    for m in recent_moments:
        moments_by_match.setdefault(m.match_id, set()).add(m.moment_type)
    streak_clean = 0
    for mid in recent_ids:
        if top_issue.moment_type not in moments_by_match.get(mid, set()):
            streak_clean += 1
        else:
            break
    display = MOMENT_LABELS.get(
        top_issue.moment_type,
        top_issue.moment_type.replace("_", " ").title(),
    )
    return {
        "moment_type": top_issue.moment_type,
        "display": display,
        "coaching_sentence": stored["coaching_sentence"],
        "cta_message": stored["cta_message"],
        "win_rate": round(top_issue.win_rate_with, 3),
        "games_seen": top_issue.games_seen,
        "total_games": top_issue.total_games,
        "streak_clean": streak_clean,
    }
```

- [ ] **Step 7: Verify clean import**

```bash
cd sidecar && python -c "import main; print('ok')"
```

Expected: `ok` (no import errors)

- [ ] **Step 8: Commit**

```bash
git add sidecar/main.py
git commit -m "feat: add /focus endpoint and post-game focus card generation"
```

---

### Task 3: `FocusCard.tsx` component

**Files:**
- Create: `src/chat/FocusCard.tsx`

No tests — pure presentational component. Verified by build check.

- [ ] **Step 1: Create `src/chat/FocusCard.tsx`**

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
}

interface FocusCardProps {
  card: FocusCardData
  onAsk: (message: string) => void
}

export function FocusCard({ card, onAsk }: FocusCardProps) {
  return (
    <div className="mx-4 mb-2 bg-[#1a1a3a] border border-indigo-500/40 rounded-lg px-3 py-2 flex-shrink-0">
      <div className="text-[9px] font-bold tracking-wider text-indigo-400 mb-1">
        🎯 FOCUS FOR NEXT GAME
      </div>
      <div className="text-sm font-semibold text-white mb-1">{card.display}</div>
      <div className="text-xs text-gray-400 leading-relaxed mb-2">{card.coaching_sentence}</div>
      {card.streak_clean >= 1 && (
        <div className="bg-green-950/50 border border-green-500/30 rounded px-2 py-1 mb-2">
          <span className="text-green-400 text-[10px]">
            ↑ Clean last {card.streak_clean} game{card.streak_clean === 1 ? '' : 's'} — keep it up
          </span>
        </div>
      )}
      <div className="flex items-center">
        <span className="text-[10px] text-red-400">{Math.round(card.win_rate * 100)}% WR</span>
        <span className="text-gray-600 mx-1.5">·</span>
        <span className="text-[10px] text-gray-500">
          {card.games_seen} of {card.total_games} games
        </span>
        <button
          onClick={() => onAsk(card.cta_message)}
          className="ml-auto text-[10px] bg-indigo-600 hover:bg-indigo-500 text-white px-2 py-1 rounded transition-colors"
        >
          Ask Claude →
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript build passes**

```bash
npm run build 2>&1 | head -40
```

Expected: build completes with zero TypeScript errors

- [ ] **Step 3: Commit**

```bash
git add src/chat/FocusCard.tsx
git commit -m "feat: add FocusCard component"
```

---

### Task 4: Integrate FocusCard into App.tsx

**Files:**
- Modify: `src/chat/App.tsx`

- [ ] **Step 1: Add imports for `FocusCard` and `FocusCardData`**

In `src/chat/App.tsx`, find:

```tsx
import { TrendChart } from './TrendChart'
```

Replace with:

```tsx
import { TrendChart } from './TrendChart'
import { FocusCard, FocusCardData } from './FocusCard'
```

- [ ] **Step 2: Add `focusCard` state**

Find:

```tsx
  const [matchesError, setMatchesError] = useState(false)
```

Replace with:

```tsx
  const [matchesError, setMatchesError] = useState(false)
  const [focusCard, setFocusCard] = useState<FocusCardData | null>(null)
```

- [ ] **Step 3: Add `useEffect` to fetch `/focus` on mount**

Find:

```tsx
  useEffect(() => {
    if (!isSetup) return
    fetch(`http://localhost:${port}/patterns`)
```

Insert before it:

```tsx
  useEffect(() => {
    if (!isSetup) return
    fetch(`http://localhost:${port}/focus`)
      .then(r => r.ok ? r.json() : null)
      .then(data => setFocusCard(data as FocusCardData | null))
      .catch(() => {})
  }, [port, isSetup])

```

- [ ] **Step 4: Render `<FocusCard>` above pattern pills in the Chat tab**

Find:

```tsx
      {/* Chat tab */}
      {tab === 'chat' && (
        <>
          {patterns.length > 0 && (
```

Replace with:

```tsx
      {/* Chat tab */}
      {tab === 'chat' && (
        <>
          {focusCard && (
            <FocusCard card={focusCard} onAsk={sendMessage} />
          )}
          {patterns.length > 0 && (
```

- [ ] **Step 5: Build and verify**

```bash
npm run build
```

Expected: zero TypeScript errors, build completes

- [ ] **Step 6: Commit**

```bash
git add src/chat/App.tsx
git commit -m "feat: integrate FocusCard into Chat tab"
```

---

### Task 5: End-to-end verification

No code changes — verify the complete feature.

- [ ] **Step 1: Run the full sidecar test suite**

```bash
cd sidecar && python -m pytest --tb=short -q
```

Expected: all tests pass; the 3 new `generate_focus_card` tests from Task 1 are included

- [ ] **Step 2: Seed focus card via admin endpoint**

With the sidecar running (requires `RIOT_API_KEY` and `GEMINI_API_KEY` in env):

```bash
# Trigger reanalysis to ensure patterns exist and focus card is generated
curl -X POST http://127.0.0.1:8765/admin/reanalyze-all
# Then fetch the focus card
curl http://127.0.0.1:8765/focus
```

Expected: JSON response with all 8 fields: `moment_type`, `display`, `coaching_sentence`, `cta_message`, `win_rate`, `games_seen`, `total_games`, `streak_clean`

- [ ] **Step 3: Visual check in the app**

Start with `npm run dev`. Open the Chat tab. Verify:
- Focus card appears above pattern pills (only when patterns exist)
- Card shows display name, coaching sentence, win rate, and game count
- Green streak bar appears only when `streak_clean >= 1`
- Clicking "Ask Claude →" auto-sends the CTA message and a response appears

- [ ] **Step 4: Verify null case**

If no patterns exist (e.g. new player with fewer than 5 games analyzed), `/focus` should return `null`. In that state the card should be hidden entirely (not an empty container).
