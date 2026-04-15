# Match History Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On startup and after setup, automatically fetch and analyze the last 30 days of match history in the background so the app is useful immediately on install.

**Architecture:** A new `sidecar/backfill.py` module owns the backfill logic with injectable dependencies (riot client, db session, claude client) for testability. `main.py` wraps it with a `_backfill_running` guard and fires it from two trigger points: the FastAPI lifespan startup handler and the `POST /setup` endpoint.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, httpx, pytest, asyncio

---

## File Structure

- **Modify:** `sidecar/database.py` — add `get_all_match_ids(db) -> set[str]`
- **Modify:** `sidecar/riot_client.py` — add `start_time: int | None = None` param to `get_recent_match_ids`
- **Create:** `sidecar/backfill.py` — `run_backfill(riot_client, db_session, claude_client, player)` and `_analyze_and_save_match(...)` helper
- **Modify:** `sidecar/main.py` — remove duplicated analysis logic, import `run_backfill`, add `_backfill_running` guard, wire two trigger points
- **Create:** `sidecar/tests/test_backfill.py` — tests for the backfill logic
- **Modify:** `sidecar/tests/test_database.py` — test for `get_all_match_ids`
- **Modify:** `sidecar/tests/test_riot_client.py` — test for `start_time` param

---

### Task 1: DB helper and riot_client param

**Files:**
- Modify: `sidecar/database.py`
- Modify: `sidecar/riot_client.py`
- Modify: `sidecar/tests/test_database.py`
- Modify: `sidecar/tests/test_riot_client.py`

- [ ] **Step 1: Write failing tests**

Append to `sidecar/tests/test_database.py`:

```python
from database import get_all_match_ids

def test_get_all_match_ids_returns_set(db):
    save_match(db, {
        "match_id": "NA1_AAA",
        "played_at": datetime(2026, 4, 1, 20, 0),
        "champion": "Jinx", "role": "BOTTOM", "result": "win",
        "duration_secs": 1800, "kda": "5/2/8", "cs": 150,
        "gold_earned": 12000, "vision_score": 20, "raw_timeline": {},
    })
    save_match(db, {
        "match_id": "NA1_BBB",
        "played_at": datetime(2026, 4, 2, 20, 0),
        "champion": "Caitlyn", "role": "BOTTOM", "result": "loss",
        "duration_secs": 1500, "kda": "3/4/6", "cs": 120,
        "gold_earned": 10000, "vision_score": 18, "raw_timeline": {},
    })
    ids = get_all_match_ids(db)
    assert ids == {"NA1_AAA", "NA1_BBB"}


def test_get_all_match_ids_empty(db):
    assert get_all_match_ids(db) == set()
```

Append to `sidecar/tests/test_riot_client.py`:

```python
@pytest.mark.asyncio
async def test_get_match_ids_with_start_time(client):
    with patch.object(client._http, "get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [SAMPLE_MATCH_ID])
        await client.get_recent_match_ids(SAMPLE_PUUID, count=100, start_time=1700000000)
    call_kwargs = mock_get.call_args
    params = call_kwargs[1]["params"]
    assert params["startTime"] == 1700000000
    assert params["count"] == 100


@pytest.mark.asyncio
async def test_get_match_ids_without_start_time_omits_param(client):
    with patch.object(client._http, "get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [SAMPLE_MATCH_ID])
        await client.get_recent_match_ids(SAMPLE_PUUID, count=5)
    params = mock_get.call_args[1]["params"]
    assert "startTime" not in params
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar
venv/Scripts/pytest tests/test_database.py::test_get_all_match_ids_returns_set tests/test_riot_client.py::test_get_match_ids_with_start_time -v
```

Expected: `FAILED` — `ImportError: cannot import name 'get_all_match_ids'` and `TypeError`

- [ ] **Step 3: Add `get_all_match_ids` to `sidecar/database.py`**

Add after `get_matches`:

```python
def get_all_match_ids(db: Session) -> set[str]:
    return {row[0] for row in db.query(Match.match_id).all()}
```

