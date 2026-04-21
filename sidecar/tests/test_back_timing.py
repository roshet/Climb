from laner_analyzer import _collect_backs


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
