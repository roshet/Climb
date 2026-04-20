import pytest
from unittest.mock import MagicMock, patch
from claude_client import ClaudeClient, build_system_prompt

def test_build_system_prompt_includes_player_name():
    prompt = build_system_prompt("TestPlayer")
    assert "TestPlayer" in prompt
    assert "analyst" in prompt.lower() or "coach" in prompt.lower()

def test_build_system_prompt_mentions_tools():
    prompt = build_system_prompt("TestPlayer")
    assert "get_matches" in prompt or "tool" in prompt.lower()

def test_claude_client_formats_tool_result_get_matches():
    db = MagicMock()
    mock_match = MagicMock()
    mock_match.match_id = "NA1_123"
    mock_match.champion = "Jinx"
    mock_match.result = "loss"
    mock_match.played_at.isoformat.return_value = "2026-04-01T20:00:00"
    mock_match.kda = "5/2/8"
    mock_match.cs = 180
    mock_match.gold_earned = 12000
    mock_match.vision_score = 22

    with patch("claude_client.get_matches", return_value=[mock_match]):
        client = ClaudeClient(api_key="test-key", db=db)
        result = client._handle_tool("get_matches", {"result": "loss", "last_n": 5})

    assert "Jinx" in result
    assert "loss" in result

def test_claude_client_formats_tool_result_get_champion_stats():
    db = MagicMock()
    mock_match = MagicMock()
    mock_match.champion = "Jinx"
    mock_match.result = "win"
    mock_match.kda = "8/1/5"
    mock_match.cs = 210
    mock_match.gold_earned = 15000
    mock_match.vision_score = 25

    with patch("claude_client.get_matches", return_value=[mock_match]):
        client = ClaudeClient(api_key="test-key", db=db)
        result = client._handle_tool("get_champion_stats", {"champion": "Jinx", "last_n": 10})

    assert "Jinx" in result
    assert "win" in result.lower() or "1" in result


from unittest.mock import patch
from timeline_analyzer import PivotalMomentData
from pattern_detector import PatternResult


def _make_coaching_client():
    db = MagicMock()
    with patch("claude_client.genai.Client"):
        client = ClaudeClient(api_key="test", db=db)
    mock_response = MagicMock()
    mock_response.text = '[{"id": 0, "coaching": "test note"}]'
    client.client.models.generate_content.return_value = mock_response
    return client


def _make_moment():
    return PivotalMomentData(
        timestamp_secs=300,
        moment_type="lane_death",
        description="You died at 5:00",
        counterfactual="",
        gold_impact=300,
    )


def _make_game_context():
    return {
        "participant_id": 1,
        "champion": "Caitlyn",
        "role": "BOTTOM",
        "side": "blue",
        "result": "loss",
        "kda": "3/7/4",
        "duration_secs": 2052,
    }


def test_generate_coaching_notes_without_patterns():
    client = _make_coaching_client()
    client.generate_coaching_notes(
        [_make_moment()], _make_game_context(), {"info": {"frames": []}}, patterns=None
    )
    prompt = client.client.models.generate_content.call_args[1]["contents"]
    assert "Player's cross-game patterns" not in prompt


def test_generate_coaching_notes_with_patterns():
    client = _make_coaching_client()
    patterns = [
        PatternResult(
            moment_type="objective_missed",
            label="recurring_issue",
            games_seen=9,
            total_games=20,
            win_rate_with=0.44,
            overall_win_rate=0.55,
            summary="missed objectives in 9 of your last 20 games (44% win rate)",
        ),
        PatternResult(
            moment_type="baron_secured",
            label="win_condition",
            games_seen=3,
            total_games=20,
            win_rate_with=1.0,
            overall_win_rate=0.55,
            summary="baron secured in 3 of your last 20 games (100% win rate)",
        ),
    ]
    client.generate_coaching_notes(
        [_make_moment()], _make_game_context(), {"info": {"frames": []}}, patterns=patterns
    )
    prompt = client.client.models.generate_content.call_args[1]["contents"]
    assert "Player's cross-game patterns" in prompt
    assert "Recurring issues:" in prompt
    assert "objective_missed" in prompt
    assert "Win conditions:" in prompt
    assert "baron_secured" in prompt


def test_generate_coaching_notes_with_empty_patterns():
    client = _make_coaching_client()
    client.generate_coaching_notes(
        [_make_moment()], _make_game_context(), {"info": {"frames": []}}, patterns=[]
    )
    prompt = client.client.models.generate_content.call_args[1]["contents"]
    assert "Player's cross-game patterns" not in prompt
