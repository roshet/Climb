# Dynamic Counterfactual Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make per-game coaching notes pattern-aware (referencing the player's cross-game history) and improve prompt structure with role-specific guidance and a tighter 3-sentence format.

**Architecture:** `generate_coaching_notes` in `claude_client.py` gains an optional `patterns` parameter. A new `_build_pattern_context` helper formats pattern data into a prompt block. `analyze_and_save_match` in `backfill.py` calls `detect_patterns(db_session)` and passes the result in. The static fallback in `counterfactual.py` is untouched.

**Tech Stack:** Python 3.11+, Google Generative AI (Gemini), pytest

---

## File Structure

- **Modify:** `sidecar/claude_client.py` — add `ROLE_GUIDANCE` dict, `_build_pattern_context` helper, update `generate_coaching_notes` signature and prompt
- **Modify:** `sidecar/backfill.py` — import `detect_patterns`, call it before `generate_coaching_notes`, pass result in
- **Modify:** `sidecar/tests/test_claude_client.py` — 3 new tests for pattern injection
- **Modify:** `sidecar/tests/test_backfill.py` — 1 new test verifying patterns kwarg is passed

---

### Task 1: Pattern-aware prompt in `claude_client.py`

**Files:**
- Modify: `sidecar/claude_client.py`
- Modify: `sidecar/tests/test_claude_client.py`

**Context:** `ClaudeClient.__init__` calls `genai.Client(api_key=api_key)` and stores it as `self.client`. `generate_coaching_notes` calls `self.client.models.generate_content(model=self.model_name, contents=prompt)`. Tests mock `genai.Client` at construction time and then set `client.client.models.generate_content.return_value` to a fake response object. `PatternResult` is a dataclass in `sidecar/pattern_detector.py` with fields: `moment_type: str`, `label: Literal["recurring_issue", "win_condition"]`, `games_seen: int`, `total_games: int`, `win_rate_with: float`, `overall_win_rate: float`, `summary: str`.

- [ ] **Step 1: Write failing tests**

Append to `sidecar/tests/test_claude_client.py`:

```python
from unittest.mock import patch
from timeline_analyzer import PivotalMomentData
from pattern_detector import PatternResult


def _make_coaching_client():
    db = MagicMock()
    with patch("claude_client.genai.Client"):
        client = ClaudeClient(api_key="test", db=db)
    mock_response = MagicMock()
    mock_response.text = '[{"id": 0, "coaching": "test note"}]'
    client.client.models.generate_content.return_value = mock_response
    return client


def _make_moment():
    return PivotalMomentData(
        timestamp_secs=300,
        moment_type="lane_death",
        description="You died at 5:00",
        counterfactual="",
        gold_impact=300,
    )


def _make_game_context():
    return {
        "participant_id": 1,
        "champion": "Caitlyn",
        "role": "BOTTOM",
        "side": "blue",
        "result": "loss",
        "kda": "3/7/4",
        "duration_secs": 2052,
    }


def test_generate_coaching_notes_without_patterns():
    client = _make_coaching_client()
    client.generate_coaching_notes(
        [_make_moment()], _make_game_context(), {"info": {"frames": []}}, patterns=None
    )
    prompt = client.client.models.generate_content.call_args[1]["contents"]
    assert "Player's cross-game patterns" not in prompt


def test_generate_coaching_notes_with_patterns():
    client = _make_coaching_client()
    patterns = [
        PatternResult(
            moment_type="objective_missed",
            label="recurring_issue",
            games_seen=9,
            total_games=20,
            win_rate_with=0.44,
            overall_win_rate=0.55,
            summary="missed objectives in 9 of your last 20 games (44% win rate)",
        ),
        PatternResult(
            moment_type="baron_secured",
            label="win_condition",
            games_seen=3,
            total_games=20,
            win_rate_with=1.0,
            overall_win_rate=0.55,
            summary="baron secured in 3 of your last 20 games (100% win rate)",
        ),
    ]
    client.generate_coaching_notes(
        [_make_moment()], _make_game_context(), {"info": {"frames": []}}, patterns=patterns
    )
    prompt = client.client.models.generate_content.call_args[1]["contents"]
    assert "Player's cross-game patterns" in prompt
    assert "Recurring issues:" in prompt
    assert "objective_missed" in prompt
    assert "Win conditions:" in prompt
    assert "baron_secured" in prompt


def test_generate_coaching_notes_with_empty_patterns():
    client = _make_coaching_client()
    client.generate_coaching_notes(
        [_make_moment()], _make_game_context(), {"info": {"frames": []}}, patterns=[]
    )
    prompt = client.client.models.generate_content.call_args[1]["contents"]
    assert "Player's cross-game patterns" not in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar
venv/Scripts/pytest tests/test_claude_client.py::test_generate_coaching_notes_without_patterns tests/test_claude_client.py::test_generate_coaching_notes_with_patterns tests/test_claude_client.py::test_generate_coaching_notes_with_empty_patterns -v
```

