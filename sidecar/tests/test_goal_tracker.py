from datetime import datetime
from database import create_goal, save_match
from goal_tracker import compute_goal_status


def _save(db, mid, day, kda="2/2/2", cs=80, vision_score=25,
          cs_at_10=None, gold_at_10=None, gold_at_14=None):
    save_match(db, {
        "match_id": mid, "played_at": datetime(2026, 1, day, 12, 0),
        "champion": "Ahri", "role": "MIDDLE", "result": "win", "duration_secs": 1800,
        "kda": kda, "cs": cs, "gold_earned": 12000, "vision_score": vision_score,
        "raw_timeline": {},
        "cs_at_10": cs_at_10, "gold_at_10": gold_at_10, "gold_at_14": gold_at_14,
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


def test_compute_goal_status_skips_matches_where_timeline_metric_not_applicable(db):
    # day1 has no timeline data (cs_at_10 None) -> must be skipped entirely, not a miss
    _save(db, "a", 1, cs_at_10=None)
    _save(db, "b", 2, cs_at_10=50)   # applicable, missed target
    _save(db, "c", 3, cs_at_10=90)   # applicable, met target (newest)
    goal = create_goal(db, metric="cs_at_10", target=80.0)
    status = compute_goal_status(db, goal)
    assert status["games_evaluated"] == 2
    assert status["last_game_met"] is True
    assert status["streak"] == 1
    assert status["history"] == [False, True]  # oldest -> newest, among applicable only


def test_compute_goal_status_streak_spans_across_none_gaps(db):
    _save(db, "a", 1, cs_at_10=90)   # applicable, met (oldest)
    _save(db, "b", 2, cs_at_10=None)  # not applicable, must not break the streak
    _save(db, "c", 3, cs_at_10=95)   # applicable, met (newest)
    goal = create_goal(db, metric="cs_at_10", target=80.0)
    status = compute_goal_status(db, goal)
    assert status["streak"] == 2
    assert status["games_evaluated"] == 2
    assert status["last_game_met"] is True


def test_compute_goal_status_all_none_yields_empty_status(db):
    _save(db, "a", 1, cs_at_10=None)
    _save(db, "b", 2, cs_at_10=None)
    goal = create_goal(db, metric="cs_at_10", target=80.0)
    status = compute_goal_status(db, goal)
    assert status == {"streak": 0, "history": [], "last_game_met": None, "games_evaluated": 0}
