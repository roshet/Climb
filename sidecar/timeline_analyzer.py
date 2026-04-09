from dataclasses import dataclass
import math

# Team 100 = participants 1-5, Team 200 = participants 6-10
TEAM_100_IDS = set(range(1, 6))
TEAM_200_IDS = set(range(6, 11))

# Gold values for objectives (approximate LoL values)
GOLD_VALUES = {
    "DRAGON": 350,
    "BARON_NASHOR": 900,
    "RIFTHERALD": 400,
    "TOWER_OUTER": 150,
    "TOWER_INNER": 250,
    "TOWER_BASE": 350,
    "INHIBITOR": 400,
    "DEATH": 300,
}

# Approximate Summoner's Rift turret positions (x, y)
BLUE_TURRETS = [
    (981, 10441), (1512, 6699), (1169, 4287),   # Top lane
    (5846, 6396), (5048, 4812), (3651, 3696),    # Mid lane
    (10504, 1029), (6919, 1483), (4281, 1241),   # Bot lane
    (1748, 2270), (2177, 1807), (1364, 1485),    # Base
]

RED_TURRETS = [
    (13866, 4357), (13327, 8143), (13604, 10474),  # Top lane
    (8955, 8510), (9767, 10175), (11134, 11207),   # Mid lane
    (4318, 13875), (8955, 13411), (10961, 13654),  # Bot lane
    (12611, 13084), (13052, 12612), (13846, 13372), # Base
]

TOWER_DIVE_RADIUS = 1000
LANING_PHASE_SECS = 840  # 14:00


@dataclass
class PivotalMomentData:
    timestamp_secs: int
    moment_type: str
    description: str
    counterfactual: str
    gold_impact: int


def _player_team(participant_id: int) -> set:
    return TEAM_100_IDS if participant_id in TEAM_100_IDS else TEAM_200_IDS


def _enemy_team(participant_id: int) -> set:
    return TEAM_200_IDS if participant_id in TEAM_100_IDS else TEAM_100_IDS


def _friendly_turrets(participant_id: int) -> list[tuple[int, int]]:
    return BLUE_TURRETS if participant_id in TEAM_100_IDS else RED_TURRETS


def _near_friendly_turret(position: dict, participant_id: int) -> bool:
    px, py = position.get("x", 0), position.get("y", 0)
    for tx, ty in _friendly_turrets(participant_id):
        if math.sqrt((px - tx) ** 2 + (py - ty) ** 2) < TOWER_DIVE_RADIUS:
            return True
    return False


def _classify_death(
    event: dict,
    participant_id: int,
    enemy_jungler_id: int | None,
) -> PivotalMomentData | None:
    if event.get("victimId") != participant_id:
        return None

    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    time_str = f"{mins}:{secs:02d}"
    position = event.get("position", {"x": 0, "y": 0})
    killer_id = event.get("killerId", 0)
    assisters = event.get("assistingParticipantIds", [])
    total_enemies = len(set([killer_id] + list(assisters)) - {0})

    # killerId == 0 means tower/environment finish with no champion credit
    if killer_id == 0 and not assisters:
        return PivotalMomentData(
            timestamp_secs=ts,
            moment_type="death",
            description=f"You were executed at {time_str}.",
            counterfactual="",
            gold_impact=GOLD_VALUES["DEATH"],
        )

    # Priority 1: tower dive
    if _near_friendly_turret(position, participant_id):
        return PivotalMomentData(
            timestamp_secs=ts,
            moment_type="death",
            description=f"You were tower dived at {time_str}.",
            counterfactual="",
            gold_impact=GOLD_VALUES["DEATH"],
        )

    # Priority 2: ganked (laning phase only, jungler involved)
    if (
        ts < LANING_PHASE_SECS
        and enemy_jungler_id is not None
        and (killer_id == enemy_jungler_id or enemy_jungler_id in assisters)
    ):
        return PivotalMomentData(
            timestamp_secs=ts,
            moment_type="death",
            description=f"You were ganked at {time_str}.",
            counterfactual="",
            gold_impact=GOLD_VALUES["DEATH"],
        )

    # Priority 3: outnumbered
    if total_enemies >= 2:
        return PivotalMomentData(
            timestamp_secs=ts,
            moment_type="death",
            description=f"You were caught {total_enemies}v1 at {time_str}.",
            counterfactual="",
            gold_impact=GOLD_VALUES["DEATH"],
        )

    # Priority 4: 1v1 loss
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="death",
        description=f"You lost a 1v1 at {time_str}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _score_objective_missed(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("type") != "ELITE_MONSTER_KILL":
        return None
    enemy_team = _enemy_team(participant_id)
    killer_id = event.get("killerId", 0)
    if killer_id not in enemy_team:
        return None
    monster = event.get("monsterType", "UNKNOWN")
    gold = GOLD_VALUES.get(monster, 300)
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="objective_missed",
        description=f"Enemy team secured {monster.replace('_', ' ').title()} at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=gold,
    )


def _score_objective_secured(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("type") != "ELITE_MONSTER_KILL":
        return None
    player_team = _player_team(participant_id)
    killer_id = event.get("killerId", 0)
    if killer_id not in player_team:
        return None
    monster = event.get("monsterType", "UNKNOWN")
    gold = GOLD_VALUES.get(monster, 300)
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="objective_secured",
        description=f"Your team secured {monster.replace('_', ' ').title()} at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=gold,
    )


def _score_solo_kill(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("killerId") != participant_id:
        return None
    assisters = event.get("assistingParticipantIds", [])
    if assisters:
        return None
    victim_id = event.get("victimId", 0)
    if victim_id == participant_id or victim_id == 0:
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="solo_kill",
        description=f"You got a solo kill at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _score_tower(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("type") != "BUILDING_KILL":
        return None
    enemy_team = _enemy_team(participant_id)
    killer_id = event.get("killerId", 0)
    if killer_id not in enemy_team:
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


def analyze_timeline(
    timeline: dict,
    participant_id: int,
    enemy_jungler_id: int | None = None,
    role: str = "UNKNOWN",
    champion: str = "Unknown",
) -> list[PivotalMomentData]:
    if role == "JUNGLE":
        from jungle_analyzer import analyze_jungle
        return analyze_jungle(timeline, participant_id, enemy_jungler_id)

    moments: list[PivotalMomentData] = []
    frames = timeline.get("info", {}).get("frames", [])

    for frame in frames:
        for event in frame.get("events", []):
            event_type = event.get("type")
            moment = None
            if event_type == "CHAMPION_KILL":
                death = _classify_death(event, participant_id, enemy_jungler_id)
                solo = _score_solo_kill(event, participant_id)
                moment = death or solo
            elif event_type == "ELITE_MONSTER_KILL":
                missed = _score_objective_missed(event, participant_id)
                secured = _score_objective_secured(event, participant_id)
                moment = missed or secured
            elif event_type == "BUILDING_KILL":
                moment = _score_tower(event, participant_id)
            if moment:
                moments.append(moment)

    moments.sort(key=lambda m: m.timestamp_secs)
    return moments
