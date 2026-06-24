# Higher-Elo Benchmarks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the player how their recent average on each of the five existing goal metrics compares to the average of players one rank tier above them, woven into the Goals tab.

**Architecture:** A new background harvester samples high-elo players via league-v4 on the user's own Riot key (no timeline calls — all five metrics read off match detail), accumulating per-(tier, role, metric) running sums in SQLite. A `/benchmarks` endpoint pairs those tier averages with the user's own recent role-matched averages. The metric set stays sourced from `goal_metrics.METRICS`; the harvest reuses the `backfill.py` rate-limit/resume pattern.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy (SQLite), httpx (async); React 18 + TypeScript + Vite; pytest / Vitest + RTL.

## Global Constraints

- Metric set is sourced **only** from `goal_metrics.METRICS` — never hardcode the metric list anywhere else.
- All metric values accumulated/averaged as **floats** via `METRICS[key].value(obj)`; round only for display.
- New tables are created by `Base.metadata.create_all` (in `init_db`) — **no PRAGMA migration** (follow the `Goal` precedent, not the `matches` precedent).
- league-v4 is **platform-routed** (`{platform}.api.riotgames.com`), unlike match-v5/account-v1 which use the regional cluster.
- Harvest must: respect 429s (reuse `backfill.py` pattern), skip while a game is live, be budget-capped and resumable, and self-gate on a 14-day freshness window.
- Backend gate: `cd sidecar && python -m pytest`. Frontend gate: `npm run typecheck`, `npm run lint`, `npm test`.
- Run pytest from inside `sidecar/` (pytest.ini sets `pythonpath=.`).
- Commit message trailer on every commit: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

- **Create** `sidecar/benchmark_tiers.py` — pure tier-ladder logic (`next_tier_up`).
- **Create** `sidecar/benchmark_metrics.py` — participant-JSON → metric-value extraction (reuses `goal_metrics`).
- **Create** `sidecar/benchmark_harvester.py` — orchestration: resolve tier, seed players, harvest loop, accumulate, refresh gate.
- **Modify** `sidecar/database.py` — `Benchmark` + `BenchmarkHarvestedMatch` models, their CRUD, generic `app_state` get/set helpers.
- **Modify** `sidecar/riot_client.py` — `self.platform`; league-v4 methods; optional `queue` filter on `get_recent_match_ids`.
- **Modify** `sidecar/main.py` — `GET /benchmarks` endpoint; register `benchmark_harvest_task` in lifespan.
- **Modify** `src/shared/types.ts` — `BenchmarkMetric` + `BenchmarkResponse` types.
- **Modify** `src/chat/GoalsPanel.tsx` — render the "Benchmarks vs {tier}" block.
- **Create** tests: `sidecar/tests/test_benchmark_tiers.py`, `test_benchmark_metrics.py`, `test_benchmark_db.py`, `test_riot_league.py`, `test_benchmark_harvester.py`, `test_benchmarks_api.py`; extend `src/chat/GoalsPanel.test.tsx`.

---

### Task 1: Tier-ladder logic

**Files:**
- Create: `sidecar/benchmark_tiers.py`
- Test: `sidecar/tests/test_benchmark_tiers.py`

**Interfaces:**
- Produces: `next_tier_up(tier: str | None) -> str`. Returns the next rung up; caps at `"CHALLENGER"`; `None`/unranked → `"PLATINUM"`. `APEX_TIERS: set[str]` = `{"MASTER","GRANDMASTER","CHALLENGER"}`.

- [ ] **Step 1: Write the failing test**

```python
# sidecar/tests/test_benchmark_tiers.py
import pytest
from benchmark_tiers import next_tier_up, APEX_TIERS


@pytest.mark.parametrize("tier,expected", [
    ("PLATINUM", "EMERALD"),
    ("EMERALD", "DIAMOND"),
    ("DIAMOND", "MASTER"),
    ("MASTER", "GRANDMASTER"),
    ("GRANDMASTER", "CHALLENGER"),
    ("CHALLENGER", "CHALLENGER"),  # caps
    ("IRON", "BRONZE"),
])
def test_next_tier_up(tier, expected):
    assert next_tier_up(tier) == expected


def test_unranked_defaults_to_platinum():
    assert next_tier_up(None) == "PLATINUM"
    assert next_tier_up("") == "PLATINUM"


def test_unknown_tier_defaults_to_platinum():
    assert next_tier_up("WOOD") == "PLATINUM"


def test_apex_tiers_constant():
    assert APEX_TIERS == {"MASTER", "GRANDMASTER", "CHALLENGER"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sidecar && python -m pytest tests/test_benchmark_tiers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'benchmark_tiers'`

- [ ] **Step 3: Write minimal implementation**

```python
# sidecar/benchmark_tiers.py
LADDER = [
    "IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM",
    "EMERALD", "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER",
]
APEX_TIERS = {"MASTER", "GRANDMASTER", "CHALLENGER"}
_DEFAULT = "PLATINUM"


def next_tier_up(tier: str | None) -> str:
    """The rung above ``tier``; caps at CHALLENGER; unranked/unknown -> PLATINUM."""
    if not tier or tier.upper() not in LADDER:
        return _DEFAULT
    idx = LADDER.index(tier.upper())
    return LADDER[min(idx + 1, len(LADDER) - 1)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sidecar && python -m pytest tests/test_benchmark_tiers.py -v`
Expected: PASS (all parametrized cases)

- [ ] **Step 5: Commit**

