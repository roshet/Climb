# Matchup Tracking Design

## Goal

Store the lane opponent's champion for each game and surface win rate + dominant loss moment for tough matchups — in the champ select overlay (before the game) and the chat tab (for reflection).

## Context

The `/focus` and pattern systems already give the player habit-based coaching across all games. Matchup tracking adds a second lens: "you specifically struggle vs Draven — and it's mostly lane_death." The data (lane opponent participant index) is already computed in `backfill.py` but the champion name is never extracted or stored.

## Architecture

Two independent tracks. Backend first: add the column, update backfill, add stats function and endpoints. Frontend second: add the matchup section to each surface.

**Files changed:**
- `sidecar/database.py` — add `lane_opponent_champion` column to `Match`
- `sidecar/backfill.py` — extract and store opponent champion name; update existing NULL rows
- `sidecar/main.py` — add `_get_matchup_stats()` function; wire into `/champ-select` and new `/matchups` endpoint
- `sidecar/tests/test_matchup_stats.py` — new test file for `_get_matchup_stats`
- `src/champ-select/ChampSelectOverlay.tsx` — add matchup section
- `src/chat/App.tsx` — fetch `/matchups`, add matchup section below pattern buttons

## Backend Changes

### DB column

Add one nullable column to `Match`:

```python
lane_opponent_champion: Mapped[Optional[str]] = mapped_column(String, nullable=True)
```

SQLAlchemy's `Base.metadata.create_all` does not auto-migrate existing tables. The column is added via a raw ALTER TABLE in `init_db()`:

```python
from sqlalchemy import text

def init_db(db_path: str = "analyst.db") -> Engine:
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE matches ADD COLUMN lane_opponent_champion TEXT"))
            conn.commit()
        except Exception:
            pass  # column already exists
    return engine
```

### Backfill extraction

In `backfill.py`, `lane_opponent_entry` is already computed. Extract champion name and pass it to `save_match`:

```python
lane_opponent_champion = lane_opponent_entry[1]["championName"] if lane_opponent_entry else None
```

Add to the `save_match` call:
```python
"lane_opponent_champion": lane_opponent_champion,
```

**Backfilling existing rows:** Backfill currently skips matches already in DB. Modify it to also update `lane_opponent_champion` for existing matches where it is NULL:

```python
existing = db_session.get(Match, match_id)
if existing is not None:
    if existing.lane_opponent_champion is None and lane_opponent_champion:
        existing.lane_opponent_champion = lane_opponent_champion
        db_session.commit()
    return
```

### `_get_matchup_stats` function

Pure function, extracted for testability. Returns the player's worst matchups sorted by win rate ascending.

```python
def _get_matchup_stats(
    db: Session,
    matches: list[Match],
    min_games: int = 3,
    top_n: int = 5,
) -> list[dict]:
```

**Logic:**
1. Filter matches where `lane_opponent_champion` is not None
2. Group by `lane_opponent_champion`
3. For each group with `len >= min_games`:
   - Compute `wins`, `losses`, `win_rate`
   - Find dominant moment: query `PivotalMoment` rows for the loss match IDs in this group, count by `moment_type`, take the most common; None if no moments. Alphabetical tiebreak.
4. Sort ascending by `win_rate`, return top `top_n`

**Return shape (per entry):**
```python
{
    "opponent": "Draven",
    "wins": 1,
    "losses": 4,
    "win_rate": 0.2,
    "dominant_moment": "lane_death",  # or None
}
```

### `/matchups` endpoint

New endpoint, no parameters. Returns top 5 worst matchups across all champions.

```python
@app.get("/matchups")
def get_matchups(db: Session = Depends(get_db)):
    matches = get_matches(db, last_n=100)
    return {"matchups": _get_matchup_stats(db, matches, min_games=3, top_n=5)}
```

### `/champ-select` response

Add `matchups` field to the existing response — top 3 worst for the locked champion only.

```python
champ_matches = get_matches(db, champion=champion_name, last_n=50)
matchups = _get_matchup_stats(db, champ_matches, min_games=3, top_n=3)
# add to return dict:
"matchups": matchups,
```

## Frontend Changes

### Champ select overlay

In `src/champ-select/ChampSelectOverlay.tsx`, add a "your tough matchups" section below the existing patterns block. Only render when `champ_data.matchups` has at least one entry:

```tsx
{champData.matchups && champData.matchups.length > 0 && (
  <div className="mt-2 pt-2 border-t border-white/10">
    <div className="text-[8px] uppercase tracking-widest text-gray-500 mb-1.5">your tough matchups</div>
    {champData.matchups.map((m) => (
      <div key={m.opponent} className="flex justify-between items-center mb-1">
        <div>
          <span className="text-[10px] text-gray-200">{m.opponent}</span>
          {m.dominant_moment && (
            <span className="text-[8px] text-gray-500 ml-1">{m.dominant_moment}</span>
          )}
        </div>
        <span className={`text-[10px] font-bold ${m.win_rate < 0.4 ? 'text-red-400' : 'text-yellow-400'}`}>
          {m.wins}W {m.losses}L
        </span>
      </div>
    ))}
  </div>
)}
```

Update `ChampData` interface to include:
```tsx
matchups?: Array<{
  opponent: string
  wins: number
  losses: number
  win_rate: number
  dominant_moment: string | null
}>
```

### Chat tab

In `src/chat/App.tsx`:
- Add `matchups` state: `useState<MatchupEntry[]>([])`
- Fetch `/matchups` on mount (alongside patterns)
- Render a "tough matchups" section below the pattern buttons, same layout as champ select but with win rate percentage shown

```tsx
{matchups.length > 0 && (
  <div className="mt-3 pt-3 border-t border-white/10">
    <div className="text-[8px] uppercase tracking-widest text-gray-500 mb-2">tough matchups</div>
    {matchups.map((m) => (
      <div key={m.opponent} className="flex justify-between items-center mb-1.5">
        <div>
          <span className="text-[10px] text-gray-200">vs {m.opponent}</span>
          {m.dominant_moment && (
            <span className="text-[8px] text-gray-500 ml-1">{m.dominant_moment}</span>
          )}
        </div>
        <span className={`text-[10px] font-bold ${m.win_rate < 0.4 ? 'text-red-400' : 'text-yellow-400'}`}>
          {m.wins}W {m.losses}L · {Math.round(m.win_rate * 100)}%
        </span>
      </div>
    ))}
  </div>
)}
```

Add `MatchupEntry` interface in `App.tsx`:
```tsx
interface MatchupEntry {
  opponent: string
  wins: number
  losses: number
  win_rate: number
  dominant_moment: string | null
}
```

## Edge Cases

| Scenario | Behaviour |
|---|---|
| Fewer than 3 games vs an opponent | Not shown |
| No matchups meet the threshold | Section hidden (empty array) |
| `lane_opponent_champion` is NULL (old match, API unavailable) | Excluded from stats |
| Dominant moment tie | Alphabetical tiebreak (sort by moment_type, take first) |
| Opponent had no role set (UNKNOWN teamPosition) | `lane_opponent_champion` stored as None, excluded from stats |

## What This Is Not

- No per-opponent pattern detection (just moment frequency in losses, not win-rate-relative recurring issues)
- No enemy jungler matchup tracking (lane opponent only)
- No UI to click into a matchup for details — matchup rows are display-only in v1
