from counterfactual import enrich_moments
from timeline_analyzer import PivotalMomentData

def make_moment(moment_type: str, gold_impact: int = 300, timestamp_secs: int = 600) -> PivotalMomentData:
    return PivotalMomentData(
        timestamp_secs=timestamp_secs,
        moment_type=moment_type,
        description="Test description.",
        counterfactual="",
        gold_impact=gold_impact,
    )

def test_death_early_game_counterfactual():
    moment = make_moment("death", timestamp_secs=480)  # 8 mins
    enriched = enrich_moments([moment])
    assert "recall" in enriched[0].counterfactual.lower() or "back" in enriched[0].counterfactual.lower() or "death" in enriched[0].counterfactual.lower()

def test_objective_missed_baron_counterfactual():
    moment = PivotalMomentData(
        timestamp_secs=1200,
        moment_type="objective_missed",
        description="Enemy team secured Baron Nashor at 20:00.",
        counterfactual="",
        gold_impact=900,
    )
    enriched = enrich_moments([moment])
    assert "baron" in enriched[0].counterfactual.lower() or "900" in enriched[0].counterfactual or "objective" in enriched[0].counterfactual.lower()

def test_tower_lost_counterfactual():
    moment = make_moment("tower_lost", gold_impact=250)
    enriched = enrich_moments([moment])
    assert len(enriched[0].counterfactual) > 20

def test_all_moments_get_counterfactuals():
    moments = [
        make_moment("death", timestamp_secs=300),
        make_moment("objective_missed", gold_impact=400),
        make_moment("tower_lost", gold_impact=200),
    ]
    enriched = enrich_moments(moments)
    assert all(len(m.counterfactual) > 10 for m in enriched)

def test_preserves_order():
    moments = [make_moment("death", timestamp_secs=i * 60) for i in range(3)]
    enriched = enrich_moments(moments)
    assert [m.timestamp_secs for m in enriched] == [m.timestamp_secs for m in moments]
