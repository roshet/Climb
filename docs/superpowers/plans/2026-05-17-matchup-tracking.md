# Matchup Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store the lane opponent's champion for each game and surface win rate + dominant loss moment for tough matchups in the champ select overlay and chat tab.

**Architecture:** Six tasks in two independent tracks. Backend (Tasks 1–4): add a nullable `lane_opponent_champion` column to the `Match` table, extract it during backfill, implement `_get_matchup_stats()` as a testable pure function, then wire it into a new `/matchups` endpoint and the existing `/champ-select` endpoint. Frontend (Tasks 5–6): add the matchup section to the champ select overlay and the chat tab.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy / SQLite (backend), React 18 / TypeScript / Tailwind CSS (frontend). No frontend test framework — frontend verification is `npm run build` + manual.

---

### Task 1: Add `lane_opponent_champion` column to the database

**Files:**
- Modify: `sidecar/database.py`
- Modify: `sidecar/tests/test_database.py`

**Context:** The `Match` model uses SQLAlchemy's `Mapped` columns (see line 12–25 of `database.py`). The DB is a persistent SQLite file, so adding a column to the model is not enough — `create_all` does not ALTER existing tables. A try/except ALTER TABLE is the established pattern for SQLite migrations in this project.

The test DB is created fresh from `Base.metadata.create_all(engine)` in `conftest.py`, so new nullable columns are included automatically in tests.

---

- [ ] **Step 1: Add the column to the `Match` model**

In `sidecar/database.py`, add one line to the `Match` class after `raw_timeline`:

```python
class Match(Base):
    __tablename__ = "matches"
    match_id: Mapped[str] = mapped_column(String, primary_key=True)
    played_at: Mapped[datetime] = mapped_column(DateTime)
    champion: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    result: Mapped[str] = mapped_column(String)
    duration_secs: Mapped[int] = mapped_column(Integer)
    kda: Mapped[str] = mapped_column(String)
    cs: Mapped[int] = mapped_column(Integer)
    gold_earned: Mapped[int] = mapped_column(Integer)
    vision_score: Mapped[int] = mapped_column(Integer)
    raw_timeline: Mapped[dict] = mapped_column(JSON)
    lane_opponent_champion: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    moments: Mapped[list["PivotalMoment"]] = relationship(back_populates="match")
```

- [ ] **Step 2: Add the ALTER TABLE migration to `init_db`**

Replace the existing `init_db` function in `sidecar/database.py`:

```python
from sqlalchemy import create_engine, String, Integer, DateTime, JSON, ForeignKey, Text, Engine, text

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

Note: `text` must be added to the `sqlalchemy` import at the top of the file:

```python
from sqlalchemy import create_engine, String, Integer, DateTime, JSON, ForeignKey, Text, Engine, text
```

- [ ] **Step 3: Write a failing test**

Add to `sidecar/tests/test_database.py`:

```python
def test_save_and_retrieve_lane_opponent_champion(db):
    save_match(db, {
        "match_id": "NA1_opp1",
        "played_at": datetime(2026, 4, 1, 20, 0),
        "champion": "Caitlyn",
        "role": "BOTTOM",
        "result": "loss",
        "duration_secs": 1800,
        "kda": "2/5/3",
        "cs": 120,
        "gold_earned": 9000,
        "vision_score": 15,
        "raw_timeline": {},
        "lane_opponent_champion": "Draven",
    })
    matches = get_matches(db)
    assert matches[0].lane_opponent_champion == "Draven"


