import pytest
from types import SimpleNamespace
from goal_metrics import METRICS, metric_catalog, evaluate_metric, goal_met


def _match(kda="5/3/7", cs=80, vision_score=25, gold_earned=12000):
    return SimpleNamespace(kda=kda, cs=cs, vision_score=vision_score, gold_earned=gold_earned)


def test_catalog_lists_all_metrics_with_labels_and_direction():
    cat = metric_catalog()
    keys = {m["key"] for m in cat}
    assert keys == {"deaths", "cs", "vision_score", "gold_earned", "kda"}
    deaths = next(m for m in cat if m["key"] == "deaths")
    assert deaths["label"] == "Deaths" and deaths["comparison"] == "lte"
    cs = next(m for m in cat if m["key"] == "cs")
    assert cs["comparison"] == "gte"


def test_evaluate_metric_reads_match_fields():
    m = _match(kda="5/3/7", cs=80, vision_score=25, gold_earned=12000)
    assert evaluate_metric("deaths", m) == 3
    assert evaluate_metric("cs", m) == 80
    assert evaluate_metric("vision_score", m) == 25
    assert evaluate_metric("gold_earned", m) == 12000
    assert evaluate_metric("kda", m) == pytest.approx((5 + 7) / 3)


def test_kda_handles_zero_deaths():
    assert evaluate_metric("kda", _match(kda="5/0/7")) == pytest.approx(12.0)


def test_goal_met_respects_direction():
    m = _match(kda="5/3/7", cs=80, vision_score=25)
    assert goal_met("deaths", 4, m) is True      # 3 <= 4
    assert goal_met("deaths", 3, m) is True       # boundary inclusive
    assert goal_met("deaths", 2, m) is False
    assert goal_met("cs", 70, m) is True          # 80 >= 70
    assert goal_met("cs", 90, m) is False


def test_unknown_metric_raises():
    with pytest.raises(KeyError):
        evaluate_metric("nonsense", _match())
