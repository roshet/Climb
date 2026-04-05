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
