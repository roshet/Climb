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