```bash
git add sidecar/benchmark_tiers.py sidecar/tests/test_benchmark_tiers.py
git commit -m "feat: add benchmark tier-ladder logic

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Participant metric extraction

**Files:**
- Create: `sidecar/benchmark_metrics.py`
- Test: `sidecar/tests/test_benchmark_metrics.py`

**Interfaces:**
- Consumes: `goal_metrics.METRICS`.
- Produces: `extract_participant_metrics(participant: dict) -> dict[str, float]` — maps a match-v5 participant dict to `{metric_key: float}` for all five metrics, reusing the `goal_metrics` value functions (single source of truth). The participant→attribute mapping mirrors `backfill.py:67-70`.

- [ ] **Step 1: Write the failing test**

```python
# sidecar/tests/test_benchmark_metrics.py
from benchmark_metrics import extract_participant_metrics


def _participant():
    return {
        "kills": 4, "deaths": 2, "assists": 6,
        "totalMinionsKilled": 180,
        "goldEarned": 13500,
        "visionScore": 28,
        "teamPosition": "MIDDLE",
    }


def test_extracts_all_five_metrics_as_floats():
    m = extract_participant_metrics(_participant())
    assert set(m.keys()) == {"deaths", "cs", "vision_score", "gold_earned", "kda"}
    assert m["deaths"] == 2.0
    assert m["cs"] == 180.0
    assert m["vision_score"] == 28.0
    assert m["gold_earned"] == 13500.0
    assert m["kda"] == (4 + 6) / 2  # (k+a)/d


def test_zero_deaths_kda_is_kills_plus_assists():
    p = _participant()
    p["deaths"] = 0
    m = extract_participant_metrics(p)
    assert m["deaths"] == 0.0
    assert m["kda"] == 10.0  # k + a when deaths == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sidecar && python -m pytest tests/test_benchmark_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'benchmark_metrics'`

- [ ] **Step 3: Write minimal implementation**

```python
# sidecar/benchmark_metrics.py
from types import SimpleNamespace

from goal_metrics import METRICS


def _participant_to_match_like(p: dict) -> SimpleNamespace:
    """Shape a match-v5 participant like a ``Match`` row so goal_metrics can read it.

    Mirrors the participant->Match mapping in backfill.analyze_and_save_match.
    """
    return SimpleNamespace(
        kda=f"{p['kills']}/{p['deaths']}/{p['assists']}",
        cs=p["totalMinionsKilled"],
        vision_score=p["visionScore"],
        gold_earned=p["goldEarned"],
    )


def extract_participant_metrics(participant: dict) -> dict[str, float]:
    """Float value of every goal metric for one match-v5 participant."""
    obj = _participant_to_match_like(participant)
    return {key: float(metric.value(obj)) for key, metric in METRICS.items()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sidecar && python -m pytest tests/test_benchmark_metrics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sidecar/benchmark_metrics.py sidecar/tests/test_benchmark_metrics.py
git commit -m "feat: extract goal metrics from match-v5 participants

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Benchmark tables, CRUD, and app_state helpers

**Files:**
- Modify: `sidecar/database.py`
- Test: `sidecar/tests/test_benchmark_db.py`

**Interfaces:**
- Produces (all importable from `database`):
  - Models `Benchmark` (`id, target_tier, role, metric_key, sum_value: float, sample_count: int, patch, updated_at`) and `BenchmarkHarvestedMatch` (`match_id` PK, `harvested_at`).
  - `record_benchmark_samples(db, target_tier: str, role: str, patch: str, metrics: dict[str, float]) -> None` — upserts, adding each metric value to `sum_value` and incrementing `sample_count` by 1 per call, keyed on `(target_tier, role, metric_key, patch)`; bumps `updated_at`.
  - `get_benchmarks(db, target_tier: str, role: str) -> dict[str, tuple[float, int]]` — `{metric_key: (total_sum, total_count)}` summed across all patches for that tier+role.
  - `is_match_harvested(db, match_id: str) -> bool`; `mark_match_harvested(db, match_id: str) -> None`.
  - `get_app_state(db, key: str) -> str | None`; `set_app_state(db, key: str, value: str) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# sidecar/tests/test_benchmark_db.py
from database import (
    record_benchmark_samples, get_benchmarks,
    is_match_harvested, mark_match_harvested,
    get_app_state, set_app_state,
)


def test_record_then_get_accumulates(db):
    record_benchmark_samples(db, "DIAMOND", "MIDDLE", "14.12", {"cs": 200.0, "deaths": 3.0})
    record_benchmark_samples(db, "DIAMOND", "MIDDLE", "14.12", {"cs": 180.0, "deaths": 5.0})
    rows = get_benchmarks(db, "DIAMOND", "MIDDLE")
    assert rows["cs"] == (380.0, 2)
    assert rows["deaths"] == (8.0, 2)


def test_get_benchmarks_sums_across_patches(db):
    record_benchmark_samples(db, "DIAMOND", "TOP", "14.12", {"cs": 100.0})
    record_benchmark_samples(db, "DIAMOND", "TOP", "14.13", {"cs": 140.0})
    rows = get_benchmarks(db, "DIAMOND", "TOP")
    assert rows["cs"] == (240.0, 2)


def test_get_benchmarks_isolates_tier_and_role(db):
    record_benchmark_samples(db, "DIAMOND", "MIDDLE", "14.12", {"cs": 200.0})
    assert get_benchmarks(db, "MASTER", "MIDDLE") == {}
    assert get_benchmarks(db, "DIAMOND", "TOP") == {}


def test_harvested_match_dedup(db):
    assert is_match_harvested(db, "NA1_1") is False
    mark_match_harvested(db, "NA1_1")
    assert is_match_harvested(db, "NA1_1") is True


