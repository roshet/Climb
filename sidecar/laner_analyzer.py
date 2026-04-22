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

# --- Back timing ---
FOUNTAIN_BLUE = (523, 523)
FOUNTAIN_RED = (14340, 14390)
FOUNTAIN_RADIUS = 1500
OBJECTIVE_DANGER_WINDOW_SECS = 90
GOLD_COMPONENT_BASELINE = 900
BACK_DEDUP_WINDOW_SECS = 60
GOLD_WASTE_THRESHOLD = 300
GOLD_MINOR_THRESHOLD = 500
RESPAWN_BASE_SECS = 8
RESPAWN_PER_LEVEL_SECS = 2.5
RESPAWN_CAP_SECS = 60
DRAGON_FIRST_SPAWN = 300
DRAGON_RESPAWN_DELAY = 300
BARON_FIRST_SPAWN = 1200
BARON_RESPAWN_DELAY = 360
HERALD_FIRST_SPAWN = 480
HERALD_SECOND_SPAWN = 840
OBJECTIVE_GOLD: dict[str, int] = {"Dragon": 350, "Baron": 900, "Rift Herald": 400}


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


def _detect_split_push_death(
    event: dict,
    participant_id: int,
) -> PivotalMomentData | None:
    if event.get("victimId") != participant_id:
        return None
    ts = event["timestamp"] // 1000
    if ts < POST_LANING_SECS:
        return None
    position = event.get("position", {"x": 0, "y": 0})
    if not _in_any_side_lane(position):
        return None
    killer_id = event.get("killerId", 0)
    assisters = event.get("assistingParticipantIds", [])
    total_enemies = len(set([killer_id] + list(assisters)) - {0})
    if total_enemies < 3:
        return None
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="split_push_death",
        description=f"You were collapsed on by {total_enemies} enemies while split pushing at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _detect_roam_kill(
    event: dict,
    participant_id: int,
) -> PivotalMomentData | None:
    killer_id = event.get("killerId", 0)
    assisters = event.get("assistingParticipantIds", [])
    if killer_id != participant_id and participant_id not in assisters:
        return None
    victim_id = event.get("victimId", 0)
    if victim_id == participant_id or victim_id == 0:
        return None
    ts = event["timestamp"] // 1000
    if ts >= LANING_PHASE_END_SECS:
        return None
    position = event.get("position", {"x": 0, "y": 0})
    if not _in_any_side_lane(position):
        return None
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="roam_kill",
        description=f"Your roam resulted in a kill at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _detect_ward_kill(
    event: dict,
    participant_id: int,
    ward_kill_count: int,
) -> PivotalMomentData | None:
    if event.get("killerId") != participant_id:
        return None
    if ward_kill_count >= WARD_KILL_CAP:
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="ward_kill",
        description=f"You destroyed an enemy ward at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=0,
    )


def _detect_roam_assist(
    event: dict,
    participant_id: int,
) -> PivotalMomentData | None:
    killer_id = event.get("killerId", 0)
    assisters = event.get("assistingParticipantIds", [])
    if killer_id != participant_id and participant_id not in assisters:
        return None
    victim_id = event.get("victimId", 0)
    if victim_id == participant_id or victim_id == 0:
        return None
    ts = event["timestamp"] // 1000
    if ts >= LANING_PHASE_END_SECS:
        return None
    position = event.get("position", {"x": 0, "y": 0})
    if not (_in_top_lane(position) or _in_mid_lane(position)):
        return None
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="roam_assist",
        description=f"Your roam contributed to a kill at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _check_low_vision(
    frames: list,
    participant_id: int,
) -> PivotalMomentData | None:
    ward_count = 0
    for frame in frames:
        if frame["timestamp"] > SUPPORT_VISION_WINDOW_MS:
            break
        for event in frame.get("events", []):
            if (event.get("type") == "WARD_PLACED"
                    and event.get("creatorId") == participant_id):
                ward_count += 1
    if ward_count >= SUPPORT_WARD_MINIMUM:
        return None
    return PivotalMomentData(
        timestamp_secs=SUPPORT_VISION_WINDOW_MS // 1000,
        moment_type="low_vision",
        description=f"You placed only {ward_count} wards in the first 20 minutes (minimum: {SUPPORT_WARD_MINIMUM}).",
        counterfactual="",
        gold_impact=0,
    )


