import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import _compute_streak_clean, _compute_focus_history, _compute_focus_trend


def test_streak_zero_when_first_game_has_issue():
    recent_ids = ["m1", "m2", "m3"]
    moments_by_match = {"m1": {"lane_death"}, "m2": set(), "m3": set()}
    assert _compute_streak_clean(recent_ids, moments_by_match, "lane_death") == 0


def test_streak_counts_consecutive_clean_games():
    recent_ids = ["m1", "m2", "m3", "m4"]
    moments_by_match = {"m1": set(), "m2": set(), "m3": {"lane_death"}, "m4": set()}
    assert _compute_streak_clean(recent_ids, moments_by_match, "lane_death") == 2


def test_streak_all_clean():
    recent_ids = ["m1", "m2", "m3"]
    moments_by_match = {"m1": set(), "m2": set(), "m3": set()}
    assert _compute_streak_clean(recent_ids, moments_by_match, "lane_death") == 3


def test_streak_missing_match_id_treated_as_clean():
    recent_ids = ["m1", "m2"]
    moments_by_match = {}
    assert _compute_streak_clean(recent_ids, moments_by_match, "lane_death") == 2


def test_streak_ignores_other_moment_types():
    recent_ids = ["m1", "m2"]
    moments_by_match = {"m1": {"cs_differential"}, "m2": {"lane_death"}}
    assert _compute_streak_clean(recent_ids, moments_by_match, "lane_death") == 1


def test_streak_empty_history():
    assert _compute_streak_clean([], {}, "lane_death") == 0


def test_focus_history_oldest_to_newest():
    # recent_ids is newest-first: m3=newest, m1=oldest
    recent_ids = ["m3", "m2", "m1"]
    moments_by_match = {"m1": {"lane_death"}, "m2": set(), "m3": {"lane_death"}}
    history = _compute_focus_history(recent_ids, moments_by_match, "lane_death")
    # reversed to oldest-first: [m1=False, m2=True, m3=False]
    assert history == [False, True, False]


def test_focus_history_caps_at_10():
    recent_ids = [f"m{i}" for i in range(15)]  # 15 games newest-first
    history = _compute_focus_history(recent_ids, {}, "lane_death")
    assert len(history) == 10


def test_focus_history_fewer_than_10_games():
    recent_ids = ["m2", "m1"]  # m2=newest, m1=oldest
    moments_by_match = {"m1": {"lane_death"}, "m2": set()}
    history = _compute_focus_history(recent_ids, moments_by_match, "lane_death")
    # oldest-first: [m1=False, m2=True]
    assert history == [False, True]


def test_focus_history_empty():
    assert _compute_focus_history([], {}, "lane_death") == []


def test_focus_history_missing_match_treated_as_clean():
    recent_ids = ["m1"]
    history = _compute_focus_history(recent_ids, {}, "lane_death")
    assert history == [True]


def test_trend_improving():
    # first 5: 2 clean, last 5: 4 clean → improving
    history = [False, False, True, False, True, True, True, True, True, False]
    assert _compute_focus_trend(history) == "improving"


def test_trend_regressing():
    # first 5: 4 clean, last 5: 1 clean → regressing
    history = [True, True, True, True, False, False, False, False, True, False]
    assert _compute_focus_trend(history) == "regressing"


def test_trend_none_when_equal_halves():
    # first 3: 2 clean, last 3: 2 clean → None
    history = [True, False, True, True, False, True]
    assert _compute_focus_trend(history) is None


def test_trend_none_when_fewer_than_6_games():
    history = [True, False, True, True, False]  # only 5
    assert _compute_focus_trend(history) is None


def test_trend_none_on_empty():
    assert _compute_focus_trend([]) is None
