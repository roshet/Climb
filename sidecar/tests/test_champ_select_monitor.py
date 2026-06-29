import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from database import save_match, save_pivotal_moments
from champ_select_monitor import ChampSelectMonitor
from lcu_client import LcuClient


def make_session(cell_id: int, champion_id: int, completed: bool) -> dict:
    return {
        "localPlayerCellId": cell_id,
        "myTeam": [{"cellId": cell_id, "championId": champion_id}],
        "actions": [[{
            "type": "pick",
            "actorCellId": cell_id,
            "completed": completed,
        }]],
    }


@pytest.fixture
def lcu():
    mock = MagicMock(spec=LcuClient)
    mock.get_champ_select_session = AsyncMock(return_value=None)
    mock.get_champion_name = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def monitor(db, lcu):
    return ChampSelectMonitor(db, lcu)


def test_no_state_when_not_in_champ_select(monitor):
    state = monitor.get_state()
    assert state["in_champ_select"] is False
    assert state["locked_champion"] is None
    assert state["champ_data"] is None


def test_lock_in_detected(monitor):
    session = make_session(cell_id=0, champion_id=104, completed=True)
    monitor._process_session(session, "Graves")
    assert monitor._in_champ_select is True
    assert monitor._locked_champion == "Graves"
    assert monitor._champ_data is not None
    assert monitor._champ_data["no_history"] is True


def test_no_lock_without_completed_action(monitor):
    session = make_session(cell_id=0, champion_id=104, completed=False)
    monitor._process_session(session, "Graves")
    assert monitor._in_champ_select is True
    assert monitor._locked_champion is None


def test_champ_data_with_history(db, lcu):
    monitor = ChampSelectMonitor(db, lcu)
    for i in range(4):
        save_match(db, {
            "match_id": f"win_{i}", "played_at": datetime(2026, 1, i + 1, 12, 0),
            "champion": "Graves", "role": "JUNGLE", "result": "win",
            "duration_secs": 1800, "kda": "5/2/8", "cs": 150,
            "gold_earned": 12000, "vision_score": 20, "raw_timeline": {},
        })
        save_pivotal_moments(db, f"win_{i}", [
            {"timestamp_secs": 300, "moment_type": "solo_kill",
             "description": "", "counterfactual": "", "gold_impact": 0},
        ])
    for i in range(3):
        save_match(db, {
            "match_id": f"loss_{i}", "played_at": datetime(2026, 1, i + 5, 12, 0),
            "champion": "Graves", "role": "JUNGLE", "result": "loss",
            "duration_secs": 1800, "kda": "2/5/3", "cs": 100,
            "gold_earned": 9000, "vision_score": 15, "raw_timeline": {},
        })
        save_pivotal_moments(db, f"loss_{i}", [
            {"timestamp_secs": 300, "moment_type": "lane_death",
             "description": "", "counterfactual": "", "gold_impact": 0},
        ])
    data = monitor._build_champ_data("Graves")
    assert data["games"] == 7
    assert data["wins"] == 4
    assert data["win_rate"] == 0.57
    assert data["no_history"] is False
    assert len(data["patterns"]) > 0


def test_champ_data_no_history(monitor):
    data = monitor._build_champ_data("NewChamp")
    assert data["games"] == 0
    assert data["no_history"] is True
    assert data["patterns"] == []


def test_pattern_top_2_issues(db, lcu):
    monitor = ChampSelectMonitor(db, lcu)
    for i in range(5):
        save_match(db, {
            "match_id": f"m_{i}", "played_at": datetime(2026, 1, i + 1, 12, 0),
            "champion": "Jinx", "role": "BOTTOM", "result": "loss",
            "duration_secs": 1800, "kda": "2/5/3", "cs": 100,
            "gold_earned": 9000, "vision_score": 15, "raw_timeline": {},
        })
        save_pivotal_moments(db, f"m_{i}", [
            {"timestamp_secs": 300, "moment_type": "lane_death",
             "description": "", "counterfactual": "", "gold_impact": 0},
            {"timestamp_secs": 600, "moment_type": "objective_missed",
             "description": "", "counterfactual": "", "gold_impact": 0},
            {"timestamp_secs": 900, "moment_type": "tower_lost",
             "description": "", "counterfactual": "", "gold_impact": 0},
        ])
    data = monitor._build_champ_data("Jinx")
    issues = [p for p in data["patterns"] if p["label"] == "recurring_issue"]
    assert len(issues) == 2


def test_win_condition_extracted(db, lcu):
    monitor = ChampSelectMonitor(db, lcu)
    for i in range(3):
        save_match(db, {
            "match_id": f"win_{i}", "played_at": datetime(2026, 1, i + 1, 12, 0),
            "champion": "Jinx", "role": "BOTTOM", "result": "win",
            "duration_secs": 1800, "kda": "5/2/8", "cs": 150,
            "gold_earned": 12000, "vision_score": 20, "raw_timeline": {},
        })
        save_pivotal_moments(db, f"win_{i}", [
            {"timestamp_secs": 300, "moment_type": "solo_kill",
             "description": "", "counterfactual": "", "gold_impact": 0},
        ])
    data = monitor._build_champ_data("Jinx")
    win_conds = [p for p in data["patterns"] if p["label"] == "win_condition"]
    assert len(win_conds) == 1
    assert win_conds[0]["moment_type"] == "solo_kill"


async def test_session_exit_resets_state(monitor, lcu):
    monitor._in_champ_select = True
    monitor._locked_champion = "Graves"
    monitor._champ_data = {"games": 7}
    lcu.get_champ_select_session.return_value = None
    await monitor._tick()
    assert monitor._in_champ_select is False
    assert monitor._locked_champion is None
    assert monitor._champ_data is None


def test_assigned_position_captured_from_session(monitor):
    """assignedPosition from LCU session is exposed via get_state()."""
    session = {
        "localPlayerCellId": 0,
        "myTeam": [{"cellId": 0, "championId": 104, "assignedPosition": "middle"}],
        "actions": [[{
            "type": "pick",
            "actorCellId": 0,
            "completed": True,
        }]],
    }
    monitor._process_session(session, "Graves")
    assert monitor.get_state()["assigned_position"] == "middle"


def test_assigned_position_none_when_blind(monitor):
    """assignedPosition='' (blind pick) is normalised to None."""
    session = {
        "localPlayerCellId": 0,
        "myTeam": [{"cellId": 0, "championId": 104, "assignedPosition": ""}],
        "actions": [[{
            "type": "pick",
            "actorCellId": 0,
            "completed": True,
        }]],
    }
    monitor._process_session(session, "Graves")
    assert monitor.get_state()["assigned_position"] is None