Expected: `FAILED` — `TypeError: generate_coaching_notes() got an unexpected keyword argument 'patterns'`

- [ ] **Step 3: Add `ROLE_GUIDANCE`, `_build_pattern_context`, and update `generate_coaching_notes`**

At the top of `sidecar/claude_client.py`, after the existing imports, add:

```python
ROLE_GUIDANCE: dict[str, str] = {
    "TOP": "Focus on wave management, split push decisions, and teleport usage. Reference the lane opponent and proximity of the enemy jungler.",
    "JUNGLE": "Focus on pathing efficiency, objective timing, and gank setup. Reference which lanes were ahead/behind and dragon/baron spawn timers.",
    "MIDDLE": "Focus on roam timing, wave control before leaving lane, and mid-game priority. Reference the lane opponent and river vision.",
    "BOTTOM": "Focus on CS efficiency, lane partner synergy, and positioning relative to the support. Reference the lane opponent and tower pressure.",
    "UTILITY": "Focus on vision control, peel timing, and roam opportunities. Reference ward placements and support item usage.",
}

_ROLE_GUIDANCE_FALLBACK = "Focus on positioning, objective control, and decision-making at the moment of the event."


def _build_pattern_context(patterns: list) -> str:
    if not patterns:
        return ""
    issues = [p for p in patterns if p.label == "recurring_issue"]
    wins = [p for p in patterns if p.label == "win_condition"]
    lines = ["Player's cross-game patterns (last 20 games):"]
    if issues:
        issue_str = ", ".join(
            f"{p.moment_type} ({p.games_seen}/{p.total_games} games, {int(p.win_rate_with * 100)}% WR)"
            for p in issues
        )
        lines.append(f"Recurring issues: {issue_str}")
    if wins:
        win_str = ", ".join(
            f"{p.moment_type} ({p.games_seen}/{p.total_games} games, {int(p.win_rate_with * 100)}% WR)"
            for p in wins
        )
        lines.append(f"Win conditions: {win_str}")
    lines.append(
        "\nWhen writing coaching notes, reference these patterns where relevant. "
        "For example, if the player has a recurring issue and this moment involves that same problem, "
        "note that this is part of a broader pattern across their games."
    )
    return "\n".join(lines)
```

Replace the `generate_coaching_notes` method signature and prompt-building section:

```python
    def generate_coaching_notes(
        self,
        moments: list,
        game_context: dict,
        timeline: dict,
        patterns: list | None = None,
    ) -> list:
        """
        Generate AI coaching notes for all moments in a single Gemini call.
        Falls back to counterfactual.enrich_moments on failure.
        Mutates and returns the moments list with counterfactual filled in.
        """
        from counterfactual import enrich_moments as fallback_enrich

        if not moments:
            return moments

        participant_id = game_context.get("participant_id", 1)

        # Collect all events from timeline for context window lookups
        all_events: list[dict] = []
        for frame in timeline.get("info", {}).get("frames", []):
            all_events.extend(frame.get("events", []))

        # Build game context header
        champion = game_context.get("champion", "Unknown")
        role = game_context.get("role", "JUNGLE")
        side = game_context.get("side", "blue")
        result = game_context.get("result", "unknown")
        kda = game_context.get("kda", "0/0/0")
        duration_secs = game_context.get("duration_secs", 0)
        dur_mins, dur_secs_r = divmod(duration_secs, 60)
        header = (
            f"Champion: {champion} | Role: {role} | Side: {side} side\n"
            f"Result: {result.upper()} | KDA: {kda} | Duration: {dur_mins}:{dur_secs_r:02d}"
        )

        # Build one block per moment
        moment_blocks = []
        for i, m in enumerate(moments):
            ctx = _build_context_window(all_events, m.timestamp_secs, participant_id)
            moment_blocks.append(
                f"[{i}] {m.moment_type} — {m.description}\n"
                f"Context (±90s):\n{ctx}"
            )

        moments_text = "\n---\n".join(moment_blocks)

        # Build prompt parts
        prompt_parts: list[str] = []
        pattern_block = _build_pattern_context(patterns or [])
        if pattern_block:
            prompt_parts.append(pattern_block)
            prompt_parts.append("")

        role_guidance = ROLE_GUIDANCE.get(role, _ROLE_GUIDANCE_FALLBACK)

        prompt_parts.append(
            f"You are coaching a {champion} {role.lower()}. {header}\n\n"
            f"For each moment below, write a coaching note in exactly 3 sentences:\n"
            f"- Sentence 1: What happened and the game state at that moment (reference surrounding context)\n"
            f"- Sentence 2: Why it mattered — the impact on gold, objectives, or map control\n"
            f"- Sentence 3: One concrete, achievable alternative action specific to a {role.lower()} player\n\n"
            f"Role-specific guidance for {role.lower()}:\n{role_guidance}\n\n"
            f"Tone: encouraging for positive moments (solo_kill, objective_secured, roam_kill, roam_assist, "
            f"ward_kill, baron_secured, dragon_stack, gank_assist). "
            f"Describe game state without moralizing for mistakes.\n\n"
            f"{moments_text}\n\n"
            f"Return ONLY valid JSON, no other text: "
            f'[{{"id": 0, "coaching": "..."}}, ...]'
        )

        prompt = "\n".join(prompt_parts)

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            raw = response.text.strip()
            # Strip markdown code fences if Gemini wraps with ```json ... ```
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            coaching_list = json.loads(raw)
            coaching_map = {item["id"]: item["coaching"] for item in coaching_list}
            for i, m in enumerate(moments):
                if i in coaching_map:
                    m.counterfactual = coaching_map[i]
        except Exception as e:
            print(f"[coaching] Gemini call failed ({e}). Using static fallback.")
            fallback_enrich(moments)

        return moments
```

- [ ] **Step 4: Run the 3 new tests**

```
cd sidecar
venv/Scripts/pytest tests/test_claude_client.py::test_generate_coaching_notes_without_patterns tests/test_claude_client.py::test_generate_coaching_notes_with_patterns tests/test_claude_client.py::test_generate_coaching_notes_with_empty_patterns -v
```

Expected: All 3 PASS.

- [ ] **Step 5: Run full suite to confirm no regressions**

```
cd sidecar
venv/Scripts/pytest tests/ -v
```

Expected: All tests PASS (124 + 3 = 127 passing).

- [ ] **Step 6: Commit**

```bash
git add sidecar/claude_client.py sidecar/tests/test_claude_client.py
git commit -m "feat: pattern-aware coaching notes with role-specific prompt improvements"
```

---

### Task 2: Wire `detect_patterns` into `backfill.py`

**Files:**
- Modify: `sidecar/backfill.py`
- Modify: `sidecar/tests/test_backfill.py`

