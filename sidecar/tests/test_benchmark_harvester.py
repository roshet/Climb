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
async def test_run_harvest_stops_mid_run_when_game_starts(db, player):
    """Per-iteration is_in_game check: harvest stops after first seed when game begins."""
    class MidRunGameRiot(FakeRiot):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._is_in_game_calls = 0

        async def is_in_game(self):
            self._is_in_game_calls += 1
            # First call: run-start check — no game yet
            # Second call: first seed iteration — game has started
            return self._is_in_game_calls >= 2

        async def get_recent_match_ids(self, puuid, count=20, queue=None):
            # Each seed has its own unique match id keyed by puuid
            return [f"NA1_{puuid}"]

    riot = MidRunGameRiot(
        solo_rank="DIAMOND",
        seed_puuids=["s1", "s2"],
        matches={
            "NA1_s1": _match("MIDDLE"),
            "NA1_s2": _match("TOP"),
        },
    )
    await bh.run_harvest(riot, db, player)

    # The run was cut short: s1's match was never fetched (game detected before s1),
    # so s2's match certainly was not fetched either.
    assert riot.match_fetches == 0
    assert get_benchmarks(db, "MASTER", "MIDDLE") == {}
    assert get_benchmarks(db, "MASTER", "TOP") == {}
    # benchmark_updated_at should still be written (partial harvest counts)
    assert get_app_state(db, "benchmark_updated_at") is not None


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
