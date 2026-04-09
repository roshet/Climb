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
