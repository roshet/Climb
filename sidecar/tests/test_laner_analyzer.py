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


# --- Turret plates ---

def test_turret_plates_lost_flagged_at_3():
    plate_events = [
        {"type": "TURRET_PLATE_DESTROYED", "timestamp": (300_000 + i * 60_000),
         "teamId": 100, "laneType": "TOP_LANE", "killerId": OPPONENT_ID}
        for i in range(3)
    ]
    timeline = {"info": {"frames": [
        make_frame(300_000 + i * 60_000, [plate_events[i]])
        for i in range(3)
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    plates = [m for m in moments if m.moment_type == "turret_plates_lost"]
    assert len(plates) == 1
    assert "480" in plates[0].description  # 3 * 160g = 480g


def test_turret_plates_not_flagged_before_3():
    plate_events = [
        {"type": "TURRET_PLATE_DESTROYED", "timestamp": (300_000 + i * 60_000),
         "teamId": 100, "laneType": "TOP_LANE", "killerId": OPPONENT_ID}
        for i in range(2)
    ]
    timeline = {"info": {"frames": [
        make_frame(300_000 + i * 60_000, [plate_events[i]])
        for i in range(2)
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    plates = [m for m in moments if m.moment_type == "turret_plates_lost"]
    assert len(plates) == 0


def test_turret_plates_not_flagged_wrong_lane():
    plate_events = [
        {"type": "TURRET_PLATE_DESTROYED", "timestamp": (300_000 + i * 60_000),
         "teamId": 100, "laneType": "MID_LANE", "killerId": OPPONENT_ID}
        for i in range(3)
    ]
    timeline = {"info": {"frames": [
        make_frame(300_000 + i * 60_000, [plate_events[i]])
        for i in range(3)
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    plates = [m for m in moments if m.moment_type == "turret_plates_lost"]
    assert len(plates) == 0


# --- Split push death (TOP) ---

def test_split_push_death_post_20min():
    timeline = {"info": {"frames": [
        make_frame(1_200_000, [
            {"type": "CHAMPION_KILL", "timestamp": 1_200_000,
             "killerId": OPPONENT_ID, "victimId": TOP_ID,
             "assistingParticipantIds": [7, 8],
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    splits = [m for m in moments if m.moment_type == "split_push_death"]
    assert len(splits) == 1
    assert "3" in splits[0].description


def test_split_push_death_not_flagged_before_20min():
    timeline = {"info": {"frames": [
        make_frame(1_199_000, [
            {"type": "CHAMPION_KILL", "timestamp": 1_199_000,
             "killerId": OPPONENT_ID, "victimId": TOP_ID,
             "assistingParticipantIds": [7, 8],
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    splits = [m for m in moments if m.moment_type == "split_push_death"]
    assert len(splits) == 0


def test_split_push_death_not_flagged_with_fewer_than_3_enemies():
    timeline = {"info": {"frames": [
        make_frame(1_200_000, [
            {"type": "CHAMPION_KILL", "timestamp": 1_200_000,
             "killerId": OPPONENT_ID, "victimId": TOP_ID,
             "assistingParticipantIds": [7],
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, TOP_ID, OPPONENT_ID, "TOP")
    splits = [m for m in moments if m.moment_type == "split_push_death"]
    assert len(splits) == 0


# --- Roam kill (MID) ---
MID_ID = 3
OPPONENT_MID_ID = 8

def test_roam_kill_mid_in_bot_lane():
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": MID_ID, "victimId": 9,
             "assistingParticipantIds": [],
             "position": {"x": 10000, "y": 2000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, MID_ID, OPPONENT_MID_ID, "MIDDLE")
    roams = [m for m in moments if m.moment_type == "roam_kill"]
    assert len(roams) == 1
    assert "roam" in roams[0].description.lower()


def test_roam_kill_not_flagged_in_mid_lane():
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": MID_ID, "victimId": OPPONENT_MID_ID,
             "assistingParticipantIds": [],
             "position": {"x": 7000, "y": 7000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, MID_ID, OPPONENT_MID_ID, "MIDDLE")
    roams = [m for m in moments if m.moment_type == "roam_kill"]
    assert len(roams) == 0


def test_roam_kill_not_flagged_after_14min():
    timeline = {"info": {"frames": [
        make_frame(900_000, [
            {"type": "CHAMPION_KILL", "timestamp": 900_000,
             "killerId": MID_ID, "victimId": 9,
             "assistingParticipantIds": [],
             "position": {"x": 10000, "y": 2000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, MID_ID, OPPONENT_MID_ID, "MIDDLE")
    roams = [m for m in moments if m.moment_type == "roam_kill"]
    assert len(roams) == 0


# --- Enemy roam kill (MID) ---

def test_enemy_roam_kill_opponent_roams_top():
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": OPPONENT_MID_ID, "victimId": 1,
             "assistingParticipantIds": [],
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, MID_ID, OPPONENT_MID_ID, "MIDDLE")
    enemy_roams = [m for m in moments if m.moment_type == "enemy_roam_kill"]
    assert len(enemy_roams) == 1
    assert "enemy mid" in enemy_roams[0].description.lower()


def test_enemy_roam_kill_not_flagged_when_killing_player():
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": OPPONENT_MID_ID, "victimId": MID_ID,
             "assistingParticipantIds": [],
             "position": {"x": 2000, "y": 12000}},
        ]),
    ]}}
    moments = analyze_laner(timeline, MID_ID, OPPONENT_MID_ID, "MIDDLE")
    enemy_roams = [m for m in moments if m.moment_type == "enemy_roam_kill"]
    assert len(enemy_roams) == 0


# --- Support signals ---
# SUPP_ID = 5 (blue team), OPPONENT_SUPP_ID = 10 (red team)
SUPP_ID = 5
OPPONENT_SUPP_ID = 10


def test_low_vision_flagged_when_under_4_wards():
    # 3 wards placed in 20 min — below SUPPORT_WARD_MINIMUM (4)
    ward_events = [
        {"type": "WARD_PLACED", "timestamp": 200_000 + i * 200_000,
         "creatorId": SUPP_ID, "wardType": "YELLOW_TRINKET"}
        for i in range(3)
    ]
    timeline = {"info": {"frames": [
        make_frame(200_000 + i * 200_000, [ward_events[i]])
        for i in range(3)
    ] + [make_frame(1_200_000, [])]}}
    moments = analyze_laner(timeline, SUPP_ID, OPPONENT_SUPP_ID, "UTILITY")
    vision = [m for m in moments if m.moment_type == "low_vision"]
    assert len(vision) == 1
    assert "3" in vision[0].description
    assert vision[0].timestamp_secs == 1200


def test_low_vision_not_flagged_when_4_or_more_wards():
    # 4 wards — meets minimum
    ward_events = [
        {"type": "WARD_PLACED", "timestamp": 200_000 + i * 200_000,
         "creatorId": SUPP_ID, "wardType": "YELLOW_TRINKET"}
        for i in range(4)
    ]
    timeline = {"info": {"frames": [
        make_frame(200_000 + i * 200_000, [ward_events[i]])
        for i in range(4)
    ] + [make_frame(1_200_000, [])]}}
    moments = analyze_laner(timeline, SUPP_ID, OPPONENT_SUPP_ID, "UTILITY")
    vision = [m for m in moments if m.moment_type == "low_vision"]
    assert len(vision) == 0


def test_low_vision_wards_after_20min_not_counted():
    # All wards placed after 20 min — should flag as 0 wards in first 20 min
    ward_events = [
        {"type": "WARD_PLACED", "timestamp": 1_300_000 + i * 60_000,
         "creatorId": SUPP_ID, "wardType": "YELLOW_TRINKET"}
        for i in range(4)
    ]
    timeline = {"info": {"frames": [
        make_frame(1_200_000, []),
        *[make_frame(1_300_000 + i * 60_000, [ward_events[i]])
          for i in range(4)],
    ]}}
    moments = analyze_laner(timeline, SUPP_ID, OPPONENT_SUPP_ID, "UTILITY")
    vision = [m for m in moments if m.moment_type == "low_vision"]
    assert len(vision) == 1
    assert "0" in vision[0].description


def test_ward_kill_flagged():
    timeline = {"info": {"frames": [
        make_frame(300_000, [
            {"type": "WARD_KILL", "timestamp": 300_000,
             "killerId": SUPP_ID, "wardType": "YELLOW_TRINKET"},
        ]),
    ]}}
    moments = analyze_laner(timeline, SUPP_ID, OPPONENT_SUPP_ID, "UTILITY")
    ward_kills = [m for m in moments if m.moment_type == "ward_kill"]
    assert len(ward_kills) == 1
    assert "ward" in ward_kills[0].description.lower()


def test_ward_kill_capped_at_3():
    # 5 ward kills — only first 3 should produce moments
    ward_kill_events = [
        {"type": "WARD_KILL", "timestamp": 300_000 + i * 60_000,
         "killerId": SUPP_ID, "wardType": "YELLOW_TRINKET"}
        for i in range(5)
    ]
    timeline = {"info": {"frames": [
        make_frame(300_000 + i * 60_000, [ward_kill_events[i]])
        for i in range(5)
    ]}}
    moments = analyze_laner(timeline, SUPP_ID, OPPONENT_SUPP_ID, "UTILITY")
    ward_kills = [m for m in moments if m.moment_type == "ward_kill"]
    assert len(ward_kills) == 3


def test_roam_assist_support_in_mid_lane():
    # SUPP_ID assists a kill in mid lane during laning phase
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": 3, "victimId": 8,
             "assistingParticipantIds": [SUPP_ID],
             "position": {"x": 7000, "y": 7000}},  # mid lane
        ]),
    ]}}
    moments = analyze_laner(timeline, SUPP_ID, OPPONENT_SUPP_ID, "UTILITY")
    roams = [m for m in moments if m.moment_type == "roam_assist"]
    assert len(roams) == 1
    assert "roam" in roams[0].description.lower()


def test_roam_assist_not_flagged_in_bot_lane():
    # Kill in bot lane — that's the support's own lane, not a roam
    timeline = {"info": {"frames": [
        make_frame(480_000, [
            {"type": "CHAMPION_KILL", "timestamp": 480_000,
             "killerId": 4, "victimId": 9,
             "assistingParticipantIds": [SUPP_ID],
             "position": {"x": 10000, "y": 2000}},  # bot lane
        ]),
    ]}}
    moments = analyze_laner(timeline, SUPP_ID, OPPONENT_SUPP_ID, "UTILITY")
    roams = [m for m in moments if m.moment_type == "roam_assist"]
    assert len(roams) == 0
