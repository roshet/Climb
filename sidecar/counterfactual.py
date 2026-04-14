from timeline_analyzer import PivotalMomentData


def _counterfactual_for_death(moment: PivotalMomentData) -> str:
    desc = moment.description.lower()

    if "tower dived" in desc:
        return (
            "Enemies who dive your tower are gambling — if you can avoid the all-in and let "
            "the tower do damage, it's often a losing trade for them. Positioning away from "
            "the tower edge and having an escape ready denies the dive."
        )

    elif "ganked" in desc:
        return (
            "Your opponent had jungle help here. Check your minimap before extending — if "
            "the enemy jungler isn't visible on the map, assume they could be in your lane. "
            "Ward tri-bush and river to spot this earlier."
        )

    elif "1v1" in desc:
        return (
            "You lost a straight-up 1v1. Consider whether your champion wins this matchup "
            "at your current item level, or play for farm over fighting until you have "
            "your power spike."
        )

    elif "v1" in desc:
        return (
            "Fighting outnumbered is almost never correct. Disengage early when you see "
            "multiple enemies collapsing — the longer you stay, the worse your odds. "
            "A flash to safety is worth more than trying to trade back."
        )

    else:
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
        elif moment.moment_type == "lane_death":
            desc = moment.description.lower()
            if "ganked" in desc:
                moment.counterfactual = (
                    "The enemy jungler was in your lane. Before extending past the halfway point, "
                    "check that the enemy jungler is visible on the map — if they're not, assume they "
                    "could be nearby. Ward your river and tribush to get earlier warning."
                )
            elif "dove" in desc:
                moment.counterfactual = (
                    "You were dove under your tower. Position away from the tower edge when low so "
                    "enemies can't pin you against it. Having an escape (Flash or dash) ready "
                    "dramatically improves your odds of surviving a dive attempt."
                )
            else:
                moment.counterfactual = (
                    "You lost a 1v1 trade in lane. Check whether your champion wins this matchup at "
                    "your current item level — some matchups are unwinnable pre-spike. If so, play "
                    "for farm over fighting until you hit your power item."
                )
        elif moment.moment_type == "cs_differential":
            moment.counterfactual = (
                "Every 10 CS missed is roughly 200g — falling behind in CS compounds like a death. "
                "Focus on last-hitting under tower, use wave freezes to farm safely when behind, "
                "and prioritize safe CS over risky trades until the gap closes."
            )
        elif moment.moment_type == "gold_differential":
            moment.counterfactual = (
                "Your opponent had a significant gold lead at 14 minutes. Identify the main source: "
                "CS deficit means work on wave management; kill gold means play safer until your "
                "first item spike; plates mean crash your wave before recalling."
            )
        elif moment.moment_type == "turret_plates_lost":
            moment.counterfactual = (
                "Each plate is 160g — losing 3 gave the enemy 480g for free. Crashing your wave "
                "into the tower before recalling denies plates. A full wave crash takes ~10 seconds "
                "and prevents the enemy from freely taking plates while you're gone."
            )
        elif moment.moment_type == "split_push_death":
            moment.counterfactual = (
                "You were collapsed on in a side lane. Before committing deep in a split push, "
                "check that 3+ enemies are accounted for on the minimap. If they're missing, "
                "back off to safety — a teleport escape or recall is worth more than the tower."
            )
        elif moment.moment_type in ("roam_kill", "roam_assist"):
            moment.counterfactual = (
                "Good roam — you created a lead by transferring lane pressure to another part of the "
                "map. Repeat this pattern: shove your wave first so you lose minimal CS, then rotate "
                "before the enemy can respond."
            )
        elif moment.moment_type == "enemy_roam_kill":
            moment.counterfactual = (
                "While you farmed, your opponent created a lead on the map. Match their roam by "
                "following, or shove your wave before they leave so they lose CS in exchange. "
                "Letting them roam for free means they get the kill and keep their CS lead."
            )
        elif moment.moment_type == "low_vision":
            moment.counterfactual = (
                "Low ward count limits your team's ability to react to flanks and objective setups. "
                "As support, aim for a ward every 90 seconds — prioritize river control near Dragon "
                "and Baron timers. A Control Ward in the objective pit before it spawns is the "
                "highest-value placement in the game."
            )
        elif moment.moment_type == "ward_kill":
            moment.counterfactual = (
                "Destroying enemy wards forces them to spend gold and time re-establishing vision. "
                "Keep sweeping high-traffic corridors and the areas around upcoming objective "
                "timers — vision denial before Dragon or Baron is especially impactful."
            )
        elif not moment.counterfactual:
            moment.counterfactual = f"This event had an estimated ~{moment.gold_impact}g impact on the game outcome."
    return moments