Also add `get_all_match_ids` to the exports list (it's implicit in Python, just make sure it's importable).

- [ ] **Step 4: Update `get_recent_match_ids` in `sidecar/riot_client.py`**

Replace:

```python
    async def get_recent_match_ids(self, puuid: str, count: int = 20) -> list[str]:
        url = f"https://{self.regional}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
        r = await self._http.get(url, params={"count": count})
        r.raise_for_status()
        return r.json()
```

With:

```python
    async def get_recent_match_ids(self, puuid: str, count: int = 20, start_time: int | None = None) -> list[str]:
        url = f"https://{self.regional}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
        params: dict = {"count": count}
        if start_time is not None:
            params["startTime"] = start_time
        r = await self._http.get(url, params=params)
        r.raise_for_status()
        return r.json()
```

- [ ] **Step 5: Run tests**

```
cd sidecar
venv/Scripts/pytest tests/test_database.py tests/test_riot_client.py -v
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add sidecar/database.py sidecar/riot_client.py sidecar/tests/test_database.py sidecar/tests/test_riot_client.py
git commit -m "feat: get_all_match_ids helper and start_time param on get_recent_match_ids"
```

---

### Task 2: `backfill.py` — core backfill logic

**Files:**
- Create: `sidecar/backfill.py`
- Create: `sidecar/tests/test_backfill.py`

**Context:** `run_backfill` takes all dependencies as parameters (riot client, db session, claude client, player) so it can be unit tested without importing `main.py`. The `_analyze_and_save_match` helper contains the fetch→analyze→save pipeline that currently lives inline in `run_post_game_analysis` — it will be reused by both backfill and the live watcher after Task 3.

The `SAMPLE_MATCH_DATA` fixture used in the tests below represents a minimal valid response from the Riot match-v5 API. It has 10 participants (IDs 1–10), the player is participant 1 (blue side, BOTTOM), and no one has Smite so `enemy_jungler_id` resolves to `None`.

- [ ] **Step 1: Write failing tests**

