from database import get_matches
from goal_metrics import goal_met

HISTORY_WINDOW = 10
STREAK_WINDOW = 20


def compute_goal_status(db, goal) -> dict:
    matches = get_matches(db, last_n=STREAK_WINDOW)  # newest-first
    if not matches:
        return {"streak": 0, "history": [], "last_game_met": None, "games_evaluated": 0}

    met_newest_first = [goal_met(goal.metric, goal.target, m) for m in matches]

    streak = 0
    for met in met_newest_first:
        if met:
            streak += 1
        else:
            break

    history = list(reversed(met_newest_first[:HISTORY_WINDOW]))  # oldest -> newest
    return {
        "streak": streak,
        "history": history,
        "last_game_met": met_newest_first[0],
        "games_evaluated": len(matches),
    }
