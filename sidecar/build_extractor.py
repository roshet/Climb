"""Pure functions for extracting item/rune/spell data from a match-v5 participant dict.

No I/O, no DB — all functions are side-effect-free.

Rune signature format (exact):
    "{primaryStyle}|{keystone},{p1},{p2},{p3}|{subStyle}|{s1},{s2}|{offense},{flex},{defense}"

Example:
    "8000|8005,9111,9105,8014|8200|8275,8236|5005,5008,5001"
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

def _extract_items(p: dict) -> list[int]:
    """Collect item0..item5, excluding item6 (trinket), zeros, and duplicates."""
    seen: set[int] = set()
    result: list[int] = []
    for slot in range(6):  # item0..item5 only
        item_id = p.get(f"item{slot}", 0)
        if item_id and item_id not in seen:
            seen.add(item_id)
            result.append(item_id)
    return result


# ---------------------------------------------------------------------------
# Rune signatures
# ---------------------------------------------------------------------------

def _find_style(styles: list[dict], description: str, fallback_index: int) -> dict:
    """Return the style entry matching *description*; fall back to index order."""
    for entry in styles:
        if entry.get("description") == description:
            return entry
    # Fall back to index order when description field is absent
    return styles[fallback_index]


def encode_rune_signature(perks: dict) -> str | None:
    """Encode a match-v5 perks dict into a compact signature string.

    Returns None if any required field is missing or malformed.
    """
    try:
        styles: list[dict] = perks["styles"]
        if len(styles) < 2:
            return None

        primary = _find_style(styles, "primaryStyle", 0)
        sub = _find_style(styles, "subStyle", 1)

        p_sel = [entry["perk"] for entry in primary["selections"]]
        s_sel = [entry["perk"] for entry in sub["selections"]]

        if len(p_sel) < 4 or len(s_sel) < 2:
            return None

        stat = perks["statPerks"]
        offense = stat["offense"]
        flex = stat["flex"]
        defense = stat["defense"]

        p_style = primary["style"]
        s_style = sub["style"]

        return (
            f"{p_style}|{p_sel[0]},{p_sel[1]},{p_sel[2]},{p_sel[3]}"
            f"|{s_style}|{s_sel[0]},{s_sel[1]}"
            f"|{offense},{flex},{defense}"
        )
    except (KeyError, IndexError, TypeError):
        return None


def decode_rune_signature(sig: str) -> dict:
    """Decode a rune signature string into its constituent ids.

    Returns a dict with keys:
        primary_style: int
        primary_perks: [keystone, p1, p2, p3]
        sub_style: int
        sub_perks: [s1, s2]
        stat_shards: [offense, flex, defense]

    Assumes a well-formed (round-trippable) input.
    """
    primary_part, sub_part, stat_part = sig.split("|")[0], sig.split("|")[2], sig.split("|")[4]
    primary_perks_part = sig.split("|")[1]
    sub_perks_part = sig.split("|")[3]

    return {
        "primary_style": int(primary_part),
        "primary_perks": [int(x) for x in primary_perks_part.split(",")],
        "sub_style": int(sub_part),
        "sub_perks": [int(x) for x in sub_perks_part.split(",")],
        "stat_shards": [int(x) for x in stat_part.split(",")],
    }


# ---------------------------------------------------------------------------
# Spell signatures
# ---------------------------------------------------------------------------

def encode_spell_signature(p: dict) -> str | None:
    """Encode summoner spells into an order-normalised string.

    Returns None if either spell id is missing or zero.
    """
    s1 = p.get("summoner1Id")
    s2 = p.get("summoner2Id")
    if not s1 or not s2:
        return None
    return f"{min(s1, s2)},{max(s1, s2)}"


def decode_spell_signature(sig: str) -> list[int]:
    """Decode a spell signature string into a list of two ints."""
    return [int(x) for x in sig.split(",")]


# ---------------------------------------------------------------------------
# Top-level extractor
# ---------------------------------------------------------------------------

def extract_participant_build(p: dict) -> dict:
    """Extract item/rune/spell data from a match-v5 participant dict.

    Returns:
        {
            "items":     list[int],   # item0..item5, no zeros, no dupes
            "rune_page": str | None,  # encoded rune signature
            "spells":    str | None,  # encoded spell signature
        }
    """
    items = _extract_items(p)

    try:
        perks = p["perks"]
        rune_page = encode_rune_signature(perks) if perks is not None else None
    except (KeyError, TypeError):
        rune_page = None

    spells = encode_spell_signature(p)

    return {"items": items, "rune_page": rune_page, "spells": spells}
