"""Tests for sidecar/timeline_metrics.py — pure per-minute stat extraction."""

from timeline_metrics import cs_at_minute, gold_at_minute, extract_timeline_metrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_pf(minions: int = 0, jungle: int = 0, gold: int = 0) -> dict:
    return {"minionsKilled": minions, "jungleMinionsKilled": jungle, "totalGold": gold}


def make_frame(timestamp_ms: int, participant_data: dict[int, dict]) -> dict:
    pf = {str(pid): data for pid, data in participant_data.items()}
    return {"timestamp": timestamp_ms, "participantFrames": pf}


def make_timeline(frames: list) -> dict:
    return {"info": {"frames": frames}}


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

PLAYER_ID = 1

# Three frames: 0 ms, 10 min, 14 min — each with distinct values so we can
# assert the correct frame is selected.
FULL_TIMELINE = make_timeline([
    make_frame(0,       {PLAYER_ID: make_pf(minions=10,  jungle=2, gold=500)}),
    make_frame(600_000, {PLAYER_ID: make_pf(minions=120, jungle=5, gold=4500)}),
    make_frame(840_000, {PLAYER_ID: make_pf(minions=180, jungle=8, gold=6000)}),
])

# Game that ends before the 10-minute mark
SHORT_TIMELINE = make_timeline([
    make_frame(0,       {PLAYER_ID: make_pf(minions=10, jungle=2, gold=500)}),
    make_frame(500_000, {PLAYER_ID: make_pf(minions=80, jungle=5, gold=3500)}),
])


# ---------------------------------------------------------------------------
# cs_at_minute — value selection
# ---------------------------------------------------------------------------

def test_cs_at_minute_10_selects_correct_frame():
    """First frame at/after 10 min (600 000 ms) is used, not the earlier 0 ms frame."""
    assert cs_at_minute(FULL_TIMELINE, PLAYER_ID, 10) == 120 + 5  # minions + jungle


def test_cs_at_minute_14_selects_correct_frame():
    """14-min frame is used, not the 10-min frame."""
    assert cs_at_minute(FULL_TIMELINE, PLAYER_ID, 14) == 180 + 8


def test_cs_includes_jungle_minions():
    """CS = minionsKilled + jungleMinionsKilled (jungle camps count)."""
    t = make_timeline([
        make_frame(600_000, {1: make_pf(minions=80, jungle=12, gold=4000)}),
    ])
    assert cs_at_minute(t, 1, 10) == 92


# ---------------------------------------------------------------------------
# cs_at_minute — None cases
# ---------------------------------------------------------------------------

def test_cs_none_when_game_shorter_than_target():
    assert cs_at_minute(SHORT_TIMELINE, PLAYER_ID, 10) is None


def test_cs_none_empty_dict():
    assert cs_at_minute({}, PLAYER_ID, 10) is None


def test_cs_none_missing_info_key():
    # dict has "frames" at the top level but no "info" wrapper
    assert cs_at_minute({"frames": []}, PLAYER_ID, 10) is None


def test_cs_none_missing_frames_key():
    assert cs_at_minute({"info": {}}, PLAYER_ID, 10) is None


def test_cs_none_empty_frames_list():
    assert cs_at_minute({"info": {"frames": []}}, PLAYER_ID, 10) is None


def test_cs_none_participant_absent_from_frame():
    """Frame exists at the target minute but the participant key is missing."""
    t = make_timeline([
        make_frame(600_000, {2: make_pf(minions=100, jungle=5, gold=4000)}),
    ])
    assert cs_at_minute(t, 1, 10) is None  # participant 1 absent


# ---------------------------------------------------------------------------
# Malformed timeline must return None, never raise
# ---------------------------------------------------------------------------

def test_cs_none_when_participant_frames_not_a_dict():
    """participantFrames present but a non-dict (list) → None, no AttributeError."""
    t = make_timeline([
        {"timestamp": 600_000, "participantFrames": []},
    ])
    assert cs_at_minute(t, 1, 10) is None


def test_gold_none_when_participant_frames_not_a_dict():
    t = make_timeline([
        {"timestamp": 600_000, "participantFrames": "not-a-dict"},
    ])
    assert gold_at_minute(t, 1, 10) is None