def _in_fountain(position: dict, participant_id: int) -> bool:
    fx, fy = FOUNTAIN_BLUE if participant_id in TEAM_100_IDS else FOUNTAIN_RED
    px, py = position.get("x", 0), position.get("y", 0)
    return math.sqrt((px - fx) ** 2 + (py - fy) ** 2) < FOUNTAIN_RADIUS


def _dedup_backs(backs: list[dict]) -> list[dict]:
    """Keep only the first back in any run where each back is within BACK_DEDUP_WINDOW_SECS of the previous kept back."""
    result: list[dict] = []
    for b in sorted(backs, key=lambda x: x["timestamp_secs"]):
        if not result or b["timestamp_secs"] - result[-1]["timestamp_secs"] > BACK_DEDUP_WINDOW_SECS:
            result.append(b)
    return result


def _collect_backs(frames: list, participant_id: int) -> list[dict]:
    """Return list of {timestamp_secs, gold} for each detected voluntary recall."""
    # Collect death windows for exclusion
    death_windows: list[tuple[float, float]] = []
    for frame in frames:
        pf = frame.get("participantFrames", {}).get(str(participant_id), {})
        level = pf.get("level", 1)
        for event in frame.get("events", []):
            if (event.get("type") == "CHAMPION_KILL"
                    and event.get("victimId") == participant_id):
                ts = event["timestamp"] / 1000
                respawn = min(
                    RESPAWN_BASE_SECS + (level - 1) * RESPAWN_PER_LEVEL_SECS,
                    RESPAWN_CAP_SECS,
                )
                death_windows.append((ts, ts + respawn))

    def _is_respawn(ts: float) -> bool:
        return any(start <= ts <= end for start, end in death_windows)

    # Collect item purchase backs and position backs
    purchase_backs: list[dict] = []
    position_backs: list[dict] = []
    prev_pf: dict | None = None

    for frame in frames:
        curr_pf = frame.get("participantFrames", {}).get(str(participant_id), {})

        for event in frame.get("events", []):
            if (event.get("type") == "ITEM_PURCHASED"
                    and event.get("participantId") == participant_id):
                ts = event["timestamp"] / 1000
                if not _is_respawn(ts):
                    gold = (prev_pf or {}).get("currentGold", 0)
                    purchase_backs.append({"timestamp_secs": ts, "gold": gold})

        if prev_pf is not None:
            prev_pos = prev_pf.get("position", {"x": 0, "y": 0})
            curr_pos = curr_pf.get("position", {"x": 0, "y": 0})
            frame_ts = frame["timestamp"] / 1000
            if (not _in_fountain(prev_pos, participant_id)
                    and _in_fountain(curr_pos, participant_id)
                    and not _is_respawn(frame_ts)):
                gold = prev_pf.get("currentGold", 0)
                position_backs.append({"timestamp_secs": frame_ts, "gold": gold})

        prev_pf = curr_pf

    # Dedup within purchase_backs (multiple items in one fountain visit)
    purchase_backs = _dedup_backs(purchase_backs)
    # Dedup within position_backs (multiple frames in fountain in consecutive frames)
    position_backs = _dedup_backs(position_backs)

    # Merge: keep purchase backs, add position backs not covered by a purchase back
    all_backs = list(purchase_backs)
    for pb in position_backs:
        if not any(
            abs(pb["timestamp_secs"] - ex["timestamp_secs"]) <= BACK_DEDUP_WINDOW_SECS
            for ex in purchase_backs
        ):
            all_backs.append(pb)

    all_backs.sort(key=lambda b: b["timestamp_secs"])
    return all_backs


