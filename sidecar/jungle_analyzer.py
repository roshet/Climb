import math
from timeline_analyzer import PivotalMomentData, TEAM_100_IDS, TEAM_200_IDS, GOLD_VALUES

# --- Map position constants ---

# Enemy jungle quadrant boundaries
BLUE_JUNGLE_X_MAX = 7000   # blue side jungle (top-left): x < 7000
BLUE_JUNGLE_Y_MIN = 7500   # blue side jungle (top-left): y > 7500

RED_JUNGLE_X_MIN = 8000    # red side jungle (bottom-right): x > 8000
RED_JUNGLE_Y_MAX = 7500    # red side jungle (bottom-right): y < 7500

# Lane position boundaries (approximate)
TOP_LANE_X_MAX = 4000      # top lane hugs left edge of map
BOT_LANE_Y_MAX = 4000      # bot lane hugs bottom edge of map

# Timing
ALIVE_WINDOW_SECS = 30     # jungler must not have died within 30s to be "alive"
VOID_GRUBS_TOTAL = 3       # Season 2025: 3 total void grubs per game


def _is_blue_side(participant_id: int) -> bool:
    return participant_id in TEAM_100_IDS


def _in_enemy_jungle(position: dict, participant_id: int) -> bool:
    """True if position is inside the enemy team's jungle quadrant."""
    px, py = position.get("x", 0), position.get("y", 0)
    if _is_blue_side(participant_id):
        # Enemy = red side = bottom-right quadrant
        return px >= RED_JUNGLE_X_MIN and py <= RED_JUNGLE_Y_MAX
    else:
        # Enemy = blue side = top-left quadrant
        return px <= BLUE_JUNGLE_X_MAX and py >= BLUE_JUNGLE_Y_MIN


def _in_ally_lane(position: dict, participant_id: int) -> bool:
    """True if position is in a lane (not jungle interior)."""
    px, py = position.get("x", 0), position.get("y", 0)
    return (
        px < TOP_LANE_X_MAX          # near top lane (left edge)
        or py < BOT_LANE_Y_MAX       # near bot lane (bottom edge)
        or (abs(px - py) < 3000 and px > 5000 and py > 5000)  # near mid lane diagonal (away from blue base)
    )


def _in_own_jungle(position: dict, participant_id: int) -> bool:
    """True if position is inside the player's own jungle quadrant."""
    px, py = position.get("x", 0), position.get("y", 0)
    if _is_blue_side(participant_id):
        return px <= BLUE_JUNGLE_X_MAX and py >= BLUE_JUNGLE_Y_MIN
    else:
        return px >= RED_JUNGLE_X_MIN and py <= RED_JUNGLE_Y_MAX


def _jungler_position_at(frames: list, timestamp_ms: int, participant_id: int) -> dict | None:
    """Get jungler's position from the most recent frame at or before timestamp_ms."""
    best_frame = None
    for frame in frames:
        if frame["timestamp"] <= timestamp_ms:
            best_frame = frame
        else:
            break
    if best_frame is None:
        return None
    pf = best_frame.get("participantFrames", {})
    return pf.get(str(participant_id), {}).get("position")


def analyze_jungle(
    timeline: dict,
    participant_id: int,
    enemy_jungler_id: int | None = None,
) -> list[PivotalMomentData]:
    """Main entry point — detect all jungle-specific moments from a timeline."""
    moments: list[PivotalMomentData] = []
    frames = timeline.get("info", {}).get("frames", [])
    enemy_team = TEAM_200_IDS if participant_id in TEAM_100_IDS else TEAM_100_IDS
    enemy_void_grub_count = 0
    last_death_ts: int | None = None

    for frame in frames:
        for event in frame.get("events", []):
            event_type = event.get("type")
            moment = None

            if event_type == "CHAMPION_KILL":
                if event.get("victimId") == participant_id:
                    last_death_ts = event["timestamp"] // 1000
                # Detection order: invade > counter-gank > gank assist > fallback
                moment = (
                    _detect_invade_death(event, participant_id)
                    or _detect_counter_ganked(event, participant_id, enemy_jungler_id)
                    or _detect_gank_assist(event, participant_id)
                    or _detect_death_fallback(event, participant_id)
                )

            elif event_type == "ELITE_MONSTER_KILL":
                killer_id = event.get("killerId", 0)
                monster = event.get("monsterType", "")

                if monster == "HORDE" and killer_id in enemy_team:
                    enemy_void_grub_count += 1
                    if enemy_void_grub_count == VOID_GRUBS_TOTAL:
                        moment = _detect_void_grubs_missed(event)
                elif monster != "HORDE":
                    moment = (
                        _detect_dragon_missed(event, frames, participant_id, last_death_ts)
                        or _detect_baron_missed(event, frames, participant_id, last_death_ts)
                        or _detect_dragon_stack(event, participant_id)
                        or _detect_baron_secured(event, participant_id)
                    )

            if moment:
                moments.append(moment)

    moments.sort(key=lambda m: m.timestamp_secs)
    return moments


