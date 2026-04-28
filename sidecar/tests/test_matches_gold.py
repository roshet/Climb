import pytest
from datetime import datetime
from database import save_match, save_pivotal_moments, get_pivotal_moments


def make_match(db, match_id, day=1):
    save_match(db, {
        "match_id": match_id,
        "played_at": datetime(2026, 1, day, 12, 0),
        "champion": "Graves",
        "role": "JUNGLE",
        "result": "loss",
        "duration_secs": 1800,
        "kda": "2/3/4",
        "cs": 100,
        "gold_earned": 9000,
        "vision_score": 15,
        "raw_timeline": {},
    })


def compute_gold_lost(moments) -> dict[str, int]:
    result: dict[str, int] = {}
    for m in moments:
        if m.gold_impact and m.gold_impact < 0:
            result[m.match_id] = result.get(m.match_id, 0) + abs(m.gold_impact)
    return result


def test_matches_includes_gold_lost(db):
    make_match(db, "m1", day=1)
    save_pivotal_moments(db, "m1", [
        {"timestamp_secs": 300, "moment_type": "lane_death",
         "description": "", "counterfactual": "", "gold_impact": -680},
        {"timestamp_secs": 800, "moment_type": "objective_missed",
         "description": "", "counterfactual": "", "gold_impact": -1460},
        {"timestamp_secs": 1200, "moment_type": "solo_kill",
         "description": "", "counterfactual": "", "gold_impact": 300},
    ])
    moments = get_pivotal_moments(db, ["m1"])
    gold_by_match = compute_gold_lost(moments)
    assert gold_by_match.get("m1", 0) == 2140  # 680 + 1460; positive solo_kill excluded


def test_matches_gold_lost_zero_when_no_moments(db):
    make_match(db, "m2", day=2)
    moments = get_pivotal_moments(db, ["m2"])
    gold_by_match = compute_gold_lost(moments)
    assert gold_by_match.get("m2", 0) == 0
