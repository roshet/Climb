from dataclasses import dataclass
from typing import Callable

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


@dataclass(frozen=True)
class GoalMetric:
    key: str
    label: str
    comparison: str            # GTE or LTE
    is_float: bool
    value: Callable[[object], float]


METRICS: dict[str, GoalMetric] = {
    "deaths": GoalMetric("deaths", "Deaths", LTE, False, _deaths),
    "cs": GoalMetric("cs", "CS", GTE, False, lambda m: float(m.cs)),
    "vision_score": GoalMetric("vision_score", "Vision Score", GTE, False, lambda m: float(m.vision_score)),
    "gold_earned": GoalMetric("gold_earned", "Gold Earned", GTE, False, lambda m: float(m.gold_earned)),
    "kda": GoalMetric("kda", "KDA", GTE, True, _kda),
}


def metric_catalog() -> list[dict]:
    return [
        {"key": m.key, "label": m.label, "comparison": m.comparison, "is_float": m.is_float}
        for m in METRICS.values()
    ]


def evaluate_metric(metric_key: str, match) -> float:
    raw = METRICS[metric_key].value(match)
    return int(raw) if not METRICS[metric_key].is_float else raw


def goal_met(metric_key: str, target: float, match) -> bool:
    metric = METRICS[metric_key]
    value = metric.value(match)
    return value <= target if metric.comparison == LTE else value >= target
