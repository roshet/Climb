"""API-layer tests for the /goals routes.

There is no FastAPI TestClient precedent in this suite, and importing ``main``
requires the runtime env keys and builds the API clients. The client
constructors are lazy (no network at import) and the background tasks only start
under the lifespan (i.e. when uvicorn runs), so we can import ``main`` with dummy
env vars and call the route handlers directly, monkeypatching the module-level
``db`` onto the in-memory test session.
"""
import os
import tempfile
from datetime import datetime

import pytest

os.environ.setdefault("RIOT_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test_goals_api.db")

import main as main_module  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from database import save_match  # noqa: E402


@pytest.fixture
def api_db(db, monkeypatch):
    """Point the route handlers' module-level db at the in-memory test session."""
    monkeypatch.setattr(main_module, "db", db)
    return db


def _save(db, mid, day, kda="2/2/2"):
    save_match(db, {
        "match_id": mid, "played_at": datetime(2026, 1, day, 12, 0),
        "champion": "Ahri", "role": "MIDDLE", "result": "win", "duration_secs": 1800,
        "kda": kda, "cs": 80, "gold_earned": 12000, "vision_score": 25,
        "raw_timeline": {},
    })


def test_metrics_endpoint_lists_all_metrics(api_db):
    cat = main_module.goal_metrics()
    assert len(cat) == 5
    assert {m["key"] for m in cat} == {"deaths", "cs", "vision_score", "gold_earned", "kda"}


def test_add_unknown_metric_raises_400(api_db):
    with pytest.raises(HTTPException) as exc:
        main_module.add_goal(main_module.GoalRequest(metric="nonsense", target=4))
    assert exc.value.status_code == 400


def test_add_nonpositive_target_raises_400(api_db):
    with pytest.raises(HTTPException) as exc:
        main_module.add_goal(main_module.GoalRequest(metric="deaths", target=0))
    assert exc.value.status_code == 400


def test_post_then_get_roundtrips_with_streak(api_db):
    _save(api_db, "m1", 1, kda="3/2/3")
    created = main_module.add_goal(main_module.GoalRequest(metric="deaths", target=4))
    assert created["metric"] == "deaths"
    assert "streak" in created
    goals = main_module.list_goals()
    assert len(goals) == 1
    assert goals[0]["id"] == created["id"]
    assert goals[0]["streak"] == 1


def test_delete_removes_goal(api_db):
    created = main_module.add_goal(main_module.GoalRequest(metric="cs", target=70))
    main_module.remove_goal(created["id"])
    assert main_module.list_goals() == []
