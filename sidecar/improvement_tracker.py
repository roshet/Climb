import logging
from collections import Counter

from sqlalchemy.orm import Session

from champ_select_monitor import MOMENT_LABELS, POSITIVE_TYPES
from database import Match, get_matches, get_pivotal_moments

log = logging.getLogger(__name__)


def get_improvement_data(db: Session, match_id: str) -> dict | None:
    this_match = db.query(Match).filter(Match.match_id == match_id).first()
    if this_match is None:
        return None

    champion = this_match.champion
    matches = get_matches(db, champion=champion, last_n=20)  # newest first

    if len(matches) < 3:
        return {"champion": champion, "patterns": []}

    match_ids = [m.match_id for m in matches]
    moments = get_pivotal_moments(db, match_ids)

    # The current game is included in match_ids, so its moments count toward
    # pattern frequency. This is intentional: the current game's events are real
    # data points. recent_rate signals how chronic a pattern is (1/5 = new, 5/5 = chronic).

    # Group moments by match_id for fast lookup
    moments_by_match: dict[str, list] = {}
    for m in moments:
        moments_by_match.setdefault(m.match_id, []).append(m)

    this_match_types = {m.moment_type for m in moments_by_match.get(match_id, [])}

    # Top 2 negative patterns
    negative_counts = Counter(
        m.moment_type for m in moments if m.moment_type not in POSITIVE_TYPES
    )

    # Top 1 positive pattern — wins only
    win_ids = {m.match_id for m in matches if m.result == "win"}
    positive_counts = Counter(
        m.moment_type for m in moments
        if m.moment_type in POSITIVE_TYPES and m.match_id in win_ids
    )

    recent_5_ids = [m.match_id for m in matches[:5]]  # newest first
    # Note: when history is 3-4 games, this window is smaller than 5.
    # recent_rate values are comparably smaller but correctly reflect available history.

    def recent_rate(moment_type: str) -> int:
        return sum(
            1 for mid in recent_5_ids
            if any(m.moment_type == moment_type for m in moments_by_match.get(mid, []))
        )

    def streak_clean(moment_type: str) -> int:
        count = 0
        for mid in match_ids:  # newest first
            types = {m.moment_type for m in moments_by_match.get(mid, [])}
            if moment_type not in types:
                count += 1
            else:
                break
        return count

    patterns = []

    for moment_type, _ in negative_counts.most_common(2):
        display = MOMENT_LABELS.get(moment_type, moment_type.replace("_", " ").title())
        had_in_game = moment_type in this_match_types
        patterns.append({
            "label": "recurring_issue",
            "moment_type": moment_type,
            "display": display,
            "had_in_game": had_in_game,
            "streak": streak_clean(moment_type) if not had_in_game else 0,
            "recent_rate": recent_rate(moment_type),
        })

    if positive_counts:
        moment_type, _ = positive_counts.most_common(1)[0]
        display = MOMENT_LABELS.get(moment_type, moment_type.replace("_", " ").title())
        had_in_game = moment_type in this_match_types
        rate = recent_rate(moment_type)
        if had_in_game or rate >= 3:
            patterns.append({
                "label": "win_condition",
                "moment_type": moment_type,
                "display": display,
                "had_in_game": had_in_game,
                "streak": 0,
                "recent_rate": rate,
            })

    return {"champion": champion, "patterns": patterns}
