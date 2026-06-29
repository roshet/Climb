"""Build view layer: resolves raw DB aggregates into the suggested_build payload.

Consumes:
  - raw dict from database.get_build_suggestions (passed in; no DB calls here)
  - an LcuClient instance for asset resolution (get_items/get_perks/get_perk_styles/
    get_summoner_spells)

Produces:
  - A suggested_build dict with status "ready" or "insufficient".

BUILD_SAMPLE_FLOOR is defined here and imported by main.py (single source of truth).
"""

from __future__ import annotations

import logging
import urllib.parse

from build_extractor import decode_rune_signature, decode_spell_signature

log = logging.getLogger(__name__)

# Minimum number of samples required before we show a build suggestion.
BUILD_SAMPLE_FLOOR = 30


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def is_core_item(meta: dict) -> bool:
    """Return True iff this item qualifies as a displayable 'core' item.

    Rules:
    - priceTotal >= 1100  (excludes cheap components and starter items)
    - `to` is empty/falsy (nothing builds *from* this — i.e. it's a finished item;
      also keeps upgraded boots like Berserker's Greaves since they have empty `to`)
    - not a Consumable (potions, elixirs)
    - not a Trinket (wards)
    """
    return (
        meta.get("priceTotal", 0) >= 1100
        and not meta.get("to")
        and "Consumable" not in meta.get("categories", [])
        and "Trinket" not in meta.get("categories", [])
    )


def _icon_url(icon_path: str | None) -> str | None:
    """Build an /lcu-image proxy URL for an LCU iconPath.

    The full path is URL-encoded so it survives as a query-string value.
    The renderer wraps this with sidecarUrl to produce the final HTTP URL.
    """
    if not icon_path:
        return None
    return "/lcu-image?path=" + urllib.parse.quote(icon_path, safe="")


def _icon(meta_map: dict, id: int) -> dict:
    """Resolve an id to a {id, name, icon_url} dict.

    If the id is not in meta_map, name falls back to str(id) and icon_url to None.
    """
    meta = meta_map.get(id, {})
    return {
        "id": id,
        "name": meta.get("name", str(id)),
        "icon_url": _icon_url(meta.get("iconPath")),
    }


def _insufficient(role: str, target_tier: str | None, n_samples: int) -> dict:
    return {
        "status": "insufficient",
        "role": role,
        "target_tier": target_tier,
        "n_samples": n_samples,
        "items": [],
        "runes": None,
        "spells": [],
    }


# ---------------------------------------------------------------------------
# Main assembly function
# ---------------------------------------------------------------------------

async def assemble_suggested_build(lcu, raw: dict, role: str, target_tier: str | None) -> dict:
    """Resolve raw DB aggregates into a suggested_build payload.

    Args:
        lcu: An LcuClient instance (or compatible stub) with async asset getters.
        raw: Dict from database.get_build_suggestions:
             {"n_samples": int, "items": [(id, count), ...], "rune_page": (sig, count)|None,
              "spells": (sig, count)|None}
        role: Role string (e.g. "MIDDLE").
        target_tier: Tier string or None.

    Returns:
        Dict with "status" == "ready" or "insufficient".  Never raises — any LCU
        failure is caught and returns the insufficient shape.
    """
    try:
        n_samples = raw["n_samples"]
        if n_samples < BUILD_SAMPLE_FLOOR:
            return _insufficient(role, target_tier, n_samples)

        # ------------------------------------------------------------------ #
        # ITEMS                                                                #
        # ------------------------------------------------------------------ #
        items_meta = await lcu.get_items() or {}
        resolved_items: list[dict] = []
        for item_id, count in raw["items"]:
            meta = items_meta.get(item_id)
            if meta is None:
                continue
            if not is_core_item(meta):
                continue
            resolved_items.append({
                "id": item_id,
                "name": meta["name"],
                "icon_url": _icon_url(meta.get("iconPath")),
                "count": count,
            })
            if len(resolved_items) == 6:
                break

        # ------------------------------------------------------------------ #
        # RUNES                                                                #
        # ------------------------------------------------------------------ #
        runes: dict | None = None
        if raw["rune_page"]:
            decoded = decode_rune_signature(raw["rune_page"][0])
            perks = await lcu.get_perks() or {}
            styles = await lcu.get_perk_styles() or {}

            keystone_id = decoded["primary_perks"][0]
            primary_rune_ids = decoded["primary_perks"][1:]   # 3 non-keystone
            sub_rune_ids = decoded["sub_perks"]               # 2
            stat_shard_ids = decoded["stat_shards"]           # 3

            runes = {
                "primary_style": _icon(styles, decoded["primary_style"]),
                "keystone": _icon(perks, keystone_id),
                "primary_runes": [_icon(perks, rid) for rid in primary_rune_ids],
                "sub_style": _icon(styles, decoded["sub_style"]),
                "sub_runes": [_icon(perks, rid) for rid in sub_rune_ids],
                "stat_shards": [_icon(perks, rid) for rid in stat_shard_ids],
            }

        # ------------------------------------------------------------------ #
        # SPELLS                                                               #
        # ------------------------------------------------------------------ #
        spells: list[dict] = []
        if raw["spells"]:
            spell_ids = decode_spell_signature(raw["spells"][0])
            spells_meta = await lcu.get_summoner_spells() or {}
            spells = [_icon(spells_meta, sid) for sid in spell_ids]

        return {
            "status": "ready",
            "role": role,
            "target_tier": target_tier,
            "n_samples": n_samples,
            "items": resolved_items,
            "runes": runes,
            "spells": spells,
        }

    except Exception as exc:  # noqa: BLE001
        log.debug("assemble_suggested_build failed: %s", exc)
        return _insufficient(role, target_tier, raw.get("n_samples", 0))
