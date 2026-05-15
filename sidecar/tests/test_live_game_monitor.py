import time
import json
import pytest
from datetime import datetime
from unittest.mock import patch
from database import save_match, save_pivotal_moments, AppState
from live_game_monitor import LiveGameMonitor


@pytest.fixture
def monitor(db):
    return LiveGameMonitor(db)


def test_no_alerts_when_not_in_game(monitor):
    state = monitor.get_state()
    assert state["in_game"] is False
    assert state["alerts"] == []


def test_dragon_kill_fires_alert(monitor):
    monitor._in_game = True
    monitor._process_events(
        [{"EventID": 1, "EventName": "DragonKill", "EventTime": 300.0}],
        "TestPlayer#NA1",
    )
    state = monitor.get_state()
    assert any("Dragon" in a["message"] for a in state["alerts"])
    assert state["alerts"][0]["alert_type"] == "objective"


def test_baron_kill_fires_alert(monitor):
    monitor._in_game = True
    monitor._process_events(
        [{"EventID": 1, "EventName": "BaronKill", "EventTime": 1200.0}],
        "TestPlayer#NA1",
    )
    state = monitor.get_state()
    assert any("Baron" in a["message"] for a in state["alerts"])
    assert state["alerts"][0]["alert_type"] == "objective"


def test_dragon_spawn_soon_alert(monitor):
    monitor._in_game = True
    monitor._next_dragon_spawn = 250.0
    monitor._check_spawn_timers(200.0)  # 50s before spawn — within 60s window
    state = monitor.get_state()
    assert any("Dragon spawns soon" in a["message"] for a in state["alerts"])


def test_baron_spawn_soon_alert(monitor):
    monitor._in_game = True
    monitor._next_baron_spawn = 1240.0
    monitor._check_spawn_timers(1190.0)  # 50s before spawn
    state = monitor.get_state()
    assert any("Baron spawns soon" in a["message"] for a in state["alerts"])


def test_player_death_fires_alert(monitor):
    monitor._in_game = True
    monitor._process_events(
        [{"EventID": 5, "EventName": "ChampionKill", "EventTime": 400.0,
          "VictimName": "TestPlayer#NA1", "KillerName": "Enemy#NA1"}],
        "TestPlayer#NA1",
    )
    state = monitor.get_state()
    assert any("dead" in a["message"] for a in state["alerts"])
    assert state["alerts"][0]["alert_type"] == "death"


def test_alert_expires_after_8s(monitor):
    monitor._in_game = True
    monitor._process_events(
        [{"EventID": 1, "EventName": "DragonKill", "EventTime": 300.0}],
        "TestPlayer#NA1",
    )
    for a in monitor._alerts:
        a.expires_at = time.time() - 1  # force expiry
    state = monitor.get_state()
    assert state["alerts"] == []


def test_max_3_alerts(monitor):
    monitor._in_game = True
    monitor._add_alert("Alert 1", "objective", "key1")
    monitor._add_alert("Alert 2", "objective", "key2")
    monitor._add_alert("Alert 3", "objective", "key3")
    monitor._add_alert("Alert 4", "objective", "key4")
    state = monitor.get_state()
    assert len(state["alerts"]) == 3
    assert all(a["message"] != "Alert 1" for a in state["alerts"])  # oldest evicted


def test_pattern_alerts_at_game_start(db):
    monitor = LiveGameMonitor(db)
    # 3 losses with objective_missed, 3 wins without — creates recurring issue pattern
    for i in range(3):
        mid = f"NA1_loss_{i}"
        save_match(db, {
            "match_id": mid, "played_at": datetime(2026, 1, i + 1, 12, 0),
            "champion": "Caitlyn", "role": "BOTTOM", "result": "loss",
            "duration_secs": 1800, "kda": "2/5/3", "cs": 100,
            "gold_earned": 9000, "vision_score": 15, "raw_timeline": {},
        })
        save_pivotal_moments(db, mid, [{
            "timestamp_secs": 300, "moment_type": "objective_missed",
            "description": "Missed dragon", "counterfactual": "", "gold_impact": 0,
        }])
    for i in range(3):
        mid = f"NA1_win_{i}"
        save_match(db, {
            "match_id": mid, "played_at": datetime(2026, 1, i + 4, 12, 0),
            "champion": "Caitlyn", "role": "BOTTOM", "result": "win",
            "duration_secs": 1800, "kda": "5/2/8", "cs": 150,
            "gold_earned": 12000, "vision_score": 20, "raw_timeline": {},
        })
    monitor._maybe_show_patterns(30.0)
    state = monitor.get_state()
    assert any(a["alert_type"] == "pattern" for a in state["alerts"])


def test_pattern_alert_deduplication(monitor):
    with patch("live_game_monitor.detect_patterns") as mock_detect:
        mock_detect.return_value = []
        monitor._maybe_show_patterns(30.0)  # first call — sets _patterns_shown flag
        monitor._maybe_show_patterns(60.0)  # second call — should be no-op
    assert mock_detect.call_count == 1


def test_death_message_no_focus(monitor):
    monitor._focus = None
    assert monitor._death_message() == "You're dead — use this time to plan your next move"


def test_death_message_with_streak_plural(monitor):
    monitor._focus = {"display": "Early Deaths", "streak_clean": 3}
    assert monitor._death_message() == "You're dead — 3 clean games on Early Deaths. Don't let it slip."


def test_death_message_with_streak_singular(monitor):
    monitor._focus = {"display": "Early Deaths", "streak_clean": 1}
    assert monitor._death_message() == "You're dead — 1 clean game on Early Deaths. Don't let it slip."


def test_death_message_no_streak(monitor):
    monitor._focus = {"display": "Early Deaths", "streak_clean": 0}
    assert monitor._death_message() == "You're dead — think about Early Deaths while you wait."


def test_load_focus_reads_from_db(db):
    db.merge(AppState(key="focus_card", value=json.dumps({
        "display": "Early Deaths", "streak_clean": 2, "moment_type": "early_death"
    })))
    db.commit()
    monitor = LiveGameMonitor(db)
    monitor._load_focus()
    assert monitor._focus is not None
    assert monitor._focus["display"] == "Early Deaths"


def test_load_focus_missing_returns_none(monitor):
    monitor._load_focus()
    assert monitor._focus is None


def test_death_alert_uses_focus(db):
    db.merge(AppState(key="focus_card", value=json.dumps({
        "display": "Early Deaths", "streak_clean": 0, "moment_type": "early_death"
    })))
    db.commit()
    monitor = LiveGameMonitor(db)
    monitor._in_game = True
    monitor._load_focus()
    monitor._process_events(
        [{"EventID": 10, "EventName": "ChampionKill", "EventTime": 400.0,
          "VictimName": "TestPlayer#NA1", "KillerName": "Enemy#NA1"}],
        "TestPlayer#NA1",
    )
    state = monitor.get_state()
    death_alerts = [a for a in state["alerts"] if a["alert_type"] == "death"]
    assert len(death_alerts) == 1
    assert "Early Deaths" in death_alerts[0]["message"]