def test_cs_none_when_frame_element_not_a_dict():
    """A non-dict element inside the frames list must not raise."""
    t = make_timeline(["not-a-frame", 42])
    assert cs_at_minute(t, 1, 10) is None
    assert gold_at_minute(t, 1, 10) is None


def test_cs_none_when_info_not_a_dict():
    assert cs_at_minute({"info": "nope"}, 1, 10) is None
    assert gold_at_minute({"info": ["nope"]}, 1, 10) is None


def test_cs_none_when_frames_not_a_list():
    assert cs_at_minute({"info": {"frames": "nope"}}, 1, 10) is None


def test_extract_metrics_malformed_participant_frames_all_none():
    t = make_timeline([
        {"timestamp": 600_000, "participantFrames": []},
        {"timestamp": 840_000, "participantFrames": []},
    ])
    assert extract_timeline_metrics(t, 1) == {
        "cs_at_10": None, "gold_at_10": None, "gold_at_14": None,
    }


# ---------------------------------------------------------------------------
# cs_at_minute — string-key access
# ---------------------------------------------------------------------------

def test_cs_string_key_access_with_int_participant_id():
    """participantFrames uses string keys ("1"); participant_id is passed as int."""
    t = make_timeline([
        make_frame(600_000, {1: make_pf(minions=100, jungle=5, gold=4000)}),
    ])
    # The frame dict will have key "1" (str). Passing int 1 must still work.
    assert cs_at_minute(t, 1, 10) == 105


# ---------------------------------------------------------------------------
# gold_at_minute — value selection
# ---------------------------------------------------------------------------

def test_gold_at_minute_10():
    assert gold_at_minute(FULL_TIMELINE, PLAYER_ID, 10) == 4500


def test_gold_at_minute_14():
    assert gold_at_minute(FULL_TIMELINE, PLAYER_ID, 14) == 6000


# ---------------------------------------------------------------------------
# gold_at_minute — None cases
# ---------------------------------------------------------------------------

def test_gold_none_when_game_shorter_than_target():
    assert gold_at_minute(SHORT_TIMELINE, PLAYER_ID, 10) is None


def test_gold_none_empty_dict():
    assert gold_at_minute({}, PLAYER_ID, 10) is None


def test_gold_none_missing_info_key():
    assert gold_at_minute({"frames": []}, PLAYER_ID, 10) is None


def test_gold_none_missing_frames_key():
    assert gold_at_minute({"info": {}}, PLAYER_ID, 10) is None


def test_gold_none_empty_frames_list():
    assert gold_at_minute({"info": {"frames": []}}, PLAYER_ID, 10) is None


def test_gold_none_participant_absent_from_frame():
    t = make_timeline([
        make_frame(600_000, {2: make_pf(gold=5000)}),
    ])
    assert gold_at_minute(t, 1, 10) is None


# ---------------------------------------------------------------------------
# extract_timeline_metrics
# ---------------------------------------------------------------------------

def test_extract_metrics_all_present():
    result = extract_timeline_metrics(FULL_TIMELINE, PLAYER_ID)
    assert result == {
        "cs_at_10":   120 + 5,  # 125
        "gold_at_10": 4500,
        "gold_at_14": 6000,
    }


def test_extract_metrics_short_game_all_none():
    """All three metrics are None when the game ends before 10 minutes."""
    result = extract_timeline_metrics(SHORT_TIMELINE, PLAYER_ID)
    assert result == {
        "cs_at_10":   None,
        "gold_at_10": None,
        "gold_at_14": None,
    }


def test_extract_metrics_reaches_10_not_14():
    """Game that has a 10-min frame but no 14-min frame."""
    t = make_timeline([
        make_frame(600_000, {1: make_pf(minions=120, jungle=5, gold=4500)}),
        make_frame(700_000, {1: make_pf(minions=145, jungle=6, gold=5000)}),
    ])
    result = extract_timeline_metrics(t, 1)
    assert result["cs_at_10"]   == 125
    assert result["gold_at_10"] == 4500
    assert result["gold_at_14"] is None


def test_extract_metrics_empty_timeline():
    result = extract_timeline_metrics({}, 1)
    assert result == {"cs_at_10": None, "gold_at_10": None, "gold_at_14": None}


def test_extract_metrics_returns_exactly_three_keys():
    result = extract_timeline_metrics(FULL_TIMELINE, PLAYER_ID)
    assert set(result.keys()) == {"cs_at_10", "gold_at_10", "gold_at_14"}