def test_app_state_roundtrip(db):
    assert get_app_state(db, "benchmark_target_tier") is None
    set_app_state(db, "benchmark_target_tier", "DIAMOND")
    assert get_app_state(db, "benchmark_target_tier") == "DIAMOND"
    set_app_state(db, "benchmark_target_tier", "MASTER")  # overwrites
    assert get_app_state(db, "benchmark_target_tier") == "MASTER"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sidecar && python -m pytest tests/test_benchmark_db.py -v`
Expected: FAIL with `ImportError: cannot import name 'record_benchmark_samples'`

- [ ] **Step 3: Write minimal implementation**

Add the models after the `Goal` class in `sidecar/database.py`:

```python
class Benchmark(Base):
    __tablename__ = "benchmarks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_tier: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    metric_key: Mapped[str] = mapped_column(String)
    sum_value: Mapped[float] = mapped_column(Float, default=0.0)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    patch: Mapped[str] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class BenchmarkHarvestedMatch(Base):
    __tablename__ = "benchmark_harvested_matches"
    match_id: Mapped[str] = mapped_column(String, primary_key=True)
    harvested_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
```

Add the helpers at the end of `sidecar/database.py`:

```python
# --- Benchmark queries ---

def record_benchmark_samples(db: Session, target_tier: str, role: str, patch: str,
                             metrics: dict[str, float]) -> None:
    now = datetime.now(timezone.utc)
    for metric_key, value in metrics.items():
        row = (
            db.query(Benchmark)
            .filter(
                Benchmark.target_tier == target_tier,
                Benchmark.role == role,
                Benchmark.metric_key == metric_key,
                Benchmark.patch == patch,
            )
            .first()
        )
        if row is None:
            row = Benchmark(target_tier=target_tier, role=role, metric_key=metric_key,
                            sum_value=0.0, sample_count=0, patch=patch)
            db.add(row)
        row.sum_value += value
        row.sample_count += 1
        row.updated_at = now
    db.commit()


def get_benchmarks(db: Session, target_tier: str, role: str) -> dict[str, tuple[float, int]]:
    rows = (
        db.query(Benchmark)
        .filter(Benchmark.target_tier == target_tier, Benchmark.role == role)
        .all()
    )
    out: dict[str, tuple[float, int]] = {}
    for r in rows:
        s, c = out.get(r.metric_key, (0.0, 0))
        out[r.metric_key] = (s + r.sum_value, c + r.sample_count)
    return out


def is_match_harvested(db: Session, match_id: str) -> bool:
    return db.query(BenchmarkHarvestedMatch).filter(
        BenchmarkHarvestedMatch.match_id == match_id).first() is not None


def mark_match_harvested(db: Session, match_id: str) -> None:
    db.merge(BenchmarkHarvestedMatch(match_id=match_id))
    db.commit()


# --- Generic app_state ---

def get_app_state(db: Session, key: str) -> Optional[str]:
    row = db.query(AppState).filter(AppState.key == key).first()
    return row.value if row else None


def set_app_state(db: Session, key: str, value: str) -> None:
    db.merge(AppState(key=key, value=value))
    db.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sidecar && python -m pytest tests/test_benchmark_db.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add sidecar/database.py sidecar/tests/test_benchmark_db.py
git commit -m "feat: add benchmark tables, CRUD, and app_state helpers

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: league-v4 support in RiotClient

**Files:**
- Modify: `sidecar/riot_client.py`
- Test: `sidecar/tests/test_riot_league.py`

**Interfaces:**
- Produces (on `RiotClient`):
  - `self.platform: str` = `region.lower()` (league-v4 host).
  - `async get_solo_rank(puuid: str) -> str | None` — tier of the RANKED_SOLO_5x5 entry, else `None`.
  - `async get_apex_league_puuids(tier: str) -> list[str]` — for `tier` in `APEX_TIERS`.
  - `async get_tier_division_puuids(tier: str, division: str, page: int = 1) -> list[str]` — sub-apex.
  - `get_recent_match_ids` gains optional `queue: int | None = None`.

- [ ] **Step 1: Write the failing test**

```python
# sidecar/tests/test_riot_league.py
import pytest
from riot_client import RiotClient


class _FakeResp:
    def __init__(self, data):
        self._data = data
    def raise_for_status(self):
        pass
    def json(self):
        return self._data


class _FakeHttp:
    def __init__(self, route_map):
        self.route_map = route_map
        self.calls = []
    async def get(self, url, params=None):
        self.calls.append((url, params))
        for frag, data in self.route_map.items():
            if frag in url:
                return _FakeResp(data)
        raise AssertionError(f"no fake route for {url}")


def _client(route_map):
    c = RiotClient(api_key="k", region="NA1")
    c._http = _FakeHttp(route_map)
    return c


def test_platform_is_lowercased_region():
    assert RiotClient(api_key="k", region="EUW1").platform == "euw1"


@pytest.mark.asyncio
async def test_get_solo_rank_returns_solo_tier():
    c = _client({"entries/by-puuid": [
        {"queueType": "RANKED_FLEX_SR", "tier": "GOLD"},
        {"queueType": "RANKED_SOLO_5x5", "tier": "PLATINUM"},
    ]})
    assert await c.get_solo_rank("puuid-1") == "PLATINUM"


@pytest.mark.asyncio
async def test_get_solo_rank_none_when_unranked():
    c = _client({"entries/by-puuid": []})
    assert await c.get_solo_rank("puuid-1") is None


@pytest.mark.asyncio
async def test_get_apex_league_puuids():
    c = _client({"challengerleagues/by-queue": {"entries": [
        {"puuid": "a"}, {"puuid": "b"}, {"summonerId": "no-puuid"},
    ]}})
    assert await c.get_apex_league_puuids("CHALLENGER") == ["a", "b"]


@pytest.mark.asyncio
async def test_get_tier_division_puuids():
    c = _client({"entries/RANKED_SOLO_5x5/EMERALD/I": [
        {"puuid": "x"}, {"puuid": "y"},
    ]})
    assert await c.get_tier_division_puuids("EMERALD", "I") == ["x", "y"]


@pytest.mark.asyncio
async def test_recent_match_ids_passes_queue_param():
    c = _client({"by-puuid/p/ids": ["NA1_1", "NA1_2"]})
    await c.get_recent_match_ids("p", count=5, queue=420)
    url, params = c._http.calls[-1]
    assert params["queue"] == 420
    assert params["count"] == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sidecar && python -m pytest tests/test_riot_league.py -v`
