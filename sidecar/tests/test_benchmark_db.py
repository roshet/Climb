from database import (
    record_benchmark_samples, get_benchmarks,
    is_match_harvested, mark_match_harvested,
    get_app_state, set_app_state,
)


def test_record_then_get_accumulates(db):
    record_benchmark_samples(db, "DIAMOND", "MIDDLE", "14.12", {"cs": 200.0, "deaths": 3.0})
    record_benchmark_samples(db, "DIAMOND", "MIDDLE", "14.12", {"cs": 180.0, "deaths": 5.0})
    rows = get_benchmarks(db, "DIAMOND", "MIDDLE")
    assert rows["cs"] == (380.0, 2)
    assert rows["deaths"] == (8.0, 2)


def test_get_benchmarks_sums_across_patches(db):
    record_benchmark_samples(db, "DIAMOND", "TOP", "14.12", {"cs": 100.0})
    record_benchmark_samples(db, "DIAMOND", "TOP", "14.13", {"cs": 140.0})
    rows = get_benchmarks(db, "DIAMOND", "TOP")
    assert rows["cs"] == (240.0, 2)


def test_get_benchmarks_isolates_tier_and_role(db):
    record_benchmark_samples(db, "DIAMOND", "MIDDLE", "14.12", {"cs": 200.0})
    assert get_benchmarks(db, "MASTER", "MIDDLE") == {}
    assert get_benchmarks(db, "DIAMOND", "TOP") == {}


def test_harvested_match_dedup(db):
    assert is_match_harvested(db, "NA1_1") is False
    mark_match_harvested(db, "NA1_1")
    assert is_match_harvested(db, "NA1_1") is True


def test_app_state_roundtrip(db):
    assert get_app_state(db, "benchmark_target_tier") is None
    set_app_state(db, "benchmark_target_tier", "DIAMOND")
    assert get_app_state(db, "benchmark_target_tier") == "DIAMOND"
    set_app_state(db, "benchmark_target_tier", "MASTER")  # overwrites
    assert get_app_state(db, "benchmark_target_tier") == "MASTER"