def test_lane_opponent_champion_nullable(db):
    save_match(db, {
        "match_id": "NA1_opp2",
        "played_at": datetime(2026, 4, 2, 20, 0),
        "champion": "Caitlyn",
        "role": "BOTTOM",
        "result": "win",
        "duration_secs": 1800,
        "kda": "8/2/5",
        "cs": 200,
        "gold_earned": 14000,
        "vision_score": 25,
        "raw_timeline": {},
    })
    matches = get_matches(db)
    assert matches[0].lane_opponent_champion is None
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
cd sidecar && python -m pytest tests/test_database.py::test_save_and_retrieve_lane_opponent_champion tests/test_database.py::test_lane_opponent_champion_nullable -v
```

Expected: `AttributeError` or `TypeError` — column doesn't exist yet.

- [ ] **Step 5: Run tests after implementation to verify they pass**

```bash
cd sidecar && python -m pytest tests/test_database.py::test_save_and_retrieve_lane_opponent_champion tests/test_database.py::test_lane_opponent_champion_nullable -v
```

Expected: 2 PASS

- [ ] **Step 6: Run full test suite to check no regressions**

```bash
cd sidecar && python -m pytest --tb=short -q
```

Expected: all 213 existing tests pass + 2 new = 215 total.

- [ ] **Step 7: Commit**

```bash
git add sidecar/database.py sidecar/tests/test_database.py
git commit -m "feat: add lane_opponent_champion column to matches table"
```

---

### Task 2: Extract and store opponent champion in backfill

**Files:**
- Modify: `sidecar/backfill.py`
- Modify: `sidecar/tests/test_backfill.py`

**Context:** In `backfill.py`, `lane_opponent_entry` is already computed (line 43–49). It's a tuple of `(participant_index, participant_dict)` or `None`. The champion name is `lane_opponent_entry[1]["championName"]`. The `run_backfill` function currently only processes new match IDs; we also need it to fill in `lane_opponent_champion` for existing matches that have `NULL` (from before this feature).

`TEAM_100_IDS = {1, 2, 3, 4, 5}` — the player is on team 100 if their participant_index is in this set, meaning the enemy lane opponent is on team 200 (indices 6–10).

---

- [ ] **Step 1: Extract and pass `lane_opponent_champion` in `analyze_and_save_match`**

In `sidecar/backfill.py`, add one line after the `lane_opponent_id` assignment and update the `save_match` call:

```python
    lane_opponent_id = lane_opponent_entry[0] if lane_opponent_entry else None
    lane_opponent_champion = lane_opponent_entry[1]["championName"] if lane_opponent_entry else None

    save_match(db_session, {
        "match_id": match_id,
        "played_at": datetime.fromtimestamp(info["gameStartTimestamp"] / 1000, tz=timezone.utc),
        "champion": champion,
        "role": role,
        "result": "win" if participant["win"] else "loss",
        "duration_secs": info["gameDuration"],
        "kda": f"{participant['kills']}/{participant['deaths']}/{participant['assists']}",
        "cs": participant["totalMinionsKilled"],
        "gold_earned": participant["goldEarned"],
        "vision_score": participant["visionScore"],
        "raw_timeline": timeline_data,
        "lane_opponent_champion": lane_opponent_champion,
    })
```

- [ ] **Step 2: Add `_backfill_opponent_champions` to fill in existing NULL rows**

Add this function to `sidecar/backfill.py` immediately after `analyze_and_save_match`:

```python
async def _backfill_opponent_champions(riot_client, db_session, player) -> None:
    from database import Match
    null_rows = (
        db_session.query(Match)
        .filter(Match.lane_opponent_champion.is_(None))
        .limit(20)
        .all()
    )
    if not null_rows:
        return
    print(f"[backfill] Filling opponent champion for {len(null_rows)} existing matches")
    for match in null_rows:
        try:
            match_data = await riot_client.get_match(match.match_id)
            info = match_data["info"]
            participants = info["participants"]
            participant = next(
                (p for p in participants if p["puuid"] == player.riot_puuid), None
            )
            if not participant:
                continue
            participant_index = participants.index(participant) + 1
            player_team_ids = TEAM_100_IDS if participant_index in TEAM_100_IDS else TEAM_200_IDS
            role = participant.get("teamPosition", "UNKNOWN")
            lane_opponent_entry = next(
                ((i + 1, p) for i, p in enumerate(participants)
                 if (i + 1) not in player_team_ids
                 and p.get("teamPosition") == role),
                None,
            )
            if lane_opponent_entry:
                match.lane_opponent_champion = lane_opponent_entry[1]["championName"]
                db_session.commit()
            await asyncio.sleep(1)
        except Exception as e:
            print(f"[backfill] Could not update opponent for {match.match_id}: {e}")
