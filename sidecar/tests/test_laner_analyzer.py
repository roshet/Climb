import pytest
from laner_analyzer import analyze_laner

TOP_ID = 1          # blue side top (team 100, participants 1-5)
OPPONENT_ID = 6     # red side top (team 200, participants 6-10)
ENEMY_JUNGLER_ID = 7


def make_frame(
    timestamp_ms: int,
    events: list,
    positions: dict | None = None,
    cs: dict | None = None,
    gold: dict | None = None,
) -> dict:
    pf = {}
    for pid in range(1, 11):
        pos = (positions or {}).get(pid, (5000, 5000))
        pf[str(pid)] = {
            "position": {"x": pos[0], "y": pos[1]},
            "minionsKilled": (cs or {}).get(pid, 0),
            "totalGold": (gold or {}).get(pid, 3000),
        }
    return {"timestamp": timestamp_ms, "participantFrames": pf, "events": events}


# --- lane_death ---

def test_lane_death_ganked_top_lane():
    timeline = {"info": {"frames": [
        make_frame(300_000, [
            {"type": "CHAMPION_KILL", "timestamp": 300_000,
             "killerId": ENEMY_JUNGLER_ID, "victimId": TOP_ID,
             "assistingParticipantIds": [OPPONENT_ID],
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP", ENEMY_JUNGLER_ID)
    deaths = [m for m in moments if m.moment_type == "lane_death"]
    assert len(deaths) == 1
    assert "ganked" in deaths[0].description.lower()


def test_lane_death_dove_top_lane():
    # Dies with 3 enemies at Blue top turret position (981, 10441) — within TOWER_DIVE_RADIUS
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": OPPONENT_ID, "victimId": TOP_ID,
             "assistingParticipantIds": [7, 8],
             "position": {"x": 981, "y": 10441}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP", ENEMY_JUNGLER_ID)
    deaths = [m for m in moments if m.moment_type == "lane_death"]
    assert len(deaths) == 1
    assert "dove" in deaths[0].description.lower()


def test_lane_death_1v1_loss_top_lane():
    timeline = {"info": {"frames": [
        make_frame(300_000, [
            {"type": "CHAMPION_KILL", "timestamp": 300_000,
             "killerId": OPPONENT_ID, "victimId": TOP_ID,
             "assistingParticipantIds": [],
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP", ENEMY_JUNGLER_ID)
    deaths = [m for m in moments if m.moment_type == "lane_death"]
    assert len(deaths) == 1
    assert "1v1" in deaths[0].description.lower()


def test_lane_death_not_flagged_after_14min():
    timeline = {"info": {"frames": [
        make_frame(900_000, [
            {"type": "CHAMPION_KILL", "timestamp": 900_000,
             "killerId": OPPONENT_ID, "victimId": TOP_ID,
             "assistingParticipantIds": [],
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP", ENEMY_JUNGLER_ID)
    deaths = [m for m in moments if m.moment_type == "lane_death"]
    assert len(deaths) == 0


def test_lane_death_not_flagged_outside_lane():
    timeline = {"info": {"frames": [
        make_frame(300_000, [
            {"type": "CHAMPION_KILL", "timestamp": 300_000,
             "killerId": OPPONENT_ID, "victimId": TOP_ID,
             "assistingParticipantIds": [],
             "position": {"x": 8000, "y": 8000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP", ENEMY_JUNGLER_ID)
    deaths = [m for m in moments if m.moment_type == "lane_death"]
    assert len(deaths) == 0


# --- solo_kill ---

def test_solo_kill_in_lane_on_opponent():
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": TOP_ID, "victimId": OPPONENT_ID,
             "assistingParticipantIds": [],
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP", ENEMY_JUNGLER_ID)
    kills = [m for m in moments if m.moment_type == "solo_kill"]
    assert len(kills) == 1
    assert "solo kill" in kills[0].description.lower()


def test_solo_kill_not_flagged_with_assists():
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": TOP_ID, "victimId": OPPONENT_ID,
             "assistingParticipantIds": [2],
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP", ENEMY_JUNGLER_ID)
    kills = [m for m in moments if m.moment_type == "solo_kill"]
    assert len(kills) == 0


def test_solo_kill_not_flagged_outside_lane():
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": TOP_ID, "victimId": OPPONENT_ID,
             "assistingParticipantIds": [],
             "position": {"x": 8000, "y": 8000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP", ENEMY_JUNGLER_ID)
    kills = [m for m in moments if m.moment_type == "solo_kill"]
    assert len(kills) == 0


def test_lane_death_red_side_top_lane():
    # Participant 6 (red side) dies at x=13000 (red top lane area), before 14 min
    RED_TOP_ID = 6
    RED_OPPONENT_ID = 1
    timeline = {"info": {"frames": [
        make_frame(300_000, [
            {"type": "CHAMPION_KILL", "timestamp": 300_000,
             "killerId": RED_OPPONENT_ID, "victimId": RED_TOP_ID,
             "assistingParticipantIds": [],
             "position": {"x": 13000, "y": 8000}},  # Red side top lane
        ]),
    ]}}
    moments = analyze_laner(timeline, RED_TOP_ID, RED_OPPONENT_ID, "TOP")
    deaths = [m for m in moments if m.moment_type == "lane_death"]
    assert len(deaths) == 1
    assert "1v1" in deaths[0].description.lower()


def test_lane_death_red_side_bot_lane():
    # Participant 6 (red side) dies at y=13000 (red bot lane area), before 14 min
    RED_BOT_ID = 6
    RED_OPPONENT_ID = 1
    timeline = {"info": {"frames": [
        make_frame(300_000, [
            {"type": "CHAMPION_KILL", "timestamp": 300_000,
             "killerId": RED_OPPONENT_ID, "victimId": RED_BOT_ID,
             "assistingParticipantIds": [],
             "position": {"x": 10000, "y": 13000}},  # Red side bot lane
        ]),
    ]}}
    moments = analyze_laner(timeline, RED_BOT_ID, RED_OPPONENT_ID, "BOTTOM")
    deaths = [m for m in moments if m.moment_type == "lane_death"]
    assert len(deaths) == 1


# --- objectives ---

def test_objective_missed_dragon():
    timeline = {"info": {"frames": [
        make_frame(325_000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 323_000,
             "killerId": OPPONENT_ID, "monsterType": "DRAGON"},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    missed = [m for m in moments if m.moment_type == "objective_missed"]
    assert len(missed) == 1


def test_objective_secured_baron():
    timeline = {"info": {"frames": [
        make_frame(1_205_000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 1_203_000,
             "killerId": 3, "monsterType": "BARON_NASHOR"},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    secured = [m for m in moments if m.moment_type == "objective_secured"]
    assert len(secured) == 1
    assert secured[0].gold_impact == 900


# --- tower ---

def test_tower_lost():
    # teamId=100 means team 100 (player's team) LOST the tower
    timeline = {"info": {"frames": [
        make_frame(720_000, [
            {"type": "BUILDING_KILL", "timestamp": 725_000,
             "killerId": OPPONENT_ID, "teamId": 100,
             "buildingType": "TOWER_BUILDING",
             "laneType": "TOP_LANE", "towerType": "OUTER_TURRET"},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    towers = [m for m in moments if m.moment_type == "tower_lost"]
    assert len(towers) == 1


# --- CS differential ---

def test_cs_differential_flagged_when_15_behind():
    timeline = {"info": {"frames": [
        make_frame(840_000, [], cs={TOP_ID: 60, OPPONENT_ID: 80}),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    cs_moments = [m for m in moments if m.moment_type == "cs_differential"]
    assert len(cs_moments) == 1
    assert "20 CS" in cs_moments[0].description
    assert cs_moments[0].timestamp_secs == 840


def test_cs_differential_not_flagged_when_less_than_15_behind():
    timeline = {"info": {"frames": [
        make_frame(840_000, [], cs={TOP_ID: 70, OPPONENT_ID: 80}),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    cs_moments = [m for m in moments if m.moment_type == "cs_differential"]
    assert len(cs_moments) == 0


def test_cs_differential_not_flagged_for_support():
    timeline = {"info": {"frames": [
        make_frame(840_000, [], cs={1: 0, 6: 80}),
    ]}}
    moments = analyze_laner(timeline, 1, 6, "UTILITY")
    cs_moments = [m for m in moments if m.moment_type == "cs_differential"]
    assert len(cs_moments) == 0


def test_cs_differential_not_flagged_when_ahead():
    timeline = {"info": {"frames": [
        make_frame(840_000, [], cs={TOP_ID: 90, OPPONENT_ID: 70}),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    cs_moments = [m for m in moments if m.moment_type == "cs_differential"]
    assert len(cs_moments) == 0


# --- Gold differential ---

def test_gold_differential_flagged_when_1000_behind():
    timeline = {"info": {"frames": [
        make_frame(840_000, [], gold={TOP_ID: 4000, OPPONENT_ID: 5500}),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    gold_moments = [m for m in moments if m.moment_type == "gold_differential"]
    assert len(gold_moments) == 1
    assert "1500" in gold_moments[0].description
    assert gold_moments[0].timestamp_secs == 840


def test_gold_differential_flagged_for_support():
    timeline = {"info": {"frames": [
        make_frame(840_000, [], gold={1: 2000, 6: 4000}),
    ]}}
    moments = analyze_laner(timeline, 1, 6, "UTILITY")
    gold_moments = [m for m in moments if m.moment_type == "gold_differential"]
    assert len(gold_moments) == 1


def test_gold_differential_not_flagged_when_less_than_1000_behind():
    timeline = {"info": {"frames": [
        make_frame(840_000, [], gold={TOP_ID: 4200, OPPONENT_ID: 5000}),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    gold_moments = [m for m in moments if m.moment_type == "gold_differential"]
    assert len(gold_moments) == 0
