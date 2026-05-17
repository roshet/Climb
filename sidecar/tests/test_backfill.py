import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
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
        "lane_opponent_champion": "Darius",
    })

    mock_riot = make_mock_riot(["NA1_EXISTING", "NA1_NEW"])
    mock_claude = make_mock_claude()
    player = make_player()

    with patch("backfill.asyncio.sleep", new_callable=AsyncMock):
        with patch("backfill._backfill_opponent_champions", new_callable=AsyncMock):
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
        "lane_opponent_champion": "Darius",
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
        with patch("backfill._backfill_opponent_champions", new_callable=AsyncMock):
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

    mock_dt.now.assert_called_with(timezone.utc)
    call_kwargs = mock_riot.get_recent_match_ids.call_args
    start_time = call_kwargs[1]["start_time"]
    expected = int(1714000000.0 - 30 * 24 * 3600)
    assert start_time == expected


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


@pytest.mark.asyncio
async def test_analyze_and_save_match_passes_none_patterns_on_detect_failure(db):
    from backfill import analyze_and_save_match

    mock_riot = make_mock_riot(["NA1_NEW"])
    mock_claude = make_mock_claude()
    player = make_player()

    with patch("backfill.detect_patterns", side_effect=Exception("db error")):
        with patch("backfill.asyncio.sleep", new_callable=AsyncMock):
            await analyze_and_save_match(mock_riot, db, mock_claude, player, "NA1_NEW")

    call_kwargs = mock_claude.generate_coaching_notes.call_args[1]
    assert call_kwargs["patterns"] is None


@pytest.mark.asyncio
async def test_backfill_stores_lane_opponent_champion(db):
    from database import get_matches
    mock_riot = AsyncMock()
    mock_riot.get_recent_match_ids.return_value = ["NA1_OPP"]
    mock_riot.get_match.return_value = SAMPLE_MATCH_WITH_OPPONENT
    mock_riot.get_timeline.return_value = SAMPLE_TIMELINE

    mock_claude = make_mock_claude()
    player = make_player()

    with patch("backfill.asyncio.sleep", new_callable=AsyncMock):
        await run_backfill(mock_riot, db, mock_claude, player)

    matches = get_matches(db)
    assert len(matches) == 1
    assert matches[0].lane_opponent_champion == "Draven"
