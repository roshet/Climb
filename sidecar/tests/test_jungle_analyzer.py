from jungle_analyzer import analyze_jungle

JUNGLE_ID = 1   # blue side jungler (participant 1, team 100)

def make_frame(timestamp_ms: int, events: list, positions: dict | None = None) -> dict:
    """
    positions: {participant_id: (x, y)} — optional per-participant positions.
    Defaults to (5000, 5000) for all participants if not provided.
    """
    participant_frames = {}
    for pid in range(1, 11):
        pos = (positions or {}).get(pid, (5000, 5000))
        participant_frames[str(pid)] = {
            "totalGold": 5000,
            "currentGold": 1000,
            "position": {"x": pos[0], "y": pos[1]},
        }
    return {"timestamp": timestamp_ms, "participantFrames": participant_frames, "events": events}


def test_invade_death_in_enemy_jungle():
    # Blue side jungler dies at (12000, 4000) — inside red side jungle
    timeline = {"info": {"frames": [
        make_frame(300000, [
            {"type": "CHAMPION_KILL", "timestamp": 300000,
             "killerId": 6, "victimId": JUNGLE_ID,
             "assistingParticipantIds": [],
             "position": {"x": 12000, "y": 4000}}
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    invades = [m for m in moments if m.moment_type == "invade_death"]
    assert len(invades) == 1
    assert "enemy jungle" in invades[0].description.lower()


def test_invade_death_not_triggered_in_own_jungle():
    # Blue side jungler dies at (2000, 10000) — inside blue side jungle (own jungle)
    # Should produce jungle_death (catch-all), NOT invade_death
    timeline = {"info": {"frames": [
        make_frame(300000, [
            {"type": "CHAMPION_KILL", "timestamp": 300000,
             "killerId": 6, "victimId": JUNGLE_ID,
             "assistingParticipantIds": [],
             "position": {"x": 2000, "y": 10000}}
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    invades = [m for m in moments if m.moment_type == "invade_death"]
    assert len(invades) == 0
    jungle_deaths = [m for m in moments if m.moment_type == "jungle_death"]
    assert len(jungle_deaths) == 1


def test_counter_ganked_in_ally_lane():
    # Jungler ganking bot lane (y=2000), killed by enemy laner + enemy jungler.
    # Position (5000, 2000): y=2000 < 4000 (bot lane) AND x=5000 < 8000 (not enemy jungle).
    timeline = {"info": {"frames": [
        make_frame(480000, [
            {"type": "CHAMPION_KILL", "timestamp": 480000,
             "killerId": 6, "victimId": JUNGLE_ID,
             "assistingParticipantIds": [7],  # enemy jungler assists
             "position": {"x": 5000, "y": 2000}}  # bot lane, NOT enemy jungle
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID, enemy_jungler_id=7)
    counter_ganks = [m for m in moments if m.moment_type == "counter_ganked"]
    assert len(counter_ganks) == 1
    assert "counter-ganked" in counter_ganks[0].description.lower()


def test_counter_ganked_requires_enemy_jungler():
    # Same event but no enemy_jungler_id provided — should NOT flag as counter-gank
    timeline = {"info": {"frames": [
        make_frame(480000, [
            {"type": "CHAMPION_KILL", "timestamp": 480000,
             "killerId": 6, "victimId": JUNGLE_ID,
             "assistingParticipantIds": [7],
             "position": {"x": 5000, "y": 2000}}  # bot lane, NOT enemy jungle
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID, enemy_jungler_id=None)
    counter_ganks = [m for m in moments if m.moment_type == "counter_ganked"]
    assert len(counter_ganks) == 0


def test_gank_assist_in_lane():
    # Jungler assists a kill in bot lane (y=2000)
    timeline = {"info": {"frames": [
        make_frame(480000, [
            {"type": "CHAMPION_KILL", "timestamp": 480000,
             "killerId": 2, "victimId": 7,  # teammate kills enemy
             "assistingParticipantIds": [JUNGLE_ID],  # jungler assisted
             "position": {"x": 8000, "y": 2000}}  # bot lane
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    ganks = [m for m in moments if m.moment_type == "gank_assist"]
    assert len(ganks) == 1
    assert "ganked" in ganks[0].description.lower() or "kill" in ganks[0].description.lower()


def test_gank_assist_not_in_jungle():
    # Jungler kills enemy but in jungle (not a lane gank)
    timeline = {"info": {"frames": [
        make_frame(480000, [
            {"type": "CHAMPION_KILL", "timestamp": 480000,
             "killerId": JUNGLE_ID, "victimId": 7,
             "assistingParticipantIds": [],
             "position": {"x": 5000, "y": 5000}}  # mid-map, not in a lane
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    ganks = [m for m in moments if m.moment_type == "gank_assist"]
    assert len(ganks) == 0


def test_dragon_stack_secured():
    # Player's team (team 100) secures Dragon
    timeline = {"info": {"frames": [
        make_frame(325000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 323000,
             "killerId": 3,  # teammate on team 100
             "monsterType": "DRAGON",
             "position": {"x": 9866, "y": 4414}}
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    stacks = [m for m in moments if m.moment_type == "dragon_stack"]
    assert len(stacks) == 1
    assert "Dragon" in stacks[0].description
    assert stacks[0].gold_impact == 350


def test_baron_secured():
    # Player's team (team 100) secures Baron
    timeline = {"info": {"frames": [
        make_frame(1205000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 1203000,
             "killerId": 1,  # jungler themselves smites Baron
             "monsterType": "BARON_NASHOR",
             "position": {"x": 5007, "y": 10471}}
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    secured = [m for m in moments if m.moment_type == "baron_secured"]
    assert len(secured) == 1
    assert "Baron" in secured[0].description
    assert secured[0].gold_impact == 900


def test_dragon_missed_wrong_side():
    # Jungler is top-side (y=10000) when enemy takes Dragon at 5:23
    timeline = {"info": {"frames": [
        make_frame(280000, [], positions={JUNGLE_ID: (2000, 10000)}),  # jungler top-side
        make_frame(325000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 323000,
             "killerId": 6, "monsterType": "DRAGON",
             "position": {"x": 9866, "y": 4414}}
        ], positions={JUNGLE_ID: (2000, 10000)}),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    misses = [m for m in moments if m.moment_type == "dragon_missed"]
    assert len(misses) == 1
    assert "Dragon" in misses[0].description


def test_dragon_not_missed_if_jungler_recently_dead():
    # Jungler died 23s before Dragon — correct concede, should NOT flag
    timeline = {"info": {"frames": [
        make_frame(300000, [
            {"type": "CHAMPION_KILL", "timestamp": 300000,
             "killerId": 6, "victimId": JUNGLE_ID,
             "assistingParticipantIds": [],
             "position": {"x": 2000, "y": 10000}}
        ], positions={JUNGLE_ID: (2000, 10000)}),
        make_frame(325000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 323000,
             "killerId": 6, "monsterType": "DRAGON",
             "position": {"x": 9866, "y": 4414}}
        ], positions={JUNGLE_ID: (2000, 10000)}),
    ]}}
    # Jungler died at 300s, Dragon at 323s — 23s gap (within ALIVE_WINDOW_SECS=30)
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    misses = [m for m in moments if m.moment_type == "dragon_missed"]
    assert len(misses) == 0


def test_baron_missed_wrong_side():
    # Jungler is bot-side (y=2000) when enemy takes Baron at 20:00
    timeline = {"info": {"frames": [
        make_frame(1195000, [], positions={JUNGLE_ID: (8000, 2000)}),  # jungler bot-side
        make_frame(1205000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 1203000,
             "killerId": 6, "monsterType": "BARON_NASHOR",
             "position": {"x": 5007, "y": 10471}}
        ], positions={JUNGLE_ID: (8000, 2000)}),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    misses = [m for m in moments if m.moment_type == "baron_missed"]
    assert len(misses) == 1
    assert "Baron" in misses[0].description


def test_void_grubs_missed_all_three():
    # Enemy takes all 3 void grubs
    grub_events = [
        {"type": "ELITE_MONSTER_KILL", "timestamp": 305000 + i * 60000,
         "killerId": 6, "monsterType": "HORDE"}
        for i in range(3)
    ]
    timeline = {"info": {"frames": [
        make_frame(300000 + i * 60000, [grub_events[i]])
        for i in range(3)
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    grub_misses = [m for m in moments if m.moment_type == "void_grubs_missed"]
    assert len(grub_misses) == 1
    assert "Void Grub" in grub_misses[0].description


def test_void_grubs_not_flagged_if_player_team_gets_them():
    # Player's team takes all 3 void grubs — should NOT flag
    grub_events = [
        {"type": "ELITE_MONSTER_KILL", "timestamp": 305000 + i * 60000,
         "killerId": 1, "monsterType": "HORDE"}  # team 100 jungler
        for i in range(3)
    ]
    timeline = {"info": {"frames": [
        make_frame(300000 + i * 60000, [grub_events[i]])
        for i in range(3)
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    grub_misses = [m for m in moments if m.moment_type == "void_grubs_missed"]
    assert len(grub_misses) == 0


def test_death_fallback_own_jungle():
    # Blue side jungler dies at (3000, 9000) — inside blue side jungle (own jungle)
    # Not in enemy jungle (x < 8000 or y > 7500), not in a lane
    timeline = {"info": {"frames": [
        make_frame(600000, [
            {"type": "CHAMPION_KILL", "timestamp": 600000,
             "killerId": 6, "victimId": JUNGLE_ID,
             "assistingParticipantIds": [],
             "position": {"x": 3000, "y": 9000}}
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    assert len(moments) == 1
    assert moments[0].moment_type == "jungle_death"
    assert "jungle" in moments[0].description.lower()
    assert moments[0].gold_impact == 300


def test_death_fallback_skirmish():
    # Blue side jungler dies at (7500, 6000) — mid-map, not own jungle, not enemy jungle, not lane
    timeline = {"info": {"frames": [
        make_frame(900000, [
            {"type": "CHAMPION_KILL", "timestamp": 900000,
             "killerId": 7, "victimId": JUNGLE_ID,
             "assistingParticipantIds": [],
             "position": {"x": 7500, "y": 6000}}
        ]),
    ]}}
    moments = analyze_jungle(timeline, participant_id=JUNGLE_ID)
    assert len(moments) == 1
    assert moments[0].moment_type == "death"
    assert moments[0].gold_impact == 300
