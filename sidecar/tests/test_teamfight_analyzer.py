from teamfight_analyzer import analyze_teamfights


def _kill(ts_secs, killer, victim, assists=None):
    return {
        "type": "CHAMPION_KILL",
        "timestamp": ts_secs * 1000,
        "killerId": killer,
        "victimId": victim,
        "assistingParticipantIds": assists or [],
        "position": {"x": 0, "y": 0},
    }


def _monster(ts_secs, killer, monster):
    return {
        "type": "ELITE_MONSTER_KILL",
        "timestamp": ts_secs * 1000,
        "killerId": killer,
        "monsterType": monster,
    }


def _timeline(events):
    return {"info": {"frames": [{"events": events}]}}


def test_won_fight_emits_one_won_moment():
    # 3 enemies die within 20s, player (1) lands one of the kills -> 3-for-0 win
    tl = _timeline([_kill(600, 1, 6), _kill(605, 2, 7), _kill(610, 3, 8)])
    moments = analyze_teamfights(tl, participant_id=1)
    assert len(moments) == 1
    assert moments[0].moment_type == "teamfight_won"
    assert moments[0].timestamp_secs == 600
    assert moments[0].gold_impact == 900  # abs(3-0) * 300


def test_lost_fight_emits_one_lost_moment():
    # 3 allies die (1,2,3) within 20s -> 0-for-3 loss
    tl = _timeline([_kill(600, 6, 1), _kill(605, 7, 2), _kill(610, 8, 3)])
    moments = analyze_teamfights(tl, participant_id=1)
    assert len(moments) == 1
    assert moments[0].moment_type == "teamfight_lost"


def test_even_trade_is_skipped():
    # 2 enemy + 2 ally deaths -> 2-for-2, no moment
    tl = _timeline([_kill(600, 1, 6), _kill(603, 6, 1), _kill(606, 2, 7), _kill(609, 7, 2)])
    assert analyze_teamfights(tl, participant_id=1) == []


def test_skirmish_below_threshold_is_skipped():
    # only 2 kills -> not a team fight
    tl = _timeline([_kill(600, 1, 6), _kill(605, 2, 7)])
    assert analyze_teamfights(tl, participant_id=1) == []


def test_kills_far_apart_are_separate_clusters():
    # two 3-kill fights >20s apart -> two moments
    tl = _timeline([
        _kill(600, 1, 6), _kill(605, 2, 7), _kill(610, 3, 8),
        _kill(700, 1, 9), _kill(705, 2, 10), _kill(710, 3, 6),
    ])
    moments = analyze_teamfights(tl, participant_id=1)
    assert len(moments) == 2


def test_player_involvement_reported():
    tl = _timeline([_kill(600, 1, 6), _kill(605, 2, 7, assists=[1]), _kill(610, 8, 1)])
    # player got 1 kill, 1 assist, and died -> still a 2-for-1 win
    moment = analyze_teamfights(tl, participant_id=1)[0]
    assert moment.moment_type == "teamfight_won"
    assert "kill" in moment.description
    assert "assist" in moment.description
    assert "died" in moment.description


def test_player_not_involved_reported():
    tl = _timeline([_kill(600, 2, 6), _kill(605, 3, 7), _kill(610, 4, 8)])
    desc = analyze_teamfights(tl, participant_id=1)[0].description
    assert "weren't involved" in desc


def test_empty_timeline_returns_no_moments():
    assert analyze_teamfights({}, participant_id=1) == []
    assert analyze_teamfights(_timeline([]), participant_id=1) == []


def test_objective_in_window_annotated():
    tl = _timeline([
        _kill(600, 1, 6), _kill(605, 2, 7), _kill(610, 3, 8),
        _monster(608, 2, "DRAGON"),
    ])
    moment = analyze_teamfights(tl, participant_id=1)[0]
    assert "near Dragon" in moment.description
    assert moment.gold_impact == 900 + 350  # kill swing + dragon gold