def _compute_objective_spawn_times(frames: list) -> list[tuple[int, str]]:
    """Return sorted list of (spawn_timestamp_secs, objective_name) for the whole game."""
    spawns: set[tuple[int, str]] = {
        (DRAGON_FIRST_SPAWN, "Dragon"),
        (BARON_FIRST_SPAWN, "Baron"),
        (HERALD_FIRST_SPAWN, "Rift Herald"),
        (HERALD_SECOND_SPAWN, "Rift Herald"),
    }
    for frame in frames:
        for event in frame.get("events", []):
            if event.get("type") != "ELITE_MONSTER_KILL":
                continue
            monster = event.get("monsterType", "")
            ts = event["timestamp"] // 1000
            if monster == "DRAGON":
                spawns = {s for s in spawns if s[1] != "Dragon"}
                spawns.add((ts + DRAGON_RESPAWN_DELAY, "Dragon"))
            elif monster == "BARON_NASHOR":
                spawns = {s for s in spawns if s[1] != "Baron"}
                spawns.add((ts + BARON_RESPAWN_DELAY, "Baron"))
            elif monster == "RIFT_HERALD":
                # Discard only the spawn that just occurred; the later one may still be pending
                for herald_seed in (HERALD_FIRST_SPAWN, HERALD_SECOND_SPAWN):
                    if herald_seed <= ts:
                        spawns.discard((herald_seed, "Rift Herald"))
    return sorted(spawns)


def _detect_bad_backs(
    frames: list,
    participant_id: int,
    role: str,  # reserved for future role-specific thresholds
) -> list[PivotalMomentData]:
    moments: list[PivotalMomentData] = []
    backs = _collect_backs(frames, participant_id)
    spawn_times = _compute_objective_spawn_times(frames)

    for back in backs:
        ts = back["timestamp_secs"]
        gold = back["gold"]

        if ts < 60:  # ignore game-start starter item purchases
            continue

        # Signal 1: back within objective spawn window
        for spawn_secs, obj_name in spawn_times:
            gap = spawn_secs - ts
            if 0 < gap <= OBJECTIVE_DANGER_WINDOW_SECS:
                spawn_mins, spawn_secs_rem = divmod(spawn_secs, 60)
                moments.append(PivotalMomentData(
                    timestamp_secs=int(ts),
                    moment_type="bad_back_objective",
                    description=(
                        f"You recalled {int(gap)}s before {obj_name} was due to spawn "
                        f"at {spawn_mins}:{spawn_secs_rem:02d}."
                    ),
                    counterfactual=(
                        "If you were healthy when you recalled, staying to contest "
                        "or waiting until after the spawn would have kept your team "
                        "at full strength for the objective."
                    ),
                    gold_impact=OBJECTIVE_GOLD.get(obj_name, 350),
                ))
                break  # one flag per back

        # Signal 2: low gold back (3:00–20:00 only; before 3:00 frame gold is unreliable)
        if 180 <= ts < POST_LANING_SECS:
            mins, secs_rem = divmod(int(ts), 60)
            if gold < GOLD_WASTE_THRESHOLD:
                moments.append(PivotalMomentData(
                    timestamp_secs=int(ts),
                    moment_type="bad_back_gold",
                    description=(
                        f"You recalled with only {gold}g at {mins}:{secs_rem:02d} "
                        f"— not enough to buy any component."
                    ),
                    counterfactual=(
                        "If you were healthy when you recalled, staying in lane to "
                        "accumulate gold for a meaningful purchase would have been "
                        "more efficient."
                    ),
                    gold_impact=GOLD_COMPONENT_BASELINE - gold,
                ))
            elif gold < GOLD_MINOR_THRESHOLD:
                moments.append(PivotalMomentData(
                    timestamp_secs=int(ts),
                    moment_type="bad_back_gold",
                    description=(
                        f"You recalled with only {gold}g at {mins}:{secs_rem:02d} "
                        f"— enough for only a minor component."
                    ),
                    counterfactual=(
                        "If you were healthy when you recalled, staying in lane a "
                        "bit longer to reach a more meaningful purchase threshold "
                        "would have been more efficient."
                    ),
                    # gold_impact targets the same 900g ceiling for both tiers —
                    # how far short of a meaningful first component they were.
                    gold_impact=GOLD_COMPONENT_BASELINE - gold,
                ))

    return moments


