"""API-layer tests for GET /benchmarks (same import-main pattern as test_goals_api)."""
import os
import tempfile
from datetime import datetime

import pytest

os.environ.setdefault("RIOT_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test_benchmarks_api.db")

import main as main_module  # noqa: E402
from database import save_match, record_benchmark_samples, set_app_state  # noqa: E402


@pytest.fixture
def api_db(db, monkeypatch):
    monkeypatch.setattr(main_module, "db", db)
    return db


def _save(db, mid, day, role="MIDDLE", kda="4/2/6", cs=180):
    save_match(db, {
        "match_id": mid, "played_at": datetime(2026, 1, day, 12, 0),
        "champion": "Ahri", "role": role, "result": "win", "duration_secs": 1800,
        "kda": kda, "cs": cs, "gold_earned": 12000, "vision_score": 25,
        "raw_timeline": {},
    })


def test_status_none_when_no_harvest(api_db):
    _save(api_db, "m1", 1)
    out = main_module.get_benchmarks_view()
    assert out["status"] == "none"
    assert out["metrics"] == []


def test_pairs_your_avg_with_tier_avg(api_db):
    _save(api_db, "m1", 1, role="MIDDLE", cs=180)
    _save(api_db, "m2", 2, role="MIDDLE", cs=220)
    set_app_state(api_db, "benchmark_user_tier", "PLATINUM")
    set_app_state(api_db, "benchmark_target_tier", "DIAMOND")
    set_app_state(api_db, "benchmark_updated_at", datetime.now().isoformat())
    # 40 MIDDLE samples for cs so it clears the floor
    for _ in range(40):
        record_benchmark_samples(api_db, "DIAMOND", "MIDDLE", "14.12", {"cs": 250.0})
    out = main_module.get_benchmarks_view()
    assert out["role"] == "MIDDLE"
    assert out["target_tier"] == "DIAMOND"
    assert out["status"] == "ready"
    cs = next(m for m in out["metrics"] if m["metric_key"] == "cs")
    assert cs["your_avg"] == 200.0          # (180+220)/2
    assert cs["tier_avg"] == 250.0
    assert cs["sample_count"] == 40


def test_tier_avg_null_below_sample_floor(api_db):
    _save(api_db, "m1", 1, role="MIDDLE")
    set_app_state(api_db, "benchmark_target_tier", "DIAMOND")
    set_app_state(api_db, "benchmark_updated_at", datetime.now().isoformat())
    record_benchmark_samples(api_db, "DIAMOND", "MIDDLE", "14.12", {"cs": 250.0})  # 1 < floor
    out = main_module.get_benchmarks_view()
    cs = next(m for m in out["metrics"] if m["metric_key"] == "cs")
    assert cs["tier_avg"] is None
    assert out["status"] == "harvesting"  # no metric cleared the floor yet
