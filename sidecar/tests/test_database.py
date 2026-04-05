from datetime import datetime
from database import (
    Match, PivotalMoment, ChatMessage, Player,
    save_match, get_matches, save_pivotal_moments,
    get_pivotal_moments, save_chat_message, get_chat_history,
    save_player, get_player, set_pending_popup, get_pending_popup, clear_pending_popup
)

def test_save_and_retrieve_match(db):
    save_match(db, {
        "match_id": "NA1_123",
        "played_at": datetime(2026, 4, 1, 20, 0),
        "champion": "Jinx",
        "role": "BOTTOM",
        "result": "loss",
        "duration_secs": 1380,
        "kda": "5/2/8",
        "cs": 180,
        "gold_earned": 12000,
        "vision_score": 22,
        "raw_timeline": {"frames": []},
    })
    matches = get_matches(db)
    assert len(matches) == 1
    assert matches[0].champion == "Jinx"
    assert matches[0].result == "loss"

def test_save_and_retrieve_pivotal_moments(db):
    save_match(db, {
        "match_id": "NA1_123",
        "played_at": datetime(2026, 4, 1, 20, 0),
        "champion": "Jinx", "role": "BOTTOM", "result": "loss",
        "duration_secs": 1380, "kda": "5/2/8", "cs": 180,
        "gold_earned": 12000, "vision_score": 22, "raw_timeline": {},
    })
    save_pivotal_moments(db, "NA1_123", [
        {
            "timestamp_secs": 872,
            "moment_type": "recall",
            "description": "Recalled with tower at 20% HP nearby.",
            "counterfactual": "Staying to take the tower was the higher-value play. Est. cost: 400g.",
            "gold_impact": 400,
        }
    ])
    moments = get_pivotal_moments(db, ["NA1_123"])
    assert len(moments) == 1
    assert moments[0].moment_type == "recall"
    assert moments[0].gold_impact == 400

def test_chat_history_persists(db):
    save_chat_message(db, session_id="s1", match_id="NA1_123", role="user", content="Why did I lose?")
    save_chat_message(db, session_id="s1", match_id=None, role="assistant", content="You over-extended.")
    history = get_chat_history(db, session_id="s1")
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[1].content == "You over-extended."

def test_player_profile(db):
    save_player(db, summoner_name="TestPlayer", puuid="abc-123", region="NA1")
    player = get_player(db)
    assert player.summoner_name == "TestPlayer"
    assert player.riot_puuid == "abc-123"

def test_pending_popup_flag(db):
    assert get_pending_popup(db) is None
    set_pending_popup(db, match_id="NA1_123")
    assert get_pending_popup(db) == "NA1_123"
    clear_pending_popup(db)
    assert get_pending_popup(db) is None