def _detect_enemy_roam_kill(
    event: dict,
    participant_id: int,
    lane_opponent_id: int,
) -> PivotalMomentData | None:
    killer_id = event.get("killerId", 0)
    assisters = event.get("assistingParticipantIds", [])
    if killer_id != lane_opponent_id and lane_opponent_id not in assisters:
        return None
    if event.get("victimId") == participant_id:
        return None
    ts = event["timestamp"] // 1000
    if ts >= LANING_PHASE_END_SECS:
        return None
    position = event.get("position", {"x": 0, "y": 0})
    if not _in_any_side_lane(position):
        return None
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="enemy_roam_kill",
        description=f"Enemy mid roamed for a kill at {mins}:{secs:02d} while you were in lane.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
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

    plate_count = 0
    plates_flagged = False
    player_team_id = 100 if participant_id in TEAM_100_IDS else 200
    role_to_lane = {"TOP": "TOP_LANE", "MIDDLE": "MID_LANE", "BOTTOM": "BOT_LANE"}
    ward_kill_count = 0

    for frame in frames:
        for event in frame.get("events", []):
            event_type = event.get("type")
            moment = None

            if event_type == "CHAMPION_KILL":
                moment = (
                    _detect_lane_death(event, participant_id, enemy_jungler_id, role)
                    or _detect_solo_kill_in_lane(event, participant_id, lane_opponent_id, role)
                )
                if moment is None and role == "TOP":
                    moment = _detect_split_push_death(event, participant_id)
                if moment is None and role == "MIDDLE":
                    moment = _detect_roam_kill(event, participant_id)
                    if moment is None and lane_opponent_id is not None:
                        moment = _detect_enemy_roam_kill(event, participant_id, lane_opponent_id)
                if moment is None and role == "UTILITY":
                    moment = _detect_roam_assist(event, participant_id)
            elif event_type == "ELITE_MONSTER_KILL":
                moment = (
                    score_objective_missed(event, participant_id)
                    or score_objective_secured(event, participant_id)
                )
            elif event_type == "BUILDING_KILL":
                moment = _score_tower_lost(event, participant_id)
            elif event_type == "WARD_KILL" and role == "UTILITY":
                wk = _detect_ward_kill(event, participant_id, ward_kill_count)
                if wk:
                    ward_kill_count += 1
                    moment = wk
            elif event_type == "TURRET_PLATE_DESTROYED" and not plates_flagged and role in role_to_lane:
                if (event.get("teamId") == player_team_id
                        and event.get("laneType") == role_to_lane[role]):
                    plate_count += 1
                    if plate_count == PLATE_FLAG_THRESHOLD:
                        plates_flagged = True
                        ts = event["timestamp"] // 1000
                        mins, secs = divmod(ts, 60)
                        total_gold = PLATE_FLAG_THRESHOLD * PLATE_GOLD
                        moment = PivotalMomentData(
                            timestamp_secs=ts,
                            moment_type="turret_plates_lost",
                            description=f"Enemy took {PLATE_FLAG_THRESHOLD} tower plates in your lane by {mins}:{secs:02d} ({total_gold}g given up).",
                            counterfactual="",
                            gold_impact=total_gold,
                        )

            if moment:
                moments.append(moment)

    # Support: low vision check
    if role == "UTILITY":
        vision_moment = _check_low_vision(frames, participant_id)
        if vision_moment:
            moments.append(vision_moment)

    # Frame-based signals: CS and gold differential
    if lane_opponent_id is not None:
        if role in ("TOP", "MIDDLE", "BOTTOM"):
            cs_moment = _cs_differential_at_14(frames, participant_id, lane_opponent_id)
            if cs_moment:
                moments.append(cs_moment)
        gold_moment = _gold_differential_at_14(frames, participant_id, lane_opponent_id)
        if gold_moment:
            moments.append(gold_moment)

    # Back timing analysis (all laner roles)
    back_moments = _detect_bad_backs(frames, participant_id, role)
    moments.extend(back_moments)

    moments.sort(key=lambda m: m.timestamp_secs)
    return moments