Expected: FAIL — `AttributeError: 'RiotClient' object has no attribute 'platform'` / missing methods.

- [ ] **Step 3: Write minimal implementation**

In `sidecar/riot_client.py`, set the platform in `__init__` (right after `self.regional = ...`):

```python
        self.platform = region.lower()
```

Replace `get_recent_match_ids` to accept `queue`:

```python
    async def get_recent_match_ids(self, puuid: str, count: int = 20,
                                   start_time: int | None = None,
                                   queue: int | None = None) -> list[str]:
        url = f"https://{self.regional}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
        params: dict = {"count": count}
        if start_time is not None:
            params["startTime"] = start_time
        if queue is not None:
            params["queue"] = queue
        r = await self._http.get(url, params=params)
        r.raise_for_status()
        return r.json()
```

Add the league-v4 methods (after `get_timeline`):

```python
    _APEX_SLUG = {
        "MASTER": "masterleagues",
        "GRANDMASTER": "grandmasterleagues",
        "CHALLENGER": "challengerleagues",
    }

    async def get_solo_rank(self, puuid: str) -> str | None:
        url = f"https://{self.platform}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"
        r = await self._http.get(url)
        r.raise_for_status()
        for entry in r.json():
            if entry.get("queueType") == "RANKED_SOLO_5x5":
                return entry.get("tier")
        return None

    async def get_apex_league_puuids(self, tier: str) -> list[str]:
        slug = self._APEX_SLUG[tier]
        url = f"https://{self.platform}.api.riotgames.com/lol/league/v4/{slug}/by-queue/RANKED_SOLO_5x5"
        r = await self._http.get(url)
        r.raise_for_status()
        return [e["puuid"] for e in r.json().get("entries", []) if e.get("puuid")]

    async def get_tier_division_puuids(self, tier: str, division: str, page: int = 1) -> list[str]:
        url = f"https://{self.platform}.api.riotgames.com/lol/league/v4/entries/RANKED_SOLO_5x5/{tier}/{division}"
        r = await self._http.get(url, params={"page": page})
        r.raise_for_status()
        return [e["puuid"] for e in r.json() if e.get("puuid")]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sidecar && python -m pytest tests/test_riot_league.py -v`
Expected: PASS (6 tests). Then run the full backend gate to confirm no regression in existing match-id callers: `cd sidecar && python -m pytest`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sidecar/riot_client.py sidecar/tests/test_riot_league.py
git commit -m "feat: add league-v4 rank + seed-player lookups to RiotClient

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Benchmark harvester

**Files:**
- Create: `sidecar/benchmark_harvester.py`
- Test: `sidecar/tests/test_benchmark_harvester.py`

**Interfaces:**
- Consumes: `benchmark_tiers.next_tier_up`, `benchmark_tiers.APEX_TIERS`, `benchmark_metrics.extract_participant_metrics`, `database.{record_benchmark_samples,is_match_harvested,mark_match_harvested,set_app_state,get_app_state}`, `RiotClient.{get_solo_rank,get_apex_league_puuids,get_tier_division_puuids,get_recent_match_ids,get_match,is_in_game}`.
- Produces:
  - `should_harvest(db, now: datetime) -> bool` — `True` if no prior run or last run > `STALE_DAYS` ago.
  - `async run_harvest(riot, db, player) -> None` — resolves target tier, seeds players, harvests up to `MATCH_FETCH_BUDGET` new ranked-solo matches, accumulates every participant's metrics bucketed by `teamPosition`, writes `benchmark_user_tier` / `benchmark_target_tier` / `benchmark_updated_at` app_state. Skips when `is_in_game()`.
  - Constants: `SEED_PLAYER_CAP=30`, `MATCHES_PER_SEED=10`, `MATCH_FETCH_BUDGET=300`, `RANKED_SOLO_QUEUE=420`, `STALE_DAYS=14`, `SEED_DIVISION="I"`, `HARVEST_PACING_SECS=1.2`.

- [ ] **Step 1: Write the failing test**

