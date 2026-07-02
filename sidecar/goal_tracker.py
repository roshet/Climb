from database import get_matches
from goal_metrics import goal_met

HISTORY_WINDOW = 10
STREAK_WINDOW = 20


def compute_goal_status(db, goal) -> dict:
    matches = get_matches(db, last_n=STREAK_WINDOW)  # newest-first

    # Skip matches where the metric doesn't apply (e.g. no timeline data) entirely,
    # rather than treating them as a miss / streak-breaker.
    met_newest_first = [goal_met(goal.metric, goal.target, m) for m in matches]
    applicable_newest_first = [met for met in met_newest_first if met is not None]

    if not applicable_newest_first:
        return {"streak": 0, "history": [], "last_game_met": None, "games_evaluated": 0}

    streak = 0
    for met in applicable_newest_first:
        if met:
            streak += 1
        else:
            break

    history = list(reversed(applicable_newest_first[:HISTORY_WINDOW]))  # oldest -> newest
    return {
        "streak": streak,
        "history": history,
        "last_game_met": applicable_newest_first[0],
        "games_evaluated": len(applicable_newest_first),
    }
