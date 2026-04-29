import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock
from database import save_match, save_pivotal_moments
from champ_select_monitor import ChampSelectMonitor
from lcu_client import LcuClient


def make_match(db, match_id, champion, result, day):
    save_match(db, {
        "match_id": match_id,
        "played_at": datetime(2026, 1, day, 12, 0),
        "champion": champion,
        "role": "JUNGLE",
        "result": result,
        "duration_secs": 1800,
        "kda": "3/5/2",
        "cs": 100,
        "gold_earned": 9000,
        "vision_score": 15,
        "raw_timeline": {},
    })


@pytest.fixture
def lcu():
    mock = MagicMock(spec=LcuClient)
    mock.get_champ_select_session = AsyncMock(return_value=None)
    mock.get_champion_name = AsyncMock(return_value=None)
    return mock


def test_focus_champion_specific(db, lcu):
    monitor = ChampSelectMonitor(db, lcu)
    # 5 games on Graves, lane_death in 4 games with -680g each
    for i in range(5):
        make_match(db, f"m_{i}", "Graves", "loss", i + 1)
        moments = []
        if i < 4:
            moments.append({
                "timestamp_secs": 300, "moment_type": "lane_death",
                "description": "", "counterfactual": "", "gold_impact": -680,
            })
        save_pivotal_moments(db, f"m_{i}", moments)

    data = monitor._build_champ_data("Graves")
    focus = data["focus"]
    assert focus is not None
    assert focus["moment_type"] == "lane_death"
    assert focus["games_seen"] == 4
    assert focus["total_games"] == 5
    assert focus["avg_gold_lost"] == 680
    assert focus["champion_specific"] is True


def test_focus_cross_champion_fallback(db, lcu):
    monitor = ChampSelectMonitor(db, lcu)
    # 2 Graves games — below the 3-game threshold
    for i in range(2):
        make_match(db, f"graves_{i}", "Graves", "loss", i + 1)
        save_pivotal_moments(db, f"graves_{i}", [{
            "timestamp_secs": 300, "moment_type": "lane_death",
            "description": "", "counterfactual": "", "gold_impact": -500,
        }])
    # 5 Jinx games with objective_missed (more games than lane_death)
    for i in range(5):
        make_match(db, f"jinx_{i}", "Jinx", "loss", i + 3)
        save_pivotal_moments(db, f"jinx_{i}", [{
            "timestamp_secs": 600, "moment_type": "objective_missed",
            "description": "", "counterfactual": "", "gold_impact": -900,
        }])

    data = monitor._build_champ_data("Graves")
    focus = data["focus"]
    assert focus is not None
    assert focus["champion_specific"] is False
    assert focus["total_games"] == 7  # 2 Graves + 5 Jinx
    assert focus["moment_type"] == "objective_missed"  # 5 games > 2 games


def test_focus_null_when_no_negatives(db, lcu):
    monitor = ChampSelectMonitor(db, lcu)
    # 5 games with only positive moments
    for i in range(5):
        make_match(db, f"m_{i}", "Graves", "win", i + 1)
        save_pivotal_moments(db, f"m_{i}", [{
            "timestamp_secs": 300, "moment_type": "solo_kill",
            "description": "", "counterfactual": "", "gold_impact": 300,
        }])

    data = monitor._build_champ_data("Graves")
    assert data["focus"] is None
