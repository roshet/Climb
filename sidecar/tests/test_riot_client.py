import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from riot_client import RiotClient

SAMPLE_PUUID = "abc-puuid-123"
SAMPLE_MATCH_ID = "NA1_4567890"

SAMPLE_MATCH = {
    "metadata": {"matchId": SAMPLE_MATCH_ID, "participants": [SAMPLE_PUUID]},
    "info": {
        "gameDuration": 1380,
        "participants": [{
            "puuid": SAMPLE_PUUID,
            "championName": "Jinx",
            "teamPosition": "BOTTOM",
            "win": False,
            "kills": 5, "deaths": 2, "assists": 8,
            "totalMinionsKilled": 180,
            "goldEarned": 12000,
            "visionScore": 22,
        }]
    }
}

SAMPLE_TIMELINE = {
    "metadata": {"matchId": SAMPLE_MATCH_ID},
    "info": {
        "frames": [
            {"timestamp": 60000, "participantFrames": {}, "events": []},
            {"timestamp": 120000, "participantFrames": {}, "events": [
                {"type": "CHAMPION_KILL", "timestamp": 95000, "killerId": 1, "victimId": 2, "position": {"x": 5000, "y": 7000}}
            ]}
        ]
    }
}

@pytest.fixture
def client():
    return RiotClient(api_key="RGAPI-test", region="NA1")

@pytest.mark.asyncio
async def test_get_match_ids(client):
    with patch.object(client._http, "get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [SAMPLE_MATCH_ID])
        ids = await client.get_recent_match_ids(SAMPLE_PUUID, count=1)
    assert ids == [SAMPLE_MATCH_ID]

@pytest.mark.asyncio
async def test_get_match(client):
    with patch.object(client._http, "get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: SAMPLE_MATCH)
        match = await client.get_match(SAMPLE_MATCH_ID)
    assert match["info"]["participants"][0]["championName"] == "Jinx"

@pytest.mark.asyncio
async def test_get_timeline(client):
    with patch.object(client._http, "get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: SAMPLE_TIMELINE)
        timeline = await client.get_timeline(SAMPLE_MATCH_ID)
    assert len(timeline["info"]["frames"]) == 2

@pytest.mark.asyncio
async def test_get_puuid_by_summoner(client):
    with patch.object(client._http, "get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"puuid": SAMPLE_PUUID, "gameName": "TestPlayer", "tagLine": "NA1"})
        puuid = await client.get_puuid_by_summoner("TestPlayer", "NA1")
    assert puuid == SAMPLE_PUUID

@pytest.mark.asyncio
async def test_is_in_game_true(client):
    with patch.object(client._live_http, "get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200)
        result = await client.is_in_game()
    assert result is True

@pytest.mark.asyncio
async def test_is_in_game_false_on_connection_error(client):
    with patch.object(client._live_http, "get", side_effect=httpx.ConnectError("refused")):
        result = await client.is_in_game()
    assert result is False


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