Create `sidecar/tests/test_backfill.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from database import save_match, save_player, get_all_match_ids
import backfill as backfill_module
from backfill import run_backfill

PLAYER_PUUID = "test-puuid-abc"

SAMPLE_MATCH_DATA = {
    "info": {
        "gameStartTimestamp": 1700000000000,
        "gameDuration": 1800,
        "participants": [
            {
                "puuid": PLAYER_PUUID,
                "championName": "Caitlyn",
                "teamPosition": "BOTTOM",
                "win": True,
                "kills": 5, "deaths": 2, "assists": 8,
                "totalMinionsKilled": 150,
                "goldEarned": 12000,
                "visionScore": 20,
                "summoner1Id": 4, "summoner2Id": 21,
            }
        ] + [
            {
                "puuid": f"other-puuid-{i}",
                "championName": "Darius",
                "teamPosition": "TOP" if i % 5 == 0 else "",
                "win": True,
                "kills": 1, "deaths": 1, "assists": 1,
                "totalMinionsKilled": 100,
                "goldEarned": 8000,
                "visionScore": 10,
                "summoner1Id": 4, "summoner2Id": 21,
            }
            for i in range(9)
        ],
    }
}

SAMPLE_TIMELINE = {"info": {"frames": []}}


def make_mock_riot(match_ids: list[str]) -> AsyncMock:
    mock = AsyncMock()
    mock.get_recent_match_ids.return_value = match_ids
    mock.get_match.return_value = SAMPLE_MATCH_DATA
    mock.get_timeline.return_value = SAMPLE_TIMELINE
    return mock


def make_mock_claude() -> MagicMock:
    mock = MagicMock()
    mock.generate_coaching_notes.return_value = []
    return mock


def make_player():
    p = MagicMock()
    p.riot_puuid = PLAYER_PUUID
    p.summoner_name = "TestPlayer"
    p.region = "NA1"
    return p


@pytest.mark.asyncio
async def test_backfill_processes_only_new_matches(db):
    # NA1_EXISTING is already in DB — should be skipped
    save_match(db, {
        "match_id": "NA1_EXISTING",
        "played_at": datetime(2026, 4, 1),
        "champion": "Caitlyn", "role": "BOTTOM", "result": "win",
        "duration_secs": 1800, "kda": "5/2/8", "cs": 150,
        "gold_earned": 12000, "vision_score": 20, "raw_timeline": {},
    })

    mock_riot = make_mock_riot(["NA1_EXISTING", "NA1_NEW"])
    mock_claude = make_mock_claude()
    player = make_player()

    with patch("backfill.asyncio.sleep", new_callable=AsyncMock):
        await run_backfill(mock_riot, db, mock_claude, player)

    mock_riot.get_match.assert_called_once_with("NA1_NEW")
    mock_riot.get_timeline.assert_called_once_with("NA1_NEW")


@pytest.mark.asyncio
async def test_backfill_skips_all_when_nothing_new(db):
    save_match(db, {
        "match_id": "NA1_AAA",
        "played_at": datetime(2026, 4, 1),
        "champion": "Caitlyn", "role": "BOTTOM", "result": "win",
        "duration_secs": 1800, "kda": "5/2/8", "cs": 150,
        "gold_earned": 12000, "vision_score": 20, "raw_timeline": {},
    })

    mock_riot = make_mock_riot(["NA1_AAA"])
    mock_claude = make_mock_claude()
    player = make_player()

    with patch("backfill.asyncio.sleep", new_callable=AsyncMock):
        await run_backfill(mock_riot, db, mock_claude, player)

    mock_riot.get_match.assert_not_called()


@pytest.mark.asyncio
async def test_backfill_continues_after_single_match_error(db):
    mock_riot = make_mock_riot(["NA1_FAIL", "NA1_OK"])
    mock_riot.get_match.side_effect = [Exception("network error"), SAMPLE_MATCH_DATA]
    mock_riot.get_timeline.return_value = SAMPLE_TIMELINE
    mock_claude = make_mock_claude()
    player = make_player()

    with patch("backfill.asyncio.sleep", new_callable=AsyncMock):
        await run_backfill(mock_riot, db, mock_claude, player)

    # Despite NA1_FAIL erroring, NA1_OK should still be processed
    assert mock_riot.get_match.call_count == 2


@pytest.mark.asyncio
async def test_backfill_uses_start_time_30_days_ago(db):
    mock_riot = make_mock_riot([])
    mock_claude = make_mock_claude()
    player = make_player()

    with patch("backfill.asyncio.sleep", new_callable=AsyncMock):
        with patch("backfill.datetime") as mock_dt:
            mock_dt.now.return_value.timestamp.return_value = 1714000000.0
            mock_dt.fromtimestamp = datetime.fromtimestamp
            await run_backfill(mock_riot, db, mock_claude, player)

    call_kwargs = mock_riot.get_recent_match_ids.call_args
    start_time = call_kwargs[1]["start_time"]
    expected = int(1714000000.0 - 30 * 24 * 3600)
    assert start_time == expected
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd sidecar
venv/Scripts/pytest tests/test_backfill.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'backfill'`

- [ ] **Step 3: Create `sidecar/backfill.py`**

