from benchmark_metrics import extract_participant_metrics


def _participant():
    return {
        "kills": 4, "deaths": 2, "assists": 6,
        "totalMinionsKilled": 180,
        "goldEarned": 13500,
        "visionScore": 28,
        "teamPosition": "MIDDLE",
    }


def test_extracts_all_five_metrics_as_floats():
    m = extract_participant_metrics(_participant())
    assert set(m.keys()) == {"deaths", "cs", "vision_score", "gold_earned", "kda"}
    assert m["deaths"] == 2.0
    assert m["cs"] == 180.0
    assert m["vision_score"] == 28.0
    assert m["gold_earned"] == 13500.0
    assert m["kda"] == (4 + 6) / 2  # (k+a)/d


def test_zero_deaths_kda_is_kills_plus_assists():
    p = _participant()
    p["deaths"] = 0
    m = extract_participant_metrics(p)
    assert m["deaths"] == 0.0
    assert m["kda"] == 10.0  # k + a when deaths == 0
