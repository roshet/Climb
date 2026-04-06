from timeline_analyzer import PivotalMomentData


def _counterfactual_for_death(moment: PivotalMomentData) -> str:
    desc = moment.description.lower()

    if "tower dived" in desc:
        return (
            "Enemies who dive your tower are gambling — if you can avoid the all-in and let "
            "the tower do damage, it's often a losing trade for them. Positioning away from "
            "the tower edge and having an escape ready denies the dive."
        )

    if "ganked" in desc:
        return (
            "Your opponent had jungle help here. Check your minimap before extending — if "
            "the enemy jungler isn't visible on the map, assume they could be in your lane. "
            "Ward tri-bush and river to spot this earlier."
        )

    if "1v1" in desc:
        return (
            "You lost a straight-up 1v1. Consider whether your champion wins this matchup "
            "at your current item level, or play for farm over fighting until you have "
            "your power spike."
        )

    if "v1" in desc:
        return (
            "Fighting outnumbered is almost never correct. Disengage early when you see "
            "multiple enemies collapsing — the longer you stay, the worse your odds. "
            "A flash to safety is worth more than trying to trade back."
        )

    # Fallback for any unclassified death
    mins = moment.timestamp_secs // 60
    if mins < 10:
        return (
            f"Dying at {mins} minutes in the early game is high cost — you missed CS, "
            f"XP, and gave your opponent a lead. Playing safer or recalling when low "
            f"would have preserved your lane advantage."
        )
    elif mins < 20:
        return (
            f"This death at {mins} minutes likely disrupted your team's mid-game tempo. "
            f"Fights in this window often decide which team gets the first major objective. "
            f"Consider whether the fight was necessary or if backing was the safer call."
        )
    else:
        return (
            f"Late-game deaths at {mins} minutes can be game-ending — respawn timers are long "
            f"and the enemy can convert a kill into an inhibitor or Baron. "
            f"Staying grouped and avoiding solo plays is the highest-value choice here."
        )


def _counterfactual_for_objective_missed(moment: PivotalMomentData) -> str:
    gold = moment.gold_impact
    desc_lower = moment.description.lower()
    if "baron" in desc_lower:
        return (
            f"Baron Nashor is the most impactful objective in the game (~{gold}g team advantage + buff). "
            f"When Baron spawns, your team should be grouped and contesting or forcing the enemy away. "
            f"Securing or denying Baron often determines the winner."
        )
    elif "dragon" in desc_lower:
        return (
            f"Each Dragon soul stack is worth roughly {gold}g in stats and compounds over the game. "
            f"Letting the enemy stack Dragons for free accelerates their scaling. "
            f"Contesting Dragon when you have lane priority is a high-value play."
        )
    else:
        return (
            f"Your team missed an objective worth ~{gold}g in team advantage. "
            f"Grouping around spawn timers and converting lane pressure into objectives "
            f"is one of the highest-leverage macro habits to build."
        )


def _counterfactual_for_tower(moment: PivotalMomentData) -> str:
    gold = moment.gold_impact
    return (
        f"Losing this tower gave the enemy ~{gold}g and opened a new avenue into your base. "
        f"Towers are best defended by not giving the enemy free time to siege — "
        f"rotating when you see your laner backing or being outnumbered prevents this."
    )


def _counterfactual_for_solo_kill(_moment: PivotalMomentData) -> str:
    return (
        "Clean 1v1 — you identified the right window to commit and won the trade. "
        "Look for similar patterns where your opponent is low or out of cooldowns."
    )


def _counterfactual_for_objective_secured(_moment: PivotalMomentData) -> str:
    return (
        "Good macro — converting map pressure into an objective is how leads become wins. "
        "Keep looking for these trades."
    )


def enrich_moments(moments: list[PivotalMomentData]) -> list[PivotalMomentData]:
    for moment in moments:
        if moment.moment_type == "death":
            moment.counterfactual = _counterfactual_for_death(moment)
        elif moment.moment_type == "objective_missed":
            moment.counterfactual = _counterfactual_for_objective_missed(moment)
        elif moment.moment_type == "tower_lost":
            moment.counterfactual = _counterfactual_for_tower(moment)
        elif moment.moment_type == "solo_kill":
            moment.counterfactual = _counterfactual_for_solo_kill(moment)
        elif moment.moment_type == "objective_secured":
            moment.counterfactual = _counterfactual_for_objective_secured(moment)
        elif not moment.counterfactual:
            moment.counterfactual = f"This event had an estimated ~{moment.gold_impact}g impact on the game outcome."
    return moments
