from datetime import datetime, timedelta
import pytest
from database import save_match, save_pivotal_moments
from pattern_detector import detect_patterns, PatternResult


def _make_match(db, match_id: str, result: str, played_at: datetime, moment_types: list[str]) -> None:
    save_match(db, {
        "match_id": match_id,
        "played_at": played_at,
        "champion": "Caitlyn",
        "role": "BOTTOM",
        "result": result,
        "duration_secs": 1800,
        "kda": "5/2/8",
        "cs": 150,
        "gold_earned": 12000,
        "vision_score": 20,
        "raw_timeline": {},
    })
    save_pivotal_moments(db, match_id, [
        {
            "timestamp_secs": 300,
            "moment_type": t,
            "description": f"test {t}",
            "counterfactual": "",
            "gold_impact": 300,
        }
        for t in moment_types
    ])


BASE_DATE = datetime(2026, 4, 1)


def test_empty_when_no_games(db):
    assert detect_patterns(db) == []


def test_empty_when_fewer_than_3_games(db):
    for i in range(2):
        _make_match(db, f"NA1_{i}", "loss", BASE_DATE + timedelta(days=i), ["lane_death"])
    assert detect_patterns(db) == []


def test_detects_recurring_issue(db):
    # lane_death in 7/10 games, all losses → win_rate_with = 0.0, overall = 0.3
    for i in range(10):
        result = "win" if i < 3 else "loss"
        types = ["lane_death"] if i >= 3 else []
        _make_match(db, f"NA1_{i}", result, BASE_DATE + timedelta(days=i), types)
    patterns = detect_patterns(db)
    issue = next((p for p in patterns if p.moment_type == "lane_death"), None)
    assert issue is not None
    assert issue.label == "recurring_issue"
    assert issue.games_seen == 7
    assert issue.total_games == 10


def test_detects_win_condition(db):
    # objective_secured in 6/10 games, all wins → win_rate_with = 1.0, overall = 0.6
    for i in range(10):
        result = "win" if i < 6 else "loss"
        types = ["objective_secured"] if i < 6 else []
        _make_match(db, f"NA1_{i}", result, BASE_DATE + timedelta(days=i), types)
    patterns = detect_patterns(db)
    cond = next((p for p in patterns if p.moment_type == "objective_secured"), None)
    assert cond is not None
    assert cond.label == "win_condition"
    assert cond.games_seen == 6
    assert cond.total_games == 10


def test_drops_below_win_rate_threshold(db):
    # cs_differential in 10/10 games, 5 wins → win_rate_with = 0.5, overall = 0.5, delta = 0
    for i in range(10):
        result = "win" if i < 5 else "loss"
        _make_match(db, f"NA1_{i}", result, BASE_DATE + timedelta(days=i), ["cs_differential"])
    patterns = detect_patterns(db)
    assert all(p.moment_type != "cs_differential" for p in patterns)


def test_drops_below_min_games(db):
    # lane_death in only 2 games — below threshold of 3
    for i in range(10):
        types = ["lane_death"] if i < 2 else []
        _make_match(db, f"NA1_{i}", "loss", BASE_DATE + timedelta(days=i), types)
    patterns = detect_patterns(db)
    assert all(p.moment_type != "lane_death" for p in patterns)


def test_sorted_issues_first_then_conditions(db):
    # recurring issue: death in 8/10 games, all losses (overall win rate = 0.5)
    # win condition: solo_kill in 5/10 games, all wins
    for i in range(10):
        result = "win" if i < 5 else "loss"
        types = []
        if i >= 2:   # death in games 2-9 = 8 games, all losses
            types.append("death")
        if i < 5:    # solo_kill in games 0-4 = 5 games, all wins
            types.append("solo_kill")
        _make_match(db, f"NA1_{i}", result, BASE_DATE + timedelta(days=i), types)
    patterns = detect_patterns(db)
    labels = [p.label for p in patterns]
    seen_win_condition = False
    for label in labels:
        if label == "win_condition":
            seen_win_condition = True
        if seen_win_condition:
            assert label == "win_condition", "recurring_issue appeared after win_condition"


def test_capped_at_five(db):
    # 10 distinct moment types each in 8/10 loss games → all recurring issues → only 5 returned
    moment_types = [
        "lane_death", "cs_differential", "gold_differential",
        "turret_plates_lost", "split_push_death", "enemy_roam_kill",
        "low_vision", "objective_missed", "tower_lost", "death",
    ]
    for i in range(10):
        result = "win" if i < 2 else "loss"
        types = moment_types if i >= 2 else []
        _make_match(db, f"NA1_{i}", result, BASE_DATE + timedelta(days=i), types)
    patterns = detect_patterns(db)
    assert len(patterns) == 5
