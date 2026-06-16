from timeline_analyzer import PivotalMomentData, _player_team

KILL_GROUP_GAP_SECS = 20   # kills within this gap join the same fight
MIN_FIGHT_KILLS = 3        # a cluster needs at least this many kills to be a "team fight"
KILL_GOLD = 300            # approximate gold value of a champion kill

OBJECTIVE_GOLD = {"BARON_NASHOR": 900, "DRAGON": 350, "RIFTHERALD": 400}
OBJECTIVE_LABEL = {"BARON_NASHOR": "Baron", "DRAGON": "Dragon", "RIFTHERALD": "Herald"}


def _collect(timeline: dict) -> tuple[list[dict], list[dict]]:
    kills, objectives = [], []
    for frame in timeline.get("info", {}).get("frames", []):
        for event in frame.get("events", []):
            etype = event.get("type")
            if etype == "CHAMPION_KILL":
                kills.append(event)
            elif etype == "ELITE_MONSTER_KILL":
                objectives.append(event)
    kills.sort(key=lambda e: e.get("timestamp", 0))
    return kills, objectives


def _cluster(kills: list[dict]) -> list[list[dict]]:
    clusters: list[list[dict]] = []
    for kill in kills:
        ts = kill.get("timestamp", 0)
        if clusters and ts - clusters[-1][-1].get("timestamp", 0) <= KILL_GROUP_GAP_SECS * 1000:
            clusters[-1].append(kill)
        else:
            clusters.append([kill])
    return clusters


def _involvement(cluster: list[dict], participant_id: int) -> str:
    kills = assists = 0
    died = False
    for kill in cluster:
        if kill.get("killerId") == participant_id and kill.get("victimId") != participant_id:
            kills += 1
        if participant_id in kill.get("assistingParticipantIds", []):
            assists += 1
        if kill.get("victimId") == participant_id:
            died = True
    parts = []
    if kills:
        parts.append(f"got {kills} kill{'s' if kills > 1 else ''}")
    if assists:
        parts.append(f"got {assists} assist{'s' if assists > 1 else ''}")
    if died:
        parts.append("died")
    if not parts:
        return "you weren't involved"
    return "you " + " and ".join(parts)


def _objective_in_window(objectives: list[dict], start_ms: int, end_ms: int) -> str | None:
    """Return the monsterType (e.g. 'DRAGON') of a contested objective in the window, or None."""
    for obj in objectives:
        ts = obj.get("timestamp", 0)
        if start_ms <= ts <= end_ms and obj.get("monsterType") in OBJECTIVE_GOLD:
            return obj.get("monsterType")
    return None


def analyze_teamfights(timeline: dict, participant_id: int) -> list[PivotalMomentData]:
    kills, objectives = _collect(timeline)
    player_team = _player_team(participant_id)
    moments: list[PivotalMomentData] = []

    for cluster in _cluster(kills):
        if len(cluster) < MIN_FIGHT_KILLS:
            continue
        your_kills = sum(1 for k in cluster if k.get("victimId", 0) not in player_team)
        their_kills = sum(1 for k in cluster if k.get("victimId", 0) in player_team)
        if your_kills == their_kills:
            continue  # skip even trades

        start_ms = cluster[0].get("timestamp", 0)
        end_ms = cluster[-1].get("timestamp", 0)
        ts = start_ms // 1000
        mins, secs = divmod(ts, 60)
        time_str = f"{mins}:{secs:02d}"

        monster = _objective_in_window(objectives, start_ms, end_ms)
        near = f" near {OBJECTIVE_LABEL[monster]}" if monster else ""
        involvement = _involvement(cluster, participant_id)

        won = your_kills > their_kills
        if won:
            moment_type = "teamfight_won"
            outcome = f"Your team won a {your_kills}-for-{their_kills} fight"
        else:
            moment_type = "teamfight_lost"
            outcome = f"Your team lost a fight ({your_kills} for {their_kills})"

        gold = abs(your_kills - their_kills) * KILL_GOLD
        if monster:
            gold += OBJECTIVE_GOLD[monster]

        moments.append(PivotalMomentData(
            timestamp_secs=ts,
            moment_type=moment_type,
            description=f"{outcome}{near} at {time_str} — {involvement}.",
            counterfactual="",
            gold_impact=gold,
        ))

    return moments
