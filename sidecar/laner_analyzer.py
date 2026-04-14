import math
from timeline_analyzer import (
    PivotalMomentData,
    TEAM_100_IDS, TEAM_200_IDS, GOLD_VALUES,
    BLUE_TURRETS, RED_TURRETS, TOWER_DIVE_RADIUS,
    score_objective_missed, score_objective_secured,
)

# --- Timing ---
LANING_PHASE_END_SECS = 840   # 14:00
POST_LANING_SECS = 1200       # 20:00

# --- Lane position thresholds ---
TOP_LANE_X_MAX = 4500
BOT_LANE_Y_MAX = 4500

# --- Plate tracking ---
PLATE_FLAG_THRESHOLD = 3
PLATE_GOLD = 160

# --- Support vision ---
SUPPORT_WARD_MINIMUM = 4
SUPPORT_VISION_WINDOW_MS = 1_200_000
WARD_KILL_CAP = 3


# --- Position helpers ---

def _in_top_lane(position: dict) -> bool:
    return position.get("x", 0) < TOP_LANE_X_MAX


def _in_bot_lane(position: dict) -> bool:
    return position.get("y", 0) < BOT_LANE_Y_MAX


def _in_mid_lane(position: dict) -> bool:
    px, py = position.get("x", 0), position.get("y", 0)
    return abs(px - py) < 2500 and 3000 < px < 12000


def _in_any_side_lane(position: dict) -> bool:
    return _in_top_lane(position) or _in_bot_lane(position)


def _in_player_lane(position: dict, role: str, participant_id: int) -> bool:
    is_blue_side = participant_id in TEAM_100_IDS
    if role == "TOP":
        px = position.get("x", 0)
        return px < TOP_LANE_X_MAX if is_blue_side else px > 10000
    if role == "MIDDLE":
        return _in_mid_lane(position)
    if role in ("BOTTOM", "UTILITY"):
        py = position.get("y", 0)
        return py < BOT_LANE_Y_MAX if is_blue_side else py > 10000
    return False


def _near_friendly_turret(position: dict, participant_id: int) -> bool:
    px, py = position.get("x", 0), position.get("y", 0)
    turrets = BLUE_TURRETS if participant_id in TEAM_100_IDS else RED_TURRETS
    return any(
        math.sqrt((px - tx) ** 2 + (py - ty) ** 2) < TOWER_DIVE_RADIUS
        for tx, ty in turrets
    )


# --- Shared signal detectors ---

def _detect_lane_death(
    event: dict,
    participant_id: int,
    enemy_jungler_id: int | None,
    role: str,
) -> PivotalMomentData | None:
    if event.get("victimId") != participant_id:
        return None
    ts = event["timestamp"] // 1000
    if ts >= LANING_PHASE_END_SECS:
        return None
    position = event.get("position", {"x": 0, "y": 0})
    if not _in_player_lane(position, role, participant_id):
        return None

    killer_id = event.get("killerId", 0)
    assisters = event.get("assistingParticipantIds", [])
    total_enemies = len(set([killer_id] + list(assisters)) - {0})
    mins, secs = divmod(ts, 60)
    time_str = f"{mins}:{secs:02d}"

    if total_enemies >= 3 and _near_friendly_turret(position, participant_id):
        return PivotalMomentData(
            timestamp_secs=ts,
            moment_type="lane_death",
            description=f"You were dove at {time_str} ({total_enemies} enemies collapsed under your tower).",
            counterfactual="",
            gold_impact=GOLD_VALUES["DEATH"],
        )

    if enemy_jungler_id and (killer_id == enemy_jungler_id or enemy_jungler_id in assisters):
        return PivotalMomentData(
            timestamp_secs=ts,
            moment_type="lane_death",
            description=f"You were ganked at {time_str}.",
            counterfactual="",
            gold_impact=GOLD_VALUES["DEATH"],
        )

    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="lane_death",
        description=f"You lost a 1v1 trade at {time_str}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _detect_solo_kill_in_lane(
    event: dict,
    participant_id: int,
    lane_opponent_id: int | None,
    role: str,
) -> PivotalMomentData | None:
    if event.get("killerId") != participant_id:
        return None
    if event.get("assistingParticipantIds"):
        return None
    if lane_opponent_id is None or event.get("victimId") != lane_opponent_id:
        return None
    position = event.get("position", {"x": 0, "y": 0})
    if not _in_player_lane(position, role, participant_id):
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="solo_kill",
        description=f"You got a solo kill on your lane opponent at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _score_tower_lost(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("type") != "BUILDING_KILL":
        return None
    player_team_id = 100 if participant_id in TEAM_100_IDS else 200
    if event.get("teamId") != player_team_id:
        return None
    tower_type = event.get("towerType", "OUTER_TURRET")
    gold = GOLD_VALUES.get(f"TOWER_{tower_type.replace('_TURRET', '')}", 150)
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    lane = event.get("laneType", "").replace("_LANE", "").title()
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="tower_lost",
        description=f"Enemy took your {lane} {tower_type.replace('_', ' ').lower()} at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=gold,
    )


