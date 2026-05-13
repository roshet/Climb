import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import _compute_streak_clean


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