```python
# sidecar/tests/test_benchmark_harvester.py
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import benchmark_harvester as bh
from database import get_benchmarks, is_match_harvested, get_app_state


class FakeRiot:
    def __init__(self, *, solo_rank, seed_puuids, matches, in_game=False):
        self.solo_rank = solo_rank
        self.seed_puuids = seed_puuids
        self.matches = matches  # {match_id: match_dict}
        self._in_game = in_game
        self.match_fetches = 0

    async def is_in_game(self):
        return self._in_game

    async def get_solo_rank(self, puuid):
        return self.solo_rank

    async def get_apex_league_puuids(self, tier):
        return list(self.seed_puuids)

    async def get_tier_division_puuids(self, tier, division, page=1):
        return list(self.seed_puuids)

    async def get_recent_match_ids(self, puuid, count=20, queue=None):
        return list(self.matches.keys())

    async def get_match(self, match_id):
        self.match_fetches += 1
        return self.matches[match_id]


def _match(*positions):
    """A match whose participants each have the given teamPosition."""
    parts = []
    for i, pos in enumerate(positions):
        parts.append({
            "kills": 5, "deaths": 2, "assists": 7,
            "totalMinionsKilled": 200, "goldEarned": 14000, "visionScore": 30,
            "teamPosition": pos,
        })
    return {"info": {"gameVersion": "14.12.1", "participants": parts}}


@pytest.fixture
def player():
    return SimpleNamespace(riot_puuid="me")


@pytest.mark.asyncio
async def test_run_harvest_accumulates_per_role(db, player):
    riot = FakeRiot(
        solo_rank="DIAMOND",  # -> target MASTER (apex)
        seed_puuids=["s1"],
        matches={"NA1_1": _match("MIDDLE", "TOP")},
    )
    await bh.run_harvest(riot, db, player)
    mid = get_benchmarks(db, "MASTER", "MIDDLE")
    top = get_benchmarks(db, "MASTER", "TOP")
    assert mid["cs"] == (200.0, 1)
    assert top["cs"] == (200.0, 1)
    assert get_app_state(db, "benchmark_target_tier") == "MASTER"
    assert get_app_state(db, "benchmark_user_tier") == "DIAMOND"
    assert get_app_state(db, "benchmark_updated_at") is not None


@pytest.mark.asyncio
async def test_run_harvest_skips_unknown_role(db, player):
    riot = FakeRiot(solo_rank="DIAMOND", seed_puuids=["s1"],
                    matches={"NA1_1": _match("MIDDLE", "")})
    await bh.run_harvest(riot, db, player)
    assert get_benchmarks(db, "MASTER", "MIDDLE")["cs"] == (200.0, 1)
    assert get_benchmarks(db, "MASTER", "") == {}


@pytest.mark.asyncio
async def test_run_harvest_dedups_matches(db, player):
    riot = FakeRiot(solo_rank="DIAMOND", seed_puuids=["s1", "s2"],
                    matches={"NA1_1": _match("MIDDLE")})
    await bh.run_harvest(riot, db, player)
    # both seeds return NA1_1; it must only be counted once
    assert get_benchmarks(db, "MASTER", "MIDDLE")["cs"] == (200.0, 1)
    assert is_match_harvested(db, "NA1_1") is True
    assert riot.match_fetches == 1


@pytest.mark.asyncio
async def test_run_harvest_skips_when_in_game(db, player):
    riot = FakeRiot(solo_rank="DIAMOND", seed_puuids=["s1"],
                    matches={"NA1_1": _match("MIDDLE")}, in_game=True)
    await bh.run_harvest(riot, db, player)
    assert get_benchmarks(db, "MASTER", "MIDDLE") == {}


@pytest.mark.asyncio
async def test_run_harvest_unranked_targets_platinum(db, player):
    riot = FakeRiot(solo_rank=None, seed_puuids=["s1"],
                    matches={"NA1_1": _match("BOTTOM")})
    await bh.run_harvest(riot, db, player)
    assert get_app_state(db, "benchmark_user_tier") == "UNRANKED"
    assert get_app_state(db, "benchmark_target_tier") == "PLATINUM"
    assert get_benchmarks(db, "PLATINUM", "BOTTOM")["cs"] == (200.0, 1)


def test_should_harvest_true_when_never_run(db):
    assert bh.should_harvest(db, datetime.now(timezone.utc)) is True


def test_should_harvest_false_when_fresh(db):
    from database import set_app_state
    now = datetime.now(timezone.utc)
    set_app_state(db, "benchmark_updated_at", now.isoformat())
    assert bh.should_harvest(db, now + timedelta(days=1)) is False


def test_should_harvest_true_when_stale(db):
    from database import set_app_state
    now = datetime.now(timezone.utc)
    set_app_state(db, "benchmark_updated_at", now.isoformat())
    assert bh.should_harvest(db, now + timedelta(days=15)) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sidecar && python -m pytest tests/test_benchmark_harvester.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'benchmark_harvester'`

- [ ] **Step 3: Write minimal implementation**