```python
import asyncio
from datetime import datetime, timezone

import httpx

from database import (
    get_all_match_ids, save_match, save_pivotal_moments,
)
from timeline_analyzer import analyze_timeline, TEAM_100_IDS, TEAM_200_IDS

BACKFILL_DAYS = 30
SMITE_ID = 11


async def _analyze_and_save_match(
    riot_client,
    db_session,
    claude_client,
    player,
    match_id: str,
) -> None:
    match_data = await riot_client.get_match(match_id)
    timeline_data = await riot_client.get_timeline(match_id)

    info = match_data["info"]
    participants = info["participants"]
    participant = next(p for p in participants if p["puuid"] == player.riot_puuid)
    participant_index = participants.index(participant) + 1
    role = participant.get("teamPosition", "UNKNOWN")
    champion = participant["championName"]

    player_team_ids = TEAM_100_IDS if participant_index in TEAM_100_IDS else TEAM_200_IDS

    enemy_jungler_entry = next(
        ((i + 1, p) for i, p in enumerate(participants)
         if (i + 1) not in player_team_ids
         and (p.get("summoner1Id") == SMITE_ID or p.get("summoner2Id") == SMITE_ID)),
        None,
    )
    enemy_jungler_id = enemy_jungler_entry[0] if enemy_jungler_entry else None

    lane_opponent_entry = next(
        ((i + 1, p) for i, p in enumerate(participants)
         if (i + 1) not in player_team_ids
         and p.get("teamPosition") == role),
        None,
    )
    lane_opponent_id = lane_opponent_entry[0] if lane_opponent_entry else None

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
    })

    moments = analyze_timeline(
        timeline_data,
        participant_id=participant_index,
        enemy_jungler_id=enemy_jungler_id,
        role=role,
        champion=champion,
        lane_opponent_id=lane_opponent_id,
    )
    side = "blue" if participant_index in TEAM_100_IDS else "red"
    game_context = {
        "participant_id": participant_index,
        "champion": champion,
        "role": role,
        "side": side,
        "result": "win" if participant["win"] else "loss",
        "kda": f"{participant['kills']}/{participant['deaths']}/{participant['assists']}",
        "duration_secs": info["gameDuration"],
    }
    enriched = claude_client.generate_coaching_notes(moments, game_context, timeline_data)
    save_pivotal_moments(db_session, match_id, [
        {
            "timestamp_secs": m.timestamp_secs,
            "moment_type": m.moment_type,
            "description": m.description,
            "counterfactual": m.counterfactual,
            "gold_impact": m.gold_impact,
        }
        for m in enriched
    ])


async def run_backfill(riot_client, db_session, claude_client, player) -> None:
    start_time = int(datetime.now(timezone.utc).timestamp() - BACKFILL_DAYS * 24 * 3600)
    match_ids = await riot_client.get_recent_match_ids(
        player.riot_puuid, count=100, start_time=start_time
    )
    existing_ids = get_all_match_ids(db_session)
    new_ids = [mid for mid in match_ids if mid not in existing_ids]
    print(f"[backfill] {len(new_ids)} new matches to analyze")

    for match_id in new_ids:
        try:
            await _analyze_and_save_match(riot_client, db_session, claude_client, player, match_id)
            await asyncio.sleep(3)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                print(f"[backfill] Rate limited — waiting 10s before retrying {match_id}")
                await asyncio.sleep(10)
                try:
                    await _analyze_and_save_match(riot_client, db_session, claude_client, player, match_id)
                except Exception as retry_err:
                    print(f"[backfill] Retry failed for {match_id}: {retry_err}")
            else:
                print(f"[backfill] HTTP error for {match_id}: {e}")
        except Exception as e:
            print(f"[backfill] Error processing {match_id}: {e}")

    print(f"[backfill] Complete")
```

- [ ] **Step 4: Run tests**

```
cd sidecar
venv/Scripts/pytest tests/test_backfill.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add sidecar/backfill.py sidecar/tests/test_backfill.py
git commit -m "feat: backfill.py — run_backfill and _analyze_and_save_match"
```

---

### Task 3: Wire backfill into `main.py`

**Files:**
- Modify: `sidecar/main.py`

**Context:** This task refactors `run_post_game_analysis` to use `_analyze_and_save_match` from `backfill.py` (eliminating the duplicated fetch/analyze/save logic), adds the `_backfill_running` guard, and wires two trigger points. No new tests needed — the backfill logic is tested in Task 2, and the wiring is trivial.

- [ ] **Step 1: Update imports in `sidecar/main.py`**

Replace the existing imports block at the top of `main.py`:

