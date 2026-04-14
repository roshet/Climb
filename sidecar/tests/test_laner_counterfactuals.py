from timeline_analyzer import PivotalMomentData
from counterfactual import enrich_moments


def make_moment(moment_type: str, description: str = "", gold_impact: int = 300) -> PivotalMomentData:
    return PivotalMomentData(
        timestamp_secs=300,
        moment_type=moment_type,
        description=description,
        counterfactual="",
        gold_impact=gold_impact,
    )


def test_lane_death_ganked_counterfactual():
    m = make_moment("lane_death", "You were ganked at 5:00.")
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
    assert "jungler" in enriched.counterfactual.lower() or "ward" in enriched.counterfactual.lower()


def test_lane_death_dove_counterfactual():
    m = make_moment("lane_death", "You were dove at 8:00 (3 enemies collapsed under your tower).")
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
    assert "tower" in enriched.counterfactual.lower() or "dive" in enriched.counterfactual.lower()


def test_lane_death_1v1_counterfactual():
    m = make_moment("lane_death", "You lost a 1v1 trade at 5:00.")
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
    assert "trade" in enriched.counterfactual.lower() or "matchup" in enriched.counterfactual.lower()


def test_cs_differential_counterfactual():
    m = make_moment("cs_differential", "You were 25 CS behind your lane opponent at 14:00.", gold_impact=525)
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
    assert "cs" in enriched.counterfactual.lower() or "farm" in enriched.counterfactual.lower()


def test_gold_differential_counterfactual():
    m = make_moment("gold_differential", "You were 1500g behind your lane opponent at 14:00.", gold_impact=1500)
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
    assert len(enriched.counterfactual) > 20


def test_turret_plates_lost_counterfactual():
    m = make_moment("turret_plates_lost", "Enemy took 3 tower plates in your lane by 8:00 (480g given up).", gold_impact=480)
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
    assert "plate" in enriched.counterfactual.lower() or "wave" in enriched.counterfactual.lower()


def test_split_push_death_counterfactual():
    m = make_moment("split_push_death", "You were collapsed on by 3 enemies while split pushing at 22:00.")
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
    assert "split" in enriched.counterfactual.lower() or "side lane" in enriched.counterfactual.lower()


def test_roam_kill_counterfactual():
    m = make_moment("roam_kill", "Your roam resulted in a kill at 7:00.")
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""


def test_enemy_roam_kill_counterfactual():
    m = make_moment("enemy_roam_kill", "Enemy mid roamed for a kill at 6:00 while you were in lane.")
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
    assert "roam" in enriched.counterfactual.lower()


def test_low_vision_counterfactual():
    m = make_moment("low_vision", "You placed only 2 wards in the first 20 minutes (minimum: 4).")
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
    assert "ward" in enriched.counterfactual.lower()


def test_ward_kill_counterfactual():
    m = make_moment("ward_kill", "You destroyed an enemy ward at 5:00.")
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""


def test_roam_assist_counterfactual():
    m = make_moment("roam_assist", "Your roam contributed to a kill at 7:30.")
    [enriched] = enrich_moments([m])
    assert enriched.counterfactual != ""
