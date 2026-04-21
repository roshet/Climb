from laner_analyzer import _collect_backs, _detect_bad_backs


def make_frame(
    timestamp_ms: int,
    events: list,
    positions: dict | None = None,
    current_gold: dict | None = None,
    levels: dict | None = None,
) -> dict:
    pf = {}
    for pid in range(1, 11):
        pos = (positions or {}).get(pid, (5000, 5000))
        pf[str(pid)] = {
            "position": {"x": pos[0], "y": pos[1]},
            "currentGold": (current_gold or {}).get(pid, 1000),
            "totalGold": (current_gold or {}).get(pid, 1000),
            "minionsKilled": 0,
            "level": (levels or {}).get(pid, 5),
        }
    return {"timestamp": timestamp_ms, "participantFrames": pf, "events": events}


PLAYER = 1  # blue side, team 100


def test_deduplication():
    # ITEM_PURCHASED at 30s + position jump at 60s frame → one back, not two
    frames = [
        make_frame(0, [], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 400}),
        make_frame(60_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 1001, "timestamp": 30_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 100}),
    ]
    backs = _collect_backs(frames, participant_id=PLAYER)
    assert len(backs) == 1


def test_back_excluded_after_death():
    # Player dies at 5s (level 5 → respawn ~20s), buys at 15s → within respawn window → excluded
    frames = [
        make_frame(0, [
            {"type": "CHAMPION_KILL", "timestamp": 5_000,
             "victimId": PLAYER, "killerId": 6, "assistingParticipantIds": []},
        ], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 400}, levels={PLAYER: 5}),
        make_frame(60_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 1001, "timestamp": 15_000},
        ], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 100}),
    ]
    backs = _collect_backs(frames, participant_id=PLAYER)
    assert len(backs) == 0


def test_position_back_after_death_window_purchase():
    # Bug scenario: death at 5s, purchase during respawn window at 15s (excluded),
    # then position jump to fountain at 90s (real voluntary recall, should be included)
    # Player: blue side (team 100), fountain at (523, 523)
    # Level 5: respawn = 8 + 5*2.5 = 20.5s → excluded until 25.5s
    # Gap from purchase (15s) to position back (90s) = 75s > BACK_DEDUP_WINDOW_SECS (60s),
    # so even if the purchase were a dedup anchor it wouldn't block — but it isn't (excluded).
    frames = [
        make_frame(0, [
            {"type": "CHAMPION_KILL", "timestamp": 5_000,
             "victimId": PLAYER, "killerId": 6, "assistingParticipantIds": []},
        ], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 400}, levels={PLAYER: 5}),
        make_frame(15_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 1001, "timestamp": 15_000},
        ], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 350}, levels={PLAYER: 5}),
        make_frame(90_000, [
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 100}, levels={PLAYER: 5}),
    ]
    backs = _collect_backs(frames, participant_id=PLAYER)
    assert len(backs) == 1
    assert backs[0]["timestamp_secs"] == 90.0


def test_objective_window_back():
    # Back at 4:00 (240s), dragon first spawns at 5:00 (300s) → 60s before → flagged
    frames = [
        make_frame(0, [], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 800}),
        make_frame(240_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 3006, "timestamp": 240_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 800}),
    ]
    moments = _detect_bad_backs(frames, participant_id=PLAYER, role="TOP")
    obj = [m for m in moments if m.moment_type == "bad_back_objective"]
    assert len(obj) == 1
    assert "Dragon" in obj[0].description


def test_back_after_objective_safe():
    # Dragon killed at 5:00 (300s) → respawns at 10:00 (600s)
    # Player backs at 6:00 (360s) → 240s before next dragon → not flagged
    frames = [
        make_frame(0, [], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 800}),
        make_frame(300_000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 300_000,
             "monsterType": "DRAGON", "killerId": 6},
        ], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 800}),
        make_frame(360_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 3006, "timestamp": 360_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 800}),
    ]
    moments = _detect_bad_backs(frames, participant_id=PLAYER, role="TOP")
    obj = [m for m in moments if m.moment_type == "bad_back_objective"]
    assert len(obj) == 0


def test_back_safe_when_dragon_killed_off_spawn_time():
    # Dragon killed at 5:10 (310s, not exact spawn time) → respawns at 10:10 (610s)
    # Player backs at 4:40 (280s) → gap to ghost first-spawn (300s) = 20s → must NOT be flagged
    # (dragon already killed; the 300s seed should be evicted)
    frames = [
        make_frame(0, [], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 800}),
        make_frame(280_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 3006, "timestamp": 280_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 800}),
        make_frame(310_000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 310_000,
             "monsterType": "DRAGON", "killerId": 6},
        ], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 800}),
    ]
    moments = _detect_bad_backs(frames, participant_id=PLAYER, role="TOP")
    obj = [m for m in moments if m.moment_type == "bad_back_objective"]
    assert len(obj) == 0