```python
import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backfill import _analyze_and_save_match, run_backfill
from claude_client import ClaudeClient
from database import (
    AppState,
    clear_pending_popup, get_chat_history, get_matches, get_pending_popup,
    get_pivotal_moments, get_player, init_db, save_chat_message, save_match,
    save_pivotal_moments, save_player, set_pending_popup,
)
from riot_client import RiotClient, REGIONAL_ROUTING
from timeline_analyzer import analyze_timeline, TEAM_100_IDS, TEAM_200_IDS
```

- [ ] **Step 2: Add `_backfill_running` flag and `backfill_history()` wrapper**

After the line `_watcher_task: Optional[asyncio.Task] = None`, add:

```python
_backfill_running = False


async def backfill_history() -> None:
    global _backfill_running
    if _backfill_running:
        return
    _backfill_running = True
    try:
        player = get_player(db)
        if not player:
            return
        await run_backfill(riot, db, claude, player)
    finally:
        _backfill_running = False
```

- [ ] **Step 3: Simplify `run_post_game_analysis` to use `_analyze_and_save_match`**

Replace the entire `run_post_game_analysis` function with:

```python
async def run_post_game_analysis():
    player = get_player(db)
    if not player:
        return
    try:
        match_ids = await riot.get_recent_match_ids(player.riot_puuid, count=1)
        if not match_ids:
            return
        match_id = match_ids[0]
        existing = get_matches(db, last_n=1)
        if existing and existing[0].match_id == match_id:
            return  # already analyzed
        await _analyze_and_save_match(riot, db, claude, player, match_id)
        set_pending_popup(db, match_id=match_id)
    except Exception as e:
        print(f"[watcher] Error during post-game analysis: {e}")
```

- [ ] **Step 4: Fire backfill on startup**

Replace the lifespan function:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _watcher_task
    _watcher_task = asyncio.create_task(game_end_watcher())
    asyncio.create_task(backfill_history())
    yield
    if _watcher_task:
        _watcher_task.cancel()
    await riot.close()
    db.close()
```

- [ ] **Step 5: Fire backfill after setup completes**

Replace the `setup` endpoint:

```python
@app.post("/setup")
async def setup(req: SetupRequest):
    riot.region = req.region
    riot.regional = REGIONAL_ROUTING.get(req.region, "americas")
    try:
        puuid = await riot.get_puuid_by_summoner(req.summoner_name, req.tag_line)
        save_player(db, summoner_name=req.summoner_name, puuid=puuid, region=req.region)
        asyncio.create_task(backfill_history())
        return {"ok": True, "puuid": puuid}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 6: Run the full test suite**

```
cd sidecar
venv/Scripts/pytest tests/ -v
```

Expected: All tests PASS (including all pre-existing tests — `run_post_game_analysis` behavior is unchanged externally).

- [ ] **Step 7: Commit**

```bash
git add sidecar/main.py
git commit -m "feat: wire backfill_history into startup and setup triggers"
```

---

## Self-Review

**Spec coverage:**
- ✅ Background backfill on startup — Task 3, Step 4
- ✅ Background backfill after setup — Task 3, Step 5
- ✅ 30-day window via `start_time` — Task 1 + Task 2
- ✅ Skip already-analyzed matches — Task 2, `get_all_match_ids` dedup
- ✅ `asyncio.sleep(3)` rate limiting between games — Task 2
- ✅ 429 retry with 10s wait — Task 2
- ✅ Per-game error handling (continue loop) — Task 2
- ✅ `_backfill_running` guard against concurrent runs — Task 3, Step 2
- ✅ `get_all_match_ids` DB helper — Task 1
- ✅ `start_time` param on `get_recent_match_ids` — Task 1

**Placeholder scan:** No TBDs. All code blocks are complete.

**Type consistency:** `run_backfill(riot_client, db_session, claude_client, player)` signature is consistent across `backfill.py` definition, `test_backfill.py` call sites, and `main.py`'s `backfill_history()` wrapper. `_analyze_and_save_match` signature is the same everywhere.