```python
# sidecar/benchmark_harvester.py
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from benchmark_metrics import extract_participant_metrics
from benchmark_tiers import APEX_TIERS, next_tier_up
from database import (
    get_app_state, is_match_harvested, mark_match_harvested,
    record_benchmark_samples, set_app_state,
)

logger = logging.getLogger(__name__)

SEED_PLAYER_CAP = 30
MATCHES_PER_SEED = 10
MATCH_FETCH_BUDGET = 300
RANKED_SOLO_QUEUE = 420
SEED_DIVISION = "I"
STALE_DAYS = 14
HARVEST_PACING_SECS = 1.2
_RATE_LIMIT_BACKOFF_SECS = 10


def should_harvest(db, now: datetime) -> bool:
    updated = get_app_state(db, "benchmark_updated_at")
    if not updated:
        return True
    return now - datetime.fromisoformat(updated) > timedelta(days=STALE_DAYS)


async def _seed_puuids(riot, target_tier: str) -> list[str]:
    if target_tier in APEX_TIERS:
        return await riot.get_apex_league_puuids(target_tier)
    return await riot.get_tier_division_puuids(target_tier, SEED_DIVISION)


def _accumulate_match(db, target_tier: str, match: dict) -> None:
    info = match["info"]
    patch = info.get("gameVersion", "unknown")
    for p in info["participants"]:
        role = p.get("teamPosition") or ""
        if not role:
            continue
        record_benchmark_samples(db, target_tier, role, patch, extract_participant_metrics(p))


async def run_harvest(riot, db, player) -> None:
    if await riot.is_in_game():
        logger.info("[benchmark] game in progress; skipping harvest")
        return

    user_tier = await riot.get_solo_rank(player.riot_puuid)
    target_tier = next_tier_up(user_tier)
    set_app_state(db, "benchmark_user_tier", user_tier or "UNRANKED")
    set_app_state(db, "benchmark_target_tier", target_tier)
    logger.info("[benchmark] harvesting tier=%s (user=%s)", target_tier, user_tier)

    seed_puuids = (await _seed_puuids(riot, target_tier))[:SEED_PLAYER_CAP]
    fetches = 0
    for puuid in seed_puuids:
        if fetches >= MATCH_FETCH_BUDGET:
            break
        try:
            match_ids = await riot.get_recent_match_ids(
                puuid, count=MATCHES_PER_SEED, queue=RANKED_SOLO_QUEUE)
        except Exception as e:
            logger.warning("[benchmark] match-id fetch failed for %s: %s", puuid, e)
            continue
        for mid in match_ids:
            if fetches >= MATCH_FETCH_BUDGET:
                break
            if is_match_harvested(db, mid):
                continue
            try:
                match = await riot.get_match(mid)
                fetches += 1
                await asyncio.sleep(HARVEST_PACING_SECS)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning("[benchmark] rate limited; backing off")
                    await asyncio.sleep(_RATE_LIMIT_BACKOFF_SECS)
                continue
            except Exception as e:
                logger.warning("[benchmark] match fetch failed for %s: %s", mid, e)
                continue
            _accumulate_match(db, target_tier, match)
            mark_match_harvested(db, mid)

    set_app_state(db, "benchmark_updated_at", datetime.now(timezone.utc).isoformat())
    logger.info("[benchmark] harvest complete: %d matches", fetches)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sidecar && python -m pytest tests/test_benchmark_harvester.py -v`
Expected: PASS (8 tests). The `asyncio.sleep(1.2)` calls run in-test against the fake (1 match each), so runtime stays small.

- [ ] **Step 5: Commit**

```bash
git add sidecar/benchmark_harvester.py sidecar/tests/test_benchmark_harvester.py
git commit -m "feat: add high-elo benchmark harvester

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: `/benchmarks` endpoint + background task

**Files:**
- Modify: `sidecar/main.py`
- Test: `sidecar/tests/test_benchmarks_api.py`

**Interfaces:**
- Consumes: `database.{get_benchmarks,get_app_state}`, `goal_metrics.METRICS`, `benchmark_harvester.{run_harvest,should_harvest}`, `get_matches`, `get_player`, `Counter`.
- Produces:
  - `get_benchmarks_view()` (handler for `GET /benchmarks`) returning
    `{user_tier, target_tier, role, status, updated_at, metrics: [{metric_key,label,comparison,your_avg,tier_avg,sample_count}]}`.
  - `benchmark_harvest_task()` registered in `lifespan`.
  - Module constant `BENCHMARK_SAMPLE_FLOOR = 30`.

- [ ] **Step 1: Write the failing test**

```python
# sidecar/tests/test_benchmarks_api.py
"""API-layer tests for GET /benchmarks (same import-main pattern as test_goals_api)."""
import os
import tempfile
from datetime import datetime

import pytest

os.environ.setdefault("RIOT_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test_benchmarks_api.db")

import main as main_module  # noqa: E402
from database import save_match, record_benchmark_samples, set_app_state  # noqa: E402


@pytest.fixture
def api_db(db, monkeypatch):
    monkeypatch.setattr(main_module, "db", db)
    return db


def _save(db, mid, day, role="MIDDLE", kda="4/2/6", cs=180):
    save_match(db, {
        "match_id": mid, "played_at": datetime(2026, 1, day, 12, 0),
        "champion": "Ahri", "role": role, "result": "win", "duration_secs": 1800,
        "kda": kda, "cs": cs, "gold_earned": 12000, "vision_score": 25,
        "raw_timeline": {},
    })


def test_status_none_when_no_harvest(api_db):
    _save(api_db, "m1", 1)
    out = main_module.get_benchmarks_view()
    assert out["status"] == "none"
    assert out["metrics"] == []


def test_pairs_your_avg_with_tier_avg(api_db):
    _save(api_db, "m1", 1, role="MIDDLE", cs=180)
    _save(api_db, "m2", 2, role="MIDDLE", cs=220)
    set_app_state(api_db, "benchmark_user_tier", "PLATINUM")
    set_app_state(api_db, "benchmark_target_tier", "DIAMOND")
    set_app_state(api_db, "benchmark_updated_at", datetime.now().isoformat())
    # 40 MIDDLE samples for cs so it clears the floor
    for _ in range(40):
        record_benchmark_samples(api_db, "DIAMOND", "MIDDLE", "14.12", {"cs": 250.0})
    out = main_module.get_benchmarks_view()
    assert out["role"] == "MIDDLE"
    assert out["target_tier"] == "DIAMOND"
    assert out["status"] == "ready"
    cs = next(m for m in out["metrics"] if m["metric_key"] == "cs")
    assert cs["your_avg"] == 200.0          # (180+220)/2
    assert cs["tier_avg"] == 250.0
    assert cs["sample_count"] == 40