```

- [ ] **Step 3: Call `_backfill_opponent_champions` at the end of `run_backfill`**

In `run_backfill`, add this after the `print(f"[backfill] Complete")` line at the end:

```python
    print(f"[backfill] Complete")
    await _backfill_opponent_champions(riot_client, db_session, player)
```

Wait — place it *before* the Complete print so the log sequence makes sense:

```python
async def run_backfill(riot_client, db_session, claude_client, player) -> None:
    start_time = int(datetime.now(timezone.utc).timestamp() - BACKFILL_DAYS * 24 * 3600)
    match_ids = await riot_client.get_recent_match_ids(
        player.riot_puuid, count=20, start_time=start_time
    )
    existing_ids = get_all_match_ids(db_session)
    new_ids = [mid for mid in match_ids if mid not in existing_ids]
    print(f"[backfill] {len(new_ids)} new matches to analyze")

    for match_id in new_ids:
        try:
            await analyze_and_save_match(riot_client, db_session, claude_client, player, match_id)
            await asyncio.sleep(3)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                print(f"[backfill] Rate limited — waiting 10s before retrying {match_id}")
                await asyncio.sleep(10)
                try:
                    await analyze_and_save_match(riot_client, db_session, claude_client, player, match_id)
                    await asyncio.sleep(3)
                except Exception as retry_err:
                    print(f"[backfill] Retry failed for {match_id}: {retry_err}")
            else:
                print(f"[backfill] HTTP error for {match_id}: {e}")
        except Exception as e:
            print(f"[backfill] Error processing {match_id}: {e}")

    await _backfill_opponent_champions(riot_client, db_session, player)
    print(f"[backfill] Complete")
```

- [ ] **Step 4: Write a failing test for opponent champion extraction**

Add to `sidecar/tests/test_backfill.py`. First, add sample data with a real lane opponent at the top of the file (alongside `SAMPLE_MATCH_DATA`):

```python
# 10-player match with Caitlyn (BOTTOM, team 100) vs Draven (BOTTOM, team 200)
SAMPLE_MATCH_WITH_OPPONENT = {
    "info": {
        "gameStartTimestamp": 1700000000000,
        "gameDuration": 1800,
        "participants": [
            # Team 100 (participant indices 1-5)
            {"puuid": PLAYER_PUUID, "championName": "Caitlyn", "teamPosition": "BOTTOM", "win": True,
             "kills": 5, "deaths": 2, "assists": 8, "totalMinionsKilled": 150, "goldEarned": 12000,
             "visionScore": 20, "summoner1Id": 4, "summoner2Id": 21},
            {"puuid": "t1-2", "championName": "Thresh", "teamPosition": "UTILITY", "win": True,
             "kills": 0, "deaths": 1, "assists": 10, "totalMinionsKilled": 20, "goldEarned": 8000,
             "visionScore": 30, "summoner1Id": 4, "summoner2Id": 21},
            {"puuid": "t1-3", "championName": "Ahri", "teamPosition": "MID", "win": True,
             "kills": 8, "deaths": 2, "assists": 5, "totalMinionsKilled": 200, "goldEarned": 15000,
             "visionScore": 15, "summoner1Id": 4, "summoner2Id": 21},
            {"puuid": "t1-4", "championName": "Vi", "teamPosition": "JUNGLE", "win": True,
             "kills": 4, "deaths": 2, "assists": 8, "totalMinionsKilled": 50, "goldEarned": 10000,
             "visionScore": 25, "summoner1Id": 11, "summoner2Id": 4},
            {"puuid": "t1-5", "championName": "Garen", "teamPosition": "TOP", "win": True,
             "kills": 2, "deaths": 2, "assists": 4, "totalMinionsKilled": 140, "goldEarned": 9000,
             "visionScore": 10, "summoner1Id": 4, "summoner2Id": 21},
            # Team 200 (participant indices 6-10)
            {"puuid": "t2-1", "championName": "Draven", "teamPosition": "BOTTOM", "win": False,
             "kills": 2, "deaths": 5, "assists": 3, "totalMinionsKilled": 120, "goldEarned": 9000,
             "visionScore": 15, "summoner1Id": 4, "summoner2Id": 21},
            {"puuid": "t2-2", "championName": "Lux", "teamPosition": "UTILITY", "win": False,
             "kills": 0, "deaths": 3, "assists": 5, "totalMinionsKilled": 10, "goldEarned": 7000,
             "visionScore": 20, "summoner1Id": 4, "summoner2Id": 21},
            {"puuid": "t2-3", "championName": "Syndra", "teamPosition": "MID", "win": False,
             "kills": 3, "deaths": 3, "assists": 2, "totalMinionsKilled": 140, "goldEarned": 9000,
             "visionScore": 12, "summoner1Id": 4, "summoner2Id": 21},
            {"puuid": "t2-4", "championName": "LeeSin", "teamPosition": "JUNGLE", "win": False,
             "kills": 2, "deaths": 4, "assists": 5, "totalMinionsKilled": 40, "goldEarned": 8000,
             "visionScore": 18, "summoner1Id": 11, "summoner2Id": 4},
            {"puuid": "t2-5", "championName": "Darius", "teamPosition": "TOP", "win": False,
             "kills": 3, "deaths": 3, "assists": 2, "totalMinionsKilled": 130, "goldEarned": 8500,
             "visionScore": 8, "summoner1Id": 4, "summoner2Id": 21},
        ],
    }
}
```

Then add the test:

```python
@pytest.mark.asyncio
async def test_backfill_stores_lane_opponent_champion(db):
    from database import get_matches
    mock_riot = AsyncMock()
    mock_riot.get_recent_match_ids.return_value = ["NA1_OPP"]
    mock_riot.get_match.return_value = SAMPLE_MATCH_WITH_OPPONENT
    mock_riot.get_timeline.return_value = SAMPLE_TIMELINE

    mock_claude = make_mock_claude()
    player = make_player()

    await run_backfill(mock_riot, db, mock_claude, player)

    matches = get_matches(db)
    assert len(matches) == 1
    assert matches[0].lane_opponent_champion == "Draven"