**Context:** `backfill.py` already imports from `pattern_detector` indirectly via `main.py`. The import needs to be added explicitly here. `analyze_and_save_match` currently calls `claude_client.generate_coaching_notes(moments, game_context, timeline_data)` on line 82. The change wraps `detect_patterns` in a try/except and passes the result as `patterns=game_patterns`. The existing backfill tests mock `claude_client.generate_coaching_notes` via `mock_claude = MagicMock()` and `mock_claude.generate_coaching_notes.return_value = []`.

- [ ] **Step 1: Write failing test**

Append to `sidecar/tests/test_backfill.py`:

```python
@pytest.mark.asyncio
async def test_analyze_and_save_match_passes_patterns_kwarg(db):
    from backfill import analyze_and_save_match

    mock_riot = make_mock_riot(["NA1_NEW"])
    mock_claude = make_mock_claude()
    player = make_player()

    with patch("backfill.asyncio.sleep", new_callable=AsyncMock):
        await analyze_and_save_match(mock_riot, db, mock_claude, player, "NA1_NEW")

    call_kwargs = mock_claude.generate_coaching_notes.call_args[1]
    assert "patterns" in call_kwargs
```

- [ ] **Step 2: Run test to verify it fails**

```
cd sidecar
venv/Scripts/pytest tests/test_backfill.py::test_analyze_and_save_match_passes_patterns_kwarg -v
```

Expected: `FAILED` — `AssertionError: assert "patterns" in {}`

- [ ] **Step 3: Update `backfill.py`**

Add to the imports at the top of `sidecar/backfill.py` (after the existing `from database import ...` line):

```python
from pattern_detector import detect_patterns
```

Replace line 82 in `sidecar/backfill.py`:

```python
    enriched = claude_client.generate_coaching_notes(moments, game_context, timeline_data)
```

With:

```python
    try:
        game_patterns = detect_patterns(db_session)
    except Exception:
        game_patterns = None
    enriched = claude_client.generate_coaching_notes(moments, game_context, timeline_data, patterns=game_patterns)
```

- [ ] **Step 4: Run new test**

```
cd sidecar
venv/Scripts/pytest tests/test_backfill.py::test_analyze_and_save_match_passes_patterns_kwarg -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite**

```
cd sidecar
venv/Scripts/pytest tests/ -v
```

Expected: All 128 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add sidecar/backfill.py sidecar/tests/test_backfill.py
git commit -m "feat: pass cross-game patterns into coaching note generation"
```

---

## Self-Review

**Spec coverage:**
- ✅ `patterns: list | None = None` parameter added to `generate_coaching_notes` — Task 1, Step 3
- ✅ `_build_pattern_context` helper formats recurring issues and win conditions — Task 1, Step 3
- ✅ Pattern block omitted when `patterns` is `None` or `[]` — Task 1, Step 3 + tests
- ✅ `ROLE_GUIDANCE` dict with 5 roles + fallback — Task 1, Step 3
- ✅ Improved 3-sentence prompt format — Task 1, Step 3
- ✅ `detect_patterns` called in `analyze_and_save_match` with try/except — Task 2, Step 3
- ✅ `game_patterns` passed as `patterns=` kwarg — Task 2, Step 3
- ✅ 3 prompt injection tests — Task 1, Step 1
- ✅ 1 wiring test verifying `patterns` kwarg — Task 2, Step 1
- ✅ Static fallback (`counterfactual.enrich_moments`) unchanged

**Placeholder scan:** No TBDs. All code blocks complete.

**Type consistency:** `patterns: list | None = None` in `generate_coaching_notes` matches `game_patterns = detect_patterns(db_session)` call site — `detect_patterns` returns `list[PatternResult]` which satisfies `list`. `_build_pattern_context` receives `list` and accesses `.label`, `.moment_type`, `.games_seen`, `.total_games`, `.win_rate_with` — all fields on `PatternResult`.