def test_herald_second_spawn_still_flagged_after_first_killed():
    # First Herald killed at 490s, second Herald spawns at 840s
    # Player backs at 760s (80s before 840s) → should be flagged
    frames = [
        make_frame(0, [], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 800}),
        make_frame(490_000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 490_000,
             "monsterType": "RIFT_HERALD", "killerId": 6},
        ], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 800}),
        make_frame(760_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 3006, "timestamp": 760_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 800}),
    ]
    moments = _detect_bad_backs(frames, participant_id=PLAYER, role="TOP")
    obj = [m for m in moments if m.moment_type == "bad_back_objective"]
    assert len(obj) == 1
    assert "Rift Herald" in obj[0].description


def test_dragon_second_kill_no_stale_respawn():
    # Dragon killed at 310s (respawn 610s), then killed again at 630s (respawn 930s)
    # Player backs at 560s — 50s before 610s respawn that will be killed at 630s → must NOT be flagged
    # (_compute_objective_spawn_times has global visibility of all kills, including future ones)
    frames = [
        make_frame(0, [], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 800}),
        make_frame(310_000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 310_000,
             "monsterType": "DRAGON", "killerId": 6},
        ], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 800}),
        make_frame(560_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 3006, "timestamp": 560_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 800}),
        make_frame(630_000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 630_000,
             "monsterType": "DRAGON", "killerId": 6},
        ], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 800}),
    ]
    moments = _detect_bad_backs(frames, participant_id=PLAYER, role="TOP")
    obj = [m for m in moments if m.moment_type == "bad_back_objective"]
    assert len(obj) == 0


def test_baron_second_kill_no_stale_respawn():
    # Baron killed at 1210s (respawn 1570s), then killed again at 1590s (respawn 1950s)
    # Player backs at 1510s — 60s before 1570s respawn that will be killed at 1590s → must NOT be flagged
    frames = [
        make_frame(0, [], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 800}),
        make_frame(1210_000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 1210_000,
             "monsterType": "BARON_NASHOR", "killerId": 6},
        ], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 800}),
        make_frame(1510_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 3006, "timestamp": 1510_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 800}),
        make_frame(1590_000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 1590_000,
             "monsterType": "BARON_NASHOR", "killerId": 6},
        ], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 800}),
    ]
    moments = _detect_bad_backs(frames, participant_id=PLAYER, role="TOP")
    obj = [m for m in moments if m.moment_type == "bad_back_objective"]
    assert len(obj) == 0


def test_low_gold_back_under_300():
    # Back at 3:00 with 250g → waste tier flagged
    frames = [
        make_frame(0, [], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 250}),
        make_frame(180_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 2003, "timestamp": 180_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 50}),
    ]
    moments = _detect_bad_backs(frames, participant_id=PLAYER, role="TOP")
    gold_m = [m for m in moments if m.moment_type == "bad_back_gold"]
    assert len(gold_m) == 1
    assert "not enough" in gold_m[0].description.lower()


def test_low_gold_back_300_to_500():
    # Back at 3:00 with 400g → minor tier flagged
    frames = [
        make_frame(0, [], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 400}),
        make_frame(180_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 1036, "timestamp": 180_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 50}),
    ]
    moments = _detect_bad_backs(frames, participant_id=PLAYER, role="TOP")
    gold_m = [m for m in moments if m.moment_type == "bad_back_gold"]
    assert len(gold_m) == 1
    assert "minor component" in gold_m[0].description.lower()


def test_gold_back_after_20min():
    # Back at 21:00 with 200g → not flagged (late game cutoff)
    frames = [
        make_frame(0, [], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 200}),
        make_frame(1260_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 2003, "timestamp": 1260_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 50}),
    ]
    moments = _detect_bad_backs(frames, participant_id=PLAYER, role="TOP")
    gold_m = [m for m in moments if m.moment_type == "bad_back_gold"]
    assert len(gold_m) == 0


def test_high_gold_not_flagged():
    # Back at 3:00 with 1000g → not flagged for gold
    frames = [
        make_frame(0, [], positions={PLAYER: (3000, 12000)}, current_gold={PLAYER: 1000}),
        make_frame(180_000, [
            {"type": "ITEM_PURCHASED", "participantId": PLAYER,
             "itemId": 3006, "timestamp": 180_000},
        ], positions={PLAYER: (523, 523)}, current_gold={PLAYER: 150}),
    ]
    moments = _detect_bad_backs(frames, participant_id=PLAYER, role="TOP")
    gold_m = [m for m in moments if m.moment_type == "bad_back_gold"]
    assert len(gold_m) == 0