```

- [ ] **Step 5: Run test to verify it fails**

```bash
cd sidecar && python -m pytest tests/test_backfill.py::test_backfill_stores_lane_opponent_champion -v
```

Expected: FAIL — `lane_opponent_champion` not in `save_match` call.

- [ ] **Step 6: Run test to verify it passes after implementation**

```bash
cd sidecar && python -m pytest tests/test_backfill.py::test_backfill_stores_lane_opponent_champion -v
```

Expected: PASS

- [ ] **Step 7: Run full test suite**

```bash
cd sidecar && python -m pytest --tb=short -q
```

Expected: 216 total, all pass.

- [ ] **Step 8: Commit**

```bash
git add sidecar/backfill.py sidecar/tests/test_backfill.py
git commit -m "feat: extract and store lane_opponent_champion during backfill"
```

---

### Task 3: Implement `_get_matchup_stats`

**Files:**
- Modify: `sidecar/main.py`
- Create: `sidecar/tests/test_matchup_stats.py`

**Context:** `_get_matchup_stats` is a pure function that takes the global `db` session and a list of `Match` objects, groups by `lane_opponent_champion`, and returns the worst matchups sorted by win rate ascending. It queries `PivotalMoment` rows directly via the session to find the dominant moment type in losses.

`PivotalMoment` is not currently imported in `main.py` — add it to the `from database import (...)` block. `Counter` from `collections` is also not yet imported — add it.

The existing pattern for helper functions in `main.py` is to define them as module-level functions just before they're used (see `_compute_streak_clean`, `_compute_focus_history`, `_compute_focus_trend` around lines 205–242).

---

- [ ] **Step 1: Write failing tests**

Create `sidecar/tests/test_matchup_stats.py`:

```python
from datetime import datetime, timedelta
import pytest
from database import save_match, save_pivotal_moments
from main import _get_matchup_stats

BASE_DATE = datetime(2026, 4, 1)


