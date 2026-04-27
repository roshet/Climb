import pytest
from datetime import datetime
from database import save_match, save_pivotal_moments
from improvement_tracker import get_improvement_data


def make_match(db, match_id, champion="Graves", result="loss", day=1, moment_types=None):
    save_match(db, {
        "match_id": match_id,
        "played_at": datetime(2026, 1, day, 12, 0),
        "champion": champion,
        "role": "JUNGLE",
        "result": result,
        "duration_secs": 1800,
        "kda": "2/3/4",
        "cs": 100,
        "gold_earned": 9000,
        "vision_score": 15,
        "raw_timeline": {},
    })
    if moment_types:
        save_pivotal_moments(db, match_id, [
            {"timestamp_secs": 300, "moment_type": mt,
             "description": "", "counterfactual": "", "gold_impact": 0}
            for mt in moment_types
        ])


def test_returns_empty_when_insufficient_history(db):
    for i in range(2):
        make_match(db, f"m{i}", day=i + 1, moment_types=["lane_death"])
    result = get_improvement_data(db, "m1")
    assert result is not None
    assert result["patterns"] == []


def test_returns_none_when_match_not_found(db):
    result = get_improvement_data(db, "nonexistent_id")
    assert result is None


def test_had_in_game_true_when_moment_present(db):
    for i in range(5):
        make_match(db, f"m{i}", day=i + 1, moment_types=["lane_death"])
    result = get_improvement_data(db, "m4")
    issue = next(p for p in result["patterns"] if p["moment_type"] == "lane_death")
    assert issue["had_in_game"] is True


def test_had_in_game_false_when_moment_absent(db):
    for i in range(4):
        make_match(db, f"m{i}", day=i + 1, moment_types=["lane_death"])
    make_match(db, "m4", day=5, moment_types=[])
    result = get_improvement_data(db, "m4")
    issue = next(p for p in result["patterns"] if p["moment_type"] == "lane_death")
    assert issue["had_in_game"] is False


def test_streak_counts_consecutive_clean_games(db):
    # 4 games with lane_death (days 1-4), 3 clean (days 5-7), this game clean (day 8)
    for i in range(4):
        make_match(db, f"dirty_{i}", day=i + 1, moment_types=["lane_death"])
    for i in range(3):
        make_match(db, f"clean_{i}", day=i + 5, moment_types=[])
    make_match(db, "this_game", day=8, moment_types=[])
    result = get_improvement_data(db, "this_game")
    issue = next(p for p in result["patterns"] if p["moment_type"] == "lane_death")
    assert issue["streak"] == 4  # this_game + 3 preceding clean games


def test_recent_rate_counts_last_5_games(db):
    # 10 games + this game, all with lane_death → last 5 all hit → recent_rate == 5
    for i in range(10):
        make_match(db, f"old_{i}", day=i + 1, moment_types=["lane_death"])
    make_match(db, "this_game", day=11, moment_types=["lane_death"])
    result = get_improvement_data(db, "this_game")
    issue = next(p for p in result["patterns"] if p["moment_type"] == "lane_death")
    assert issue["recent_rate"] == 5


def test_win_condition_filtered_when_rare_and_absent(db):
    # 7 early wins with solo_kill (days 1-7), 3 recent wins without (days 8-10), this game no solo_kill (day 11)
    # recent_rate in last 5 (days 7-11): only day 7 has solo_kill → recent_rate=1, had_in_game=False → filtered
    for i in range(7):
        make_match(db, f"old_win_{i}", result="win", day=i + 1,
                   moment_types=["solo_kill", "lane_death"])
    for i in range(3):
        make_match(db, f"recent_{i}", result="win", day=i + 8,
                   moment_types=["lane_death"])
    make_match(db, "this_game", result="loss", day=11, moment_types=["lane_death"])
    result = get_improvement_data(db, "this_game")
    win_cond = next((p for p in result["patterns"] if p["label"] == "win_condition"), None)
    assert win_cond is None
