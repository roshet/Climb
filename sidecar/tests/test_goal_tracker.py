from datetime import datetime
from database import create_goal, save_match
from goal_tracker import compute_goal_status


def _save(db, mid, day, kda="2/2/2", cs=80, vision_score=25):
    save_match(db, {
        "match_id": mid, "played_at": datetime(2026, 1, day, 12, 0),
        "champion": "Ahri", "role": "MIDDLE", "result": "win", "duration_secs": 1800,
        "kda": kda, "cs": cs, "gold_earned": 12000, "vision_score": vision_score,
        "raw_timeline": {},
    })


def test_streak_counts_consecutive_met_from_newest(db):
    # days 1-2 miss (5 deaths), days 3-5 met (2 deaths); newest = day 5
    for d in (1, 2):
        _save(db, f"m{d}", d, kda="3/5/3")
    for d in (3, 4, 5):
        _save(db, f"m{d}", d, kda="3/2/3")
    goal = create_goal(db, metric="deaths", target=4.0)
    status = compute_goal_status(db, goal)
    assert status["streak"] == 3
    assert status["last_game_met"] is True
    assert status["history"][-1] is True and status["history"][0] is False


def test_streak_zero_when_latest_missed(db):
    _save(db, "a", 1, kda="3/2/3")
    _save(db, "b", 2, kda="3/9/3")  # newest missed
    goal = create_goal(db, metric="deaths", target=4.0)
    status = compute_goal_status(db, goal)
    assert status["streak"] == 0 and status["last_game_met"] is False


def test_no_matches_yields_empty_status(db):
    goal = create_goal(db, metric="cs", target=70.0)
    status = compute_goal_status(db, goal)
    assert status == {"streak": 0, "history": [], "last_game_met": None, "games_evaluated": 0}
