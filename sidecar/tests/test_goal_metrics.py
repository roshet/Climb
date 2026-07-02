import pytest
from types import SimpleNamespace
from goal_metrics import METRICS, metric_catalog, evaluate_metric, goal_met


def _match(kda="5/3/7", cs=80, vision_score=25, gold_earned=12000,
           cs_at_10=None, gold_at_10=None, gold_at_14=None):
    return SimpleNamespace(
        kda=kda, cs=cs, vision_score=vision_score, gold_earned=gold_earned,
        cs_at_10=cs_at_10, gold_at_10=gold_at_10, gold_at_14=gold_at_14,
    )


def test_catalog_lists_all_metrics_with_labels_and_direction():
    cat = metric_catalog()
    keys = {m["key"] for m in cat}
    assert keys == {
        "deaths", "cs", "vision_score", "gold_earned", "kda",
        "cs_at_10", "gold_at_10", "gold_at_14",
    }
    deaths = next(m for m in cat if m["key"] == "deaths")
    assert deaths["label"] == "Deaths" and deaths["comparison"] == "lte"
    cs = next(m for m in cat if m["key"] == "cs")
    assert cs["comparison"] == "gte"


def test_catalog_includes_new_timeline_metrics():
    cat = metric_catalog()
    cs10 = next(m for m in cat if m["key"] == "cs_at_10")
    assert cs10["label"] == "CS@10" and cs10["comparison"] == "gte" and cs10["is_float"] is False
    gold10 = next(m for m in cat if m["key"] == "gold_at_10")
    assert gold10["label"] == "Gold@10" and gold10["comparison"] == "gte"
    gold14 = next(m for m in cat if m["key"] == "gold_at_14")
    assert gold14["label"] == "Gold@14" and gold14["comparison"] == "gte"


def test_new_metrics_are_not_benchmarkable_existing_metrics_are():
    assert METRICS["deaths"].benchmarkable is True
    assert METRICS["cs"].benchmarkable is True
    assert METRICS["vision_score"].benchmarkable is True
    assert METRICS["gold_earned"].benchmarkable is True
    assert METRICS["kda"].benchmarkable is True
    assert METRICS["cs_at_10"].benchmarkable is False
    assert METRICS["gold_at_10"].benchmarkable is False
    assert METRICS["gold_at_14"].benchmarkable is False


def test_evaluate_metric_reads_timeline_columns_when_present():
    m = _match(cs_at_10=75, gold_at_10=3200, gold_at_14=5100)
    assert evaluate_metric("cs_at_10", m) == 75
    assert evaluate_metric("gold_at_10", m) == 3200
    assert evaluate_metric("gold_at_14", m) == 5100


def test_evaluate_metric_returns_none_when_timeline_column_absent():
    m = _match()  # cs_at_10/gold_at_10/gold_at_14 default to None
    assert evaluate_metric("cs_at_10", m) is None
    assert evaluate_metric("gold_at_10", m) is None
    assert evaluate_metric("gold_at_14", m) is None


def test_evaluate_metric_returns_none_when_attribute_missing_entirely():
    m = SimpleNamespace(kda="5/3/7", cs=80, vision_score=25, gold_earned=12000)
    assert evaluate_metric("cs_at_10", m) is None


def test_goal_met_returns_none_when_timeline_column_absent():
    m = _match()
    assert goal_met("cs_at_10", 70, m) is None
    assert goal_met("gold_at_10", 3000, m) is None
    assert goal_met("gold_at_14", 5000, m) is None


def test_goal_met_respects_direction_for_new_metrics_when_present():
    m = _match(cs_at_10=75, gold_at_10=3200, gold_at_14=5100)
    assert goal_met("cs_at_10", 70, m) is True
    assert goal_met("cs_at_10", 80, m) is False
    assert goal_met("gold_at_10", 3000, m) is True
    assert goal_met("gold_at_14", 5200, m) is False


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