def _make_match(db, match_id, result, opponent=None, moment_types=None):
    idx = int(match_id.split("_")[1])
    save_match(db, {
        "match_id": match_id,
        "played_at": BASE_DATE + timedelta(days=idx),
        "champion": "Jinx",
        "role": "BOTTOM",
        "result": result,
        "duration_secs": 1800,
        "kda": "5/2/8",
        "cs": 150,
        "gold_earned": 12000,
        "vision_score": 20,
        "raw_timeline": {},
        "lane_opponent_champion": opponent,
    })
    if moment_types:
        save_pivotal_moments(db, match_id, [
            {
                "timestamp_secs": 300,
                "moment_type": t,
                "description": "",
                "counterfactual": "",
                "gold_impact": -300,
            }
            for t in moment_types
        ])


def test_matchup_stats_empty(db):
    assert _get_matchup_stats(db, []) == []


def test_matchup_stats_no_opponent_data(db):
    from database import get_matches
    _make_match(db, "m_0", "loss", opponent=None)
    _make_match(db, "m_1", "loss", opponent=None)
    _make_match(db, "m_2", "loss", opponent=None)
    matches = get_matches(db)
    assert _get_matchup_stats(db, matches) == []


def test_matchup_stats_min_games_filter(db):
    from database import get_matches
    # Only 2 games vs Draven — below min_games=3
    _make_match(db, "m_0", "loss", opponent="Draven")
    _make_match(db, "m_1", "loss", opponent="Draven")
    matches = get_matches(db)
    assert _get_matchup_stats(db, matches, min_games=3) == []


def test_matchup_stats_basic(db):
    from database import get_matches
    # 3 losses vs Draven — should appear
    for i in range(3):
        _make_match(db, f"m_{i}", "loss", opponent="Draven")
    matches = get_matches(db)
    result = _get_matchup_stats(db, matches, min_games=3)
    assert len(result) == 1
    assert result[0]["opponent"] == "Draven"
    assert result[0]["wins"] == 0
    assert result[0]["losses"] == 3
    assert result[0]["win_rate"] == 0.0


def test_matchup_stats_sorted_worst_first(db):
    from database import get_matches
    # Draven: 1W 4L (20%), Caitlyn: 2W 3L (40%)
    for i in range(5):
        result = "win" if i == 0 else "loss"
        _make_match(db, f"m_{i}", result, opponent="Draven")
    for i in range(5, 10):
        result = "win" if i < 7 else "loss"
        _make_match(db, f"m_{i}", result, opponent="Caitlyn")
    matches = get_matches(db)
    stats = _get_matchup_stats(db, matches, min_games=3)
    assert stats[0]["opponent"] == "Draven"
    assert stats[1]["opponent"] == "Caitlyn"


def test_matchup_stats_top_n(db):
    from database import get_matches
    for opp in ["Draven", "Caitlyn", "Jhin", "Jinx", "Kalista", "Zeri"]:
        for i in range(3):
            idx = ["Draven", "Caitlyn", "Jhin", "Jinx", "Kalista", "Zeri"].index(opp) * 3 + i
            _make_match(db, f"m_{idx}", "loss", opponent=opp)
    matches = get_matches(db)
    stats = _get_matchup_stats(db, matches, min_games=3, top_n=3)
    assert len(stats) == 3


def test_matchup_stats_dominant_moment(db):
    from database import get_matches
    # 4 losses vs Draven, 3 have lane_death, 1 has cs_differential
    _make_match(db, "m_0", "loss", opponent="Draven", moment_types=["lane_death"])
    _make_match(db, "m_1", "loss", opponent="Draven", moment_types=["lane_death"])
    _make_match(db, "m_2", "loss", opponent="Draven", moment_types=["lane_death"])
    _make_match(db, "m_3", "loss", opponent="Draven", moment_types=["cs_differential"])
    matches = get_matches(db)
    stats = _get_matchup_stats(db, matches, min_games=3)
    assert stats[0]["dominant_moment"] == "lane_death"


def test_matchup_stats_dominant_moment_none_when_no_moments(db):
    from database import get_matches
    for i in range(3):
        _make_match(db, f"m_{i}", "loss", opponent="Draven")
    matches = get_matches(db)
    stats = _get_matchup_stats(db, matches, min_games=3)
    assert stats[0]["dominant_moment"] is None


