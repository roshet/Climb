from datetime import datetime, timedelta
import pytest
from database import save_match, save_pivotal_moments
from main import _get_matchup_stats

BASE_DATE = datetime(2026, 4, 1)


def _make_match(db, match_id, result, opponent=None, moment_types=None):
    idx = int(match_id.split("_")[1])
    save_match(db, {
        "match_id": match_id,
        "played_at": BASE_DATE + timedelta(days=idx),
        "champion": "Jinx",
        "role": "BOTTOM",
        "result": result,
        "duration_secs": 1800,
        "kda": "5/2/8",
        "cs": 150,
        "gold_earned": 12000,
        "vision_score": 20,
        "raw_timeline": {},
        "lane_opponent_champion": opponent,
    })
    if moment_types:
        save_pivotal_moments(db, match_id, [
            {
                "timestamp_secs": 300,
                "moment_type": t,
                "description": "",
                "counterfactual": "",
                "gold_impact": -300,
            }
            for t in moment_types
        ])


def test_matchup_stats_empty(db):
    assert _get_matchup_stats(db, []) == []


def test_matchup_stats_no_opponent_data(db):
    from database import get_matches
    _make_match(db, "m_0", "loss", opponent=None)
    _make_match(db, "m_1", "loss", opponent=None)
    _make_match(db, "m_2", "loss", opponent=None)
    matches = get_matches(db)
    assert _get_matchup_stats(db, matches) == []


def test_matchup_stats_min_games_filter(db):
    from database import get_matches
    # Only 2 games vs Draven — below min_games=3
    _make_match(db, "m_0", "loss", opponent="Draven")
    _make_match(db, "m_1", "loss", opponent="Draven")
    matches = get_matches(db)
    assert _get_matchup_stats(db, matches, min_games=3) == []


def test_matchup_stats_basic(db):
    from database import get_matches
    # 3 losses vs Draven — should appear
    for i in range(3):
        _make_match(db, f"m_{i}", "loss", opponent="Draven")
    matches = get_matches(db)
    result = _get_matchup_stats(db, matches, min_games=3)
    assert len(result) == 1
    assert result[0]["opponent"] == "Draven"
    assert result[0]["wins"] == 0
    assert result[0]["losses"] == 3
    assert result[0]["win_rate"] == 0.0


def test_matchup_stats_sorted_worst_first(db):
    from database import get_matches
    # Draven: 1W 4L (20%), Caitlyn: 2W 3L (40%)
    for i in range(5):
        result = "win" if i == 0 else "loss"
        _make_match(db, f"m_{i}", result, opponent="Draven")
    for i in range(5, 10):
        result = "win" if i < 7 else "loss"
        _make_match(db, f"m_{i}", result, opponent="Caitlyn")
    matches = get_matches(db)
    stats = _get_matchup_stats(db, matches, min_games=3)
    assert stats[0]["opponent"] == "Draven"
    assert stats[1]["opponent"] == "Caitlyn"


def test_matchup_stats_top_n(db):
    from database import get_matches
    for opp in ["Draven", "Caitlyn", "Jhin", "Jinx", "Kalista", "Zeri"]:
        for i in range(3):
            idx = ["Draven", "Caitlyn", "Jhin", "Jinx", "Kalista", "Zeri"].index(opp) * 3 + i
            _make_match(db, f"m_{idx}", "loss", opponent=opp)
    matches = get_matches(db)
    stats = _get_matchup_stats(db, matches, min_games=3, top_n=3)
    assert len(stats) == 3


def test_matchup_stats_dominant_moment(db):
    from database import get_matches
    # 4 losses vs Draven, 3 have lane_death, 1 has cs_differential
    _make_match(db, "m_0", "loss", opponent="Draven", moment_types=["lane_death"])
    _make_match(db, "m_1", "loss", opponent="Draven", moment_types=["lane_death"])
    _make_match(db, "m_2", "loss", opponent="Draven", moment_types=["lane_death"])
    _make_match(db, "m_3", "loss", opponent="Draven", moment_types=["cs_differential"])
    matches = get_matches(db)
    stats = _get_matchup_stats(db, matches, min_games=3)
    assert stats[0]["dominant_moment"] == "lane_death"


def test_matchup_stats_dominant_moment_none_when_no_moments(db):
    from database import get_matches
    for i in range(3):
        _make_match(db, f"m_{i}", "loss", opponent="Draven")
    matches = get_matches(db)
    stats = _get_matchup_stats(db, matches, min_games=3)
    assert stats[0]["dominant_moment"] is None


def test_matchup_stats_dominant_moment_tiebreak_alphabetical(db):
    from database import get_matches
    # 2 losses with lane_death, 2 losses with cs_differential — tie, alphabetical → cs_differential wins
    _make_match(db, "m_0", "loss", opponent="Draven", moment_types=["lane_death"])
    _make_match(db, "m_1", "loss", opponent="Draven", moment_types=["lane_death"])
    _make_match(db, "m_2", "loss", opponent="Draven", moment_types=["cs_differential"])
    _make_match(db, "m_3", "loss", opponent="Draven", moment_types=["cs_differential"])
    matches = get_matches(db)
    stats = _get_matchup_stats(db, matches, min_games=3)
    assert stats[0]["dominant_moment"] == "cs_differential"


def test_matchup_stats_wins_not_counted_for_dominant_moment(db):
    from database import get_matches
    # 3 losses with lane_death, 5 wins with solo_kill — solo_kill should NOT be dominant
    for i in range(3):
        _make_match(db, f"m_{i}", "loss", opponent="Draven", moment_types=["lane_death"])
    for i in range(3, 8):
        _make_match(db, f"m_{i}", "win", opponent="Draven", moment_types=["solo_kill"])
    matches = get_matches(db)
    stats = _get_matchup_stats(db, matches, min_games=3)
    assert stats[0]["dominant_moment"] == "lane_death"
