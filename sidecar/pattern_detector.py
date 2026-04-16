from dataclasses import dataclass
from sqlalchemy.orm import Session
from database import get_matches, get_pivotal_moments

MOMENT_TYPE_LABELS: dict[str, str] = {
    "lane_death": "Lane Deaths",
    "cs_differential": "CS Deficit",
    "gold_differential": "Gold Deficit",
    "turret_plates_lost": "Plates Lost",
    "split_push_death": "Split Push Deaths",
    "enemy_roam_kill": "Enemy Roams",
    "low_vision": "Low Vision",
    "objective_missed": "Missed Objectives",
    "tower_lost": "Towers Lost",
    "death": "Deaths",
    "solo_kill": "Solo Kills",
    "objective_secured": "Objectives Secured",
    "roam_kill": "Roam Kills",
    "roam_assist": "Roam Assists",
    "ward_kill": "Vision Control",
}


@dataclass
class PatternResult:
    moment_type: str
    label: str            # "recurring_issue" or "win_condition"
    games_seen: int
    total_games: int
    win_rate_with: float
    overall_win_rate: float
    summary: str


def detect_patterns(db: Session, last_n: int = 20) -> list[PatternResult]:
    matches = get_matches(db, last_n=last_n)
    total_games = len(matches)
    if total_games < 3:
        return []

    overall_wins = sum(1 for m in matches if m.result == "win")
    overall_win_rate = overall_wins / total_games

    match_ids = [m.match_id for m in matches]
    result_by_id = {m.match_id: m.result for m in matches}

    all_moments = get_pivotal_moments(db, match_ids)

    # Build match_id -> set of distinct moment_types (one game counts once per type)
    types_by_match: dict[str, set[str]] = {mid: set() for mid in match_ids}
    for moment in all_moments:
        types_by_match[moment.match_id].add(moment.moment_type)

    # Invert: moment_type -> list of match_ids where it appeared
    type_games: dict[str, list[str]] = {}
    for mid, types in types_by_match.items():
        for t in types:
            type_games.setdefault(t, []).append(mid)

    results: list[PatternResult] = []
    for moment_type, game_ids in type_games.items():
        games_seen = len(game_ids)
        if games_seen < 3:
            continue

        wins_with = sum(1 for mid in game_ids if result_by_id[mid] == "win")
        win_rate_with = wins_with / games_seen

        if win_rate_with < overall_win_rate - 0.10:
            label = "recurring_issue"
        elif win_rate_with > overall_win_rate + 0.10:
            label = "win_condition"
        else:
            continue

        human = MOMENT_TYPE_LABELS.get(moment_type, moment_type.replace("_", " ").title())
        summary = (
            f"{human.lower()} in {games_seen} of your last {total_games} games "
            f"({int(win_rate_with * 100)}% win rate)"
        )

        results.append(PatternResult(
            moment_type=moment_type,
            label=label,
            games_seen=games_seen,
            total_games=total_games,
            win_rate_with=win_rate_with,
            overall_win_rate=overall_win_rate,
            summary=summary,
        ))

    recurring = sorted(
        [r for r in results if r.label == "recurring_issue"],
        key=lambda r: r.games_seen,
        reverse=True,
    )
    win_conds = sorted(
        [r for r in results if r.label == "win_condition"],
        key=lambda r: r.win_rate_with,
        reverse=True,
    )
    return (recurring + win_conds)[:5]
