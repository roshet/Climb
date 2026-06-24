LADDER = [
    "IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM",
    "EMERALD", "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER",
]
APEX_TIERS = {"MASTER", "GRANDMASTER", "CHALLENGER"}
_DEFAULT = "PLATINUM"


def next_tier_up(tier: str | None) -> str:
    """The rung above ``tier``; caps at CHALLENGER; unranked/unknown -> PLATINUM."""
    if not tier or tier.upper() not in LADDER:
        return _DEFAULT
    idx = LADDER.index(tier.upper())
    return LADDER[min(idx + 1, len(LADDER) - 1)]