def test_matchup_stats_dominant_moment_tiebreak_alphabetical(db):
    from database import get_matches
    # 2 losses with lane_death, 2 losses with cs_differential — tie, alphabetical → cs_differential wins
    _make_match(db, "m_0", "loss", opponent="Draven", moment_types=["lane_death"])
    _make_match(db, "m_1", "loss", opponent="Draven", moment_types=["lane_death"])
    _make_match(db, "m_2", "loss", opponent="Draven", moment_types=["cs_differential"])
    _make_match(db, "m_3", "loss", opponent="Draven", moment_types=["cs_differential"])
    matches = get_matches(db)
    stats = _get_matchup_stats(db, matches, min_games=3)
    assert stats[0]["dominant_moment"] == "cs_differential"


def test_matchup_stats_wins_not_counted_for_dominant_moment(db):
    from database import get_matches
    # 3 losses with lane_death, 5 wins with solo_kill — solo_kill should NOT be dominant
    for i in range(3):
        _make_match(db, f"m_{i}", "loss", opponent="Draven", moment_types=["lane_death"])
    for i in range(3, 8):
        _make_match(db, f"m_{i}", "win", opponent="Draven", moment_types=["solo_kill"])
    matches = get_matches(db)
    stats = _get_matchup_stats(db, matches, min_games=3)
    assert stats[0]["dominant_moment"] == "lane_death"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sidecar && python -m pytest tests/test_matchup_stats.py -v
```

Expected: `ImportError: cannot import name '_get_matchup_stats' from 'main'`

- [ ] **Step 3: Add imports to `main.py`**

Add `Counter` to the stdlib imports at the top of `sidecar/main.py`:

```python
from collections import Counter
```

Add `PivotalMoment` to the database import block:

```python
from database import (
    AppState, PivotalMoment,
    clear_pending_popup, delete_pivotal_moments, get_chat_history, get_matches,
    get_pending_popup, get_pivotal_moments, get_player, init_db, save_chat_message,
    save_pivotal_moments, save_player, set_pending_popup,
)
```

- [ ] **Step 4: Implement `_get_matchup_stats` in `main.py`**

Add immediately after `_compute_focus_trend` (around line 243):

```python
def _get_matchup_stats(
    db: Session,
    matches: list,
    min_games: int = 3,
    top_n: int = 5,
) -> list[dict]:
    with_opponent = [m for m in matches if m.lane_opponent_champion]
    by_opponent: dict[str, list] = {}
    for m in with_opponent:
        by_opponent.setdefault(m.lane_opponent_champion, []).append(m)

    results = []
    for opponent, opp_matches in by_opponent.items():
        if len(opp_matches) < min_games:
            continue
        wins = sum(1 for m in opp_matches if m.result == "win")
        losses = len(opp_matches) - wins
        win_rate = round(wins / len(opp_matches), 3)

        loss_ids = [m.match_id for m in opp_matches if m.result == "loss"]
        dominant_moment = None
        if loss_ids:
            moments = db.query(PivotalMoment).filter(
                PivotalMoment.match_id.in_(loss_ids)
            ).all()
            if moments:
                counts = Counter(m.moment_type for m in moments)
                dominant_moment = min(counts, key=lambda t: (-counts[t], t))

        results.append({
            "opponent": opponent,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "dominant_moment": dominant_moment,
        })

    results.sort(key=lambda r: (r["win_rate"], r["opponent"]))
    return results[:top_n]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd sidecar && python -m pytest tests/test_matchup_stats.py -v
