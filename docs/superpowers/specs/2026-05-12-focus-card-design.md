# Focus for Next Game — Design Spec

## Overview

A persistent coaching card at the top of the Chat tab that surfaces the player's single biggest recurring issue and gives them a one-tap path to getting coached on it. Powered by a Claude-generated sentence after every game, cached in `AppState`, and updated automatically so it always reflects the player's current weaknesses.

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Placement | Top of Chat tab (above pattern pills) | Same screen as chat; CTA flows directly into conversation below |
| Content density | Medium — name + coaching sentence + win rate + streak indicator | Enough context to understand the problem; not so much that it crowds the chat |
| Coaching sentence source | Gemini-generated, cached in `AppState` | Personalized to actual stats; one call per game, zero latency on render |
| CTA behavior | Auto-send prefilled message | Lowest friction path to coaching value |
| Improvement indicator | Show when `streak_clean >= 1` | Motivating and uses already-computed improvement data |
| Storage | `AppState` key `focus_card` | No schema migration; same pattern as `pending_popup` and `open_chat` |

---

## Architecture

```
[Post-game analysis / Backfill]
       │
       ▼
detect_patterns(db) → top recurring issue
       │
       ▼
claude_client.generate_focus_card(pattern, summoner_name)
       │  returns {coaching_sentence, cta_message}
       ▼
AppState(key="focus_card", value=json_string)

[Frontend mount]
       │
       ▼
GET /focus
  reads AppState "focus_card"
  + fresh stats from detect_patterns()
  + streak_clean from get_improvement_data()
       │
       ▼
<FocusCard /> rendered above pattern pills
```

---

## Backend

### `sidecar/claude_client.py`

New method `generate_focus_card(pattern, summoner_name: str) -> dict`:

- `pattern` is a `PatternResult` (moment_type, games_seen, total_games, win_rate_with, overall_win_rate, summary)
- Sends a single `generate_content` call (no tools, no chat session) to Gemini
- Prompt asks for two things:
  1. `coaching_sentence`: 1–2 sentences, specific to the player's actual numbers, describing what's happening and one concrete fix
  2. `cta_message`: first-person question the player would ask Claude (e.g. "I keep getting caught in my jungle early — walk me through how to fix this")
- Returns `{"coaching_sentence": str, "cta_message": str}`
- On failure: returns `{"coaching_sentence": pattern.summary, "cta_message": f"Help me fix my {pattern.moment_type} habit."}`

**Prompt structure:**

```
You are a League of Legends coach. Write a focus card for a player with this recurring issue:

Pattern: {pattern.moment_type}
Frequency: {pattern.games_seen} of last {pattern.total_games} games
Win rate with this issue: {win_rate_with_pct}% (overall: {overall_pct}%)

Return ONLY valid JSON: {"coaching_sentence": "...", "cta_message": "..."}

coaching_sentence: 1-2 sentences. Use the player's actual numbers. Describe what's going wrong and one concrete fix.
cta_message: The first-person question {summoner_name} would ask a coach. Start with "I" and end with a question mark.
```

### `sidecar/main.py`

**Trigger 1 — after each game**: At the end of `run_post_game_analysis()`, after `set_pending_popup()`:

```python
patterns = detect_patterns(db)
top_issue = next((p for p in patterns if p.label == "recurring_issue"), None)
if top_issue:
    player = get_player(db)
    focus = claude.generate_focus_card(top_issue, player.summoner_name)
    db.merge(AppState(key="focus_card", value=json.dumps(focus)))
    db.commit()
```

**Trigger 2 — after backfill**: At the end of `backfill_history()`, same logic, so the card is populated immediately on first launch.

**New endpoint `GET /focus`**:

```python
@app.get("/focus")
def get_focus():
    row = db.query(AppState).filter(AppState.key == "focus_card").first()
    if not row or not row.value:
        return None
    stored = json.loads(row.value)
    # Get fresh live stats
    patterns = detect_patterns(db)
    top_issue = next((p for p in patterns if p.label == "recurring_issue"), None)
    if not top_issue:
        return None
    # Compute streak_clean across ALL champions (improvement_tracker is per-champion)
    recent_matches = get_matches(db, last_n=20)
    recent_ids = [m.match_id for m in recent_matches]
    recent_moments = get_pivotal_moments(db, recent_ids)
    moments_by_match: dict[str, set] = {}
    for m in recent_moments:
        moments_by_match.setdefault(m.match_id, set()).add(m.moment_type)
    streak_clean = 0
    for mid in recent_ids:  # newest first
        if top_issue.moment_type not in moments_by_match.get(mid, set()):
            streak_clean += 1
        else:
            break
    # Readable display label using existing MOMENT_LABELS map
    from champ_select_monitor import MOMENT_LABELS
    display = MOMENT_LABELS.get(top_issue.moment_type, top_issue.moment_type.replace("_", " ").title())
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

**Imports to add**: `json` (already present). `MOMENT_LABELS` imported locally inside the function to avoid circular import risk.

---

## Frontend

### New `src/chat/FocusCard.tsx`

Props:
```ts
interface FocusCardData {
  moment_type: string
  display: string           // human-readable label, e.g. "Early jungle deaths"
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
```

Renders:
- `🎯 FOCUS FOR NEXT GAME` label (purple, small caps)
- Pattern name (white, bold) — use `card.display` (the server resolves it via `MOMENT_LABELS`)
- Coaching sentence (gray body text)
- If `streak_clean >= 1`: green bar — `↑ Clean last {streak_clean} game{s} — keep it up`
- Bottom row: red win rate, game count, purple "Ask Claude →" button
- Button `onClick`: calls `onAsk(card.cta_message)`

### Modified `src/chat/App.tsx`

- Import `FocusCard` and `FocusCardData`
- New state: `const [focusCard, setFocusCard] = useState<FocusCardData | null>(null)`
- New fetch on mount:
  ```ts
  useEffect(() => {
    fetch(`http://127.0.0.1:${port}/focus`)
      .then(r => r.ok ? r.json() : null)
      .then(data => setFocusCard(data))
      .catch(() => {})
  }, [port])
  ```
- Re-fetch after each chat response (so it updates if a new game just completed)
- Render `{focusCard && <FocusCard card={focusCard} onAsk={handleFocusAsk} />}` between TrendChart and pattern pills
- `handleFocusAsk`: sets the message and triggers the existing send flow

---

## API Contract

```
GET /focus
→ null                          (no patterns yet — card hidden)
→ {
    moment_type: string,
    display: string,            // human-readable, e.g. "Early Jungle Deaths"
    coaching_sentence: string,
    cta_message: string,
    win_rate: number,           (0–1)
    games_seen: number,
    total_games: number,
    streak_clean: number        (0 = not clean recently; ≥1 = clean N games)
  }
```

---

## Edge Cases

| Case | Behavior |
|---|---|
| No patterns yet (< 5 games) | `/focus` returns `null`; frontend hides card entirely |
| Gemini call fails during generation | Falls back to `pattern.summary` + generic CTA; card still shows |
| Player has no recurring issues (all win conditions) | `/focus` returns `null`; card hidden |
| Backfill still running | Card shows as soon as backfill completes and patterns exist |
| streak_clean = 0 | No green bar; coaching sentence + stats only |

---

## What Doesn't Change

- No database schema migrations
- TrendChart, pattern pills, chat input — untouched
- Post-game analysis timing and popup flow — untouched
- Pattern detection logic — untouched
