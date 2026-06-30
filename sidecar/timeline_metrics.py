"""
timeline_metrics.py — pure functions for extracting per-minute stats from a
stored Riot match timeline (shape: timeline["info"]["frames"]).

No I/O, no DB, no external dependencies.
"""

from __future__ import annotations


def _participant_frame_at_minute(
    timeline: dict,
    participant_id: int,
    minute: int,
) -> dict | None:
    """Return the participantFrame dict for the FIRST frame at or after *minute* minutes.

    Returns None for any falsy, malformed, or truncated input.
    """
    if not timeline:
        return None

    try:
        frames = timeline["info"]["frames"]
    except (KeyError, TypeError):
        return None

    if not frames:
        return None

    target_ms = minute * 60_000
    snapshot = next(
        (f for f in frames if f.get("timestamp", -1) >= target_ms),
        None,
    )
    if snapshot is None:
        return None

    pf = snapshot.get("participantFrames", {})
    return pf.get(str(participant_id))


def cs_at_minute(timeline: dict, participant_id: int, minute: int) -> int | None:
    """Return total CS (lane minions + jungle camps) at *minute* minutes, or None.

    None is returned when:
    - timeline is falsy or missing info/frames
    - no frame reaches the target minute (game ended early)
    - the participant key is absent from the chosen frame
    """
    pf = _participant_frame_at_minute(timeline, participant_id, minute)
    if pf is None:
        return None
    try:
        return pf.get("minionsKilled", 0) + pf.get("jungleMinionsKilled", 0)
    except TypeError:
        return None


def gold_at_minute(timeline: dict, participant_id: int, minute: int) -> int | None:
    """Return totalGold at *minute* minutes, or None.

    Same None conditions as cs_at_minute.
    """
    pf = _participant_frame_at_minute(timeline, participant_id, minute)
    if pf is None:
        return None
    try:
        return pf.get("totalGold")
    except TypeError:
        return None


def extract_timeline_metrics(
    timeline: dict,
    participant_id: int,
) -> dict[str, int | None]:
    """Return the three standard early-game metrics for a participant.

    Keys: "cs_at_10", "gold_at_10", "gold_at_14".
    Any metric that cannot be read (e.g. short game) is None.
    """
    return {
        "cs_at_10":   cs_at_minute(timeline,  participant_id, 10),
        "gold_at_10": gold_at_minute(timeline, participant_id, 10),
        "gold_at_14": gold_at_minute(timeline, participant_id, 14),
    }
