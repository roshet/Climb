from dataclasses import dataclass
from typing import Callable, Optional

GTE = "gte"  # higher is better -> met if value >= target
LTE = "lte"  # lower is better  -> met if value <= target


def _deaths(match) -> float:
    parts = (match.kda or "0/0/0").split("/")
    return float(int(parts[1])) if len(parts) == 3 else 0.0


def _kda(match) -> float:
    parts = (match.kda or "0/0/0").split("/")
    if len(parts) != 3:
        return 0.0
    k, d, a = (int(p) for p in parts)
    return (k + a) / d if d > 0 else float(k + a)


def _opt(value) -> Optional[float]:
    """None if the timeline column is unset, else its float value."""
    return None if value is None else float(value)


@dataclass(frozen=True)
class GoalMetric:
    key: str
    label: str
    comparison: str            # GTE or LTE
    is_float: bool
    value: Callable[[object], Optional[float]]
    benchmarkable: bool = True


METRICS: dict[str, GoalMetric] = {
    "deaths": GoalMetric("deaths", "Deaths", LTE, False, _deaths),
    "cs": GoalMetric("cs", "CS", GTE, False, lambda m: float(m.cs)),
    "vision_score": GoalMetric("vision_score", "Vision Score", GTE, False, lambda m: float(m.vision_score)),
    "gold_earned": GoalMetric("gold_earned", "Gold Earned", GTE, False, lambda m: float(m.gold_earned)),
    "kda": GoalMetric("kda", "KDA", GTE, True, _kda),
    "cs_at_10": GoalMetric(
        "cs_at_10", "CS@10", GTE, False,
        lambda m: _opt(getattr(m, "cs_at_10", None)), benchmarkable=False,
    ),
    "gold_at_10": GoalMetric(
        "gold_at_10", "Gold@10", GTE, False,
        lambda m: _opt(getattr(m, "gold_at_10", None)), benchmarkable=False,
    ),
    "gold_at_14": GoalMetric(
        "gold_at_14", "Gold@14", GTE, False,
        lambda m: _opt(getattr(m, "gold_at_14", None)), benchmarkable=False,
    ),
}


def metric_catalog() -> list[dict]:
    return [
        {"key": m.key, "label": m.label, "comparison": m.comparison, "is_float": m.is_float}
        for m in METRICS.values()
    ]


def evaluate_metric(metric_key: str, match) -> Optional[float]:
    metric = METRICS[metric_key]
    raw = metric.value(match)
    if raw is None:
        return None
    return int(raw) if not metric.is_float else raw


def goal_met(metric_key: str, target: float, match) -> Optional[bool]:
    metric = METRICS[metric_key]
    value = metric.value(match)
    if value is None:
        return None
    return value <= target if metric.comparison == LTE else value >= target
