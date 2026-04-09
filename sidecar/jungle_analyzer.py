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
        or abs(px - py) < 3000       # near mid lane diagonal
    )


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
                # Detection order: invade > counter-gank > gank assist
                moment = (
                    _detect_invade_death(event, participant_id)
                    or _detect_counter_ganked(event, participant_id, enemy_jungler_id)
                    or _detect_gank_assist(event, participant_id)
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
    pass  # implemented in Task 3


def _detect_counter_ganked(event: dict, participant_id: int, enemy_jungler_id: int | None) -> PivotalMomentData | None:
    pass  # implemented in Task 3


def _detect_gank_assist(event: dict, participant_id: int) -> PivotalMomentData | None:
    pass  # implemented in Task 4


def _detect_dragon_missed(event: dict, frames: list, participant_id: int, last_death_ts: int | None) -> PivotalMomentData | None:
    pass  # implemented in Task 5


def _detect_baron_missed(event: dict, frames: list, participant_id: int, last_death_ts: int | None) -> PivotalMomentData | None:
    pass  # implemented in Task 5


def _detect_void_grubs_missed(event: dict) -> PivotalMomentData | None:
    pass  # implemented in Task 5


def _detect_dragon_stack(event: dict, participant_id: int) -> PivotalMomentData | None:
    pass  # implemented in Task 4


def _detect_baron_secured(event: dict, participant_id: int) -> PivotalMomentData | None:
    pass  # implemented in Task 4
