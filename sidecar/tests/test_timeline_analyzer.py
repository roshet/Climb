from timeline_analyzer import analyze_timeline, PivotalMomentData

PARTICIPANT_ID = 1  # 1-indexed in Riot API

def make_frame(timestamp_ms: int, events: list) -> dict:
    frames = {str(i): {"totalGold": 5000, "currentGold": 1000} for i in range(1, 11)}
    return {"timestamp": timestamp_ms, "participantFrames": frames, "events": events}

def test_detects_death_event():
    timeline = {"info": {"frames": [
        make_frame(60000, []),
        make_frame(880000, [
            {"type": "CHAMPION_KILL", "timestamp": 872000,
             "killerId": 3, "victimId": PARTICIPANT_ID,
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    death_moments = [m for m in moments if m.moment_type == "death"]
    assert len(death_moments) >= 1
    assert death_moments[0].timestamp_secs == 872

def test_detects_missed_objective():
    # Player's team (team 100, participants 1-5) didn't take dragon at 15 mins
    timeline = {"info": {"frames": [
        make_frame(900000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 905000,
             "killerId": 6,  # enemy team (participants 6-10)
             "monsterType": "DRAGON", "position": {"x": 9866, "y": 4414}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    obj_moments = [m for m in moments if m.moment_type == "objective_missed"]
    assert len(obj_moments) >= 1
    assert obj_moments[0].gold_impact >= 300

def test_detects_tower_kill_by_enemy():
    timeline = {"info": {"frames": [
        make_frame(720000, [
            {"type": "BUILDING_KILL", "timestamp": 725000,
             "killerId": 7, "teamId": 200,
             "buildingType": "TOWER_BUILDING",
             "laneType": "BOT_LANE", "towerType": "OUTER_TURRET"}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    tower_moments = [m for m in moments if m.moment_type == "tower_lost"]
    assert len(tower_moments) >= 1

def test_returns_top_5_max():
    # Generate many events
    events = [
        {"type": "CHAMPION_KILL", "timestamp": (i + 1) * 60000,
         "killerId": 3, "victimId": PARTICIPANT_ID,
         "position": {"x": 5000, "y": 7000}}
        for i in range(10)
    ]
    timeline = {"info": {"frames": [make_frame((i + 1) * 60000, [events[i]]) for i in range(10)]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    assert len(moments) <= 5

def test_death_tower_dive():
    # Blue turret at (981, 10441) — death within 1000 units
    timeline = {"info": {"frames": [
        make_frame(300000, [
            {"type": "CHAMPION_KILL", "timestamp": 300000,
             "killerId": 6, "victimId": PARTICIPANT_ID,
             "assistingParticipantIds": [],
             "position": {"x": 1200, "y": 10300}}  # ~340 units from (981, 10441)
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    deaths = [m for m in moments if m.moment_type == "death"]
    assert len(deaths) == 1
    assert "tower dived" in deaths[0].description

def test_death_ganked_before_14min():
    # Enemy jungler (participant 10) kills player at 5:00
    timeline = {"info": {"frames": [
        make_frame(300000, [
            {"type": "CHAMPION_KILL", "timestamp": 300000,
             "killerId": 10, "victimId": PARTICIPANT_ID,
             "assistingParticipantIds": [7],
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID, enemy_jungler_id=10)
    deaths = [m for m in moments if m.moment_type == "death"]
    assert len(deaths) == 1
    assert "ganked" in deaths[0].description

def test_death_not_ganked_after_14min():
    # Same event but at 15:00 → outnumbered, not ganked
    timeline = {"info": {"frames": [
        make_frame(900000, [
            {"type": "CHAMPION_KILL", "timestamp": 900000,
             "killerId": 10, "victimId": PARTICIPANT_ID,
             "assistingParticipantIds": [7],
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID, enemy_jungler_id=10)
    deaths = [m for m in moments if m.moment_type == "death"]
    assert len(deaths) == 1
    assert "ganked" not in deaths[0].description
    assert "v1" in deaths[0].description

def test_death_outnumbered():
    # 2 enemies involved (no jungler context)
    timeline = {"info": {"frames": [
        make_frame(480000, [
            {"type": "CHAMPION_KILL", "timestamp": 480000,
             "killerId": 7, "victimId": PARTICIPANT_ID,
             "assistingParticipantIds": [8],
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    deaths = [m for m in moments if m.moment_type == "death"]
    assert len(deaths) == 1
    assert "v1" in deaths[0].description

def test_death_1v1_loss():
    # Exactly one enemy, no assists
    timeline = {"info": {"frames": [
        make_frame(480000, [
            {"type": "CHAMPION_KILL", "timestamp": 480000,
             "killerId": 7, "victimId": PARTICIPANT_ID,
             "assistingParticipantIds": [],
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    deaths = [m for m in moments if m.moment_type == "death"]
    assert len(deaths) == 1
    assert "1v1" in deaths[0].description

def test_solo_kill():
    # Player kills an enemy with no assists
    timeline = {"info": {"frames": [
        make_frame(480000, [
            {"type": "CHAMPION_KILL", "timestamp": 480000,
             "killerId": PARTICIPANT_ID, "victimId": 7,
             "assistingParticipantIds": [],
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    kills = [m for m in moments if m.moment_type == "solo_kill"]
    assert len(kills) == 1
    assert "solo kill" in kills[0].description

def test_solo_kill_not_detected_with_assists():
    # Player kills enemy but had assists — not a solo kill
    timeline = {"info": {"frames": [
        make_frame(480000, [
            {"type": "CHAMPION_KILL", "timestamp": 480000,
             "killerId": PARTICIPANT_ID, "victimId": 7,
             "assistingParticipantIds": [2],
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    kills = [m for m in moments if m.moment_type == "solo_kill"]
    assert len(kills) == 0

def test_objective_secured():
    # Player's team (team 100, participants 1-5) kills Baron
    timeline = {"info": {"frames": [
        make_frame(1200000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 1200000,
             "killerId": 3,  # teammate on team 100
             "monsterType": "BARON_NASHOR",
             "position": {"x": 5007, "y": 10471}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    secured = [m for m in moments if m.moment_type == "objective_secured"]
    assert len(secured) == 1
    assert "Baron" in secured[0].description
    assert secured[0].gold_impact == 900

def test_death_execute():
    # killerId=0 (tower/environment finish, no assisting champions)
    timeline = {"info": {"frames": [
        make_frame(300000, [
            {"type": "CHAMPION_KILL", "timestamp": 300000,
             "killerId": 0, "victimId": PARTICIPANT_ID,
             "assistingParticipantIds": [],
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    deaths = [m for m in moments if m.moment_type == "death"]
    assert len(deaths) == 1
    assert "executed" in deaths[0].description

def test_death_execute_near_own_turret():
    # killerId=0 near Blue top turret (981, 10441) — still "executed", not "tower dived"
    timeline = {"info": {"frames": [
        make_frame(300000, [
            {"type": "CHAMPION_KILL", "timestamp": 300000,
             "killerId": 0, "victimId": PARTICIPANT_ID,
             "assistingParticipantIds": [],
             "position": {"x": 981, "y": 10441}}  # exactly on turret
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    deaths = [m for m in moments if m.moment_type == "death"]
    assert len(deaths) == 1
    assert "executed" in deaths[0].description

def test_sorted_by_gold_impact_descending():
    timeline = {"info": {"frames": [
        make_frame(900000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 905000,
             "killerId": 6, "monsterType": "BARON_NASHOR",
             "position": {"x": 5007, "y": 10471}}
        ]),
        make_frame(500000, [
            {"type": "CHAMPION_KILL", "timestamp": 502000,
             "killerId": 3, "victimId": PARTICIPANT_ID,
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    if len(moments) >= 2:
        assert moments[0].gold_impact >= moments[1].gold_impact
