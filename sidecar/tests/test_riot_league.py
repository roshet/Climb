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