def _detect_invade_death(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("victimId") != participant_id:
        return None
    position = event.get("position", {"x": 0, "y": 0})
    if not _in_enemy_jungle(position, participant_id):
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="invade_death",
        description=f"You were caught in the enemy jungle at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _detect_counter_ganked(
    event: dict,
    participant_id: int,
    enemy_jungler_id: int | None,
) -> PivotalMomentData | None:
    if event.get("victimId") != participant_id:
        return None
    if enemy_jungler_id is None:
        return None
    killer_id = event.get("killerId", 0)
    assisters = event.get("assistingParticipantIds", [])
    if killer_id != enemy_jungler_id and enemy_jungler_id not in assisters:
        return None
    position = event.get("position", {"x": 0, "y": 0})
    if not _in_ally_lane(position, participant_id):
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="counter_ganked",
        description=f"You were counter-ganked at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _detect_gank_assist(event: dict, participant_id: int) -> PivotalMomentData | None:
    killer_id = event.get("killerId", 0)
    assisters = event.get("assistingParticipantIds", [])
    if killer_id != participant_id and participant_id not in assisters:
        return None
    victim_id = event.get("victimId", 0)
    if victim_id == participant_id or victim_id == 0:
        return None
    position = event.get("position", {"x": 0, "y": 0})
    if not _in_ally_lane(position, participant_id):
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="gank_assist",
        description=f"You ganked and got a kill at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _detect_death_fallback(event: dict, participant_id: int) -> PivotalMomentData | None:
    """Catch-all: fires for any jungler death not caught by a more specific detector."""
    if event.get("victimId") != participant_id:
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    time_str = f"{mins}:{secs:02d}"
    position = event.get("position", {"x": 0, "y": 0})
    if _in_own_jungle(position, participant_id):
        return PivotalMomentData(
            timestamp_secs=ts,
            moment_type="jungle_death",
            description=f"You were caught in your jungle at {time_str}.",
            counterfactual="",
            gold_impact=GOLD_VALUES["DEATH"],
        )
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="death",
        description=f"You died in a skirmish at {time_str}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _detect_dragon_missed(
    event: dict,
    frames: list,
    participant_id: int,
    last_death_ts: int | None,
) -> PivotalMomentData | None:
    if event.get("monsterType") != "DRAGON":
        return None
    enemy_team = TEAM_200_IDS if participant_id in TEAM_100_IDS else TEAM_100_IDS
    if event.get("killerId", 0) not in enemy_team:
        return None
    ts = event["timestamp"] // 1000
    # Alive check: jungler must not have died within ALIVE_WINDOW_SECS
    if last_death_ts is not None and ts - last_death_ts <= ALIVE_WINDOW_SECS:
        return None
    # Position check: jungler must have been on the wrong side (away from Dragon)
    jungler_pos = _jungler_position_at(frames, event["timestamp"], participant_id)
    if jungler_pos is None:
        return None
    py = jungler_pos.get("y", 0)
    # Dragon is in bot river (low y). Wrong side = top-heavy position (high y).
    on_wrong_side = py > 7000
    if not on_wrong_side:
        return None
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="dragon_missed",
        description=f"Enemy secured Dragon at {mins}:{secs:02d} while you were on the wrong side of the map.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DRAGON"],
    )


def _detect_baron_missed(
    event: dict,
    frames: list,
    participant_id: int,
    last_death_ts: int | None,
) -> PivotalMomentData | None:
    if event.get("monsterType") != "BARON_NASHOR":
        return None
    enemy_team = TEAM_200_IDS if participant_id in TEAM_100_IDS else TEAM_100_IDS
    if event.get("killerId", 0) not in enemy_team:
        return None
    ts = event["timestamp"] // 1000
    if last_death_ts is not None and ts - last_death_ts <= ALIVE_WINDOW_SECS:
        return None
    jungler_pos = _jungler_position_at(frames, event["timestamp"], participant_id)
    if jungler_pos is None:
        return None
    py = jungler_pos.get("y", 0)
    # Baron is in top river (high y). Wrong side = bot-heavy position (low y).
    on_wrong_side = py < 7500
    if not on_wrong_side:
        return None
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="baron_missed",
        description=f"Enemy secured Baron Nashor at {mins}:{secs:02d} while you were on the wrong side of the map.",
        counterfactual="",
        gold_impact=GOLD_VALUES["BARON_NASHOR"],
    )


def _detect_void_grubs_missed(event: dict) -> PivotalMomentData | None:
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="void_grubs_missed",
        description=f"Enemy secured all {VOID_GRUBS_TOTAL} Void Grubs at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=300,
    )


def _detect_dragon_stack(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("monsterType") != "DRAGON":
        return None
    player_team = TEAM_100_IDS if participant_id in TEAM_100_IDS else TEAM_200_IDS
    if event.get("killerId", 0) not in player_team:
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="dragon_stack",
        description=f"Your team secured Dragon at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DRAGON"],
    )


def _detect_baron_secured(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("monsterType") != "BARON_NASHOR":
        return None
    player_team = TEAM_100_IDS if participant_id in TEAM_100_IDS else TEAM_200_IDS
    if event.get("killerId", 0) not in player_team:
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="baron_secured",
        description=f"Your team secured Baron Nashor at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["BARON_NASHOR"],
    )