```

Expected: 9 PASS

- [ ] **Step 6: Run full test suite**

```bash
cd sidecar && python -m pytest --tb=short -q
```

Expected: all tests pass (217+ total).

- [ ] **Step 7: Commit**

```bash
git add sidecar/main.py sidecar/tests/test_matchup_stats.py
git commit -m "feat: add _get_matchup_stats function"
```

---

### Task 4: Add `/matchups` endpoint and augment `/champ-select`

**Files:**
- Modify: `sidecar/main.py`

**Context:** All endpoints in `main.py` use the module-level `db = Session(engine)` directly — there is no FastAPI dependency injection. The `/champ-select` endpoint currently just returns `champ_select_monitor.get_state()`. We post-process that return value to inject matchup data without modifying `ChampSelectMonitor`.

---

- [ ] **Step 1: Add the `/matchups` endpoint**

Add this endpoint to `sidecar/main.py` after the `/champ-select` endpoint (after line 194):

```python
@app.get("/matchups")
def get_matchups():
    matches = get_matches(db, last_n=100)
    return {"matchups": _get_matchup_stats(db, matches, min_games=3, top_n=5)}
```

- [ ] **Step 2: Augment `/champ-select` to include matchup data**

Replace the existing `get_champ_select` function:

```python
@app.get("/champ-select")
def get_champ_select():
    state = dict(champ_select_monitor.get_state())
    if state.get("champ_data") is not None and state.get("locked_champion"):
        state["champ_data"] = dict(state["champ_data"])
        champ_matches = get_matches(db, champion=state["locked_champion"], last_n=50)
        state["champ_data"]["matchups"] = _get_matchup_stats(db, champ_matches, min_games=3, top_n=3)
    return state
```

- [ ] **Step 3: Verify the endpoints respond correctly**

Start the sidecar manually and test with curl (or just verify the full test suite still passes):

```bash
cd sidecar && python -m pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add sidecar/main.py
git commit -m "feat: add /matchups endpoint and wire matchup data into /champ-select"
```

---

### Task 5: Render matchup section in champ select overlay

**Files:**
- Modify: `src/champ-select/App.tsx`

**Context:** The champ select overlay is a single-file React app at `src/champ-select/App.tsx`. It polls `/champ-select` every 2 seconds and renders based on `ChampSelectState`. The `ChampData` interface needs a new optional `matchups` field. The matchup section renders below the existing patterns list (inside the `<div className="px-3 py-2 flex flex-col gap-1.5">` block, after `champ_data.patterns.map(...)`).

No TypeScript errors means the build passes — verify with `npm run build`.

---

- [ ] **Step 1: Add the `MatchupEntry` interface and update `ChampData`**

In `src/champ-select/App.tsx`, add a new interface and update `ChampData`:

```tsx
interface MatchupEntry {
  opponent: string
  wins: number
  losses: number
  win_rate: number
  dominant_moment: string | null
}

interface ChampData {
  games: number
  wins: number
  win_rate: number
  no_history: boolean
  patterns: Pattern[]
  focus: Focus | null
  matchups?: MatchupEntry[]
}
```

- [ ] **Step 2: Add the matchup section to the render**

In `ChampSelectApp`, after the closing `</div>` of the `<div className="px-3 py-2 flex flex-col gap-1.5">` patterns block (the one that renders `PatternRow` components), add:

```tsx
        {champ_data?.matchups && champ_data.matchups.length > 0 && (
          <div className="px-3 py-2 border-t border-white/10">
            <div className="text-[8px] uppercase tracking-widest text-gray-500 mb-1.5">your tough matchups</div>
            {champ_data.matchups.map((m) => (
              <div key={m.opponent} className="flex justify-between items-center mb-1">
                <div>
                  <span className="text-[10px] text-gray-200">{m.opponent}</span>
                  {m.dominant_moment && (
                    <span className="text-[8px] text-gray-500 ml-1">
                      {m.dominant_moment.replace(/_/g, ' ')}
                    </span>
                  )}
                </div>
                <span className={`text-[10px] font-bold ${
                  m.win_rate < 0.4 ? 'text-red-400' : 'text-yellow-400'
                }`}>
                  {m.wins}W {m.losses}L
                </span>
              </div>
            ))}
          </div>
        )}
