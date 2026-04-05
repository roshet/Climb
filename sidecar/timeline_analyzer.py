from dataclasses import dataclass

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
    "DEATH": 300,  # approximate bounty
}


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


def _score_death(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("victimId") != participant_id:
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="death",
        description=f"You died at {mins}:{secs:02d}.",
        counterfactual="Avoiding this death would have kept pressure on the map and denied your bounty.",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _score_objective(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("type") != "ELITE_MONSTER_KILL":
        return None
    enemy_team = _enemy_team(participant_id)
    killer_id = event.get("killerId", 0)
    if killer_id not in enemy_team:
        return None  # our team took it
    monster = event.get("monsterType", "UNKNOWN")
    gold = GOLD_VALUES.get(monster, 300)
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="objective_missed",
        description=f"Enemy team secured {monster.replace('_', ' ').title()} at {mins}:{secs:02d}.",
        counterfactual=f"Your team missing this objective gave the enemy a ~{gold}g advantage and map pressure.",
        gold_impact=gold,
    )


def _score_tower(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("type") != "BUILDING_KILL":
        return None
    enemy_team = _enemy_team(participant_id)
    killer_id = event.get("killerId", 0)
    if killer_id not in enemy_team:
        return None  # our team took it
    tower_type = event.get("towerType", "OUTER_TURRET")
    gold = GOLD_VALUES.get(f"TOWER_{tower_type.replace('_TURRET', '')}", 150)
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    lane = event.get("laneType", "").replace("_LANE", "").title()
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="tower_lost",
        description=f"Enemy took your {lane} {tower_type.replace('_', ' ').lower()} at {mins}:{secs:02d}.",
        counterfactual=f"Losing this tower opened your base and gave the enemy ~{gold}g.",
        gold_impact=gold,
    )


def analyze_timeline(timeline: dict, participant_id: int) -> list[PivotalMomentData]:
    moments: list[PivotalMomentData] = []
    frames = timeline.get("info", {}).get("frames", [])

    for frame in frames:
        for event in frame.get("events", []):
            event_type = event.get("type")
            moment = None
            if event_type == "CHAMPION_KILL":
                moment = _score_death(event, participant_id)
            elif event_type == "ELITE_MONSTER_KILL":
                moment = _score_objective(event, participant_id)
            elif event_type == "BUILDING_KILL":
                moment = _score_tower(event, participant_id)
            if moment:
                moments.append(moment)

    moments.sort(key=lambda m: m.gold_impact, reverse=True)
    return moments[:5]