def test_tier_avg_null_below_sample_floor(api_db):
    _save(api_db, "m1", 1, role="MIDDLE")
    set_app_state(api_db, "benchmark_target_tier", "DIAMOND")
    set_app_state(api_db, "benchmark_updated_at", datetime.now().isoformat())
    record_benchmark_samples(api_db, "DIAMOND", "MIDDLE", "14.12", {"cs": 250.0})  # 1 < floor
    out = main_module.get_benchmarks_view()
    cs = next(m for m in out["metrics"] if m["metric_key"] == "cs")
    assert cs["tier_avg"] is None
    assert out["status"] == "harvesting"  # no metric cleared the floor yet
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sidecar && python -m pytest tests/test_benchmarks_api.py -v`
Expected: FAIL with `AttributeError: module 'main' has no attribute 'get_benchmarks_view'`

- [ ] **Step 3: Write minimal implementation**

In `sidecar/main.py`, extend imports:

```python
from database import (
    ...,
    get_app_state, get_benchmarks,
)
from benchmark_harvester import run_harvest, should_harvest
```

Add the constant near the other module constants (after `REGION = ...`):

```python
BENCHMARK_SAMPLE_FLOOR = 30
```

Add the background task (after `backfill_history`):

```python
async def benchmark_harvest_task():
    await asyncio.sleep(60)  # let first-run backfill take the rate limit first
    while True:
        try:
            player = get_player(db)
            if player and should_harvest(db, datetime.now(timezone.utc)):
                await run_harvest(riot, db, player)
        except Exception as e:
            logger.error("[benchmark] harvest task error: %s", e)
        await asyncio.sleep(6 * 3600)
```

Register it in `lifespan`, alongside the other `create_task` calls:

```python
    asyncio.create_task(benchmark_harvest_task())
```

Add the endpoint (after the `/goals` routes):

```python
def _benchmark_status(updated_at: Optional[str], has_data: bool) -> str:
    if not has_data:
        return "harvesting"
    if updated_at:
        parsed = datetime.fromisoformat(updated_at)
        if parsed.tzinfo is None:  # tolerate naive timestamps
            parsed = parsed.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - parsed).days > 14:
            return "stale"
    return "ready"


@app.get("/benchmarks")
def get_benchmarks_view():
    recent = get_matches(db, last_n=20)
    user_tier = get_app_state(db, "benchmark_user_tier")
    target_tier = get_app_state(db, "benchmark_target_tier")
    updated_at = get_app_state(db, "benchmark_updated_at")

    if not recent or not target_tier:
        return {
            "user_tier": user_tier, "target_tier": target_tier, "role": None,
            "status": "harvesting" if target_tier else "none",
            "updated_at": updated_at, "metrics": [],
        }

    primary_role = Counter(m.role for m in recent).most_common(1)[0][0]
    role_matches = [m for m in recent if m.role == primary_role]
    tier_rows = get_benchmarks(db, target_tier, primary_role)

    metrics = []
    for key, metric in METRICS.items():
        your_vals = [metric.value(m) for m in role_matches]
        your_avg = round(sum(your_vals) / len(your_vals), 1) if your_vals else None
        agg = tier_rows.get(key)
        if agg and agg[1] >= BENCHMARK_SAMPLE_FLOOR:
            tier_avg = round(agg[0] / agg[1], 1)
        else:
            tier_avg = None
        metrics.append({
            "metric_key": key, "label": metric.label, "comparison": metric.comparison,
            "your_avg": your_avg, "tier_avg": tier_avg,
            "sample_count": agg[1] if agg else 0,
        })

    has_data = any(m["tier_avg"] is not None for m in metrics)
    return {
        "user_tier": user_tier, "target_tier": target_tier, "role": primary_role,
        "status": _benchmark_status(updated_at, has_data),
        "updated_at": updated_at, "metrics": metrics,
    }
```

(`Counter` is already imported at the top of `main.py`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sidecar && python -m pytest tests/test_benchmarks_api.py -v`
Expected: PASS (3 tests). Then the full backend gate: `cd sidecar && python -m pytest`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sidecar/main.py sidecar/tests/test_benchmarks_api.py
git commit -m "feat: add /benchmarks endpoint and auto-harvest task

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Frontend benchmark block in GoalsPanel

**Files:**
- Modify: `src/shared/types.ts`
- Modify: `src/chat/GoalsPanel.tsx`
- Test: `src/chat/GoalsPanel.test.tsx`

**Interfaces:**
- Consumes: `GET /benchmarks` (shape from Task 6).
- Produces: `BenchmarkMetric` + `BenchmarkResponse` types; a "Benchmarks vs {tier}" block rendered above the goals list.

- [ ] **Step 1: Write the failing test**

Add to `src/chat/GoalsPanel.test.tsx`. First extend the imports and the mocked `getJson` to serve `/benchmarks`, then add the new cases:

```typescript
import type { Goal, GoalMetricInfo, BenchmarkResponse } from '../shared/types'

const benchmarks: BenchmarkResponse = {
  user_tier: 'PLATINUM',
  target_tier: 'DIAMOND',
  role: 'MIDDLE',
  status: 'ready',
  updated_at: '2026-06-24T00:00:00Z',
  metrics: [
    { metric_key: 'deaths', label: 'Deaths', comparison: 'lte', your_avg: 5.4, tier_avg: 4.1, sample_count: 1830 },
    { metric_key: 'cs', label: 'CS', comparison: 'gte', your_avg: 180, tier_avg: 220, sample_count: 1830 },
  ],
}
```

Update the existing `beforeEach` `getJson` mock to add a `/benchmarks` branch:

```typescript
    if (path === '/benchmarks') return benchmarks as unknown as never
```

Add the test cases inside `describe('GoalsPanel', ...)`:

```typescript
  it('renders the benchmark block against the target tier', async () => {
    render(<GoalsPanel />)
    expect(await screen.findByText(/Benchmarks vs Diamond/i)).toBeInTheDocument()
    expect(screen.getByTestId('bench-deaths')).toHaveTextContent('5.4')
    expect(screen.getByTestId('bench-deaths')).toHaveTextContent('4.1')
  })

  it('shows a building state while harvesting', async () => {
    vi.mocked(api.getJson).mockImplementation(async (path: string) => {
      if (path === '/goals') return [] as unknown as never
      if (path === '/goals/metrics') return metrics as unknown as never
      if (path === '/benchmarks') return { ...benchmarks, status: 'harvesting', metrics: [] } as unknown as never
      return null
    })
    render(<GoalsPanel />)
    expect(await screen.findByText(/building your benchmarks/i)).toBeInTheDocument()
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- GoalsPanel`
Expected: FAIL — `BenchmarkResponse` not exported / "Benchmarks vs Diamond" not found.

- [ ] **Step 3: Write minimal implementation**

Add to `src/shared/types.ts` (after the `Goal` interface):

```typescript
/** One metric row from `GET /benchmarks`. */
export interface BenchmarkMetric {
  metric_key: string
  label: string
  comparison: 'gte' | 'lte'
  your_avg: number | null
  tier_avg: number | null
  sample_count: number
}

/** `GET /benchmarks` payload: your recent averages vs the target tier's. */
export interface BenchmarkResponse {
  user_tier: string | null
  target_tier: string | null
  role: string | null
  status: 'ready' | 'harvesting' | 'stale' | 'none'
  updated_at: string | null
  metrics: BenchmarkMetric[]
}
```

In `src/chat/GoalsPanel.tsx`, extend the type import and add benchmark state + fetch, then render the block. Update the import line:

```typescript
import type { Goal, GoalMetricInfo, BenchmarkResponse, BenchmarkMetric } from '../shared/types'
```

Add a helper above the component (after `COMPARISON_WORDS`):

```typescript
const titleCase = (s: string) => s.charAt(0) + s.slice(1).toLowerCase()

/** Is the player's average on the good side of the tier benchmark? */
function meetsTier(m: BenchmarkMetric): boolean | null {
  if (m.your_avg === null || m.tier_avg === null) return null
  return m.comparison === 'lte' ? m.your_avg <= m.tier_avg : m.your_avg >= m.tier_avg
}
```

Inside the component, add state and a fetch effect (after the existing `useEffect`):

```typescript
  const [bench, setBench] = useState<BenchmarkResponse | null>(null)

  useEffect(() => {
    getJson<BenchmarkResponse>('/benchmarks').then(d => setBench(d ?? null))
  }, [])
```

Render the block at the top of the returned `<div className="flex-1 ...">`, immediately after the `🎯 GOALS` header div:

```tsx
      {bench && bench.status !== 'none' && (
        <div className="mb-4 bg-[#1a1a3a] border border-indigo-500/40 rounded-lg px-3 py-2">
          <div className="text-[10px] font-bold text-indigo-300 mb-2">
            📊 Benchmarks vs {bench.target_tier ? titleCase(bench.target_tier) : ''}
          </div>
          {bench.status === 'harvesting' || bench.metrics.length === 0 ? (
            <div className="text-gray-500 text-xs">Building your benchmarks…</div>
          ) : (
            <div className="flex flex-col gap-1">
              {bench.metrics.map(m => {
                const good = meetsTier(m)
                return (
                  <div
                    key={m.metric_key}
                    data-testid={`bench-${m.metric_key}`}
                    className="flex items-center text-xs"
                  >
                    <span className="text-gray-300 w-24">{m.label}</span>
                    <span
                      className={
                        good === null ? 'text-gray-400'
                          : good ? 'text-green-400' : 'text-red-400'
                      }
                    >
                      {m.your_avg ?? '—'}
                    </span>
                    <span className="text-gray-600 mx-1">vs</span>
                    <span className="text-gray-300">
                      {m.tier_avg ?? 'not enough data'}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
```

- [ ] **Step 4: Run tests + full frontend gate**

Run: `npm test -- GoalsPanel`
Expected: PASS (existing 4 + new 2).

Run: `npm run typecheck && npm run lint && npm test`
Expected: all green (lint baseline 0 errors; the only warnings are the expected `react-refresh/only-export-components` on window entry files).

- [ ] **Step 5: Commit**

```bash
git add src/shared/types.ts src/chat/GoalsPanel.tsx src/chat/GoalsPanel.test.tsx
git commit -m "feat: show higher-elo benchmarks in the Goals tab

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification (after all tasks)

- [ ] `cd sidecar && python -m pytest` — full backend suite green.
- [ ] `npm run typecheck && npm run lint && npm test` — full frontend gate green.
- [ ] Manual smoke (optional, needs a real key): run the sidecar, hit `GET /benchmarks`; confirm it returns `status: "harvesting"` immediately and (after the background harvest) paired averages.

## Self-review notes (spec coverage)

- **Metric scope (5 match-row metrics, no timeline):** Task 2 + Task 5 (`extract_participant_metrics`, no `get_timeline` call). ✅
- **Adaptive "one above me" + unranked fallback + Challenger cap:** Task 1 + Task 5. ✅
- **league-v4 platform routing:** Task 4. ✅
- **All-10-participants attribution, role bucketing:** Task 5 (`_accumulate_match`). ✅
- **Data model (sum+count, dedup table, app_state):** Task 3. ✅
- **Fully-automatic, budget-capped, 429-aware, skip-in-game, 14-day refresh:** Task 5 + Task 6. ✅
- **Goals-tab UI, sourced from one metric registry:** Task 6 (`METRICS` loop) + Task 7. ✅
- **Sample-count floor → "not enough data":** Task 6 + Task 7. ✅
- **Spec deviation (intentional):** the auto-refresh trigger uses the 14-day age gate only, not patch-change detection (patch-change would cost an extra Riot call; 14-day cadence already covers ~biweekly patch turnover). `patch` is still stored per row for transparency and is summed across patches in `get_benchmarks`.