def _cs_differential_at_14(
    frames: list,
    participant_id: int,
    lane_opponent_id: int,
) -> PivotalMomentData | None:
    snapshot = next(
        (f for f in frames if f["timestamp"] >= 840_000),
        None,
    )
    if snapshot is None:
        return None
    pf = snapshot.get("participantFrames", {})
    player_cs = pf.get(str(participant_id), {}).get("minionsKilled", 0)
    opponent_cs = pf.get(str(lane_opponent_id), {}).get("minionsKilled", 0)
    diff = opponent_cs - player_cs
    if diff < 15:
        return None
    return PivotalMomentData(
        timestamp_secs=840,
        moment_type="cs_differential",
        description=f"You were {diff} CS behind your lane opponent at 14:00.",
        counterfactual="",
        gold_impact=diff * 21,
    )


def _gold_differential_at_14(
    frames: list,
    participant_id: int,
    lane_opponent_id: int,
) -> PivotalMomentData | None:
    snapshot = next(
        (f for f in frames if f["timestamp"] >= 840_000),
        None,
    )
    if snapshot is None:
        return None
    pf = snapshot.get("participantFrames", {})
    player_gold = pf.get(str(participant_id), {}).get("totalGold", 0)
    opponent_gold = pf.get(str(lane_opponent_id), {}).get("totalGold", 0)
    diff = opponent_gold - player_gold
    if diff < 1000:
        return None
    return PivotalMomentData(
        timestamp_secs=840,
        moment_type="gold_differential",
        description=f"You were {diff}g behind your lane opponent at 14:00.",
        counterfactual="",
        gold_impact=diff,
    )


# --- Entry point ---

def analyze_laner(
    timeline: dict,
    participant_id: int,
    lane_opponent_id: int | None,
    role: str,
    enemy_jungler_id: int | None = None,
) -> list[PivotalMomentData]:
    moments: list[PivotalMomentData] = []
    frames = timeline.get("info", {}).get("frames", [])

    for frame in frames:
        for event in frame.get("events", []):
            event_type = event.get("type")
            moment = None

            if event_type == "CHAMPION_KILL":
                moment = (
                    _detect_lane_death(event, participant_id, enemy_jungler_id, role)
                    or _detect_solo_kill_in_lane(event, participant_id, lane_opponent_id, role)
                )
            elif event_type == "ELITE_MONSTER_KILL":
                moment = (
                    score_objective_missed(event, participant_id)
                    or score_objective_secured(event, participant_id)
                )
            elif event_type == "BUILDING_KILL":
                moment = _score_tower_lost(event, participant_id)

            if moment:
                moments.append(moment)

    # Frame-based signals: CS and gold differential
    if lane_opponent_id is not None:
        if role in ("TOP", "MIDDLE", "BOTTOM"):
            cs_moment = _cs_differential_at_14(frames, participant_id, lane_opponent_id)
            if cs_moment:
                moments.append(cs_moment)
        gold_moment = _gold_differential_at_14(frames, participant_id, lane_opponent_id)
        if gold_moment:
            moments.append(gold_moment)

    moments.sort(key=lambda m: m.timestamp_secs)
    return moments
