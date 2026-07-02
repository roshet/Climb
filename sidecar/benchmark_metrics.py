from types import SimpleNamespace

from goal_metrics import METRICS


def _participant_to_match_like(p: dict) -> SimpleNamespace:
    """Shape a match-v5 participant like a ``Match`` row so goal_metrics can read it.

    Mirrors the participant->Match mapping in backfill.analyze_and_save_match.
    """
    return SimpleNamespace(
        kda=f"{p['kills']}/{p['deaths']}/{p['assists']}",
        cs=p["totalMinionsKilled"],
        vision_score=p["visionScore"],
        gold_earned=p["goldEarned"],
    )


def extract_participant_metrics(participant: dict) -> dict[str, float]:
    """Float value of every benchmarkable goal metric for one match-v5 participant.

    Timeline-derived metrics (e.g. cs_at_10) aren't computable from a match-v5
    participant and are excluded via ``GoalMetric.benchmarkable``.
    """
    obj = _participant_to_match_like(participant)
    return {
        key: float(metric.value(obj))
        for key, metric in METRICS.items()
        if metric.benchmarkable
    }