```

- [ ] **Step 3: Build to verify no TypeScript errors**

```bash
npm run build
```

Expected: build completes with no errors.

- [ ] **Step 4: Commit**

```bash
git add src/champ-select/App.tsx
git commit -m "feat: render matchup section in champ select overlay"
```

---

### Task 6: Render matchup section in chat tab

**Files:**
- Modify: `src/chat/App.tsx`

**Context:** `src/chat/App.tsx` fetches patterns, focus, and backfill status via `useEffect` hooks. It uses a module-level `MOMENT_LABELS` dict and renders pattern buttons in a horizontal scroll row. The matchup section goes below the pattern buttons row and above the "Summarize today's session" button. The backfill status `useEffect` (around line 122) already refreshes patterns and focus when backfill completes — also refresh matchups there.

---

- [ ] **Step 1: Add the `MatchupEntry` interface**

Add near the top of `src/chat/App.tsx`, alongside the `Pattern` interface:

```tsx
interface MatchupEntry {
  opponent: string
  wins: number
  losses: number
  win_rate: number
  dominant_moment: string | null
}
```

- [ ] **Step 2: Add `matchups` state**

Add inside `ChatApp`, alongside the other `useState` declarations:

```tsx
const [matchups, setMatchups] = useState<MatchupEntry[]>([])
```

- [ ] **Step 3: Fetch matchups on mount**

Add a new `useEffect` alongside the existing patterns/focus fetch effects:

```tsx
  useEffect(() => {
    if (isSetup !== true) return
    fetch(`http://localhost:${port}/matchups`)
      .then(r => r.ok ? r.json() : { matchups: [] })
      .then((data: { matchups: MatchupEntry[] }) => setMatchups(data.matchups))
      .catch(() => {})
  }, [port, isSetup])
```

- [ ] **Step 4: Refresh matchups when backfill completes**

In the backfill status `useEffect` (the one that polls `/status`), inside the `if (!running)` block alongside the existing patterns and focus refreshes, add:

```tsx
            fetch(`http://localhost:${port}/matchups`)
              .then(r => r.ok ? r.json() : { matchups: [] })
              .then((d: { matchups: MatchupEntry[] }) => setMatchups(d.matchups))
              .catch(() => {})
```

The full `if (!running)` block should look like:

```tsx
          if (!running) {
            fetch(`http://localhost:${port}/patterns`)
              .then(r => r.ok ? r.json() : { patterns: [] })
              .then((d: { patterns: Pattern[] }) => setPatterns(d.patterns))
              .catch(() => {})
            fetch(`http://localhost:${port}/focus`)
              .then(r => r.ok ? r.json() : null)
              .then(d => setFocusCard(d as FocusCardData | null))
              .catch(() => {})
            fetch(`http://localhost:${port}/matchups`)
              .then(r => r.ok ? r.json() : { matchups: [] })
              .then((d: { matchups: MatchupEntry[] }) => setMatchups(d.matchups))
              .catch(() => {})
          }
```

- [ ] **Step 5: Render the matchup section**

In the JSX render, add the matchup section after the `{patterns.length > 0 && (...)}` patterns block and before the `<div className="px-4 py-2 border-b border-white/10 flex-shrink-0">` summarize button div:

```tsx
          {matchups.length > 0 && (
            <div className="px-4 py-2 border-b border-white/10 flex-shrink-0">
              <div className="text-[8px] uppercase tracking-widest text-gray-500 mb-2">tough matchups</div>
              {matchups.map((m) => (
                <div key={m.opponent} className="flex justify-between items-center mb-1.5">
                  <div>
                    <span className="text-[10px] text-gray-200">vs {m.opponent}</span>
                    {m.dominant_moment && (
                      <span className="text-[8px] text-gray-500 ml-1">
                        {m.dominant_moment.replace(/_/g, ' ')}
                      </span>
                    )}
                  </div>
                  <span className={`text-[10px] font-bold ${
                    m.win_rate < 0.4 ? 'text-red-400' : 'text-yellow-400'
                  }`}>
                    {m.wins}W {m.losses}L · {Math.round(m.win_rate * 100)}%
                  </span>
                </div>
              ))}
            </div>
          )}
```

- [ ] **Step 6: Build to verify no TypeScript errors**

```bash
npm run build
```

Expected: build completes with no errors.

- [ ] **Step 7: Commit**

```bash
git add src/chat/App.tsx
git commit -m "feat: render matchup section in chat tab"
```
