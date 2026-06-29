# sidecar/tests/test_build_harvester.py
"""Tests that run_harvest also records build samples (items/runes/spells)."""
from types import SimpleNamespace

import pytest

import benchmark_harvester as bh
from database import get_benchmarks, get_build_suggestions


# ---------------------------------------------------------------------------
# Shared rune/spell fixture data
# ---------------------------------------------------------------------------

_PERKS = {
    "styles": [
        {
            "description": "primaryStyle",
            "style": 8000,
            "selections": [
                {"perk": 8005},
                {"perk": 9111},
                {"perk": 9105},
                {"perk": 8014},
            ],
        },
        {
            "description": "subStyle",
            "style": 8200,
            "selections": [
                {"perk": 8275},
                {"perk": 8236},
            ],
        },
    ],
    "statPerks": {"offense": 5005, "flex": 5008, "defense": 5001},
}

_EXPECTED_RUNE_SIG = "8000|8005,9111,9105,8014|8200|8275,8236|5005,5008,5001"


# ---------------------------------------------------------------------------
# Match builder
# ---------------------------------------------------------------------------

def _participant(position: str, champion: str = "Ahri", **overrides) -> dict:
    """Build a participant dict with typical build fields."""
    base = {
        # metrics fields (needed by extract_participant_metrics)
        "kills": 5, "deaths": 2, "assists": 7,
        "totalMinionsKilled": 200, "goldEarned": 14000, "visionScore": 30,
        # build fields
        "teamPosition": position,
        "championName": champion,
        "item0": 3157, "item1": 4645, "item2": 3089,
        "item3": 3135, "item4": 3020, "item5": 3916, "item6": 3364,
        "summoner1Id": 4,   # Flash
        "summoner2Id": 14,  # Ignite
        "perks": _PERKS,
    }
    base.update(overrides)
    return base


def _match_with_builds(*participants) -> dict:
    """Wrap a list of participant dicts into a match dict."""
    return {"info": {"gameVersion": "14.12.1", "participants": list(participants)}}


# ---------------------------------------------------------------------------
# FakeRiot (mirrors test_benchmark_harvester.py)
# ---------------------------------------------------------------------------

class FakeRiot:
    def __init__(self, *, solo_rank, seed_puuids, matches, in_game=False):
        self.solo_rank = solo_rank
        self.seed_puuids = seed_puuids
        self.matches = matches
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


@pytest.fixture
def player():
    return SimpleNamespace(riot_puuid="me")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_harvest_records_build_and_benchmark(db, player):
    """After harvest, both benchmark rows and build rows exist."""
    riot = FakeRiot(
        solo_rank="DIAMOND",  # -> target MASTER (apex)
        seed_puuids=["s1"],
        matches={"NA1_1": _match_with_builds(
            _participant("MIDDLE", "Ahri"),
            _participant("TOP", "Garen"),
        )},
    )
    await bh.run_harvest(riot, db, player)

    # Benchmark rows still exist
    mid_bench = get_benchmarks(db, "MASTER", "MIDDLE")
    assert mid_bench["cs"] == (200.0, 1)

    # Build rows for MIDDLE/Ahri
    mid_build = get_build_suggestions(db, "Ahri", "MIDDLE", "MASTER")
    assert mid_build["n_samples"] == 1
    # item0..item5 are [3157, 4645, 3089, 3135, 3020, 3916] (item6 is trinket, excluded)
    item_ids = [item_id for item_id, _ in mid_build["items"]]
    assert 3157 in item_ids
    assert 3364 not in item_ids  # trinket excluded
    # Rune page was recorded
    assert mid_build["rune_page"] is not None
    rune_sig, rune_count = mid_build["rune_page"]
    assert rune_sig == _EXPECTED_RUNE_SIG
    assert rune_count == 1
    # Spells were recorded (4,14 -> sorted -> "4,14")
    assert mid_build["spells"] == ("4,14", 1)

    # Build rows for TOP/Garen too
    top_build = get_build_suggestions(db, "Garen", "TOP", "MASTER")
    assert top_build["n_samples"] == 1


@pytest.mark.asyncio
async def test_run_harvest_no_double_count_on_reharvest(db, player):
    """Re-running harvest with the same match id does not double-count builds."""
    riot = FakeRiot(
        solo_rank="DIAMOND",
        seed_puuids=["s1", "s2"],  # both seeds return same match id
        matches={"NA1_1": _match_with_builds(_participant("MIDDLE", "Ahri"))},
    )
    await bh.run_harvest(riot, db, player)

    build_first = get_build_suggestions(db, "Ahri", "MIDDLE", "MASTER")
    assert build_first["n_samples"] == 1

    # Run again — same match id is already in the ledger, must be skipped
    await bh.run_harvest(riot, db, player)

    build_second = get_build_suggestions(db, "Ahri", "MIDDLE", "MASTER")
    assert build_second["n_samples"] == 1  # unchanged, not doubled


@pytest.mark.asyncio
async def test_run_harvest_skips_build_for_unknown_role(db, player):
    """A participant with empty teamPosition is skipped for builds (and benchmarks)."""
    riot = FakeRiot(
        solo_rank="DIAMOND",
        seed_puuids=["s1"],
        matches={"NA1_1": _match_with_builds(
            _participant("MIDDLE", "Ahri"),
            _participant("", "Zed"),  # no role
        )},
    )
    await bh.run_harvest(riot, db, player)

    # Ahri/MIDDLE has build data
    mid_build = get_build_suggestions(db, "Ahri", "MIDDLE", "MASTER")
    assert mid_build["n_samples"] == 1

    # Zed with no role has NO build data (n_samples == 0, items empty)
    zed_build = get_build_suggestions(db, "Zed", "", "MASTER")
    assert zed_build["n_samples"] == 0
    assert zed_build["items"] == []
